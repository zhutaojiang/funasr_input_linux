"""语音输入法核心：热键 → 录音 → 识别 → 输出。

润色与注入异步执行：识别完成后立即释放 _busy 锁，允许新一轮录音；
润色+注入由 _PolishQueue 保序后台执行。
"""

from __future__ import annotations

import logging
import signal
import threading
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("funasr_input")

from funasr_input.audio import AudioConfig, AudioRecorder, AudioSegment
from funasr_input.asr import ASREngine
from funasr_input.input import FocusGuard, TextInjector
from funasr_input.config import load_config
from funasr_input.polish import Polisher, make_polisher_from_config
from funasr_input.live import LiveTranscriber
from funasr_input.preview import PreviewWindow
from funasr_input.presets import resolve_preset


class _PolishQueue:
    """保序润色+注入队列。

    多轮识别结果并发提交，后台线程按提交顺序依次润色并注入文本，
    保证先识别的结果先注入（即使后提交的先润色完）。
    """

    def __init__(
        self,
        *,
        polisher: Optional[Polisher],
        injector: TextInjector,
        on_polish_start: Optional[Callable[[str], None]] = None,
        on_polish_done: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._polisher = polisher
        self._injector = injector
        self._on_polish_start = on_polish_start
        self._on_polish_done = on_polish_done
        self._seq = 0
        self._next = 1
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._results: dict[int, str] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="polish-queue"
        )
        self._thread.start()

    def submit(self, text: str) -> int:
        with self._lock:
            seq = self._seq + 1
            self._seq = seq
            self._results[seq] = text
            self._cond.notify_all()
        return seq

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._cond.notify_all()
        self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                while self._next not in self._results and not self._stop.is_set():
                    self._cond.wait(timeout=0.5)
                if self._stop.is_set():
                    return
                seq = self._next
                text = self._results.pop(seq)
                self._next = seq + 1

            if self._polisher is not None:
                if self._on_polish_start:
                    self._on_polish_start(text)
                logger.info("✍ [polish-queue] 润色 #%d: %r", seq, text)
                text = self._polisher.polish(text)

            logger.info("✅ [polish-queue] 注入 #%d: %r", seq, text)
            self._injector.write(text)

            if self._on_polish_done:
                self._on_polish_done(text)


