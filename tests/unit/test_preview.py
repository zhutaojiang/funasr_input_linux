"""PreviewWindow 和 PreviewLogHandler 单元测试。"""

from __future__ import annotations

import logging


def test_preview_log_handler_emits():
    from funasr_input.preview import PreviewLogHandler

    class _FakePreview:
        def __init__(self):
            self.logs = []

        def append_log(self, line):
            self.logs.append(line)

    preview = _FakePreview()
    handler = PreviewLogHandler(preview)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
    assert preview.logs == ["hello"]


def test_preview_log_handler_ignores_exception():
    from funasr_input.preview import PreviewLogHandler

    class _BrokenPreview:
        def append_log(self, line):
            raise RuntimeError("boom")

    handler = PreviewLogHandler(_BrokenPreview())
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
