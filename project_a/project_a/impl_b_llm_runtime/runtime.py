"""Impl B: the LLM computes tax per request from retrieved rule text.
No calculator tool on purpose (the point is to measure the LLM doing arithmetic)."""
from __future__ import annotations

from pydantic import ValidationError

from ..llm_client import generate_json
from ..models import RuleError, TaxInput, TaxOutput
from ..rules_text import load_rule_text, topics_for

SYSTEM = """You compute Indian income tax for a salaried resident individual under BOTH the old and new regimes.
Use ONLY the rule text given. All amounts are integer rupees.
Process per regime: gross salary, subtract exemptions/deductions allowed in that regime (never below zero),
round taxable income to nearest 10 (5 rounds up), compute slab tax, apply 87A rebate / marginal relief,
add surcharge with marginal relief if income > 50 lakh, add 4% cess (round half up to whole rupee),
then round total tax to nearest 10 (5 rounds up).
Return JSON matching the schema. 'trace' lines: kind 'income' lines (signed) must sum to taxable_income;
kind 'tax' lines (signed: slab tax +, rebate -, surcharge +, relief -, cess +, rounding +/-) must sum to total_tax.
Every trace line's clause_id MUST be one of the allowed clause ids. recommended_regime = lower total_tax (tie: new),
unless regime_override is set."""


def build_prompt(inp: TaxInput, rule_text: str, clause_ids: list[str]) -> str:
    return (f"ALLOWED clause ids: {', '.join(clause_ids)}\n\nRULE TEXT:\n{rule_text}\n\n"
            f"INPUT (JSON):\n{inp.model_dump_json()}\n")


def compute(inp: TaxInput, use_cache: bool = True) -> TaxOutput:
    text, _hash, ids = load_rule_text(inp.fy, topics_for(inp))
    res = generate_json(build_prompt(inp, text, ids), schema=TaxOutput, system=SYSTEM,
                        rule_text=text, use_cache=use_cache)
    try:
        return TaxOutput.model_validate_json(res.text)
    except ValidationError as e:  # LOUD
        raise RuleError(f"impl B returned invalid output: {e}") from e
