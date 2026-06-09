"""funasr_input 主入口。"""

from __future__ import annotations

from funasr_input.ime import VoiceIME


def main() -> None:
    ime = VoiceIME(device="cpu")
    ime.start()


if __name__ == "__main__":
    main()
