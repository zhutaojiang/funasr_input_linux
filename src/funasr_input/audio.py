"""音频采集模块。

封装 sounddevice 实时流 + WAV 写出，提供同步/异步两种接口，
方便业务层调用，也方便测试时 Mock。
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

import numpy as np


def _load_sounddevice():
    """惰性导入 sounddevice，未安装时给出友好提示。"""
    try:
        import sounddevice as sd
    except ImportError as exc:  # pragma: no cover - 取决于运行环境
        raise RuntimeError(
            "请先安装 sounddevice: pip install sounddevice"
        ) from exc
    return sd


def _load_soundfile():
    """惰性导入 soundfile，未安装时给出友好提示。"""
    try:
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover - 取决于运行环境
        raise RuntimeError(
            "请先安装 soundfile: pip install soundfile"
        ) from exc
    return sf


@dataclass(frozen=True)
class AudioConfig:
    """音频采集参数。"""

    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "float32"
    device: Optional[Union[str, int]] = None  # sounddevice 设备标识


@dataclass
class AudioSegment:
    """单次录音结果。"""

    samples: np.ndarray
    sample_rate: int
    channels: int

    def to_wav(self, path: Union[str, Path]) -> Path:
        """写出为 WAV 文件。"""
        sf = _load_soundfile()
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out), self.samples, self.sample_rate)
        return out

    def duration_sec(self) -> float:
        return len(self.samples) / float(self.sample_rate)


class AudioRecorder:
    """基于 sounddevice 的实时录音器。"""

    def __init__(
        self,
        config: AudioConfig,
        *,
        silence_threshold: float = 0.015,
        silence_duration_sec: float = 1.0,
        max_record_sec: float = 30.0,
        on_chunk: Optional[Callable[[np.ndarray], None]] = None,
    ) -> None:
        self._config = config
        self._silence_threshold = silence_threshold
        self._silence_frames = int(silence_duration_sec * config.sample_rate)
        self._max_frames = int(max_record_sec * config.sample_rate)
        self._on_chunk = on_chunk

        self._q: queue.Queue[np.ndarray] = queue.Queue()
        self._recording = threading.Event()
        self._stream = None  # type: Optional[object]  # sd.InputStream

    # ---- 公共接口 ----

    def record(
        self,
        *,
        on_window: Optional[Callable[[np.ndarray], None]] = None,
        window_interval: float = 2.5,
    ) -> AudioSegment:
        """同步录音：自动按静音停止，返回 AudioSegment。"""
        self._recording.set()
        buffer: list[np.ndarray] = []
        total_frames = 0
        silence_start: Optional[int] = None
        speech_started = False  # 仅在检测到语音后才用静音判断停止
        window_frames = int(window_interval * self._config.sample_rate)
        next_window = window_frames

        sd = _load_sounddevice()
        try:
            with sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype=self._config.dtype,
                device=self._config.device,
                callback=self._callback,
            ):
                while total_frames < self._max_frames and self._recording.is_set():
                    try:
                        chunk = self._q.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    buffer.append(chunk)
                    total_frames += len(chunk)
                    if on_window and window_frames > 0 and total_frames >= next_window:
                        on_window(np.concatenate(buffer).copy())
                        next_window += window_frames
                    if self._on_chunk:
                        self._on_chunk(chunk)

                    volume = float(np.sqrt(np.mean(chunk ** 2)))
                    if volume < self._silence_threshold:
                        # 语音尚未开始时，忽略前导静音，避免一上来就停录
                        if not speech_started:
                            continue
                        if silence_start is None:
                            silence_start = total_frames
                        elif total_frames - silence_start >= self._silence_frames:
                            break
                    else:
                        speech_started = True
                        silence_start = None
        finally:
            self._recording.clear()

        if not buffer:
            raise RuntimeError("未录制到有效音频")

        samples = np.concatenate(buffer)
        return AudioSegment(
            samples=samples,
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
        )

    def start_stream(self) -> None:
        """启动后台流，持续写入 self._q，直到 stop_stream()。"""
        if self._stream is not None:
            return
        sd = _load_sounddevice()
        self._recording.set()
        self._stream = sd.InputStream(
            samplerate=self._config.sample_rate,
            channels=self._config.channels,
            dtype=self._config.dtype,
            device=self._config.device,
            callback=self._callback,
        )
        self._stream.start()

    def stop_stream(self) -> None:
        """停止后台流。"""
        self._recording.clear()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    # ---- 内部 ----

    def _callback(self, indata, frames, time_info, status):  # type: ignore[no-untyped-def]
        if self._recording.is_set():
            self._q.put(indata.copy())
