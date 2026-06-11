"""Windows 输入注入模块。

使用 Win32 ``SendInput`` 将文本逐字“敲”进当前焦点窗口，
通过 ``KEYEVENTF_UNICODE`` 直接发送 Unicode 码点，兼容中文等任意字符，
不依赖系统当前输入法/键盘布局，适用于 CMD / PowerShell / WSL / 各种 GUI 程序。
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

logger = logging.getLogger("funasr_input")

# ---- Win32 常量 ----
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

VK_RETURN = 0x0D
VK_BACK = 0x08

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    # 仅用于让联合体大小正确（SendInput 的 cbSize 需匹配 INPUT 实际尺寸）。
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


class FocusGuard:
    """记住当前前台窗口并在需要时恢复焦点。

    热键触发后某些应用会弹出菜单导致焦点丢失，录音前调用 restore()
    强制把焦点切回之前的文本框，确保后续 SendInput 注入到正确窗口。
    """

    def __init__(self) -> None:
        self._hwnd: int = 0
        self._user32 = None

    def _get_user32(self):
        if self._user32 is None:
            import ctypes as _ctypes

            self._user32 = _ctypes.windll.user32  # type: ignore[attr-defined]
        return self._user32

    def save(self) -> None:
        try:
            self._hwnd = self._get_user32().GetForegroundWindow()
        except Exception:
            pass

    def restore(self) -> None:
        if not self._hwnd:
            return
        try:
            self._get_user32().SetForegroundWindow(self._hwnd)
        except Exception:
            pass


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
            # 局部导入：尊重测试时对 sys.modules["ctypes"] 的替换，
            # 避免单测/集成测试误触发真实的 Windows 按键注入。
            import ctypes as _ctypes

            self._user32 = _ctypes.windll.user32  # type: ignore[attr-defined]
        return self._user32

    # ---- 公共接口 ----

    def write(self, text: str) -> None:
        """将文本写入当前焦点窗口。"""
        if not text:
            return

        for ch in text:
            down, up = self._build_unicode_inputs(ch)
            self._send([down, up])
            if self._char_delay > 0:
                time.sleep(self._char_delay)

    def press_enter(self) -> None:
        """模拟按下 Enter 键。"""
        down, up = self._build_vk_inputs(VK_RETURN)
        self._send([down, up])

    def press_backspace(self, count: int = 1) -> None:
        """模拟按下退格键。"""
        for _ in range(count):
            down, up = self._build_vk_inputs(VK_BACK)
            self._send([down, up])
            time.sleep(0.01)

    # ---- 内部方法 ----

    def _build_unicode_inputs(self, ch: str) -> tuple[INPUT, INPUT]:
        """构造单个 Unicode 字符的按下/释放事件。

        码点写入 ``wScan``、``wVk`` 置 0，配合 ``KEYEVENTF_UNICODE``，
        这样系统直接注入字符而不经过键盘布局映射。
        """
        code = ord(ch)
        down = self._make_kbd_input(w_vk=0, w_scan=code, flags=KEYEVENTF_UNICODE)
        up = self._make_kbd_input(
            w_vk=0, w_scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        )
        return down, up

    def _build_vk_inputs(self, vk: int) -> tuple[INPUT, INPUT]:
        """构造单个虚拟键的按下/释放事件。"""
        down = self._make_kbd_input(w_vk=vk, w_scan=0, flags=0)
        up = self._make_kbd_input(w_vk=vk, w_scan=0, flags=KEYEVENTF_KEYUP)
        return down, up

    @staticmethod
    def _make_kbd_input(*, w_vk: int, w_scan: int, flags: int) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki = KEYBDINPUT(
            wVk=w_vk,
            wScan=w_scan,
            dwFlags=flags,
            time=0,
            dwExtraInfo=None,
        )
        return inp

    def _send(self, inputs: list[INPUT]) -> None:
        """提交一批 INPUT 事件到 SendInput。"""
        user32 = self._get_user32()
        n = len(inputs)
        array = (INPUT * n)(*inputs)
        user32.SendInput(n, array, ctypes.sizeof(INPUT))
