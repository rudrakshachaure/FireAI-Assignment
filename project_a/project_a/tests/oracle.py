"""INDEPENDENT oracle for FY 2024-25. Deliberately boring: constants are
hard-coded here (NOT read from impl_a's JSON), slabs are explicit if-chains,
arithmetic is Decimal. Shares nothing with impl_a_rules except the policy of
half-up rounding of intermediate rupee amounts and nearest-10 at the end."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

D = Decimal


def _r(x) -> int:
    return int(D(x).quantize(D(1), rounding=ROUND_HALF_UP))


def _r10(x: int) -> int:
    return int((D(x) / 10).quantize(D(1), rounding=ROUND_HALF_UP)) * 10


def _pct(amount: int, pct: str) -> int:
    return _r(D(amount) * D(pct))


# ----- slab tax before rebate -----
def _old_tax(ti: int, age: str) -> int:
    exempt = {"<60": 250000, "60-79": 300000, "80+": 500000}[age]
    t = D(0)
    if ti > 1000000:
        t += (ti - 1000000) * D("0.30")
    if ti > 500000:
        t += (min(ti, 1000000) - 500000) * D("0.20")
    if exempt < 500000 and ti > exempt:
        t += (min(ti, 500000) - exempt) * D("0.05")
    return _r(t)


def _new_tax(ti: int, age: str = "<60") -> int:
    t = D(0)
    if ti > 1500000:
        t += (ti - 1500000) * D("0.30")
    if ti > 1200000:
        t += (min(ti, 1500000) - 1200000) * D("0.20")
    if ti > 1000000:
        t += (min(ti, 1200000) - 1000000) * D("0.15")
    if ti > 700000:
        t += (min(ti, 1000000) - 700000) * D("0.10")
    if ti > 300000:
        t += (min(ti, 700000) - 300000) * D("0.05")
    return _r(t)


_SUR_OLD = [(50_000_000, 37), (20_000_000, 25), (10_000_000, 15), (5_000_000, 10)]
_SUR_NEW = [(20_000_000, 25), (10_000_000, 15), (5_000_000, 10)]


def _with_surcharge(ti: int, base_fn, table, age: str) -> int:
    """tax + surcharge, after marginal relief (min against threshold position)."""
    tax = base_fn(ti, age)
    for limit, rate in table:
        if ti > limit:
            s = _r(D(tax) * rate / 100)
            capped = _with_surcharge(limit, base_fn, table, age) + (ti - limit)
            return min(tax + s, capped)
    return tax


# ----- taxable income -----
def _ti_old(i: dict) -> int:
    d = i["deductions"]
    basic, rent, hra = i["basic_plus_da"], i["rent_paid_annual"], i["hra_received"]
    share = "0.50" if i["metro"] else "0.40"
    hra_ex = min(hra, max(0, rent - _pct(basic, "0.10")), _pct(basic, share))
    salary = i["gross_salary"] - hra_ex
    salary -= min(50000, salary)
    hp = min(d["home_loan_interest"], 200000, salary)
    gti = salary - hp
    self_cap = 25000 if i["age_band"] == "<60" else 50000
    par_cap = 50000 if i["parent_senior"] else 25000
    vi_a = (min(d["sec_80c"], 150000) + min(d["sec_80ccd_1b"], 50000)
            + min(d["sec_80d_self"], self_cap) + min(d["sec_80d_parents"], par_cap)
            + min(i["employer_nps"], _pct(basic, "0.10")))
    return _r10(gti - min(vi_a, gti))


def _ti_new(i: dict) -> int:
    salary = i["gross_salary"] - min(75000, i["gross_salary"])
    nps = min(i["employer_nps"], _pct(i["basic_plus_da"], "0.14"))
    return _r10(salary - min(nps, salary))


# ----- totals -----
def _finish(ti: int, base_fn, table, age: str, rebate_limit: int, rebate_max: int, relief: bool) -> int:
    tax = base_fn(ti, age)
    if ti <= rebate_limit:
        tax_after = tax - min(tax, rebate_max)
        sur_total = tax_after
    else:
        tax_after = min(tax, ti - rebate_limit) if relief else tax
        sur_total = _with_surcharge(ti, base_fn, table, age) if tax_after == tax else tax_after
    base = sur_total
    cess = _r(D(base) * D("0.04"))
    return _r10(base + cess)


def expected(i: dict) -> dict:
    """i: plain dict shaped like TaxInput (FY 2024-25 only)."""
    if i["fy"] != "2024-25":
        raise NotImplementedError("oracle for FY 2025-26 is written in Task 5")
    ti_o, ti_n = _ti_old(i), _ti_new(i)
    old = _finish(ti_o, _old_tax, _SUR_OLD, i["age_band"], 500000, 12500, False)
    new = _finish(ti_n, _new_tax, _SUR_NEW, i["age_band"], 700000, 25000, True)
    rec = i.get("regime_override") or ("old" if old < new else "new")
    return {"old": {"taxable_income": ti_o, "total_tax": old},
            "new": {"taxable_income": ti_n, "total_tax": new},
            "recommended_regime": rec}
