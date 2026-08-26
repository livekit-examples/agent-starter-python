"""Report content-free Hermes latency observations from JSON snapshots."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_observations(paths: list[Path]) -> dict[str, list[int]]:
    observations: dict[str, list[int]] = defaultdict(list)
    for path in paths:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("latency snapshot must be an object")
        for name, value in payload.items():
            if (
                isinstance(name, str)
                and name.endswith("_ms")
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            ):
                observations[name].append(value)
    return observations


def report(observations: dict[str, list[int]]) -> list[str]:
    lines: list[str] = []
    for name, values in sorted(observations.items()):
        lines.append(
            f"{name}: median={statistics.median(values):g}ms "
            f"observed={min(values)}-{max(values)}ms n={len(values)}"
        )
    if observations:
        largest_name, largest_values = max(
            observations.items(), key=lambda item: statistics.median(item[1])
        )
        lines.append(
            f"largest_median_stage={largest_name} "
            f"median_ms={statistics.median(largest_values):g}"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("logs/realtime-latency-latest.json")],
    )
    args = parser.parse_args()
    try:
        observations = load_observations(args.paths)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"LATENCY_REPORT_ERROR={type(exc).__name__}")
        return 1
    if not observations:
        print("LATENCY_REPORT_ERROR=no_observations")
        return 1
    for line in report(observations):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
