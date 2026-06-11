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
