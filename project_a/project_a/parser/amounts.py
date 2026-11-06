"""Rules, not LLM: unit normalisation."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

_MULT = {"": 1, "k": 1_000, "thousand": 1_000, "hazar": 1_000, "hazaar": 1_000,
         "l": 100_000, "lac": 100_000, "lacs": 100_000, "lakh": 100_000, "lakhs": 100_000, "lpa": 100_000,
         "cr": 10_000_000, "crore": 10_000_000, "crores": 10_000_000}


def parse_amount(raw: str) -> Optional[int]:
    """'18L' -> 1800000, '1.8 cr' -> 18000000, '15,00,000' -> 1500000, '40k' -> 40000. None if unparseable."""
    s = raw.lower().replace(",", "").replace("₹", "").replace("inr", "").replace("rs.", "").replace("rs", "").strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-z]*)", s)
    if not m or m.group(2) not in _MULT:
        return None
    val = Decimal(m.group(1)) * _MULT[m.group(2)]
    return int(val) if val == val.to_integral_value() else None


def to_annual(raw: str, period: str) -> Optional[int]:
    """None if the amount or the period is not determinable (caller must ask)."""
    amt = parse_amount(raw)
    if amt is None or period not in ("annual", "monthly"):
        return None
    return amt * (12 if period == "monthly" else 1)
