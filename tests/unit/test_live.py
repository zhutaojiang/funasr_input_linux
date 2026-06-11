"""LiveTranscriber 单元测试。"""

from __future__ import annotations

import threading

import numpy as np

from funasr_input.live import LiveTranscriber


def test_take_pending_latest_wins():
    lt = LiveTranscriber(recognize=lambda s: "", on_partial=lambda t: None)
    lt.submit(np.zeros(3, dtype="float32"))
    lt.submit(np.ones(5, dtype="float32"))
    pending = lt._take_pending()
    assert pending is not None and len(pending) == 5   # 取到最新一份
    assert lt._take_pending() is None                   # 取走后清空


def test_worker_recognizes_and_calls_on_partial():
    done = threading.Event()
    seen = {}

    def recognize(samples):
        return f"len={len(samples)}"

    def on_partial(text):
        seen["text"] = text
        done.set()

    lt = LiveTranscriber(recognize=recognize, on_partial=on_partial)
    lt.start()
    try:
        lt.submit(np.zeros(7, dtype="float32"))
        assert done.wait(timeout=3.0), "on_partial 应被调用"
        assert seen["text"] == "len=7"
    finally:
        lt.stop()


def test_worker_swallows_recognize_error():
    done = threading.Event()

    def recognize(samples):
        raise RuntimeError("boom")

    lt = LiveTranscriber(
        recognize=recognize, on_partial=lambda t: done.set()
    )
    lt.start()
    try:
        lt.submit(np.zeros(3, dtype="float32"))
        assert not done.wait(timeout=0.5)
    finally:
        lt.stop()
