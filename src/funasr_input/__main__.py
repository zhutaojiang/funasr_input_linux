"""funasr_input 主入口。"""

from __future__ import annotations

import argparse

from funasr_input.ime import VoiceIME


def main() -> None:
    p = argparse.ArgumentParser(description="funasr_input 语音输入法")
    p.add_argument(
        "--asr-preset",
        choices=["nano", "fast"],
        help="识别模型预设 (nano=多语言, fast=中文快)",
    )
    p.add_argument("--model-name", help="ASR 模型名 (覆盖 preset)")
    p.add_argument("--vad-model", help="VAD 模型名 (覆盖 preset)")
    p.add_argument("--device", default="cpu", help="推理设备 (cpu/cuda)")
    p.add_argument("--hotkey", default="win+alt+m", help="录音热键")
    p.add_argument("--quit-hotkey", default="win+alt+x", help="退出热键")
    p.add_argument("--silence-threshold", type=float, default=0.015, help="静音阈值")
    p.add_argument(
        "--silence-duration", type=float, default=1.0, help="静音持续秒数后停止录音"
    )
    p.add_argument("--max-record-sec", type=float, default=30.0, help="最长录音秒数")
    p.add_argument("--char-delay", type=float, default=0.0, help="逐字注入延迟(秒)")
    p.add_argument(
        "--no-polish", action="store_false", dest="polish", help="禁用 LLM 润色"
    )
    p.add_argument(
        "--no-live-preview",
        action="store_false",
        dest="live_preview",
        help="禁用准流式悬浮预览",
    )
    p.add_argument("--live-interval", type=float, default=2.5, help="预览刷新间隔(秒)")
    p.add_argument("--debug", action="store_true", help="DEBUG 日志")
    args = p.parse_args()

    ime = VoiceIME(
        asr_preset=args.asr_preset,
        model_name=args.model_name,
        vad_model=args.vad_model,
        device=args.device,
        hotkey=args.hotkey,
        quit_hotkey=args.quit_hotkey,
        silence_threshold=args.silence_threshold,
        silence_duration_sec=args.silence_duration,
        max_record_sec=args.max_record_sec,
        char_delay=args.char_delay,
        polish=args.polish,
        live_preview=args.live_preview,
        live_interval=args.live_interval,
        debug=args.debug,
    )
    ime.start()


if __name__ == "__main__":
    main()
