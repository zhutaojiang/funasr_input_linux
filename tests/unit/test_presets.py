"""识别预设解析与 VoiceIME 接线测试。"""

from __future__ import annotations

import pytest

from funasr_input.presets import ASR_PRESETS, resolve_preset


def test_default_preset_is_nano():
    assert resolve_preset(None)["model"] == ASR_PRESETS["nano"]["model"]


def test_fast_preset_is_paraformer():
    assert resolve_preset("fast")["model"] == "paraformer-zh"


def test_preset_name_case_insensitive():
    assert resolve_preset("FAST")["model"] == "paraformer-zh"


def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        resolve_preset("nope")


def test_voiceime_uses_preset_model():
    from funasr_input.ime import VoiceIME

    ime = VoiceIME(asr_preset="fast", device="cpu", on_status=lambda m: None)
    assert ime._asr._model_name == "paraformer-zh"


def test_voiceime_explicit_model_overrides_preset():
    from funasr_input.ime import VoiceIME

    ime = VoiceIME(
        asr_preset="fast",
        model_name="some/other-model",
        device="cpu",
        on_status=lambda m: None,
    )
    assert ime._asr._model_name == "some/other-model"
