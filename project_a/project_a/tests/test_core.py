"""Hand-computed sanity values + impl A vs oracle + trace checks + rounding."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_a.impl_a_rules import compute
from project_a.models import RuleError, TaxInput
from project_a.rounding import div_half_up, round_to_nearest_10
from project_a.tests.gen_cases import main as gen_main
from project_a.trace import check_trace, valid_clause_ids

CASES = Path(__file__).resolve().parents[1] / "data" / "tests_200.jsonl"


def _cases() -> list[dict]:
    if not CASES.exists():
        gen_main()
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]


def test_rounding_policy() -> None:
    assert [round_to_nearest_10(x) for x in (0, 4, 5, 14, 15, 99)] == [0, 0, 10, 10, 20, 100]
    assert div_half_up(1, 2) == 1 and div_half_up(1, 3) == 0 and div_half_up(5, 2) == 3


def test_hand_values() -> None:
    # new: gross 10L -> ti 9,25,000 -> 20,000 + 22,500 = 42,500 + 4% cess = 44,200
    out = compute(TaxInput(gross_salary=1_000_000))
    assert out.new.taxable_income == 925_000 and out.new.total_tax == 44_200
    # old: ti 9,50,000 -> 12,500 + 90,000 = 1,02,500 + cess 4,100 = 1,06,600
    assert out.old.taxable_income == 950_000 and out.old.total_tax == 106_600
    assert out.recommended_regime == "new"
    # 87A new: ti exactly 7L -> zero tax; 10 above -> payable limited to 10
    assert compute(TaxInput(gross_salary=775_000)).new.total_tax == 0
    assert compute(TaxInput(gross_salary=775_010)).new.total_tax == 10


def test_missing_fy_rules_is_loud() -> None:
    with pytest.raises(RuleError):
        compute(TaxInput(gross_salary=1, fy="2025-26"))


def test_input_validation_is_loud() -> None:
    with pytest.raises(ValueError):
        TaxInput(gross_salary=100, basic_plus_da=200)


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_impl_a_matches_oracle_and_trace(case: dict) -> None:
    out = compute(TaxInput.model_validate(case["input"]))
    exp = case["expected"]
    for reg in ("old", "new"):
        res = getattr(out, reg)
        assert res.taxable_income == exp[reg]["taxable_income"], reg
        assert res.total_tax == exp[reg]["total_tax"], reg
        assert check_trace(res) == []
        assert all(t.clause_id in valid_clause_ids() for t in res.trace)
    assert out.recommended_regime == exp["recommended_regime"]
