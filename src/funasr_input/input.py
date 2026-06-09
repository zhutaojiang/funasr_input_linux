"""Windows 输入注入模块。

使用 SendInput 将文本逐字“敲”进当前焦点窗口，
兼容 CMD / PowerShell / WSL / 各种 GUI 程序。
"""

from __future__ import annotations

import time
from typing import Optional


class TextInjector:
    """通过 Win32 SendInput 注入文本。"""

    def __init__(self, *, char_delay: float = 0.0) -> None:
        """
        Args:
            char_delay: 每个字符之间的延迟（秒），默认 0（最快）。
                        某些老旧终端可能需要设成 0.01 左右。
        """
        self._char_delay = char_delay
        self._user32 = None  # lazy load

    def _get_user32(self):
        if self._user32 is None:
            import ctypes
            self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        return self._user32

    def write(self, text: str) -> None:
        """将文本写入当前焦点窗口。"""
        if not text:
            return

        user32 = self._get_user32()

        for ch in text:
            self._send_char(user32, ch)
            if self._char_delay > 0:
                time.sleep(self._char_delay)

    def press_enter(self) -> None:
        """模拟按下 Enter 键。"""
        user32 = self._get_user32()
        self._send_key(user32, vk=0x0D)  # VK_RETURN

    def press_backspace(self, count: int = 1) -> None:
        """模拟按下退格键。"""
        user32 = self._get_user32()
        for _ in range(count):
            self._send_key(user32, vk=0x08)  # VK_BACK
            time.sleep(0.01)

    # ---- 内部方法 ----

    def _send_char(self, user32, ch: str) -> None:
        """发送单个 Unicode 字符。"""
        # 使用 KEYEVENTF_UNICODE 方式，兼容所有输入法
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002

        user32.keybd_event(0, 0, KEYEVENTF_UNICODE, ord(ch))
        user32.keybd_event(0, 0, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, ord(ch))

    def _send_key(self, user32, vk: int) -> None:
        """发送虚拟键码。"""
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
