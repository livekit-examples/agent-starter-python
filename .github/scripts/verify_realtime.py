import re
import sys
from pathlib import Path


def main() -> int:
    p = Path("src/agent.py")
    if not p.exists():
        print("FAIL: src/agent.py neexistuje", file=sys.stderr)
        return 1

    code = p.read_text(encoding="utf-8")

    # 1) zakázané importy (starý pipeline)
    forbidden = [
        r"\blivekit\.plugins\.cartesia\b",
        r"\blivekit\.plugins\.deepgram\b",
        r"\blivekit\.plugins\.silero\b",
        r"\blivekit\.plugins\.turn_detector\b",
        r"\bMultilingualModel\b",
    ]
    bad = [pat for pat in forbidden if re.search(pat, code)]
    if bad:
        print("FAIL: zakázané importy/objekty:", ", ".join(bad), file=sys.stderr)
        return 2

    # 2) musí existovať RealtimeModel s gpt-4o-realtime-preview
    if not re.search(r"realtime\.RealtimeModel\s*\(", code):
        print(
            "FAIL: nenašiel som openai.realtime.RealtimeModel v agent.py",
            file=sys.stderr,
        )
        return 3

    if not re.search(r'model\s*=\s*["\']gpt-4o-realtime-preview["\']', code):
        print("FAIL: model nie je 'gpt-4o-realtime-preview'", file=sys.stderr)
        return 4

    # 3) INFO log po štarte
    if not re.search(r'logger\.info\(\s*["\']Realtime session started["\']\s*\)', code):
        print('FAIL: chýba INFO log "Realtime session started"', file=sys.stderr)
        return 5

    # 4) voliteľná BVC podľa ENABLE_BVC
    if "ENABLE_BVC" not in code or "noise_cancellation.BVC()" not in code:
        print(
            "FAIL: chýba prepínač ENABLE_BVC alebo BVC vo RoomInputOptions",
            file=sys.stderr,
        )
        return 6

    # 5) backoff v __main__
    if "AGENT_MAX_RETRIES" not in code or "AGENT_BACKOFF_BASE" not in code:
        print(
            "FAIL: chýba backoff konfigurácia (AGENT_MAX_RETRIES/AGENT_BACKOFF_BASE)",
            file=sys.stderr,
        )
        return 7

    print("OK: realtime a základné požiadavky sú splnené")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

