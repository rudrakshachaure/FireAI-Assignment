"""OFFLINE, run once per FY: Gemini turns rule text into the rules data file.
Writes ONLY the raw output (raw/). A human reviews it, copies it to frozen/ with
corrections, and logs every correction in REVIEW.md. Usage:
  python -m project_a.impl_c_llm_compiled.compile_rules --fy 2024-25 [--no-cache]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..impl_a_rules.rules_schema import RulesFile
from ..llm_client import generate_json
from ..rules_text import load_rule_text

HERE = Path(__file__).parent
SYSTEM = """Convert the Indian income-tax rule text into the JSON rules file described by the schema.
Use ONLY numbers present in the text. Rupee amounts are integers. 'allows' lists the deduction keys that regime
permits, from: hra 80c 80ccd1b 80d 24b 80ccd2. Slab 'upto' is null for the top slab. For the new regime use one
slab set with age_band 'all'. Put clause ids (from the provided list) in 'clauses'. In 'todo_verify' list anything
ambiguous or missing in the text instead of guessing."""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fy", required=True)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    text, h, ids = load_rule_text(a.fy)
    prompt = f"Clause ids: {', '.join(ids)}\nFY: {a.fy}\n\nRULE TEXT:\n{text}"
    res = generate_json(prompt, schema=RulesFile, system=SYSTEM, rule_text=text, use_cache=not a.no_cache)
    RulesFile.model_validate_json(res.text)  # loud if malformed
    out = HERE / "raw" / f"rules_fy{a.fy}.raw.json"
    out.write_text(json.dumps(json.loads(res.text), indent=2), encoding="utf-8")
    print(f"wrote {out} (rule_text_sha256={h[:12]}, tokens in/out {res.tokens_in}/{res.tokens_out})")
    print("NEXT [HUMAN]: review, copy to frozen/, list corrections in REVIEW.md")


if __name__ == "__main__":
    main()
