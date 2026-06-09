"""音频模块单元测试。"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture
def mock_soundfile():
    """让 soundfile 可用，但不需要真正的 libsndfile。"""
    fake_sf = types.ModuleType("soundfile")

    def fake_write(path, data, samplerate):
        # 使用 wave 库写出一个最小 WAV 文件
        import wave
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1 if len(data.shape) == 1 else data.shape[1])
            wf.setsampwidth(2)
            wf.setframerate(int(samplerate))
            int16 = (data * 32767).astype("<i2")
            wf.writeframes(int16.tobytes())

    fake_sf.write = fake_write
    sys.modules["soundfile"] = fake_sf
    return fake_sf


@pytest.fixture
def mock_sounddevice():
    """Mock sounddevice，避免需要麦克风设备。"""
    fake_sd = types.ModuleType("sounddevice")
    fake_stream = MagicMock()
    fake_stream.__enter__ = MagicMock(return_value=fake_stream)
    fake_stream.__exit__ = MagicMock(return_value=False)
    fake_sd.InputStream = MagicMock(return_value=fake_stream)
    sys.modules["sounddevice"] = fake_sd
    return fake_sd


# ---- AudioSegment 测试 ----

class TestAudioSegment:
    def test_duration(self, tmp_path):
        from funasr_input.audio import AudioSegment
        sr = 16000
        samples = np.zeros(sr * 2, dtype="float32")  # 2 秒静音
        seg = AudioSegment(samples=samples, sample_rate=sr, channels=1)
        assert abs(seg.duration_sec() - 2.0) < 0.01

    def test_to_wav_roundtrip(self, tmp_path, mock_soundfile, monkeypatch):
        # 关键：把 funasr_input.audio.sf 也替换成我们的 fake_soundfile，
        # 避免模块顶层已经缓存了真实的 soundfile 引用。
        import funasr_input.audio as audio_module
        monkeypatch.setattr(audio_module, "sf", mock_soundfile)

        from funasr_input.audio import AudioSegment
        sr = 16000
        # 440 Hz 正弦波 1 秒
        t = np.linspace(0, 1, sr, endpoint=False)
        samples = (0.5 * np.sin(2 * np.pi * 440 * t)).astype("float32")
        seg = AudioSegment(samples=samples, sample_rate=sr, channels=1)

        wav_path = tmp_path / "test.wav"
        out = seg.to_wav(wav_path)
        assert out.exists()
        assert out.stat().st_size > 0


# ---- AudioConfig 测试 ----

class TestAudioConfig:
    def test_defaults(self):
        from funasr_input.audio import AudioConfig
        c = AudioConfig()
        assert c.sample_rate == 16000
        assert c.channels == 1
        assert c.dtype == "float32"

    def test_custom(self):
        from funasr_input.audio import AudioConfig
        c = AudioConfig(sample_rate=48000, channels=2, dtype="int16")
        assert c.sample_rate == 48000
        assert c.channels == 2
        assert c.dtype == "int16"
