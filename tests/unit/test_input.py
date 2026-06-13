"""输入注入模块单元测试（Linux 实现）。

通过 Mock subprocess.run 验证 xdotool / xclip（X11）
或 wtype / wl-clipboard（Wayland）调用是否正确。
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, call, patch

import pytest

from funasr_input.input import FocusGuard, TextInjector, _is_wayland


# ---- 辅助 ----

def _make_completed(returncode: int = 0, stdout=b"") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


# ---- _is_wayland ----

class TestIsWayland:
    def test_wayland_when_env_set(self, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        assert _is_wayland() is True

    def test_x11_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        assert _is_wayland() is False


# ---- FocusGuard ----

class TestFocusGuardX11:
    @pytest.fixture(autouse=True)
    def force_x11(self, monkeypatch):
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    def test_save_calls_xdotool(self):
        guard = FocusGuard()
        # text=True → subprocess returns str stdout
        with patch("funasr_input.input.subprocess.run", return_value=_make_completed(stdout="12345\n")) as mock_run:
            guard.save()
        mock_run.assert_called_once()
        assert "xdotool" in mock_run.call_args.args[0]
        assert guard._window_id == "12345"

    def test_restore_calls_xdotool(self):
        guard = FocusGuard()
        guard._window_id = "99999"
        with patch("funasr_input.input.subprocess.run", return_value=_make_completed()) as mock_run:
            guard.restore()
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert "xdotool" in cmd and "windowfocus" in cmd

    def test_restore_skips_when_no_window(self):
        guard = FocusGuard()
        with patch("funasr_input.input.subprocess.run") as mock_run:
            guard.restore()
        mock_run.assert_not_called()


class TestFocusGuardWayland:
    @pytest.fixture(autouse=True)
    def force_wayland(self, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    def test_save_is_noop(self):
        guard = FocusGuard()
        with patch("funasr_input.input.subprocess.run") as mock_run:
            guard.save()
        mock_run.assert_not_called()

    def test_restore_is_noop(self):
        guard = FocusGuard()
        guard._window_id = "99999"
        with patch("funasr_input.input.subprocess.run") as mock_run:
            guard.restore()
        mock_run.assert_not_called()


# ---- TextInjector ----

class TestTextInjectorX11:
    @pytest.fixture(autouse=True)
    def force_x11(self, monkeypatch):
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    def test_write_empty_sends_nothing(self):
        inj = TextInjector()
        with patch("funasr_input.input.subprocess.run") as mock_run:
            inj.write("")
        mock_run.assert_not_called()

    def test_write_sets_clipboard_and_pastes(self):
        inj = TextInjector()
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            # xclip -o 返回旧内容
            if "-o" in cmd:
                return _make_completed(stdout=b"old")
            return _make_completed()

        with patch("funasr_input.input.subprocess.run", side_effect=fake_run):
            inj.write("你好")

        # 顺序：get_clipboard → set_text → paste → restore_clipboard
        assert any("xclip" in " ".join(c) and "-o" in c for c in calls), "应先读取剪贴板"
        set_calls = [c for c in calls if "xclip" in " ".join(c) and "-o" not in c]
        assert len(set_calls) >= 1, "应至少调用一次 xclip 写入"
        paste_calls = [c for c in calls if "xdotool" in " ".join(c) and "ctrl+v" in " ".join(c)]
        assert len(paste_calls) == 1, "应调用一次 xdotool 粘贴"

    def test_write_with_no_old_clipboard(self):
        inj = TextInjector()
        def fake_run(cmd, **kwargs):
            if "-o" in cmd:
                return _make_completed(returncode=1, stdout=b"")
            return _make_completed()

        with patch("funasr_input.input.subprocess.run", side_effect=fake_run):
            inj.write("test")  # 不应抛出异常

    def test_press_enter_uses_xdotool(self):
        inj = TextInjector()
        with patch("funasr_input.input.subprocess.run", return_value=_make_completed()) as mock_run:
            inj.press_enter()
        cmd = mock_run.call_args.args[0]
        assert "xdotool" in cmd and "Return" in cmd

    def test_press_backspace_calls_correct_times(self):
        inj = TextInjector()
        with patch("funasr_input.input.subprocess.run", return_value=_make_completed()) as mock_run:
            inj.press_backspace(3)
        assert mock_run.call_count == 3


class TestTextInjectorWayland:
    @pytest.fixture(autouse=True)
    def force_wayland(self, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    def test_write_uses_wl_copy(self):
        inj = TextInjector()
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _make_completed()

        with patch("funasr_input.input.subprocess.run", side_effect=fake_run):
            inj.write("你好")

        set_calls = [c for c in calls if "wl-copy" in " ".join(c)]
        assert len(set_calls) >= 1

    def test_press_enter_uses_wtype(self):
        inj = TextInjector()
        with patch("funasr_input.input.subprocess.run", return_value=_make_completed()) as mock_run:
            inj.press_enter()
        cmd = mock_run.call_args.args[0]
        assert "wtype" in cmd

    def test_press_backspace_uses_wtype(self):
        inj = TextInjector()
        with patch("funasr_input.input.subprocess.run", return_value=_make_completed()) as mock_run:
            inj.press_backspace(2)
        assert mock_run.call_count == 2
        cmd = mock_run.call_args_list[0].args[0]
        assert "wtype" in cmd
