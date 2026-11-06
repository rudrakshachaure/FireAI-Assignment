"""Schema of the per-FY rules data file. Shared by impl A (hand-written file),
impl C (LLM-compiled file) and the compile step's JSON-schema mode."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class Slab(BaseModel):
    upto: Optional[int]      # upper bound of the slab in rupees; null = no upper bound
    rate_pct: int


class SlabSet(BaseModel):
    age_band: str            # "<60" | "60-79" | "80+" | "all"
    slabs: list[Slab]

    @field_validator("age_band")
    @classmethod
    def _known_band(cls, v: str) -> str:
        if v not in {"<60", "60-79", "80+", "all"}:
            raise ValueError(f"age_band must be one of <60, 60-79, 80+, all (got {v!r})")
        return v

    
class Rebate(BaseModel):
    limit: int               # rebate available if taxable income <= limit
    max_amount: int
    marginal_relief: bool    # relief just above the limit


class SurchargeTier(BaseModel):
    above: int               # surcharge applies if taxable income > above
    rate_pct: int


class RegimeRules(BaseModel):
    standard_deduction: int
    employer_nps_pct_of_basic: int
    allows: list[str]        # subset of: hra 80c 80ccd1b 80d 24b 80ccd2
    slab_sets: list[SlabSet]
    rebate: Rebate
    surcharge_tiers: list[SurchargeTier]


class Caps(BaseModel):
    c80c: int
    ccd1b: int
    d80_self: int
    d80_self_senior: int
    d80_parents: int
    d80_parents_senior: int
    home_loan_interest: int


class HRARules(BaseModel):
    metro_pct: int
    nonmetro_pct: int
    rent_excess_pct_of_basic: int
    metro_cities: list[str]


class Clauses(BaseModel):
    gross: str
    std: str
    hra: str
    slabs_old: str
    slabs_new: str
    rebate: str
    surcharge: str
    cess: str
    c80c: str
    ccd1b: str
    ccd2: str
    d80d: str
    hp24b: str
    round_income: str
    round_tax: str


class RulesFile(BaseModel):
    fy: str
    cess_pct: int
    old: RegimeRules
    new: RegimeRules
    caps: Caps
    hra: HRARules
    clauses: Clauses
    todo_verify: list[str]