class VoiceIME:
    """主控制器，串联音频采集、ASR 识别和文本注入。"""

    def __init__(
        self,
        *,
        asr_preset: Optional[str] = None,
        model_name: Optional[str] = None,
        vad_model: Optional[str] = None,
        device: str = "cpu",
        hotkey: str = "win+alt+space",
        quit_hotkey: str = "win+alt+x",
        silence_threshold: float = 0.015,
        silence_duration_sec: float = 1.0,
        max_record_sec: float = 30.0,
        char_delay: float = 0.0,
        polish: bool = True,
        polisher: Optional[Polisher] = None,
        live_preview: bool = True,
        live_interval: float = 2.5,
        debug: bool = False,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        # 始终配置带时间戳的日志（debug 仅决定 INFO/DEBUG 详细程度），
        # 让每条日志都带上时间，便于排查耗时。
        logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            format="%(asctime)s.%(msecs)03d [%(threadName)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        cfg = load_config()
        # 识别预设：显式 asr_preset > config 的 [asr].preset > 默认（nano）。
        preset = resolve_preset(asr_preset or (cfg.get("asr") or {}).get("preset"))
        logger.info("识别预设: %s -> %s", preset["label"], preset["model"])
        self._asr = ASREngine(
            model_name=model_name or preset["model"],
            vad_model=vad_model or preset["vad_model"],
            punc_model=preset["punc_model"],
            device=device,
        )
        self._injector = TextInjector(char_delay=char_delay)
        if polish:
            self._polisher: Optional[Polisher] = polisher or make_polisher_from_config(
                cfg
            )
        else:
            self._polisher = None

        self._config = AudioConfig(
            sample_rate=16000,
            channels=1,
            dtype="float32",
        )
        self._recorder = AudioRecorder(
            self._config,
            silence_threshold=silence_threshold,
            silence_duration_sec=silence_duration_sec,
            max_record_sec=max_record_sec,
        )
        self._hotkey = hotkey
        self._quit_hotkey = quit_hotkey
        self._on_status = on_status
        self._busy = threading.Lock()
        self._running = False
        self._live_preview = live_preview
        self._live_interval = live_interval
        self._preview: Optional[PreviewWindow] = None
        self._quit_event = threading.Event()
        self._hk_stop = threading.Event()
        self._polish_status: Optional[str] = None
        self._record_status: Optional[str] = None
        self._focus_guard = FocusGuard()
        self._polish_queue = _PolishQueue(
            polisher=self._polisher,
            injector=self._injector,
            on_polish_start=self._on_polish_start,
            on_polish_done=self._on_polish_done,
        )

    def start(self) -> None:
        """启动热键监听。"""
        try:
            import keyboard
        except ImportError as exc:
            raise RuntimeError("请先安装 keyboard: pip install keyboard") from exc

        self._running = True

        # 预加载模型：避免录音过程中首次加载抢占 CPU、饿死麦克风采集。
        logger.info("预加载识别模型...")
        self._notify("⏳ 正在加载识别模型（首次较慢，请稍候）...")
        try:
            self._asr.load()
        except Exception as exc:
            logger.exception("模型预加载失败")
            self._notify(f"❌ 模型加载失败: {exc}")
            return
        logger.info("模型就绪")

        self._register_hotkeys(keyboard)
        # 看门狗：定时重装键盘钩子，让休眠/唤醒后失效的全局钩子自愈。
        self._start_hotkey_watchdog(keyboard)

        if self._live_preview:
            self._preview = PreviewWindow(
                idle_text=f"🎙️ 待命 · {self._hotkey} 说话 · {self._quit_hotkey} 退出"
            )
            logger.info(
                "语音输入法已启动，快捷键: %s，退出: %s",
                self._hotkey,
                self._quit_hotkey,
            )
            try:
                self._preview.run()
            except KeyboardInterrupt:
                pass
            self.stop()
        else:
            self._notify(
                f"语音输入法已启动，快捷键: {self._hotkey}，退出: {self._quit_hotkey}"
            )
            try:
                self._quit_event.wait()
            except KeyboardInterrupt:
                pass
            self.stop()

    def _register_hotkeys(self, keyboard) -> None:  # type: ignore[no-untyped-def]
        """注册录音热键与退出热键。"""
        keyboard.add_hotkey(self._hotkey, self._on_hotkey)
        keyboard.add_hotkey(self._quit_hotkey, self._on_quit)

    def _start_hotkey_watchdog(self, keyboard, interval: float = 30.0) -> None:  # type: ignore[no-untyped-def]
        """后台线程定时重装全局键盘钩子。

        Windows 在睡眠/唤醒后常会把 keyboard 库的低级钩子移除，导致热键
        （含退出键）全部失效、进程看似挂死。这里每 interval 秒 unhook_all
        后重新注册，强制重建钩子，唤醒后可自愈。
        """

        def _loop() -> None:
            while not self._hk_stop.wait(interval):
                try:
                    keyboard.unhook_all()
                    self._register_hotkeys(keyboard)
                    logger.debug("热键看门狗：已重装钩子")
                except Exception:
                    logger.exception("热键看门狗重装失败")

        threading.Thread(target=_loop, name="hotkey-watchdog", daemon=True).start()

    def _on_quit(self) -> None:
        logger.info("收到退出热键")
        self._quit_event.set()
        if self._preview is not None:
            self._preview.close()

    def stop(self) -> None:
        """停止。"""
        self._running = False
        self._hk_stop.set()
        self._polish_queue.stop()
        if self._preview is not None:
            try:
                self._preview.close()
            except Exception:
                pass
        logger.info("退出")

    def _on_hotkey(self) -> None:
        """热键回调：把流水线丢到工作线程跑，避免阻塞 keyboard 监听线程
        （否则录音/识别期间 ESC 等热键无法响应）。"""
        if self._busy.locked():
            self._notify("⚠ 正在录音/识别中，请稍候...")
            return
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self) -> None:
        with self._busy:
            self._focus_guard.save()
            self._focus_guard.restore()
            logger.info("pipeline 开始 (live_preview=%s)", self._live_preview)
            self._set_record("🎤 正在录音...")
            live: Optional[LiveTranscriber] = None
            try:
                if self._live_preview:
                    live = LiveTranscriber(
                        recognize=self._recognize_samples,
                        on_partial=self._on_partial,
                    )
                    live.start()

                    def _on_window(samples) -> None:
                        logger.info(
                            "on_window 触发: %d 样本 (%.2fs)",
                            len(samples),
                            len(samples) / self._config.sample_rate,
                        )
                        live.submit(samples)

                    segment = self._recorder.record(
                        on_window=_on_window,
                        window_interval=self._live_interval,
                    )
                else:
                    segment = self._recorder.record()
            except RuntimeError as exc:
                logger.info("录音失败: %s", exc)
                self._set_record(f"❌ 录音失败: {exc}")
                return
            finally:
                if live is not None:
                    live.stop()

            logger.info(
                "录音结束: %d 样本 (%.2fs)",
                len(segment.samples),
                segment.duration_sec(),
            )
            self._set_record("🔄 正在识别...")
            tmp_wav = Path(tempfile.mkdtemp()) / "voice_input.wav"
            segment.to_wav(tmp_wav)

            try:
                t0 = time.time()
                text = self._asr.recognize(tmp_wav)
                logger.info("最终识别: %.2fs -> %r", time.time() - t0, text)
            except Exception as exc:
                logger.exception("最终识别异常")
                self._set_record(f"❌ 识别失败: {exc}")
                return
            finally:
                try:
                    tmp_wav.unlink(missing_ok=True)
                except Exception:
                    pass

            if not text:
                logger.info("未识别到语音")
                self._set_record(None)
                if self._preview is not None:
                    self._preview.flash("❌ 未识别到语音")
                else:
                    self._notify("❌ 未识别到语音")
                return

            logger.info("提交润色队列: %r", text)
            self._set_record(None)
            self._polish_queue.submit(text)

    def _recognize_samples(self, samples) -> str:
        """把一段音频快照识别成文本（供 LiveTranscriber 调用）。"""
        n = len(samples)
        loaded_before = self._asr.is_loaded
        logger.info("快层识别开始: %d 样本, 模型已加载=%s", n, loaded_before)
        t0 = time.time()
        seg = AudioSegment(
            samples=samples,
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
        )
        tmp_wav = Path(tempfile.mkdtemp()) / "live.wav"
        seg.to_wav(tmp_wav)
        try:
            text = self._asr.recognize(tmp_wav)
            logger.info("快层识别完成: %.2fs -> %r", time.time() - t0, text)
            return text
        except Exception:
            logger.exception("快层识别异常")
            raise
        finally:
            try:
                tmp_wav.unlink(missing_ok=True)
            except Exception:
                pass

    def _on_partial(self, text: str) -> None:
        """快层粗结果回调：刷新悬浮窗，并打到终端便于观察。"""
        if not text:
            return
        logger.info("[partial] %s", text)
        self._set_record(f"识别中: {text}")

    def _on_polish_start(self, text: str) -> None:
        logger.info("✍ 润色开始: %r", text)
        self._set_polish(f"✍ 润色中… 识别：{text}")

    def _on_polish_done(self, text: str) -> None:
        logger.info("✅ 润色完成: %r", text)
        self._set_polish(None)
        if self._preview is not None:
            self._preview.flash(f"✅ 已输入：{text}", hold_sec=4.0)
        elif self._on_status:
            self._on_status(f"✅ {text}")

    def _set_polish(self, text: Optional[str]) -> None:
        self._polish_status = text
        self._refresh_preview()

    def _set_record(self, text: Optional[str]) -> None:
        self._record_status = text
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._preview is None:
            return
        lines = []
        if self._polish_status:
            lines.append(self._polish_status)
        if self._record_status:
            lines.append(self._record_status)
        if lines:
            self._preview.show("\n".join(lines))

    def _notify(self, msg: str) -> None:
        if self._preview is not None:
            self._preview.show(msg)
        if self._on_status:
            self._on_status(msg)
        logger.info("%s", msg)
