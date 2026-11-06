"""Deterministic parser layer, no LLM."""
from __future__ import annotations

import pytest

from project_a.parser.amounts import parse_amount, to_annual
from project_a.parser.schema import ExtractedFacts, Money
from project_a.parser.validate import validate


@pytest.mark.parametrize("raw,want", [("18L", 1_800_000), ("1.8 cr", 18_000_000), ("15,00,000", 1_500_000),
                                      ("40k", 40_000), ("18 lakh", 1_800_000), ("₹50,000", 50_000), ("abc", None), ("1.2345k", None)])
def test_parse_amount(raw: str, want) -> None:
    assert parse_amount(raw) == want


def test_period() -> None:
    assert to_annual("40k", "monthly") == 480_000
    assert to_annual("40k", "unknown") is None


def M(raw: str, p: str = "annual") -> Money:
    return Money(raw=raw, period=p)


def base(**kw) -> ExtractedFacts:
    d = dict(gross_salary=[M("18L")], age=30, deductions_none=True)
    d.update(kw)
    return ExtractedFacts(**d)


def test_ok_and_no_silent_default() -> None:
    r = validate(base())
    assert r["status"] == "ok" and r["input"]["gross_salary"] == 1_800_000
    assert any("not mentioned" in a for a in r["assumptions"])


def test_asks_instead_of_guessing() -> None:
    assert validate(ExtractedFacts())["field"] == "gross_salary"
    assert validate(base(age=None))["field"] == "age_band"
    assert validate(base(salary_basis="ctc"))["field"] == "gross_salary"
    assert validate(base(deductions_none=False))["field"] == "deductions"
    assert validate(base(gross_salary=[M("85000", "unknown")]))["field"] == "gross_salary"


def test_contradictions() -> None:
    assert validate(base(sec_80c=[M("max"), M("0")]))["field"] == "sec_80c"
    r = validate(base(rent_paid=[M("40k", "monthly")], hra_received=[M("2L")], basic_plus_da=[M("9L")], city="Pune", claims_metro=True))
    assert r["field"] == "metro"
    r = validate(base(rent_paid=[M("40k", "monthly")], hra_received=[M("2L")], basic_plus_da=[M("9L")], city="Pune"))
    assert r["status"] == "ok" and r["input"]["metro"] is False and r["input"]["rent_paid_annual"] == 480_000
    assert validate(base(rent_paid=[M("30L")], hra_received=[M("2L")], basic_plus_da=[M("9L")], city="Delhi"))["field"] == "rent_paid"


def test_parents() -> None:
    assert validate(base(deductions_none=False, sec_80c=[M("1.5L")]))["status"] == "ok"
    assert validate(base(sec_80d_parents=[M("30k")]))["field"] == "parent_senior"
    assert validate(base(sec_80d_parents=[M("30k")], parent_age=65))["input"]["parent_senior"] is True
