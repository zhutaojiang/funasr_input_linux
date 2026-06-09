"""音频模块单元测试。"""

from __future__ import annotations

import io
import os
import sys
import types
from pathlib import Path

import numpy as np
import pytest


# ---- 测试用 AudioConfig ----

@pytest.fixture
def config():
    from funasr_input.audio import AudioConfig
    return AudioConfig(sample_rate=16000, channels=1)


# ---- AudioSegment 测试 ----

class TestAudioSegment:
    def test_duration(self, tmp_path):
        from funasr_input.audio import AudioSegment
        sr = 16000
        samples = np.zeros(sr * 2, dtype="float32")  # 2 秒静音
        seg = AudioSegment(samples=samples, sample_rate=sr, channels=1)
        assert abs(seg.duration_sec() - 2.0) < 0.01

    def test_to_wav_roundtrip(self, tmp_path):
        pytest.importorskip("soundfile")
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
