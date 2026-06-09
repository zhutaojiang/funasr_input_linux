"""ASR 引擎单元测试。"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_funasr_module():
    """构造一个假 funasr 模块，避免真的下载模型。"""
    mod = types.ModuleType("funasr")
    auto_model_cls = MagicMock()
    mod.AutoModel = auto_model_cls
    sys.modules.setdefault("funasr", mod)
    return mod


class TestASREngine:
    def test_recognize_returns_text(self, mock_funasr_module, tmp_path):
        from funasr_input.asr import ASREngine

        fake_model = mock_funasr_module.AutoModel.return_value
        fake_model.generate.return_value = [{"text": " 你好世界 "}]

        engine = ASREngine(model_name="fake-model", device="cpu")
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"RIFF....WAVEfmt ")  # 占位，不会被真正读取

        result = engine.recognize(wav)
        assert result == "你好世界"

    def test_recognize_strips_whitespace(self, mock_funasr_module, tmp_path):
        from funasr_input.asr import ASREngine

        fake_model = mock_funasr_module.AutoModel.return_value
        fake_model.generate.return_value = [{"text": "\n  hello world \t"}]

        engine = ASREngine(model_name="fake-model", device="cpu")
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"RIFF")

        result = engine.recognize(wav)
        assert result == "hello world"

    def test_recognize_empty_result(self, mock_funasr_module, tmp_path):
        from funasr_input.asr import ASREngine

        fake_model = mock_funasr_module.AutoModel.return_value
        fake_model.generate.return_value = []

        engine = ASREngine(model_name="fake-model", device="cpu")
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"RIFF")

        result = engine.recognize(wav)
        assert result == ""

    def test_recognize_string_items(self, mock_funasr_module, tmp_path):
        from funasr_input.asr import ASREngine

        fake_model = mock_funasr_module.AutoModel.return_value
        fake_model.generate.return_value = ["hello", "world"]

        engine = ASREngine(model_name="fake-model", device="cpu")
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"RIFF")

        result = engine.recognize(wav)
        assert result == "helloworld"

    def test_recognize_with_timestamp(self, mock_funasr_module, tmp_path):
        from funasr_input.asr import ASREngine

        fake_model = mock_funasr_module.AutoModel.return_value
        fake_model.generate.return_value = [
            {"text": "hello", "start": 0, "end": 0.5},
            {"text": "world", "start": 0.6, "end": 1.0},
        ]

        engine = ASREngine(model_name="fake-model", device="cpu")
        wav = tmp_path / "test.wav"
        wav.write_bytes(b"RIFF")

        result = engine.recognize_with_timestamp(wav)
        assert len(result) == 2
        assert result[0]["text"] == "hello"

    def test_is_loaded_initially_false(self):
        from funasr_input.asr import ASREngine
        engine = ASREngine(model_name="fake", device="cpu")
        assert not engine.is_loaded

    def test_unload(self, mock_funasr_module):
        from funasr_input.asr import ASREngine

        fake_model = mock_funasr_module.AutoModel.return_value
        fake_model.generate.return_value = []

        engine = ASREngine(model_name="fake", device="cpu")
        wav = Path("dummy.wav")
        Path("dummy.wav").write_bytes(b"RIFF")

        engine.recognize(wav)
        assert engine.is_loaded

        engine.unload()
        assert not engine.is_loaded

    def test_missing_funasr_raises(self):
        from funasr_input import asr as asr_module
        original = sys.modules.get("funasr")
        sys.modules["funasr"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="funasr"):
                from funasr_input.asr import ASREngine  # noqa: F401  # type: ignore[misc]
        finally:
            if original is not None:
                sys.modules["funasr"] = original
            else:
                sys.modules.pop("funasr", None)
