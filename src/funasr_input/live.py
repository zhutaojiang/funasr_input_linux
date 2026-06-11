"""准流式识别调度：后台线程对最新音频快照做识别，刷新预览。"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger("funasr_input")


class LiveTranscriber:
    """把 submit() 的最新音频快照识别成粗文本，回调 on_partial。

    「最新优先」：识别耗时期间若有新快照，只保留最后一份，丢弃过期的，
    避免在 CPU 上排队堆积。
    """

    def __init__(
        self,
        recognize: Callable[[np.ndarray], str],
        on_partial: Callable[[str], None],
    ) -> None:
        self._recognize = recognize
        self._on_partial = on_partial
        self._pending: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, samples: np.ndarray) -> None:
        with self._lock:
            self._pending = samples
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _take_pending(self) -> Optional[np.ndarray]:
        with self._lock:
            samples = self._pending
            self._pending = None
            return samples

    def _run(self) -> None:
        logger.info("LiveTranscriber 工作线程启动")
        while not self._stop.is_set():
            self._wake.wait(timeout=0.1)
            self._wake.clear()
            samples = self._take_pending()
            if samples is None:
                continue
            try:
                text = self._recognize(samples)
            except Exception:
                logger.exception("LiveTranscriber 识别失败，跳过本次")
                continue  # 识别失败仅跳过本次，不影响后续
            if text:
                self._on_partial(text)
        logger.info("LiveTranscriber 工作线程退出")
