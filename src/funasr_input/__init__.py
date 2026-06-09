"""funasr_input - 基于 FunASR 的 Windows 语音输入法。"""

from __future__ import annotations

from funasr_input.audio import AudioConfig, AudioRecorder, AudioSegment
from funasr_input.asr import ASREngine
from funasr_input.input import TextInjector
from funasr_input.ime import VoiceIME

__all__ = [
    "AudioConfig",
    "AudioRecorder",
    "AudioSegment",
    "ASREngine",
    "TextInjector",
    "VoiceIME",
]
