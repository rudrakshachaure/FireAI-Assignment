"""Shared interface for all three implementations (brief: SHARED INTERFACE).

Extra fields vs the brief (decisions, listed in README):
  * employer_nps  - Sec 80CCD(2), optional, default 0
  * TraceLine.kind - "income" lines build taxable income, "tax" lines build total_tax
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

AgeBand = Literal["<60", "60-79", "80+"]
Regime = Literal["old", "new"]
FYear = Literal["2024-25", "2025-26"]


class RuleError(Exception):
    """LOUD failure: missing rules, bad artifact, invalid LLM output."""


class Deductions(BaseModel):
    sec_80c: int = Field(0, ge=0)
    sec_80ccd_1b: int = Field(0, ge=0)
    sec_80d_self: int = Field(0, ge=0)      # total premium incl. any preventive check-up
    sec_80d_parents: int = Field(0, ge=0)
    home_loan_interest: int = Field(0, ge=0)  # self-occupied, Sec 24(b)


class TaxInput(BaseModel):
    gross_salary: int = Field(ge=0)
    basic_plus_da: int = Field(0, ge=0)
    hra_received: int = Field(0, ge=0)
    rent_paid_annual: int = Field(0, ge=0)
    metro: bool = False
    age_band: AgeBand = "<60"
    parent_senior: bool = False
    deductions: Deductions = Field(default_factory=Deductions)
    employer_nps: int = Field(0, ge=0)
    regime_override: Optional[Regime] = None
    fy: FYear = "2024-25"

    @model_validator(mode="after")
    def _consistency(self) -> "TaxInput":
        if self.basic_plus_da > self.gross_salary:
            raise ValueError("basic_plus_da cannot exceed gross_salary")
        if self.hra_received > self.gross_salary:
            raise ValueError("hra_received cannot exceed gross_salary")
        if self.employer_nps > self.gross_salary:
            raise ValueError("employer_nps cannot exceed gross_salary")
        return self


class TraceLine(BaseModel):
    amount: int          # signed rupees
    label: str
    clause_id: str
    formula: str
    kind: Literal["income", "tax"] = "tax"


class RegimeResult(BaseModel):
    taxable_income: int
    slab_tax: int
    rebate: int              # Sec 87A rebate incl. 87A marginal relief
    surcharge: int
    marginal_relief: int     # surcharge marginal relief only
    cess: int
    total_tax: int
    trace: list[TraceLine]


class TaxOutput(BaseModel):
    old: RegimeResult
    new: RegimeResult
    recommended_regime: Regime
