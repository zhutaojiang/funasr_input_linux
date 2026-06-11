"""AudioRecorder 增长窗口回调测试。"""

from __future__ import annotations

import types

import numpy as np

from funasr_input.audio import AudioConfig, AudioRecorder


def _fake_sd():
    class FakeStream:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return types.SimpleNamespace(InputStream=FakeStream)


def test_record_ignores_leading_silence(monkeypatch):
    # 开头的静音不应触发停录；要等说话开始后、再用静音判断结束。
    from funasr_input import audio as audio_mod

    monkeypatch.setattr(audio_mod, "_load_sounddevice", _fake_sd)

    cfg = AudioConfig(sample_rate=100)
    rec = AudioRecorder(
        cfg, silence_threshold=0.01, silence_duration_sec=0.5, max_record_sec=10
    )
    silent = np.zeros(10, dtype="float32")
    loud = np.ones(10, dtype="float32") * 0.5
    # 前导静音 100 帧（> silence_frames=50），随后语音，再尾部静音
    for c in [silent] * 10 + [loud] * 3 + [silent] * 7:
        rec._q.put(c)

    seg = rec.record()
    # 应录到语音（峰值 >= 0.5），而不是在前导静音处就停掉
    assert float(np.max(np.abs(seg.samples))) >= 0.5


def test_record_fires_on_window_growing(monkeypatch):
    from funasr_input import audio as audio_mod

    monkeypatch.setattr(audio_mod, "_load_sounddevice", _fake_sd)

    cfg = AudioConfig(sample_rate=100)  # 小采样率方便算帧
    rec = AudioRecorder(
        cfg, silence_threshold=0.01, silence_duration_sec=0.5, max_record_sec=10
    )
    loud = np.ones(10, dtype="float32") * 0.5   # 音量 0.5 > 阈值
    silent = np.zeros(10, dtype="float32")       # 音量 0 < 阈值
    # 静音需累计 silence_frames=int(0.5*100)=50 帧才停止
    for c in [loud] * 3 + [silent] * 7:
        rec._q.put(c)

    sizes = []
    rec.record(on_window=lambda s: sizes.append(len(s)), window_interval=0.1)

    assert sizes, "应至少触发一次窗口回调"
    assert sizes == sorted(sizes), "窗口应随累积音频增长"
    assert sizes[0] == 10
