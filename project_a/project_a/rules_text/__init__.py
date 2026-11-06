"""Rule-text loading by simple topic lookup (used by impl B and the impl C compile step)."""
from __future__ import annotations

import json
from pathlib import Path

from ..llm_client import sha
from ..models import RuleError, TaxInput

BASE = Path(__file__).parent


def _registry(fy: str) -> list[dict]:
    reg = [c for c in json.loads((BASE / "clauses.json").read_text(encoding="utf-8")) if c["fy"] == fy]
    if not reg:
        raise RuleError(f"no rule text for FY {fy}")
    return reg


def topics_for(inp: TaxInput) -> set[str]:
    d = inp.deductions
    t = {"gross", "std", "rates", "rebate", "surcharge", "cess", "rounding"}
    if inp.hra_received or inp.rent_paid_annual:
        t.add("hra")
    for flag, topic in ((d.sec_80c, "80c"), (d.sec_80ccd_1b, "80ccd1b"), (d.sec_80d_self or d.sec_80d_parents, "80d"),
                        (d.home_loan_interest, "24b"), (inp.employer_nps, "80ccd2")):
        if flag:
            t.add(topic)
    return t


def load_rule_text(fy: str, topics: set[str] | None = None) -> tuple[str, str, list[str]]:
    """(joined text, sha256 of text, clause ids included). topics=None -> everything."""
    chosen = [c for c in _registry(fy) if topics is None or topics & set(c["topics"])]
    parts = [(BASE / c["file"]).read_text(encoding="utf-8") for c in chosen]
    text = "\n\n---\n\n".join(parts)
    return text, sha(text), [c["clause_id"] for c in chosen]
