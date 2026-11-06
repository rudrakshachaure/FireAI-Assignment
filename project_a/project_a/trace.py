"""Trace checks shared by tests and eval."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import RegimeResult, TaxOutput

CLAUSES_JSON = Path(__file__).parent / "rules_text" / "clauses.json"


@lru_cache(maxsize=1)
def valid_clause_ids() -> frozenset[str]:
    return frozenset(c["clause_id"] for c in json.loads(CLAUSES_JSON.read_text(encoding="utf-8")))


def check_trace(res: RegimeResult) -> list[str]:
    """Problems found (empty list = OK). Income lines must rebuild taxable_income,
    tax lines must rebuild total_tax."""
    problems: list[str] = []
    inc = sum(t.amount for t in res.trace if t.kind == "income")
    tax = sum(t.amount for t in res.trace if t.kind == "tax")
    if inc != res.taxable_income:
        problems.append(f"income trace {inc} != taxable_income {res.taxable_income}")
    if tax != res.total_tax:
        problems.append(f"tax trace {tax} != total_tax {res.total_tax}")
    return problems


def traceability(out: TaxOutput) -> dict[str, int]:
    """Rupees backed by a trace line with an existing clause_id vs all traced rupees."""
    ok = bad = hallucinated = 0
    ids = valid_clause_ids()
    for res in (out.old, out.new):
        for t in res.trace:
            if t.clause_id in ids:
                ok += abs(t.amount)
            else:
                bad += abs(t.amount)
                hallucinated += 1
    return {"backed": ok, "unbacked": bad, "hallucinated_citations": hallucinated}
