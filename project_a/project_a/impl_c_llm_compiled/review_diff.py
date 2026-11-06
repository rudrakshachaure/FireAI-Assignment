"""Show raw (LLM) vs frozen (human-reviewed) diff for REVIEW.md. Usage:
  python -m project_a.impl_c_llm_compiled.review_diff 2024-25"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main(fy: str) -> None:
    raw_p = HERE / "raw" / f"rules_fy{fy}.raw.json"
    fro_p = HERE / "frozen" / f"rules_fy{fy}.json"
    if not raw_p.exists():
        raise SystemExit(f"No raw file. Run compile_rules --fy {fy} first.")
    if not fro_p.exists():
        raise SystemExit(f"No frozen file yet. Copy {raw_p.name} into frozen/ as {fro_p.name}, then edit it and re-run.")
    raw = json.dumps(json.loads(raw_p.read_text(encoding="utf-8")), indent=2).splitlines()
    fro = json.dumps(json.loads(fro_p.read_text(encoding="utf-8")), indent=2).splitlines()
    print("\n".join(difflib.unified_diff(raw, fro, "raw (LLM)", "frozen (reviewed)", lineterm="")) or "no differences")


if __name__ == "__main__":
    main(sys.argv[1])
