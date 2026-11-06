"""Law-agnostic tax engine. All numbers live in rules_fy<FY>.json.

Order of operations per regime (every step emits a trace line):
  gross -> HRA exemption -> standard deduction -> 24(b) -> Chapter VI-A
  -> round income (288A) -> slab tax -> 87A rebate (+ marginal relief)
  -> surcharge -> surcharge marginal relief -> cess -> round tax (288B)

Assumptions: resident individual; salary is the only income; gross_salary
includes employer NPS; professional tax (Sec 16(iii)) not modelled.
Deductions are capped by remaining income, so income never goes negative.
"""
from __future__ import annotations

from pathlib import Path

from ..models import RegimeResult, RuleError, TaxInput, TaxOutput, TraceLine
from ..rounding import div_half_up, round_to_nearest_10
from .rules_schema import RegimeRules, RulesFile, Slab

RULES_DIR = Path(__file__).parent


def rules_path(fy: str) -> Path:
    return RULES_DIR / f"rules_fy{fy}.json"


def load_rules(fy: str) -> RulesFile:
    path = rules_path(fy)
    if not path.exists():
        raise RuleError(f"no rules file for FY {fy}: {path.name}")
    return RulesFile.model_validate_json(path.read_text(encoding="utf-8"))


# ---------- pure helpers ----------

def slab_parts(slabs: list[Slab], ti: int) -> list[tuple[int, int, int, int]]:
    """[(lower, upper, rate_pct, tax)] for slabs actually reached by ti."""
    parts: list[tuple[int, int, int, int]] = []
    lower = 0
    for s in slabs:
        upper = ti if s.upto is None else min(ti, s.upto)
        width = upper - lower
        if width > 0:
            parts.append((lower, upper, s.rate_pct, div_half_up(width * s.rate_pct, 100)))
        if s.upto is None or ti <= s.upto:
            break
        lower = s.upto
    return parts


def slab_total(slabs: list[Slab], ti: int) -> int:
    return sum(p[3] for p in slab_parts(slabs, ti))


def surcharge_with_relief(slabs: list[Slab], rr: RegimeRules, ti: int, tax: int) -> tuple[int, int]:
    """(surcharge, marginal_relief). Relief caps tax+surcharge at
    (tax+surcharge at the crossed threshold) + (income above threshold).
    Assumes no 87A rebate at these income levels."""
    crossed = [t for t in rr.surcharge_tiers if ti > t.above]
    if not crossed:
        return 0, 0
    top = max(crossed, key=lambda t: t.above)
    surcharge = div_half_up(tax * top.rate_pct, 100)
    tax_t = slab_total(slabs, top.above)
    sur_t, relief_t = surcharge_with_relief(slabs, rr, top.above, tax_t)
    limit = tax_t + sur_t - relief_t + (ti - top.above)
    return surcharge, max(0, tax + surcharge - limit)


def hra_exemption(inp: TaxInput, rules: RulesFile) -> tuple[int, str]:
    h = rules.hra
    pct = h.metro_pct if inp.metro else h.nonmetro_pct
    rent_term = max(0, inp.rent_paid_annual - div_half_up(inp.basic_plus_da * h.rent_excess_pct_of_basic, 100))
    pct_term = div_half_up(inp.basic_plus_da * pct, 100)
    amount = min(inp.hra_received, rent_term, pct_term)
    formula = (f"min(HRA {inp.hra_received}, rent-{h.rent_excess_pct_of_basic}%basic {rent_term}, "
               f"{pct}%basic {pct_term})")
    return amount, formula


# ---------- one regime ----------

