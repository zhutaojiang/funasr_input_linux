"""识别模型预设：在「多语言/质量」与「速度」之间二选一。

每个预设描述一套 ASR 配置（模型 + VAD + 标点）。后续的配置对话框
可直接读这里的 ASR_PRESETS 列出可选项、写回 config.toml 的 [asr].preset。
"""

from __future__ import annotations

from typing import Optional

# 预设名 -> 配置。label/desc 供 UI 展示；其余字段透传给 ASREngine。
ASR_PRESETS: dict[str, dict] = {
    "nano": {
        "model": "FunAudioLLM/Fun-ASR-Nano-2512",
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
        "label": "Fun-ASR-Nano（多语言）",
        "desc": "多语言 50+、中英混说强、质量高；自回归逐字生成，CPU 上慢、内存大。",
    },
    "fast": {
        "model": "paraformer-zh",
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
        "label": "Paraformer（中文·快）",
        "desc": "中文为主、非自回归一次出整句，CPU 上通常快数倍、内存更省；多语言弱。",
    },
}

DEFAULT_PRESET = "nano"


def resolve_preset(name: Optional[str]) -> dict:
    """把预设名解析成配置 dict；name 为空时用 DEFAULT_PRESET。"""
    key = (name or DEFAULT_PRESET).lower()
    if key not in ASR_PRESETS:
        raise ValueError(
            f"未知识别预设: {name!r}，可选: {list(ASR_PRESETS)}"
        )
    return ASR_PRESETS[key]
