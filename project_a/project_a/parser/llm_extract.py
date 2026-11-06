"""LLM part of parsing: messy text -> ExtractedFacts. Nothing is normalised here."""
from __future__ import annotations

from ..llm_client import generate_json
from .schema import ExtractedFacts
from .validate import validate

SYSTEM = """Extract facts about an Indian salaried person's tax situation from their message (English/Hinglish/messy).
RULES: copy amounts exactly as written into 'raw' (never convert units). If the person gives two conflicting values,
return BOTH as separate entries. Set period to 'monthly' or 'annual' only if the text says so or it is obvious
('per month', 'monthly', 'p.m.', 'LPA' = annual); otherwise 'unknown'. salary_basis is 'ctc' only if they say CTC/package,
'gross' only if they say gross. Do not guess missing values; leave them empty/null. 'maxed 80C' -> raw 'max'.
deductions_none is true ONLY if they explicitly say they have no investments/deductions/insurance/loan. Vague statements like 'some investments' give no amounts and deductions_none=false. If one deduction is given as several components, return each component as its own entry only if no total is stated.
Age: only if stated. Output JSON per schema."""


def extract(text: str, use_cache: bool = True) -> ExtractedFacts:
    res = generate_json(f"MESSAGE:\n{text}", schema=ExtractedFacts, system=SYSTEM, use_cache=use_cache)
    return ExtractedFacts.model_validate_json(res.text)


def parse(text: str, use_cache: bool = True, fy: str = "2024-25") -> dict:
    return validate(extract(text, use_cache), fy)
