"""输入注入模块单元测试。"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_ctypes():
    """Mock ctypes.windll，避免在 Linux 测试环境崩溃。"""
    fake_ctypes = types.ModuleType("ctypes")
    fake_windll = MagicMock()
    fake_ctypes.windll = fake_windll  # type: ignore[attr-defined]
    fake_user32 = MagicMock()
    fake_windll.user32 = fake_user32  # type: ignore[attr-defined]
    sys.modules.setdefault("ctypes", fake_ctypes)
    return fake_user32


class TestTextInjector:
    def test_write_empty(self, mock_ctypes):
        from funasr_input.input import TextInjector
        injector = TextInjector()
        injector.write("")  # 不应抛异常
        mock_ctypes.keybd_event.assert_not_called()

    def test_write_sends_keybd_event(self, mock_ctypes):
        from funasr_input.input import TextInjector
        injector = TextInjector(char_delay=0.0)
        injector.write("ab")
        assert mock_ctypes.keybd_event.call_count == 4  # 按下+释放 x 2

    def test_press_enter(self, mock_ctypes):
        from funasr_input.input import TextInjector
        injector = TextInjector()
        injector.press_enter()
        assert mock_ctypes.keybd_event.call_count == 2

    def test_press_backspace(self, mock_ctypes):
        from funasr_input.input import TextInjector
        injector = TextInjector()
        injector.press_backspace(3)
        assert mock_ctypes.keybd_event.call_count == 6  # 3 x (按下+释放)

    def test_char_delay(self, mock_ctypes):
        from funasr_input.input import TextInjector
        import time

        injector = TextInjector(char_delay=0.05)
        t0 = time.time()
        injector.write("xy")
        elapsed = time.time() - t0
        # 2 个字符，每个延迟 0.05s，至少应该有 0.1s
        assert elapsed >= 0.09
