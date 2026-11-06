"""Check clause registry vs files. `--strict` fails while any excerpt is still a
paraphrase / has TODO-VERIFY (use before submitting)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).parent


def main(strict: bool) -> int:
    reg = json.loads((BASE / "clauses.json").read_text(encoding="utf-8"))
    bad = 0
    for c in reg:
        p = BASE / c["file"]
        if not p.exists():
            print(f"MISSING FILE {c['file']}")
            bad += 1
            continue
        text = p.read_text(encoding="utf-8")
        if strict and ("TODO-VERIFY" in text or "PARAPHRASE" in c["status"]):
            print(f"UNVERIFIED {c['clause_id']}: {c['status']}")
            bad += 1
    print("rules_text OK" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main("--strict" in sys.argv))
