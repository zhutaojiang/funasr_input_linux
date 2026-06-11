"""输入注入模块单元测试。

注入是这个项目的核心功能，过去的实现把 Unicode 码点放进了 keybd_event 的
dwExtraInfo 参数（而非 wScan），实际上敲不出任何字符。这里的测试直接校验
SendInput 收到的 INPUT 结构体内容，确保码点落在正确的字段上。
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from funasr_input.input import (
    TextInjector,
    INPUT_KEYBOARD,
    KEYEVENTF_UNICODE,
    KEYEVENTF_KEYUP,
    VK_RETURN,
    VK_BACK,
)


class TestBuildUnicodeInputs:
    """构造 Unicode 字符的 INPUT 事件——回归测试，覆盖历史 bug。"""

    def test_scan_code_lands_in_wscan_not_extrainfo(self):
        inj = TextInjector()
        down, up = inj._build_unicode_inputs("a")

        assert down.type == INPUT_KEYBOARD
        # 关键：码点必须在 wScan，而不是 wVk / dwExtraInfo
        assert down.ki.wVk == 0
        assert down.ki.wScan == ord("a")
        assert down.ki.dwFlags == KEYEVENTF_UNICODE

        assert up.ki.wScan == ord("a")
        assert up.ki.dwFlags == KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

    def test_chinese_char(self):
        inj = TextInjector()
        down, up = inj._build_unicode_inputs("中")
        assert down.ki.wScan == ord("中") == 0x4E2D
        assert up.ki.wScan == ord("中")


class TestBuildVkInputs:
    """构造虚拟键（回车/退格）的 INPUT 事件。"""

    def test_vk_in_wvk(self):
        inj = TextInjector()
        down, up = inj._build_vk_inputs(VK_RETURN)
        assert down.ki.wVk == VK_RETURN
        assert down.ki.dwFlags == 0
        assert up.ki.wVk == VK_RETURN
        assert up.ki.dwFlags == KEYEVENTF_KEYUP


class TestTextInjector:
    def _patch_user32(self, inj):
        fake = MagicMock()
        inj._get_user32 = lambda: fake  # type: ignore[method-assign]
        return fake

    def test_write_empty_sends_nothing(self):
        inj = TextInjector()
        fake = self._patch_user32(inj)
        inj.write("")
        fake.SendInput.assert_not_called()

    def test_write_calls_sendinput_per_char(self):
        inj = TextInjector(char_delay=0.0)
        fake = self._patch_user32(inj)
        inj.write("ab")
        # 每个字符一次 SendInput 调用，每次提交 2 个事件（按下+释放）
        assert fake.SendInput.call_count == 2
        n_inputs = fake.SendInput.call_args_list[0].args[0]
        assert n_inputs == 2

    def test_press_enter(self):
        inj = TextInjector()
        fake = self._patch_user32(inj)
        inj.press_enter()
        assert fake.SendInput.call_count == 1

    def test_press_backspace(self):
        inj = TextInjector()
        fake = self._patch_user32(inj)
        inj.press_backspace(3)
        assert fake.SendInput.call_count == 3

    def test_char_delay(self):
        inj = TextInjector(char_delay=0.05)
        self._patch_user32(inj)
        t0 = time.time()
        inj.write("xy")
        elapsed = time.time() - t0
        # 2 个字符，每个延迟 0.05s，至少应该有 ~0.1s
        assert elapsed >= 0.09
