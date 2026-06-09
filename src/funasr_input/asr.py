"""ASR 引擎封装。

封装 FunASR 的加载、识别调用，屏蔽模型版本差异，
并暴露统一的 ``recognize(wav_path) -> str`` 接口。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Union


class ASREngine:
    """FunASR 引擎封装。

    初始化时加载一次模型，后续 ``recognize`` 复用同一个实例，
    避免反复下载/重建图。
    """

    def __init__(
        self,
        model_name: str = "FunAudioLLM/Fun-ASR-Nano-2512",
        vad_model: str = "fsmn-vad",
        device: str = "cpu",
        *,
        punc_model: str = "ct-punc",
        spk_model: Optional[str] = None,
    ) -> None:
        self._model_name = model_name
        self._vad_model = vad_model
        self._device = device
        self._punc_model = punc_model
        self._spk_model = spk_model
        self._model = None  # lazy load

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "未安装 funasr，请执行: pip install funasr"
            ) from exc

        kwargs = {
            "model": self._model_name,
            "vad_model": self._vad_model,
            "punc_model": self._punc_model,
            "device": self._device,
        }
        if self._spk_model:
            kwargs["spk_model"] = self._spk_model

        self._model = AutoModel(**kwargs)

    def recognize(self, wav_path: Union[str, Path]) -> str:
        """识别一段 WAV，返回纯文本。"""
        self._load()
        path = str(wav_path)
        result = self._model.generate(input=path)

        if not result or not isinstance(result, list):
            return ""

        # FunASR 返回格式: [{"text": "..."}]
        texts: list[str] = []
        for item in result:
            if isinstance(item, dict):
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)

        return "".join(texts).strip()

    def recognize_with_timestamp(self, wav_path: Union[str, Path]) -> list[dict]:
        """返回带时间戳的结构化结果（如果模型支持）。"""
        self._load()
        path = str(wav_path)
        result = self._model.generate(input=path)

        if not result or not isinstance(result, list):
            return []

        structured: list[dict] = []
        for item in result:
            if isinstance(item, dict):
                structured.append(item)
            else:
                structured.append({"text": str(item)})

        return structured

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def unload(self) -> None:
        """卸载模型，释放 GPU 显存。"""
        self._model = None
