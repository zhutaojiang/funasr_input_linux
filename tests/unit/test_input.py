"""输入注入模块单元测试。"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


def _install_mock_ctypes():
    """在 sys.modules 里安装假的 ctypes，覆盖任何已存在的真实模块。"""
    fake_ctypes = types.ModuleType("ctypes")
    fake_windll = MagicMock()
    fake_ctypes.windll = fake_windll  # type: ignore[attr-defined]
    fake_user32 = MagicMock()
    fake_windll.user32 = fake_user32  # type: ignore[attr-defined]
    sys.modules["ctypes"] = fake_ctypes
    return fake_user32


def _remove_mock_ctypes():
    sys.modules.pop("ctypes", None)


class TestTextInjector:
    def test_write_empty(self):
        fake_user32 = _install_mock_ctypes()
        try:
            from funasr_input.input import TextInjector
            injector = TextInjector()
            injector.write("")  # 不应抛异常
            fake_user32.keybd_event.assert_not_called()
        finally:
            _remove_mock_ctypes()

    def test_write_sends_keybd_event(self):
        fake_user32 = _install_mock_ctypes()
        try:
            from funasr_input.input import TextInjector
            injector = TextInjector(char_delay=0.0)
            injector.write("ab")
            assert fake_user32.keybd_event.call_count == 4  # 按下+释放 x 2
        finally:
            _remove_mock_ctypes()

    def test_press_enter(self):
        fake_user32 = _install_mock_ctypes()
        try:
            from funasr_input.input import TextInjector
            injector = TextInjector()
            injector.press_enter()
            assert fake_user32.keybd_event.call_count == 2
        finally:
            _remove_mock_ctypes()

    def test_press_backspace(self):
        fake_user32 = _install_mock_ctypes()
        try:
            from funasr_input.input import TextInjector
            injector = TextInjector()
            injector.press_backspace(3)
            assert fake_user32.keybd_event.call_count == 6  # 3 x (按下+释放)
        finally:
            _remove_mock_ctypes()

    def test_char_delay(self):
        import time

        fake_user32 = _install_mock_ctypes()
        try:
            from funasr_input.input import TextInjector
            injector = TextInjector(char_delay=0.05)
            t0 = time.time()
            injector.write("xy")
            elapsed = time.time() - t0
            # 2 个字符，每个延迟 0.05s，至少应该有 0.1s
            assert elapsed >= 0.09
        finally:
            _remove_mock_ctypes()
