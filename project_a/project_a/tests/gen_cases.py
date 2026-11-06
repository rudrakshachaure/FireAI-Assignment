"""Generate data/tests_200.jsonl, official_calc_checks.csv. Seeded; deterministic.
Usage: python -m project_a.tests.gen_cases"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from .oracle import expected

DATA = Path(__file__).resolve().parents[1] / "data"
NO_DED = {"sec_80c": 0, "sec_80ccd_1b": 0, "sec_80d_self": 0, "sec_80d_parents": 0, "home_loan_interest": 0}


def mk(gross: int, **kw) -> dict:
    ded = {**NO_DED, **kw.pop("ded", {})}
    base = {"gross_salary": gross, "basic_plus_da": 0, "hra_received": 0, "rent_paid_annual": 0,
            "metro": False, "age_band": "<60", "parent_senior": False, "employer_nps": 0,
            "regime_override": None, "fy": "2024-25"}
    base.update(kw)
    base["deductions"] = ded
    return base


def build() -> list[tuple[str, dict]]:
    cases: list[tuple[str, dict]] = []
    deltas = (-10, -1, 0, 1, 10)

    for t in (300000, 700000, 1000000, 1200000, 1500000):
        for d in deltas:
            cases.append(("new_slab_edge", mk(t + 75000 + d)))
    for age, ts in (("<60", (250000, 500000, 1000000)), ("60-79", (300000, 500000)), ("80+", (500000, 1000000))):
        for t in ts:
            for d in deltas:
                cases.append((f"old_slab_edge_{age}", mk(t + 50000 + d, age_band=age)))
    for t in (5_000_000, 10_000_000, 20_000_000, 50_000_000):
        for d in deltas:
            cases.append(("surcharge_new_edge", mk(t + 75000 + d)))
            cases.append(("surcharge_old_edge", mk(t + 50000 + d)))

    big = 2_000_000
    for v in (149999, 150000, 150001):
        cases.append(("cap_80c", mk(big, ded={"sec_80c": v})))
    for v in (49999, 50000, 50001):
        cases.append(("cap_80ccd1b", mk(big, ded={"sec_80ccd_1b": v})))
    for age in ("<60", "60-79"):
        for v in ((24999, 25000, 25001) if age == "<60" else (49999, 50000, 50001)):
            cases.append((f"cap_80d_self_{age}", mk(big, age_band=age, ded={"sec_80d_self": v})))
    for ps, vals in ((False, (24999, 25000, 25001)), (True, (49999, 50000, 50001))):
        for v in vals:
            cases.append((f"cap_80d_parents_senior={ps}", mk(big, parent_senior=ps, ded={"sec_80d_parents": v})))
    for v in (199999, 200000, 200001):
        cases.append(("cap_24b", mk(big, ded={"home_loan_interest": v})))
    for v in (99999, 100000, 100001, 139999, 140000, 140001):
        cases.append(("cap_80ccd2", mk(big, basic_plus_da=1_000_000, employer_nps=v)))
    cases.append(("home_loan_way_above_cap", mk(big, ded={"home_loan_interest": 900000})))

    # HRA: basic 600k, HRA received 240k
    for metro in (True, False):
        pct_term = 300000 if metro else 240000
        cases.append((f"hra_received_min_metro={metro}", mk(1_200_000, basic_plus_da=600000, hra_received=100000, rent_paid_annual=400000, metro=metro)))
        cases.append((f"hra_rent_excess_min_metro={metro}", mk(1_200_000, basic_plus_da=600000, hra_received=240000, rent_paid_annual=120000, metro=metro)))
        cases.append((f"hra_pct_basic_min_metro={metro}", mk(1_200_000, basic_plus_da=600000, hra_received=400000, rent_paid_annual=pct_term + 60000 + 50000, metro=metro)))
        cases.append((f"hra_boundary_metro={metro}", mk(1_200_000, basic_plus_da=600000, hra_received=240000, rent_paid_annual=pct_term + 60000, metro=metro)))
    cases.append(("hra_zero_rent", mk(1_200_000, basic_plus_da=600000, hra_received=240000)))
    cases.append(("hra_rent_below_10pct_basic", mk(1_200_000, basic_plus_da=600000, hra_received=240000, rent_paid_annual=50000)))

    for g in (0, 1, 30000, 49999, 50000, 50001, 74999, 75000, 75001):
        cases.append(("salary_below_or_near_std", mk(g)))
    cases.append(("deductions_exceed_income", mk(300000, ded={"sec_80c": 150000, "sec_80ccd_1b": 50000, "sec_80d_self": 25000, "home_loan_interest": 200000})))
    cases.append(("deductions_exceed_income_2", mk(120000, ded={"sec_80c": 150000})))
    cases.append(("override_old", mk(1_500_000, ded={"sec_80c": 150000}, regime_override="old")))
    cases.append(("override_new", mk(1_500_000, ded={"sec_80c": 150000}, regime_override="new")))

    rng = random.Random(20261105)
    for _ in range(70):
        gross = rng.choice([rng.randint(0, 3_000_000), rng.randint(0, 600_000), rng.randint(0, 15_000_000)])
        basic = rng.randint(0, gross) // 2 if gross else 0
        hra = rng.randint(0, basic // 2) if basic else 0
        cases.append(("random", mk(
            gross, basic_plus_da=basic, hra_received=hra,
            rent_paid_annual=rng.choice([0, rng.randint(0, 600_000)]), metro=rng.random() < 0.5,
            age_band=rng.choice(["<60", "<60", "60-79", "80+"]), parent_senior=rng.random() < 0.3,
            employer_nps=rng.choice([0, rng.randint(0, basic // 4 + 1)]) if basic else 0,
            ded={"sec_80c": rng.choice([0, rng.randint(0, 200000)]), "sec_80ccd_1b": rng.choice([0, rng.randint(0, 80000)]),
                 "sec_80d_self": rng.choice([0, rng.randint(0, 60000)]), "sec_80d_parents": rng.choice([0, rng.randint(0, 60000)]),
                 "home_loan_interest": rng.choice([0, rng.randint(0, 300000)])})))
    return cases


def main() -> None:
    DATA.mkdir(exist_ok=True)
    seen: set[str] = set()
    rows = []
    for tag, inp in build():
        key = json.dumps(inp, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"id": f"{len(rows) + 1:03d}-{tag}", "tag": tag, "input": inp, "expected": expected(inp)})
    assert len(rows) >= 200, f"only {len(rows)} cases"
    with open(DATA / "tests_200.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    # >=30 cases for the official calculator, spread across tags (no overrides)
    by_tag: dict[str, list[dict]] = {}
    for r in rows:
        if r["input"]["regime_override"] is None:
            by_tag.setdefault(r["tag"], []).append(r)
    picked = [v[len(v) // 2] for v in by_tag.values()]
    extra = [r for r in rows if r not in picked and r["tag"] == "random"][:max(0, 36 - len(picked))]
    picked += extra
    cols = ["case_id", "gross_salary", "basic_plus_da", "hra_received", "rent_paid_annual", "metro", "age_band",
            "parent_senior", "employer_nps", "sec_80c", "sec_80ccd_1b", "sec_80d_self", "sec_80d_parents",
            "home_loan_interest", "oracle_tax_old", "oracle_tax_new", "official_tax_old", "official_tax_new", "screenshot_ref"]
    with open(DATA / "official_calc_checks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in picked:
            i, d = r["input"], r["input"]["deductions"]
            w.writerow({"case_id": r["id"], **{k: i[k] for k in ("gross_salary", "basic_plus_da", "hra_received", "rent_paid_annual", "metro", "age_band", "parent_senior", "employer_nps")},
                        **{k: d[k] for k in ("sec_80c", "sec_80ccd_1b", "sec_80d_self", "sec_80d_parents", "home_loan_interest")},
                        "oracle_tax_old": r["expected"]["old"]["total_tax"], "oracle_tax_new": r["expected"]["new"]["total_tax"],
                        "official_tax_old": "", "official_tax_new": "", "screenshot_ref": ""})
    print(f"wrote {len(rows)} cases, {len(picked)} official-check rows")


if __name__ == "__main__":
    main()
