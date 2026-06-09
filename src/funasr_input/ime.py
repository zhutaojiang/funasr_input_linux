"""语音输入法核心：热键 → 录音 → 识别 → 输入。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from funasr_input.audio import AudioConfig, AudioRecorder, AudioSegment
from funasr_input.asr import ASREngine
from funasr_input.input import TextInjector


class VoiceIME:
    """主控制器，串联音频采集、ASR 识别和文本注入。"""

    def __init__(
        self,
        *,
        model_name: str = "FunAudioLLM/Fun-ASR-Nano-2512",
        vad_model: str = "fsmn-vad",
        device: str = "cpu",
        hotkey: str = "ctrl+alt+space",
        silence_threshold: float = 0.015,
        silence_duration_sec: float = 1.0,
        max_record_sec: float = 30.0,
        char_delay: float = 0.0,
        on_status: Optional[callable] = None,
    ) -> None:
        self._asr = ASREngine(
            model_name=model_name,
            vad_model=vad_model,
            device=device,
        )
        self._injector = TextInjector(char_delay=char_delay)

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
        self._on_status = on_status
        self._busy = threading.Lock()
        self._running = False

    def start(self) -> None:
        """启动热键监听。"""
        try:
            import keyboard
        except ImportError as exc:
            raise RuntimeError("请先安装 keyboard: pip install keyboard") from exc

        self._running = True
        keyboard.add_hotkey(self._hotkey, self._on_hotkey)
        self._notify(f"语音输入法已启动，快捷键: {self._hotkey}，退出: ESC")

        # 阻塞直到用户按 ESC
        keyboard.wait("esc")
        self.stop()

    def stop(self) -> None:
        """停止。"""
        self._running = False
        self._notify("语音输入法已退出")

    def _on_hotkey(self) -> None:
        """热键回调：独占执行，防止重复触发。"""
        if self._busy.locked():
            self._notify("⚠ 正在录音/识别中，请稍候...")
            return

        with self._busy:
            self._notify("🎤 正在录音...")
            try:
                segment = self._recorder.record()
            except RuntimeError as exc:
                self._notify(f"❌ 录音失败: {exc}")
                return

            self._notify("🔄 正在识别...")
            tmp_wav = Path(tempfile.mkdtemp()) / "voice_input.wav"
            segment.to_wav(tmp_wav)

            try:
                text = self._asr.recognize(tmp_wav)
            except Exception as exc:
                self._notify(f"❌ 识别失败: {exc}")
                return
            finally:
                try:
                    tmp_wav.unlink(missing_ok=True)
                except Exception:
                    pass

            if not text:
                self._notify("❌ 未识别到语音")
                return

            self._notify(f"✅ {text}")
            self._injector.write(text)

    def _notify(self, msg: str) -> None:
        if self._on_status:
            self._on_status(msg)
        else:
            print(msg, flush=True)
