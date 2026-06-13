"""Linux 输入注入模块。

支持 X11（xdotool + xclip）和 Wayland（wtype + wl-clipboard）两种后端，
运行时根据 WAYLAND_DISPLAY 环境变量自动选择。

X11 依赖：  xdotool, xclip
Wayland 依赖：wtype, wl-clipboard
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Optional

logger = logging.getLogger("funasr_input")


def _is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


class FocusGuard:
    """记住当前焦点窗口并在需要时恢复（仅 X11 生效；Wayland 下焦点由合成器管理）。"""

    def __init__(self) -> None:
        self._window_id: Optional[str] = None
        self._wayland = _is_wayland()

    def save(self) -> None:
        if self._wayland:
            return
        try:
            r = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=1,
            )
            if r.returncode == 0:
                self._window_id = r.stdout.strip()
        except Exception:
            pass

    def restore(self) -> None:
        if self._wayland or not self._window_id:
            return
        try:
            subprocess.run(
                ["xdotool", "windowfocus", "--sync", self._window_id],
                capture_output=True, timeout=1,
            )
        except Exception:
            pass


class TextInjector:
    """通过剪贴板+模拟粘贴向当前焦点窗口注入文本（支持 X11 和 Wayland）。

    流程：保存剪贴板 → 写入目标文本 → 模拟 Ctrl+V → 恢复剪贴板。
    """

    def __init__(self, *, char_delay: float = 0.0) -> None:
        # char_delay 保留参数接口兼容性，Linux 剪贴板注入不逐字发送
        self._char_delay = char_delay
        self._wayland = _is_wayland()

    def write(self, text: str) -> None:
        """将文本写入当前焦点窗口。"""
        if not text:
            return
        old = self._clipboard_get()
        self._clipboard_set(text.encode("utf-8"))
        time.sleep(0.05)
        self._paste()
        if self._char_delay > 0:
            time.sleep(self._char_delay)
        if old is not None:
            time.sleep(0.1)
            self._clipboard_set(old)

    def press_enter(self) -> None:
        """模拟按下 Enter 键。"""
        if self._wayland:
            self._run(["wtype", "-k", "return"])
        else:
            self._run(["xdotool", "key", "Return"])

    def press_backspace(self, count: int = 1) -> None:
        """模拟按下退格键。"""
        for _ in range(count):
            if self._wayland:
                self._run(["wtype", "-k", "BackSpace"])
            else:
                self._run(["xdotool", "key", "BackSpace"])
            if count > 1:
                time.sleep(0.01)

    # ---- 内部方法 ----

    def _paste(self) -> None:
        if self._wayland:
            self._run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"])
        else:
            self._run(["xdotool", "key", "--clearmodifiers", "ctrl+v"])

    def _clipboard_get(self) -> Optional[bytes]:
        try:
            if self._wayland:
                r = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True, timeout=1,
                )
            else:
                r = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, timeout=1,
                )
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None

    def _clipboard_set(self, data: bytes) -> None:
        try:
            if self._wayland:
                subprocess.run(
                    ["wl-copy"], input=data, capture_output=True, timeout=1,
                )
            else:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=data, capture_output=True, timeout=1,
                )
        except Exception:
            pass

    @staticmethod
    def _run(cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, capture_output=True, timeout=2)
        except Exception:
            pass