def compute_regime(inp: TaxInput, rules: RulesFile, regime: str) -> RegimeResult:
    rr = rules.old if regime == "old" else rules.new
    cl, caps, d = rules.clauses, rules.caps, inp.deductions
    trace: list[TraceLine] = []

    def add(amount: int, label: str, clause: str, formula: str, kind: str = "tax") -> None:
        trace.append(TraceLine(amount=amount, label=label, clause_id=clause, formula=formula, kind=kind))

    remaining = inp.gross_salary
    add(remaining, "Gross salary", cl.gross, "gross_salary", "income")

    def deduct(allowed: int, label: str, clause: str, formula: str) -> None:
        nonlocal remaining
        amount = min(allowed, remaining)
        if amount > 0:
            add(-amount, label, clause, f"{formula}; limited to remaining income {remaining}", "income")
            remaining -= amount

    if "hra" in rr.allows:
        amt, f = hra_exemption(inp, rules)
        deduct(amt, "HRA exemption", cl.hra, f)
    deduct(rr.standard_deduction, "Standard deduction", cl.std, f"standard_deduction {rr.standard_deduction}")
    if "24b" in rr.allows:
        deduct(min(d.home_loan_interest, caps.home_loan_interest), "Home-loan interest (self-occupied)",
               cl.hp24b, f"min({d.home_loan_interest}, cap {caps.home_loan_interest})")
    if "80c" in rr.allows:
        deduct(min(d.sec_80c, caps.c80c), "Deduction 80C", cl.c80c, f"min({d.sec_80c}, cap {caps.c80c})")
    if "80ccd1b" in rr.allows:
        deduct(min(d.sec_80ccd_1b, caps.ccd1b), "Deduction 80CCD(1B)", cl.ccd1b,
               f"min({d.sec_80ccd_1b}, cap {caps.ccd1b})")
    if "80d" in rr.allows:
        cap_self = caps.d80_self if inp.age_band == "<60" else caps.d80_self_senior
        cap_par = caps.d80_parents_senior if inp.parent_senior else caps.d80_parents
        deduct(min(d.sec_80d_self, cap_self), "Deduction 80D (self/family)", cl.d80d,
               f"min({d.sec_80d_self}, cap {cap_self})")
        deduct(min(d.sec_80d_parents, cap_par), "Deduction 80D (parents)", cl.d80d,
               f"min({d.sec_80d_parents}, cap {cap_par})")
    if "80ccd2" in rr.allows:
        nps_cap = div_half_up(inp.basic_plus_da * rr.employer_nps_pct_of_basic, 100)
        deduct(min(inp.employer_nps, nps_cap), "Deduction 80CCD(2) employer NPS", cl.ccd2,
               f"min({inp.employer_nps}, {rr.employer_nps_pct_of_basic}% of basic {nps_cap})")

    ti = round_to_nearest_10(remaining)
    if ti != remaining:
        add(ti - remaining, "Round taxable income to nearest 10", cl.round_income,
            f"round10({remaining})", "income")

    slabs = next((s.slabs for s in rr.slab_sets if s.age_band == inp.age_band), None)
    if slabs is None:
        slabs = next((s.slabs for s in rr.slab_sets if s.age_band == "all"), None)
    if slabs is None:
        raise RuleError(f"no slab set for age band {inp.age_band} in regime {regime}")
    slab_clause = cl.slabs_old if regime == "old" else cl.slabs_new
    parts = slab_parts(slabs, ti)
    for lower, upper, rate, tax_part in parts:
        if rate > 0:
            add(tax_part, f"Slab tax {lower}-{upper} @ {rate}%", slab_clause,
                f"({upper}-{lower}) * {rate}%")
    slab_tax = sum(p[3] for p in parts)

    rebate = 0
    rb = rr.rebate
    if rb.max_amount > 0:
        if ti <= rb.limit:
            rebate = min(slab_tax, rb.max_amount)
            if rebate:
                add(-rebate, "Rebate u/s 87A", cl.rebate,
                    f"min(tax {slab_tax}, max {rb.max_amount}) as income <= {rb.limit}")
        elif rb.marginal_relief and slab_tax > ti - rb.limit:
            rebate = slab_tax - (ti - rb.limit)
            add(-rebate, "Rebate u/s 87A marginal relief", cl.rebate,
                f"tax {slab_tax} - (income {ti} - limit {rb.limit})")

    tax_after_rebate = slab_tax - rebate
    surcharge, relief = surcharge_with_relief(slabs, rr, ti, tax_after_rebate)
    if surcharge:
        add(surcharge, "Surcharge", cl.surcharge, f"surcharge on {tax_after_rebate}")
    if relief:
        add(-relief, "Surcharge marginal relief", cl.surcharge, "tax+surcharge capped at threshold tax + excess income")

    base = tax_after_rebate + surcharge - relief
    cess = div_half_up(base * rules.cess_pct, 100)
    if cess:
        add(cess, f"Health & education cess {rules.cess_pct}%", cl.cess, f"{rules.cess_pct}% of {base}")

    total_unrounded = base + cess
    total = round_to_nearest_10(total_unrounded)
    if total != total_unrounded:
        add(total - total_unrounded, "Round tax to nearest 10", cl.round_tax, f"round10({total_unrounded})")

    return RegimeResult(taxable_income=ti, slab_tax=slab_tax, rebate=rebate, surcharge=surcharge,
                        marginal_relief=relief, cess=cess, total_tax=total, trace=trace)


def compute(inp: TaxInput, rules: RulesFile | None = None) -> TaxOutput:
    rules = rules or load_rules(inp.fy)
    old = compute_regime(inp, rules, "old")
    new = compute_regime(inp, rules, "new")
    if inp.regime_override:
        rec = inp.regime_override
    else:
        rec = "old" if old.total_tax < new.total_tax else "new"
    return TaxOutput(old=old, new=new, recommended_regime=rec)
