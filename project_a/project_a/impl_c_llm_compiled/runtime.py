"""Impl C runtime: frozen, human-reviewed rules + the impl A engine.

DOCUMENTED REUSE: the arithmetic engine is impl A's (brief allows this only if
documented). So impl C's accuracy measures the quality of the COMPILED RULES
(the data file), not of the engine. No LLM is called here."""
from __future__ import annotations

from pathlib import Path
from pydantic import ValidationError

from ..impl_a_rules.engine import compute as engine_compute
from ..impl_a_rules.rules_schema import RulesFile
from ..models import RuleError, TaxInput, TaxOutput

FROZEN = Path(__file__).parent / "frozen"


def load_frozen(fy: str) -> RulesFile:
    p = FROZEN / f"rules_fy{fy}.json"
    if not p.exists():
        raise RuleError(f"no frozen compiled rules for FY {fy}: run compile_rules, review, copy to frozen/")
    try:
        return RulesFile.model_validate_json(p.read_text(encoding="utf-8"))
    except ValidationError as e:
        raise RuleError(f"frozen rules for FY {fy} failed validation: {e.errors()[0]['msg']}") from e


def compute(inp: TaxInput) -> TaxOutput:
    return engine_compute(inp, load_frozen(inp.fy))
