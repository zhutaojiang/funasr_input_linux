# 准流式预览 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 说话时在置顶悬浮窗实时显示「粗识别结果」（准流式），说完后完整识别 +（可选）LLM 润色，把净本一次性敲进焦点窗口。

**Architecture:** 复用离线模型做两层识别——快层用增长窗口每隔 `live_interval` 重识别累积音频、刷新悬浮窗；慢层在静音停止后做完整识别。`AudioRecorder.record()` 增加 `on_window` 钩子；`LiveTranscriber` 在后台线程做「最新优先」识别；`PreviewWindow`（tkinter）在主线程跑事件循环、由工作线程经 `after()` 线程安全刷新。全部由 `live_preview` 开关控制，默认关闭，现有流程与测试不受影响。

**Tech Stack:** Python 3.11+，stdlib `tkinter` / `threading` / `queue`（零新依赖），numpy，pytest。

对应 spec：`docs/superpowers/specs/2026-06-09-streaming-preview-llm-polish-design.md`（第一节快层 + 第二节悬浮窗 + 第四节开关/降级）。LLM 润色已在前一份计划完成，本计划复用其 `_polisher`。

---

## File Structure

- **Modify** `src/funasr_input/audio.py` — `record()` 增加 `on_window`/`window_interval`，按帧数周期性回调累积音频快照。
- **Create** `src/funasr_input/live.py` — `LiveTranscriber`：后台线程「最新优先」识别调度。
- **Create** `src/funasr_input/preview.py` — `PreviewWindow`：tkinter 置顶悬浮窗，线程安全 `show/run/close`。
- **Modify** `src/funasr_input/ime.py` — `live_preview` 开关、`_recognize_samples`、`_on_partial`、`start()`/`_on_hotkey` 的线程模型与编排。
- **Create** `tests/unit/test_live.py`、`tests/unit/test_audio_window.py`、`tests/unit/test_ime_live.py`。

---

## Task 1: AudioRecorder.record() 增长窗口回调

**Files:**
- Modify: `src/funasr_input/audio.py`
- Test: `tests/unit/test_audio_window.py`

- [ ] **Step 1: 写失败测试**

`tests/unit/test_audio_window.py`:
```python
"""AudioRecorder 增长窗口回调测试。"""

from __future__ import annotations

import types

import numpy as np

from funasr_input.audio import AudioConfig, AudioRecorder


def _fake_sd():
    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return types.SimpleNamespace(InputStream=FakeStream)


def test_record_fires_on_window_growing(monkeypatch):
    from funasr_input import audio as audio_mod

    monkeypatch.setattr(audio_mod, "_load_sounddevice", _fake_sd)

    cfg = AudioConfig(sample_rate=100)  # 小采样率方便算帧
    rec = AudioRecorder(
        cfg, silence_threshold=0.01, silence_duration_sec=0.5, max_record_sec=10
    )
    loud = np.ones(10, dtype="float32") * 0.5   # 音量 0.5 > 阈值
    silent = np.zeros(10, dtype="float32")       # 音量 0 < 阈值
    # 静音需累计 silence_frames=int(0.5*100)=50 帧才停止
    for c in [loud] * 3 + [silent] * 7:
        rec._q.put(c)

    sizes = []
    rec.record(on_window=lambda s: sizes.append(len(s)), window_interval=0.1)

    assert sizes, "应至少触发一次窗口回调"
    assert sizes == sorted(sizes), "窗口应随累积音频增长"
    assert sizes[0] == 10
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_audio_window.py -q`
Expected: FAIL — `TypeError: record() got an unexpected keyword argument 'on_window'`

- [ ] **Step 3: 写最小实现**

在 `src/funasr_input/audio.py` 修改 `record` 方法签名与循环。

签名改为：
```python
    def record(
        self,
        *,
        on_window: Optional[Callable[[np.ndarray], None]] = None,
        window_interval: float = 2.5,
    ) -> AudioSegment:
```

在方法体 `silence_start: Optional[int] = None` 之后、`sd = _load_sounddevice()` 之前，加：
```python
        window_frames = int(window_interval * self._config.sample_rate)
        next_window = window_frames
```

在循环里，`buffer.append(chunk)` 和 `total_frames += len(chunk)` 之后、`if self._on_chunk:` 之前，加：
```python
                if on_window and window_frames > 0 and total_frames >= next_window:
                    on_window(np.concatenate(buffer).copy())
                    next_window += window_frames
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_audio_window.py -q`
Expected: PASS

- [ ] **Step 5: 回归 + 提交**

Run: `python -m pytest tests/ -q` → 全绿
```bash
git add src/funasr_input/audio.py tests/unit/test_audio_window.py
git commit -m "feat(audio): record() 增长窗口回调 on_window"
```

