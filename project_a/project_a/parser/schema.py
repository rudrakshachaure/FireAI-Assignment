"""What the LLM is allowed to return: raw quotes from the text, NOT normalised numbers."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Money(BaseModel):
    raw: str        # exactly as written, e.g. "18L", "1.8 cr", "15,00,000", "40k"; "max" for "maxed out 80C"
    period: str     # "annual" | "monthly" | "unknown"


class ExtractedFacts(BaseModel):
    gross_salary: list[Money] = Field(default_factory=list)
    salary_basis: Optional[str] = None      # "gross" | "ctc" | null
    basic_plus_da: list[Money] = Field(default_factory=list)
    hra_received: list[Money] = Field(default_factory=list)
    rent_paid: list[Money] = Field(default_factory=list)
    city: Optional[str] = None
    claims_metro: Optional[bool] = None     # user explicitly says metro / non-metro
    age: Optional[int] = None
    parents_mentioned: bool = False
    parent_age: Optional[int] = None
    parent_senior_stated: Optional[bool] = None
    sec_80c: list[Money] = Field(default_factory=list)
    sec_80ccd_1b: list[Money] = Field(default_factory=list)
    sec_80d_self: list[Money] = Field(default_factory=list)
    sec_80d_parents: list[Money] = Field(default_factory=list)
    home_loan_interest: list[Money] = Field(default_factory=list)
    deductions_none: bool = False           # person explicitly says they have no investments/insurance/loan/deductions
