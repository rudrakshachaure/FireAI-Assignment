"""Timestamp log for Task 5. python -m project_a.changes_fy2526.stopwatch start|stop impl_a [note]"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

LOG = Path(__file__).parent / "LOG.md"


def main() -> None:
    event, impl, note = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])
    new = not LOG.exists()
    with open(LOG, "a", encoding="utf-8") as f:
        if new:
            f.write("# FY 2025-26 change log\n\n| time (UTC) | event | impl | note (files touched / lines changed) |\n|---|---|---|---|\n")
        f.write(f"| {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} | {event} | {impl} | {note} |\n")
    print("logged")


if __name__ == "__main__":
    main()