---

## Task 2: LiveTranscriber 后台识别调度

**Files:**
- Create: `src/funasr_input/live.py`
- Test: `tests/unit/test_live.py`

- [ ] **Step 1: 写失败测试**

`tests/unit/test_live.py`:
```python
"""LiveTranscriber 单元测试。"""

from __future__ import annotations

import threading

import numpy as np

from funasr_input.live import LiveTranscriber


def test_take_pending_latest_wins():
    lt = LiveTranscriber(recognize=lambda s: "", on_partial=lambda t: None)
    lt.submit(np.zeros(3, dtype="float32"))
    lt.submit(np.ones(5, dtype="float32"))
    pending = lt._take_pending()
    assert pending is not None and len(pending) == 5   # 取到最新一份
    assert lt._take_pending() is None                   # 取走后清空


def test_worker_recognizes_and_calls_on_partial():
    done = threading.Event()
    seen = {}

    def recognize(samples):
        return f"len={len(samples)}"

    def on_partial(text):
        seen["text"] = text
        done.set()

    lt = LiveTranscriber(recognize=recognize, on_partial=on_partial)
    lt.start()
    try:
        lt.submit(np.zeros(7, dtype="float32"))
        assert done.wait(timeout=3.0), "on_partial 应被调用"
        assert seen["text"] == "len=7"
    finally:
        lt.stop()


def test_worker_swallows_recognize_error():
    done = threading.Event()

    def recognize(samples):
        raise RuntimeError("boom")

    lt = LiveTranscriber(
        recognize=recognize, on_partial=lambda t: done.set()
    )
    lt.start()
    try:
        lt.submit(np.zeros(3, dtype="float32"))
        # 识别异常被吞掉，不调用 on_partial、不崩溃
        assert not done.wait(timeout=0.5)
    finally:
        lt.stop()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_live.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'funasr_input.live'`

- [ ] **Step 3: 写最小实现**

`src/funasr_input/live.py`:
```python
"""准流式识别调度：后台线程对最新音频快照做识别，刷新预览。"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import numpy as np


class LiveTranscriber:
    """把 submit() 的最新音频快照识别成粗文本，回调 on_partial。

    「最新优先」：识别耗时期间若有新快照，只保留最后一份，丢弃过期的，
    避免在 CPU 上排队堆积。
    """

    def __init__(
        self,
        recognize: Callable[[np.ndarray], str],
        on_partial: Callable[[str], None],
    ) -> None:
        self._recognize = recognize
        self._on_partial = on_partial
        self._pending: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, samples: np.ndarray) -> None:
        with self._lock:
            self._pending = samples
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _take_pending(self) -> Optional[np.ndarray]:
        with self._lock:
            samples = self._pending
            self._pending = None
            return samples

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=0.1)
            self._wake.clear()
            samples = self._take_pending()
            if samples is None:
                continue
            try:
                text = self._recognize(samples)
            except Exception:
                continue  # 识别失败仅跳过本次，不影响后续
            if text:
                self._on_partial(text)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_live.py -q`
Expected: PASS（3 个）

- [ ] **Step 5: 提交**

```bash
git add src/funasr_input/live.py tests/unit/test_live.py
git commit -m "feat(live): LiveTranscriber 最新优先识别调度"
```

---

## Task 3: PreviewWindow 悬浮预览窗（tkinter）

**Files:**
- Create: `src/funasr_input/preview.py`

无自动化测试（GUI 渲染不强测，见 Task 5 手动验证）。实现要点：置顶、无边框、线程安全更新。

- [ ] **Step 1: 实现 `src/funasr_input/preview.py`**

```python
"""悬浮预览窗（tkinter）。

主线程创建并运行事件循环；工作线程通过 after() 线程安全地刷新文字。
"""

from __future__ import annotations

from typing import Optional


class PreviewWindow:
    """置顶、无边框的小条，显示当前识别/状态文字。"""

    def __init__(self, *, opacity: float = 0.85) -> None:
        import tkinter as tk

        self._root = tk.Tk()
        self._root.overrideredirect(True)            # 无边框
        self._root.attributes("-topmost", True)      # 置顶
        try:
            self._root.attributes("-alpha", opacity)  # 半透明
        except Exception:
            pass
        self._root.configure(bg="#222222")

        self._var = tk.StringVar(value="")
        self._label = tk.Label(
            self._root,
            textvariable=self._var,
            fg="#eeeeee",
            bg="#222222",
            font=("Microsoft YaHei", 14),
            padx=16,
            pady=8,
            justify="left",
            wraplength=600,
        )
        self._label.pack()
        self._position_bottom_center()

    def _position_bottom_center(self) -> None:
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        x = (sw - w) // 2
        y = sh - h - 80
        self._root.geometry(f"+{x}+{y}")

    def show(self, text: str) -> None:
        """线程安全地更新显示文字（可从任意线程调用）。"""
        self._root.after(0, self._apply, text)

    def _apply(self, text: str) -> None:
        self._var.set(text)
        self._position_bottom_center()

    def run(self) -> None:
        """在主线程运行事件循环，直到 close()。"""
        self._root.mainloop()

    def close(self) -> None:
        """线程安全地关闭窗口、退出事件循环。"""
        try:
            self._root.after(0, self._root.quit)
        except Exception:
            pass
```

