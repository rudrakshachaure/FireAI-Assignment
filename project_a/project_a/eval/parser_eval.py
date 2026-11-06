"""Parser metrics on the 50 NL descriptions (uses Gemini; responses are cached).
  python -m project_a.eval.parser_eval"""
from __future__ import annotations

import json
from pathlib import Path

from ..parser import parse

DATA = Path(__file__).resolve().parents[1] / "data" / "nl_descriptions_50.jsonl"
OUT = Path(__file__).parent / "out"
FIELDS = ["gross_salary", "basic_plus_da", "hra_received", "rent_paid_annual", "metro", "age_band", "parent_senior"]
DED = ["sec_80c", "sec_80ccd_1b", "sec_80d_self", "sec_80d_parents", "home_loan_interest"]


def main() -> None:
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
    tp = fp = fn = tn = guessed = field_ok = field_total = 0
    detail = []
    for r in rows:
        res = parse(r["text"])
        should_ask = bool(r["gold"].get("needs_clarification"))
        asked = res["status"] == "needs_clarification"
        if should_ask and asked:
            hit = res["field"] in r["gold"]["fields"]
            tp += 1
            detail.append({"id": r["id"], "result": "asked", "field_in_gold": hit, "field": res["field"]})
        elif should_ask and not asked:
            fn += 1
            guessed += 1
            detail.append({"id": r["id"], "result": "GUESSED (critical)", "got": res.get("input")})
        elif asked:
            fp += 1
            detail.append({"id": r["id"], "result": "asked unnecessarily", "field": res["field"]})
        else:
            tn += 1
            inp, d = res["input"], res["input"]["deductions"]
            wrong = []
            for k in FIELDS:
                field_total += 1
                ok = inp[k] == r["gold"][k]
                field_ok += ok
                if not ok:
                    wrong.append((k, inp[k], r["gold"][k]))
            for k in DED:
                field_total += 1
                ok = d[k] == r["gold"][k]
                field_ok += ok
                if not ok:
                    wrong.append((k, d[k], r["gold"][k]))
            detail.append({"id": r["id"], "result": "ok", "wrong_fields": wrong})
    m = {"n": len(rows), "clarification_precision": round(tp / max(1, tp + fp), 3),
         "clarification_recall": round(tp / max(1, tp + fn), 3), "guessed_when_should_ask": guessed,
         "asked_unnecessarily": fp, "field_accuracy_on_ok_cases": round(field_ok / max(1, field_total), 4),
         "asked_field_matches_gold": sum(1 for d in detail if d.get("field_in_gold"))}
    OUT.mkdir(exist_ok=True)
    (OUT / "parser_metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    (OUT / "parser_detail.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
