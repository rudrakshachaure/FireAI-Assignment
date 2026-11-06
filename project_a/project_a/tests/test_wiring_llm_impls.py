"""Impl B / C plumbing without network: the LLM call is stubbed with impl A's answer."""
from __future__ import annotations

import pytest

from project_a.impl_a_rules import compute as compute_a
from project_a.impl_b_llm_runtime import runtime as b
from project_a.impl_c_llm_compiled import runtime as c
from project_a.llm_client import LLMResult
from project_a.models import RuleError, TaxInput


def test_impl_b_validates_llm_output(monkeypatch: pytest.MonkeyPatch) -> None:
    inp = TaxInput(gross_salary=1_500_000)
    good = compute_a(inp).model_dump_json()
    monkeypatch.setattr(b, "generate_json", lambda *a, **k: LLMResult(good, 1, 1, 0.1, False, "k"))
    assert b.compute(inp) == compute_a(inp)
    monkeypatch.setattr(b, "generate_json", lambda *a, **k: LLMResult('{"old": 1}', 1, 1, 0.1, False, "k"))
    with pytest.raises(RuleError):
        b.compute(inp)


def test_impl_c_loud_without_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(c, "FROZEN", tmp_path)
    with pytest.raises(RuleError):
        c.compute(TaxInput(gross_salary=500_000))


def test_impl_c_runs_on_frozen_copy(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from project_a.impl_a_rules.engine import rules_path
    (tmp_path / "rules_fy2024-25.json").write_text(rules_path("2024-25").read_text())
    monkeypatch.setattr(c, "FROZEN", tmp_path)
    inp = TaxInput(gross_salary=2_000_000)
    assert c.compute(inp) == compute_a(inp)
