"""悬浮预览窗（tkinter）。

主线程创建并运行事件循环；工作线程通过 after() 线程安全地刷新文字。
支持两种模式：
- 日志模式（boot）：多行滚动显示启动日志，窗口较高
- 正常模式：单行状态/识别文字，窗口紧凑
"""

from __future__ import annotations

import logging
import threading
from typing import Optional


class PreviewWindow:
    """置顶、无边框的小条，显示当前识别/状态文字。"""

    _MAX_LOG_LINES = 12

    def __init__(self, *, opacity: float = 0.85, idle_text: str = "") -> None:
        import tkinter as tk

        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        try:
            self._root.attributes("-alpha", opacity)
        except Exception:
            pass
        self._root.configure(bg="#222222")

        self._idle_text = idle_text
        self._revert_id = None
        self._drag_offset: Optional[tuple[int, int]] = None
        self._user_moved = False
        self._boot_mode = True
        self._log_lines: list[str] = []
        self._log_lock = threading.Lock()

        self._var = tk.StringVar(value="")
        self._label = tk.Label(
            self._root,
            textvariable=self._var,
            fg="#eeeeee",
            bg="#222222",
            font=("Noto Sans CJK SC", 12),
            padx=16,
            pady=8,
            justify="left",
            wraplength=600,
        )
        self._label.pack()
        self._bind_drag()
        self._position_bottom_center()

    def _bind_drag(self) -> None:
        self._label.bind("<ButtonPress-1>", self._on_drag_start)
        self._label.bind("<B1-Motion>", self._on_drag_move)
        self._label.bind("<ButtonRelease-1>", self._on_drag_end)
        self._root.bind("<ButtonPress-1>", self._on_drag_start)
        self._root.bind("<B1-Motion>", self._on_drag_move)
        self._root.bind("<ButtonRelease-1>", self._on_drag_end)

    def _on_drag_start(self, event) -> None:
        self._drag_offset = (
            event.x_root - self._root.winfo_x(),
            event.y_root - self._root.winfo_y(),
        )

    def _on_drag_move(self, event) -> None:
        if self._drag_offset is None:
            return
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self._root.geometry(f"+{x}+{y}")
        self._user_moved = True

    def _on_drag_end(self, _event) -> None:
        self._drag_offset = None

    def _position_bottom_center(self) -> None:
        if self._user_moved:
            return
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        x = (sw - w) // 2
        y = sh - h - 80
        self._root.geometry(f"+{x}+{y}")

    def append_log(self, line: str) -> None:
        """线程安全地追加一行启动日志（仅 boot 模式生效）。"""
        self._root.after(0, self._apply_log, line)

    def _apply_log(self, line: str) -> None:
        if not self._boot_mode:
            return
        with self._log_lock:
            self._log_lines.append(line)
            if len(self._log_lines) > self._MAX_LOG_LINES:
                self._log_lines = self._log_lines[-self._MAX_LOG_LINES :]
        self._var.set("\n".join(self._log_lines))
        self._position_bottom_center()

    def exit_boot(self) -> None:
        """退出日志模式，切换到正常单行模式。"""
        self._root.after(0, self._apply_exit_boot)

    def _apply_exit_boot(self) -> None:
        self._boot_mode = False
        with self._log_lock:
            self._log_lines.clear()
        self._cancel_revert()
        self._var.set(self._idle_text)
        self._label.configure(font=("Noto Sans CJK SC", 14))
        self._position_bottom_center()

    def show(self, text: str) -> None:
        """线程安全地更新显示文字（可从任意线程调用）。"""
        self._root.after(0, self._apply, text)

    def flash(self, text: str, hold_sec: float = 4.0) -> None:
        """显示 text，hold_sec 秒后自动回到待命文字（线程安全）。"""
        self._root.after(0, self._apply_flash, text, hold_sec)

    def show_idle(self) -> None:
        """立即回到待命文字。"""
        self.show(self._idle_text)

    def _apply(self, text: str) -> None:
        self._cancel_revert()
        self._var.set(text)
        self._position_bottom_center()

    def _apply_flash(self, text: str, hold_sec: float) -> None:
        self._cancel_revert()
        self._var.set(text)
        self._position_bottom_center()
        self._revert_id = self._root.after(int(hold_sec * 1000), self._to_idle)

    def _to_idle(self) -> None:
        self._revert_id = None
        self._var.set(self._idle_text)
        self._position_bottom_center()

    def _cancel_revert(self) -> None:
        if self._revert_id is not None:
            try:
                self._root.after_cancel(self._revert_id)
            except Exception:
                pass
            self._revert_id = None

    def run(self) -> None:
        """在主线程运行事件循环，直到 close()。"""
        self._root.mainloop()

    def close(self, *, delay_sec: float = 0.0) -> None:
        """线程安全地关闭窗口、退出事件循环。可延迟关闭。"""
        try:
            self._root.after(int(delay_sec * 1000), self._root.quit)
        except Exception:
            pass


class PreviewLogHandler(logging.Handler):
    """将 logging 记录推送到 PreviewWindow 的日志区域。"""

    def __init__(self, preview: PreviewWindow) -> None:
        super().__init__()
        self._preview = preview

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._preview.append_log(msg)
        except Exception:
            pass
