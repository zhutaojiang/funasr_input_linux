"""集成测试：从音频录制到 ASR 识别到文本注入的端到端流程。"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


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


@pytest.fixture
def mock_soundfile():
    """Mock soundfile，避免依赖 libsndfile。"""
    fake_sf = types.ModuleType("soundfile")
    fake_sf.write = MagicMock()
    sys.modules["soundfile"] = fake_sf
    return fake_sf


@pytest.fixture
def mock_funasr():
    """Mock funasr，避免下载模型。"""
    mod = types.ModuleType("funasr")
    auto_model_cls = MagicMock()
    auto_model_cls.return_value.generate.return_value = [{"text": "集成测试"}]
    mod.AutoModel = auto_model_cls
    sys.modules["funasr"] = mod
    return mod


@pytest.fixture
def mock_keyboard():
    """Mock keyboard，避免需要输入设备权限。"""
    fake_kb = types.ModuleType("keyboard")
    fake_kb.add_hotkey = MagicMock()
    fake_kb.wait = MagicMock()
    sys.modules["keyboard"] = fake_kb
    return fake_kb


@pytest.fixture
def mock_ctypes(monkeypatch):
    """只伪造 ctypes.windll，保留真实 ctypes（input 模块在导入时需要
    ctypes.POINTER / Structure 等）。这样既避免真实 Windows API 调用，
    又不受测试导入顺序影响。"""
    import ctypes

    fake_user32 = MagicMock()
    fake_windll = MagicMock()
    fake_windll.user32 = fake_user32
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)
    return fake_user32


class TestEndToEndFlow:
    """测试完整流程：配置 → 录音 → 识别 → 输入。"""

    def test_pipeline_no_exception(
        self,
        mock_sounddevice,
        mock_soundfile,
        mock_funasr,
        mock_keyboard,
        mock_ctypes,
        tmp_path,
        monkeypatch,
    ):
        """构造 VoiceIME 并模拟一次完整触发，不应抛异常。"""
        from funasr_input.audio import AudioConfig, AudioRecorder
        from funasr_input.asr import ASREngine
        from funasr_input.input import TextInjector
        from funasr_input.ime import VoiceIME

        # 让 record() 快速返回一段音频，不真的等麦克风
        fake_segment = MagicMock()
        fake_segment.duration_sec.return_value = 1.5

        with patch.object(AudioRecorder, "record", return_value=fake_segment):
            ime = VoiceIME(device="cpu", on_status=lambda msg: None)
            # 直接调用 _on_hotkey，不经过 keyboard 库
            ime._run_pipeline()

        # ASR 识别应该被调用
        sys.modules["funasr"].AutoModel.return_value.generate.assert_called()

    def test_recognize_invoked_with_wav_path(
        self,
        mock_sounddevice,
        mock_soundfile,
        mock_funasr,
        mock_keyboard,
        mock_ctypes,
        tmp_path,
        monkeypatch,
    ):
        from funasr_input.audio import AudioConfig, AudioRecorder
        from funasr_input.asr import ASREngine
        from funasr_input.input import TextInjector
        from funasr_input.ime import VoiceIME

        fake_segment = MagicMock()
        fake_segment.duration_sec.return_value = 0.8

        captured: dict = {}

        def fake_recognize(self, wav_path):
            captured["path"] = str(wav_path)
            return "hello"

        with patch.object(AudioRecorder, "record", return_value=fake_segment):
            with patch.object(ASREngine, "recognize", fake_recognize):
                ime = VoiceIME(device="cpu", on_status=lambda msg: None)
                ime._run_pipeline()

        assert "wav" in captured.get("path", "").lower()

    def test_empty_text_skips_injection(
        self,
        mock_sounddevice,
        mock_soundfile,
        mock_funasr,
        mock_keyboard,
        mock_ctypes,
        tmp_path,
        monkeypatch,
    ):
        from funasr_input.audio import AudioConfig, AudioRecorder
        from funasr_input.asr import ASREngine
        from funasr_input.input import TextInjector
        from funasr_input.ime import VoiceIME

        fake_segment = MagicMock()
        fake_segment.duration_sec.return_value = 0.5

        with patch.object(AudioRecorder, "record", return_value=fake_segment):
            with patch.object(ASREngine, "recognize", return_value=""):
                with patch.object(TextInjector, "write") as mock_write:
                    ime = VoiceIME(device="cpu", on_status=lambda msg: None)
                    ime._run_pipeline()

        mock_write.assert_not_called()