- [ ] **Step 2: 冒烟检查（导入不报错）**

Run: `python -c "import funasr_input.preview"`
Expected: 无输出、无异常（仅导入，不创建窗口）。

- [ ] **Step 3: 提交**

```bash
git add src/funasr_input/preview.py
git commit -m "feat(preview): tkinter 置顶悬浮预览窗"
```

---

## Task 4: VoiceIME 编排（live_preview 开关 + 线程模型）

**Files:**
- Modify: `src/funasr_input/ime.py`
- Test: `tests/unit/test_ime_live.py`

先用 Read 工具读 `src/funasr_input/ime.py` 看清当前 `__init__` / `start` / `_on_hotkey` 的确切代码，再按下面精确编辑。

- [ ] **Step 1: 写失败测试（可测的纯逻辑部分）**

`tests/unit/test_ime_live.py`:
```python
"""VoiceIME 准流式相关逻辑单元测试（不涉及真实 GUI）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def _make_ime(**kwargs):
    from funasr_input.ime import VoiceIME

    return VoiceIME(device="cpu", on_status=lambda m: None, **kwargs)


def test_recognize_samples_uses_asr(monkeypatch):
    ime = _make_ime()
    monkeypatch.setattr(
        "funasr_input.audio.AudioSegment.to_wav", lambda self, p: Path(p)
    )
    monkeypatch.setattr(ime._asr, "recognize", lambda p: "粗结果")
    out = ime._recognize_samples(np.zeros(10, dtype="float32"))
    assert out == "粗结果"


class _FakePreview:
    def __init__(self):
        self.shown = []

    def show(self, text):
        self.shown.append(text)


def test_on_partial_updates_preview():
    ime = _make_ime()
    preview = _FakePreview()
    ime._preview = preview
    ime._on_partial("你好")
    assert preview.shown == ["识别中: 你好"]


def test_on_partial_noop_without_preview():
    ime = _make_ime()
    ime._preview = None
    ime._on_partial("你好")  # 不应抛异常


def test_live_disabled_by_default():
    ime = _make_ime()
    assert ime._live_preview is False
    assert ime._preview is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_ime_live.py -q`
Expected: FAIL — `AttributeError: 'VoiceIME' object has no attribute '_recognize_samples'`（或 `_live_preview`）

- [ ] **Step 3: 写最小实现，改 `src/funasr_input/ime.py`**

(a) 顶部 import 增加：
```python
from funasr_input.live import LiveTranscriber
from funasr_input.preview import PreviewWindow
```

(b) `__init__` 签名里、在 `on_status` 之前增加：
```python
        live_preview: bool = False,
        live_interval: float = 2.5,
```

(c) `__init__` 体内、`self._running = False` 附近，增加状态初始化：
```python
        self._live_preview = live_preview
        self._live_interval = live_interval
        self._preview: Optional[PreviewWindow] = None
```

(d) 在类中增加两个方法（放在 `_on_hotkey` 之后、`_notify` 之前）：
```python
    def _recognize_samples(self, samples) -> str:
        """把一段音频快照识别成文本（供 LiveTranscriber 调用）。"""
        seg = AudioSegment(
            samples=samples,
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
        )
        tmp_wav = Path(tempfile.mkdtemp()) / "live.wav"
        seg.to_wav(tmp_wav)
        try:
            return self._asr.recognize(tmp_wav)
        finally:
            try:
                tmp_wav.unlink(missing_ok=True)
            except Exception:
                pass

    def _on_partial(self, text: str) -> None:
        """快层粗结果回调：刷新悬浮窗。"""
        if text and self._preview is not None:
            self._preview.show(f"识别中: {text}")
```

(e) 让 `_notify` 在有预览窗时也刷新预览。把 `_notify` 改为：
```python
    def _notify(self, msg: str) -> None:
        if self._preview is not None:
            self._preview.show(msg)
        if self._on_status:
            self._on_status(msg)
        else:
            print(msg, flush=True)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_ime_live.py -q`
Expected: PASS（4 个）

- [ ] **Step 5: 接入 `_on_hotkey` 与 `start()` 的 live 分支**

