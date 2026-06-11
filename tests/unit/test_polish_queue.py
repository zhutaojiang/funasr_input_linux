"""_PolishQueue 保序测试。"""

from __future__ import annotations

import time

from funasr_input.ime import _PolishQueue


class _SlowPolisher:
    def __init__(self, delays: dict[str, float]):
        self._delays = delays
        self.results: list[str] = []

    def polish(self, text: str) -> str:
        if text in self._delays:
            time.sleep(self._delays[text])
        self.results.append(text)
        return f"润色:{text}"


class _FakeInjector:
    def __init__(self):
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)


def test_sequential_order():
    injector = _FakeInjector()
    polisher = _SlowPolisher({"A": 0.05, "B": 0.0})
    q = _PolishQueue(
        polisher=polisher,
        injector=injector,
    )
    q.submit("A")
    q.submit("B")
    for _ in range(100):
        if len(injector.written) >= 2:
            break
        time.sleep(0.01)
    q.stop()
    assert injector.written == ["润色:A", "润色:B"]


def test_no_polisher_passes_through():
    injector = _FakeInjector()
    q = _PolishQueue(
        polisher=None,
        injector=injector,
    )
    q.submit("原始")
    for _ in range(50):
        if injector.written:
            break
        time.sleep(0.01)
    q.stop()
    assert injector.written == ["原始"]
