"""ASR 引擎单元测试。"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _install_mock_funasr():
    """安装一个假的 funasr 模块到 sys.modules，避免真的下载模型。"""
    mod = types.ModuleType("funasr")
    auto_model_cls = MagicMock()
    mod.AutoModel = auto_model_cls
    sys.modules["funasr"] = mod
    return mod


def _remove_mock_funasr():
    sys.modules.pop("funasr", None)


class TestASREngine:
    def test_recognize_returns_text(self, tmp_path):
        mod = _install_mock_funasr()
        try:
            mod.AutoModel.return_value.generate.return_value = [{"text": " 你好世界 "}]

            from funasr_input.asr import ASREngine

            engine = ASREngine(model_name="fake-model", device="cpu")
            wav = tmp_path / "test.wav"
            wav.write_bytes(b"RIFF....WAVEfmt ")  # 占位

            result = engine.recognize(wav)
            assert result == "你好世界"
        finally:
            _remove_mock_funasr()

    def test_recognize_strips_whitespace(self, tmp_path):
        mod = _install_mock_funasr()
        try:
            mod.AutoModel.return_value.generate.return_value = [{"text": "\n  hello world \t"}]

            from funasr_input.asr import ASREngine

            engine = ASREngine(model_name="fake-model", device="cpu")
            wav = tmp_path / "test.wav"
            wav.write_bytes(b"RIFF")

            result = engine.recognize(wav)
            assert result == "hello world"
        finally:
            _remove_mock_funasr()

    def test_recognize_empty_result(self, tmp_path):
        mod = _install_mock_funasr()
        try:
            mod.AutoModel.return_value.generate.return_value = []

            from funasr_input.asr import ASREngine

            engine = ASREngine(model_name="fake-model", device="cpu")
            wav = tmp_path / "test.wav"
            wav.write_bytes(b"RIFF")

            result = engine.recognize(wav)
            assert result == ""
        finally:
            _remove_mock_funasr()

    def test_recognize_string_items(self, tmp_path):
        mod = _install_mock_funasr()
        try:
            mod.AutoModel.return_value.generate.return_value = ["hello", "world"]

            from funasr_input.asr import ASREngine

            engine = ASREngine(model_name="fake-model", device="cpu")
            wav = tmp_path / "test.wav"
            wav.write_bytes(b"RIFF")

            result = engine.recognize(wav)
            assert result == "helloworld"
        finally:
            _remove_mock_funasr()

    def test_recognize_with_timestamp(self, tmp_path):
        mod = _install_mock_funasr()
        try:
            mod.AutoModel.return_value.generate.return_value = [
                {"text": "hello", "start": 0, "end": 0.5},
                {"text": "world", "start": 0.6, "end": 1.0},
            ]

            from funasr_input.asr import ASREngine

            engine = ASREngine(model_name="fake-model", device="cpu")
            wav = tmp_path / "test.wav"
            wav.write_bytes(b"RIFF")

            result = engine.recognize_with_timestamp(wav)
            assert len(result) == 2
            assert result[0]["text"] == "hello"
        finally:
            _remove_mock_funasr()

    def test_is_loaded_initially_false(self):
        # 不注入 mock，直接测试初始状态
        from funasr_input.asr import ASREngine
        engine = ASREngine(model_name="fake", device="cpu")
        assert not engine.is_loaded

    def test_unload(self, tmp_path):
        mod = _install_mock_funasr()
        try:
            mod.AutoModel.return_value.generate.return_value = []

            from funasr_input.asr import ASREngine

            engine = ASREngine(model_name="fake", device="cpu")
            wav = tmp_path / "test.wav"
            wav.write_bytes(b"RIFF")

            engine.recognize(wav)
            assert engine.is_loaded

            engine.unload()
            assert not engine.is_loaded
        finally:
            _remove_mock_funasr()