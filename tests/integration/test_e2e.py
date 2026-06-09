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
    sys.modules.setdefault("sounddevice", fake_sd)
    return fake_sd


@pytest.fixture
def mock_soundfile():
    """Mock soundfile，避免依赖 libsndfile。"""
    fake_sf = types.ModuleType("soundfile")
    fake_sf.write = MagicMock()
    sys.modules.setdefault("soundfile", fake_sf)
    return fake_sf


@pytest.fixture
def mock_funasr():
    """Mock funasr，避免下载模型。"""
    mod = types.ModuleType("funasr")
    auto_model_cls = MagicMock()
    auto_model_cls.return_value.generate.return_value = [{"text": "集成测试"}]
    mod.AutoModel = auto_model_cls
    sys.modules.setdefault("funasr", mod)
    return mod


@pytest.fixture
def mock_keyboard():
    """Mock keyboard，避免需要输入设备权限。"""
    fake_kb = types.ModuleType("keyboard")
    fake_kb.add_hotkey = MagicMock()
    fake_kb.wait = MagicMock()
    sys.modules.setdefault("keyboard", fake_kb)
    return fake_kb


@pytest.fixture
def mock_ctypes():
    """Mock ctypes.windll，避免 Windows API 依赖。"""
    fake_ctypes = types.ModuleType("ctypes")
    fake_windll = MagicMock()
    fake_ctypes.windll = fake_windll  # type: ignore[attr-defined]
    fake_user32 = MagicMock()
    fake_windll.user32 = fake_user32  # type: ignore[attr-defined]
    sys.modules.setdefault("ctypes", fake_ctypes)
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
        fake_segment.to_wav.return_value = tmp_path / "segment.wav"

        with patch.object(AudioRecorder, "record", return_value=fake_segment):
            ime = VoiceIME(device="cpu", on_status=lambda msg: None)
            # 直接调用 _on_hotkey，不经过 keyboard 库
            ime._on_hotkey()

        # ASR 和 injector 都应该被调用
        mock_funasr["funasr"].AutoModel.return_value.generate.assert_called_once()
        assert mock_ctypes.keybd_event.call_count > 0

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
        fake_segment.to_wav.return_value = tmp_path / "seg.wav"

        captured: dict = {}

        def fake_recognize(self, wav_path):
            captured["path"] = str(wav_path)
            return "hello"

        with patch.object(AudioRecorder, "record", return_value=fake_segment):
            with patch.object(ASREngine, "recognize", fake_recognize):
                ime = VoiceIME(device="cpu", on_status=lambda msg: None)
                ime._on_hotkey()

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
        fake_segment.to_wav.return_value = tmp_path / "seg.wav"

        with patch.object(AudioRecorder, "record", return_value=fake_segment):
            with patch.object(ASREngine, "recognize", return_value=""):
                with patch.object(TextInjector, "write") as mock_write:
                    ime = VoiceIME(device="cpu", on_status=lambda msg: None)
                    ime._on_hotkey()

        mock_write.assert_not_called()
