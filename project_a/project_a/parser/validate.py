"""Rules, not LLM: validation layer applied AFTER extraction. Returns either a
TaxInput (+ visible assumptions) or ONE clarifying question. Never defaults a number silently."""
from __future__ import annotations

from typing import Any, Optional

from ..impl_a_rules.engine import load_rules
from ..models import Deductions, TaxInput
from .amounts import parse_amount, to_annual
from .schema import ExtractedFacts, Money

CAP_80C_WORDS = {"max", "maxed", "maxed out"}


def _ask(field: str, question: str) -> dict[str, Any]:
    return {"status": "needs_clarification", "field": field, "question": question}


def _distinct(field: str, items: list[Money]) -> tuple[Optional[int], Optional[dict[str, Any]]]:
    """Single annual value, or (None, clarification). Empty list -> (None, None)."""
    if not items:
        return None, None
    vals: set[int] = set()
    for m in items:
        if field == "sec_80c" and m.raw.strip().lower() in CAP_80C_WORDS:
            vals.add(150_000)  # 'maxed' = statutory cap; visible in assumptions by caller
            continue
        v = to_annual(m.raw, m.period)
        if v is None:
            if parse_amount(m.raw) is not None and m.period == "unknown":
                return None, _ask(field, f"Is {m.raw} per month or per year ({field.replace('_', ' ')})?")
            return None, _ask(field, f"I couldn't read the amount '{m.raw}' for {field.replace('_', ' ')}. What is it per year, in rupees?")
        vals.add(v)
    if len(vals) > 1:
        return None, _ask(field, f"You gave different amounts for {field.replace('_', ' ')} ({sorted(vals)}). Which one is right?")
    return vals.pop(), None


def validate(f: ExtractedFacts, fy: str = "2024-25") -> dict[str, Any]:
    rules = load_rules(fy)
    metro_cities = {c.lower() for c in rules.hra.metro_cities}
    assumptions: list[str] = []

    gross, q = _distinct("gross_salary", f.gross_salary)
    if q:
        return q
    if gross is None:
        return _ask("gross_salary", "What is your annual gross salary (before tax, excluding employer PF)?")
    if f.salary_basis == "ctc":
        return _ask("gross_salary", "That sounds like CTC. What is your annual gross salary (the taxable salary on your payslip, before deductions)?")

    if f.age is None:
        return _ask("age_band", "How old are you? (the old-regime slabs depend on whether you're under 60, 60-79 or 80+)")
    age_band = "<60" if f.age < 60 else ("60-79" if f.age < 80 else "80+")

    basic, q = _distinct("basic_plus_da", f.basic_plus_da)
    if q:
        return q
    hra, q = _distinct("hra_received", f.hra_received)
    if q:
        return q
    rent, q = _distinct("rent_paid", f.rent_paid)
    if q:
        return q
    metro = False
    if (rent or 0) > 0 or (hra or 0) > 0:
        if (rent or 0) > gross:
            return _ask("rent_paid", "The rent you mentioned is higher than your salary. Is it the annual rent, and is the figure right?")
        if hra is None:
            return _ask("hra_received", "How much HRA do you receive per year?")
        if basic is None:
            return _ask("basic_plus_da", "What is your annual basic salary plus DA?")
        city = (f.city or "").strip().lower()
        if city:
            by_city = city in metro_cities
            if f.claims_metro is not None and f.claims_metro != by_city:
                return _ask("metro", f"You said {'metro' if f.claims_metro else 'non-metro'} but {f.city} is "
                                     f"{'' if by_city else 'not '}one of {', '.join(rules.hra.metro_cities)}. Which city do you actually rent in?")
            metro = by_city
        elif f.claims_metro is not None:
            metro = f.claims_metro
        else:
            return _ask("metro", "Which city do you rent in?")
    if basic is not None and basic > gross:
        return _ask("basic_plus_da", "Your basic salary is higher than your gross salary. Which of the two figures is wrong?")
    if hra is not None and hra > gross:
        return _ask("hra_received", "Your HRA is higher than your gross salary. Is the figure right?")

    ded: dict[str, Optional[int]] = {}
    for fld in ("sec_80c", "sec_80ccd_1b", "sec_80d_self", "sec_80d_parents", "home_loan_interest"):
        v, q = _distinct(fld, getattr(f, fld))
        if q:
            return q
        ded[fld] = v
    if all(v is None for v in ded.values()) and not f.deductions_none:
        return _ask("deductions", "Do you have any 80C investments, NPS, health insurance or a home loan? (say 'none' if not)")

    parent_senior = False
    if (ded["sec_80d_parents"] or 0) > 0 or f.parents_mentioned:
        if f.parent_age is not None:
            parent_senior = f.parent_age >= 60
        elif f.parent_senior_stated is not None:
            parent_senior = f.parent_senior_stated
        elif (ded["sec_80d_parents"] or 0) > 0:
            return _ask("parent_senior", "Are your parents 60 or older? (the health-insurance limit is higher for senior citizens)")

    for fld, v in ded.items():
        if v is None:
            assumptions.append(f"{fld} not mentioned -> 0")
    if any(m.raw.strip().lower() in CAP_80C_WORDS for m in f.sec_80c):
        assumptions.append("'maxed' 80C taken as the statutory cap of 1,50,000")
    if basic is None:
        assumptions.append("basic salary not needed (no HRA/rent) -> 0")

    inp = TaxInput(gross_salary=gross, basic_plus_da=basic or 0, hra_received=hra or 0, rent_paid_annual=rent or 0,
                   metro=metro, age_band=age_band, parent_senior=parent_senior, fy=fy,  # type: ignore[arg-type]
                   deductions=Deductions(**{k: (v or 0) for k, v in ded.items()}))
    return {"status": "ok", "input": inp.model_dump(), "assumptions": assumptions}
