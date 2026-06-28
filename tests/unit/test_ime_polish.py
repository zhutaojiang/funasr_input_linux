"""VoiceIME 润色接线单元测试。"""

from __future__ import annotations

import time
from pathlib import Path


class _FakeSegment:
    samples = [0]

    def to_wav(self, path):
        return Path(path)

    def duration_sec(self):
        return 0.0


class _FakePolisher:
    def __init__(self, out: str):
        self._out = out
        self.seen = None

    def polish(self, text: str) -> str:
        self.seen = text
        return self._out


def _make_ime(monkeypatch, **kwargs):
    from funasr_input.ime import VoiceIME

    ime = VoiceIME(device="cpu", live_preview=False, on_status=lambda m: None, **kwargs)
    monkeypatch.setattr(ime._recorder, "record", lambda **_kw: _FakeSegment())
    monkeypatch.setattr(ime._asr, "recognize", lambda p: "原始文本")
    written = {}
    monkeypatch.setattr(
        ime._injector, "write", lambda t: written.__setitem__("text", t)
    )
    return ime, written


def test_polish_disabled_injects_raw(monkeypatch):
    ime, written = _make_ime(monkeypatch, polish=False)
    ime._run_pipeline()
    for _ in range(50):
        if "text" in written:
            break
        time.sleep(0.02)
    assert written["text"] == "原始文本"


def test_polish_enabled_injects_polished(monkeypatch):
    polisher = _FakePolisher("润色后文本")
    ime, written = _make_ime(monkeypatch, polish=True, polisher=polisher)
    ime._run_pipeline()
    for _ in range(50):
        if "text" in written:
            break
        time.sleep(0.02)
    assert polisher.seen == "原始文本"
    assert written["text"] == "润色后文本"


def test_polish_enabled_without_polisher_builds_from_config(monkeypatch):
    import json

    import funasr_input.ime as ime_mod
    from funasr_input.polish import OpenAICompatPolisher

    monkeypatch.setattr(
        ime_mod, "load_config", lambda: {"polish": {"model": "cfg-model"}}
    )
    from funasr_input.ime import VoiceIME

    ime = VoiceIME(device="cpu", polish=True, on_status=lambda m: None)
    assert isinstance(ime._polisher, OpenAICompatPolisher)
    _url, data, _headers = ime._polisher._build_request("x")
    assert json.loads(data.decode("utf-8"))["model"] == "cfg-model"