在 `_on_hotkey` 里，把当前「`segment = self._recorder.record()`」那一处替换为按开关分流（保留其余 try/except 不变）：
```python
            self._notify("🎤 正在录音...")
            live: Optional[LiveTranscriber] = None
            try:
                if self._live_preview:
                    live = LiveTranscriber(
                        recognize=self._recognize_samples,
                        on_partial=self._on_partial,
                    )
                    live.start()
                    segment = self._recorder.record(
                        on_window=live.submit,
                        window_interval=self._live_interval,
                    )
                else:
                    segment = self._recorder.record()
            except RuntimeError as exc:
                self._notify(f"❌ 录音失败: {exc}")
                return
            finally:
                if live is not None:
                    live.stop()
```
（注意：原来的 `try: segment = self._recorder.record() except RuntimeError ...` 整段被上面替换；后续「识别 → 润色 → 注入」逻辑保持不变。）

`start()` 改为按开关选择运行模型：
```python
    def start(self) -> None:
        """启动热键监听。"""
        try:
            import keyboard
        except ImportError as exc:
            raise RuntimeError("请先安装 keyboard: pip install keyboard") from exc

        self._running = True
        keyboard.add_hotkey(self._hotkey, self._on_hotkey)

        if self._live_preview:
            self._preview = PreviewWindow()
            keyboard.add_hotkey("esc", self._on_quit)
            self._notify(f"语音输入法已启动，快捷键: {self._hotkey}，退出: ESC")
            self._preview.run()       # 主线程事件循环，直到 ESC
            self.stop()
        else:
            self._notify(f"语音输入法已启动，快捷键: {self._hotkey}，退出: ESC")
            keyboard.wait("esc")
            self.stop()

    def _on_quit(self) -> None:
        if self._preview is not None:
            self._preview.close()
```

- [ ] **Step 6: 回归**

Run: `python -m pytest tests/ -q`
Expected: 全绿（既有 + 新增 test_ime_live 4 个 + 前面任务的测试）。

- [ ] **Step 7: 提交**

```bash
git add src/funasr_input/ime.py tests/unit/test_ime_live.py
git commit -m "feat(ime): 准流式预览编排（live_preview 开关 + tkinter 线程模型）"
```

---

## Task 5: 手动端到端验证 + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README**

在「可选：LLM 润色」一节后追加：
```markdown
### 可选：准流式预览

开启后，说话时会在屏幕下方弹出置顶悬浮窗，实时显示「识别中: …」粗结果；
说完（静音停止）后完整识别（如开了润色再润色），把净本一次性敲进焦点窗口。

\`\`\`bash
python -c "from funasr_input.ime import VoiceIME; VoiceIME(device='cpu', live_preview=True, polish=True).start()"
\`\`\`

- `live_interval`（默认 2.5 秒）控制粗结果刷新间隔；CPU 较慢可调大。
- 悬浮窗用 tkinter（无新依赖），置顶无边框，按 ESC 退出。
```

- [ ] **Step 2: 手动验证（需麦克风）**

1. `python -c "from funasr_input.ime import VoiceIME; VoiceIME(device='cpu', live_preview=True).start()"`
2. 屏幕下方应出现悬浮窗。焦点放记事本，按 Ctrl+Alt+Space 说一段较长的话。
3. 预期：说话过程中悬浮窗每隔约 2.5s 刷新「识别中: …」；停顿 1s 后净本敲进记事本。
4. 再加 `polish=True` 跑一次，确认润色后文本入框。
5. 按 ESC，悬浮窗关闭、程序退出。

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: 准流式预览用法说明"
```

---

## Self-Review

**Spec coverage（第一节快层 / 第二节悬浮窗 / 第四节开关·降级）：**
- 增长窗口快层 → Task 1（record on_window）+ Task 2（LiveTranscriber）+ Task 4（_recognize_samples/_on_partial 接线）✅
- 悬浮窗 tkinter + 主线程事件循环 + 工作线程 after() 刷新 → Task 3 + Task 4（start/_on_quit）✅
- live_preview 开关、默认关不破坏现状 → Task 4（默认 False，start 分流）+ 各 Step 回归 ✅
- 失败降级：快层识别异常跳过 → Task 2（`_run` 吞异常）；最终识别/润色沿用既有路径 ✅

**Placeholder scan:** 无 TBD/TODO；可测部分均给完整代码与测试，GUI 部分给完整实现 + 手动验证步骤。

**Type consistency:** `record(on_window, window_interval)`、`LiveTranscriber(recognize: (ndarray)->str, on_partial: (str)->None)`、`PreviewWindow.show/run/close`、`VoiceIME(live_preview, live_interval)` 与 `_recognize_samples/_on_partial/_on_quit` 在各任务间一致。

**Scope:** 聚焦准流式预览单一子系统，复用已完成的 `_polisher`。
