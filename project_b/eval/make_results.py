"""Builds the master table, heatmap, RESULTS_B.md and DECISION_MATRIX.md from eval/out/*.csv.
No hand-typed metrics: every number below is read from a CSV."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import (BATCH_SIZE, GEMINI_MODEL, PRICE_DATE, PRICE_IN_PER_M, PRICE_OUT_PER_M, PRICE_SOURCE,  # noqa: E402
                    PROBLEMS, PROFILE_OUT, ROOT, CPU_USD_PER_HOUR)
from common import BATCH_LEVEL, OUT_DIR  # noqa: E402
from eval.cost import llm_usd  # noqa: E402
from eval.scale import project  # noqa: E402

AUDIT = {"rules": "High: explicit rule, reproducible reason", "stats": "Medium: score + threshold, features inspectable",
         "llm": "Low: free-text reason, no reproducible logic", "hybrid": "Medium: each alert tagged with its source"}
DETERM = {"rules": "Deterministic", "stats": "Deterministic given seed + reference data",
          "llm": "Not deterministic across model versions (disk cache pins results)", "hybrid": "Deterministic except LLM step"}
MAINT = {"rules": "Maps/regexes need updates when schemas or wording change", "stats": "Re-fit baselines per customer; watch drift",
         "llm": "Prompt + model-version upkeep; price changes", "hybrid": "Both sets of upkeep; budget knobs to tune"}


def llm_rows() -> pd.DataFrame:
    p = OUT_DIR / "llm_results.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p)
    d = d[d.status == "ok"].copy()
    if d.empty:
        return d
    per_call = d.apply(lambda r: llm_usd(r.in_tokens / max(r.calls, 1), r.out_tokens / max(r.calls, 1)), axis=1)
    d["llm_usd_per_m"] = per_call * 1e6 / d.rows_per_call          # if applied to every row / batch
    prev = 0.05
    d["precision"] = (d.recall * prev) / (d.recall * prev + d.fpr * (1 - prev))   # precision at 5% prevalence
    scale = np.where(d.problem_type.isin(BATCH_LEVEL), 1e6 / BATCH_SIZE, 1e6)
    d["fa_per_m_rows"] = d.fpr * scale
    d["family"], d["rate"] = "llm", 0.05
    d["total_usd_per_m"] = d.llm_usd_per_m
    d["fa_unit"] = np.where(d.problem_type.isin(BATCH_LEVEL), "batches", "rows")
    return d.drop(columns=["fpr", "n_pos", "n_neg", "calls", "in_tokens", "out_tokens", "rows_per_call", "status"])


def fmt(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False, floatfmt=".3g")


def heatmap(master: pd.DataFrame) -> None:
    m = master[master.rate == 0.05].copy()
    m["col"] = np.where(m.family == "llm", "llm:" + m["mode"], m.family)
    rec = m.pivot_table(index="problem_type", columns="col", values="recall").reindex(PROBLEMS)
    fa = m.pivot_table(index="problem_type", columns="col", values="fa_per_m_rows").reindex(PROBLEMS)
    fig, ax = plt.subplots(1, 2, figsize=(14, 6))
    for a, data, title, cmap in ((ax[0], rec, "Detection (recall @5%)", "Greens"),
                                 (ax[1], np.log10(1 + fa), "False alarms (log10(1+ per M rows))", "Reds")):
        im = a.imshow(data.to_numpy(float), cmap=cmap, aspect="auto")
        a.set_xticks(range(len(data.columns)), data.columns, rotation=45, ha="right")
        a.set_yticks(range(len(data.index)), data.index)
        a.set_title(title)
        fig.colorbar(im, ax=a)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "heatmap.png", dpi=130)


def negatives(master: pd.DataFrame) -> list[str]:
    m, out = master[master.rate == 0.05], []
    for p in PROBLEMS:
        cheap, llm = m[(m.problem_type == p) & (m.family != "llm")], m[(m.problem_type == p) & (m.family == "llm")]
        if cheap.empty or llm.empty:
            continue
        best = cheap.sort_values("recall", ascending=False).iloc[0]
        top = llm.sort_values("recall", ascending=False).iloc[0]
        if top.recall <= best.recall and top.total_usd_per_m > best.total_usd_per_m:
            out.append(f"- **{p}**: LLM ({top['mode']}) recall {top.recall:.2f} vs {best.family} {best.recall:.2f}, and "
                       f"${top.total_usd_per_m:,.2f}/M rows vs ${best.total_usd_per_m:,.4f}/M rows: worse AND costlier.")
    return out or ["- (no problem type where the LLM was both worse and costlier, or LLM results are missing)"]


def main() -> None:
    cheap = pd.read_csv(OUT_DIR / "master.csv")
    master = pd.concat([cheap, llm_rows()], ignore_index=True)
    master.to_csv(OUT_DIR / "master_all.csv", index=False)
    heatmap(master)

    sysinfo = json.loads((OUT_DIR / "system_info.json").read_text())
    summ = json.loads((PROFILE_OUT / "clean_summary.json").read_text())
    issues = pd.read_csv(PROFILE_OUT / "real_issues.csv").head(8)[["issue", "count", "pct", "proposed_check_family"]]
    five = master[master.rate == 0.05].copy()
    five["fa (CI)"] = five.apply(lambda r: f"{r.fa_per_m_rows:,.0f} [{r.fa_ci_low:,.0f}-{r.fa_ci_high:,.0f}]"
                                 if pd.notna(r.get("fa_ci_low")) else f"{r.fa_per_m_rows:,.0f}", axis=1)
    five["family"] = np.where(five.family == "llm", "llm:" + five["mode"].astype(str), five.family)
    cols = ["problem_type", "family", "recall", "precision", "fa (CI)", "rows_per_sec", "total_usd_per_m", "explain_mean"]
    hyb = {f: pd.read_csv(OUT_DIR / f) for f in ("hybrid_per_type.csv", "hybrid_ablation.csv", "hybrid_sample_alerts.csv")}
    scale = project()
    scale.to_csv(OUT_DIR / "scale.csv", index=False)

    md = f"""# RESULTS_B: Rules vs LLMs for data quality (generated; edit the [HUMAN] parts)

## 1. Data and what "clean" means
NYC 311 requests created in 2023 ({summ['raw_rows']:,} raw rows). Clean = no row-level issue from the profile
(see profile/out/REAL_ISSUES.md): {summ['clean_rows_used']:,} rows in {summ['n_batches']} batches of {BATCH_SIZE}
({summ['reference_batches']} reference, {summ['heldout_batches']} held-out). False-alarm rates are measured on held-out
clean batches, so they exclude real issues that the clean definition removed (optimistic).

{fmt(issues)}

## 2. Detection, false alarms and cost at 5% injection
Machine: {sysinfo['cpu']}, {sysinfo['cores']} cores, {sysinfo['ram_gb']} GB RAM, single process.
fa = false alarms per million clean rows (batch-level problems: flagged batches per million rows), with 95% bootstrap CI over
{sysinfo['n_clean_batches']} clean batches. Cost formula: compute $/M = (1e6 / rows_per_sec) / 3600 x ${CPU_USD_PER_HOUR}/vCPU-hour;
LLM $/M = (tokens per call x list price) x calls per M rows. LLM model {GEMINI_MODEL}: ${PRICE_IN_PER_M}/M input and
${PRICE_OUT_PER_M}/M output tokens ({PRICE_SOURCE}, {PRICE_DATE}). LLM rows come from SAMPLES (see eval/out/llm_results.csv
for sample sizes) and are extrapolated; their precision is recomputed at 5% prevalence. Full grid (all rates): eval/out/master_all.csv.

{fmt(five[cols])}

![detection vs false alarms](eval/out/heatmap.png)

### Negative results (generated)
{chr(10).join(negatives(master))}

## 3. Hybrid pipeline on a mixed stream
Plan per problem type (chosen from section 2): eval/out/hybrid_plan.csv.

{fmt(hyb['hybrid_per_type.csv'])}

Ablation (what the LLM adds, per dollar):

{fmt(hyb['hybrid_ablation.csv'].T.reset_index().rename(columns={'index': 'metric'}))}

Sample of 10 alerts:

{fmt(hyb['hybrid_sample_alerts.csv'])}

## 4. Scale: 50M rows/day x 120 customers
{fmt(scale)}

[HUMAN] Write the design discussion here (max 2 pages total): engine change (DuckDB/Spark), per-customer baselines and schema
mapping, LLM for schema-mapping/onboarding and alert triage instead of per-row, caching, baseline drift, alert-fatigue controls,
per-customer thresholds, PII via cheaper NER. Sensitivity line is in the table (LLM sample rate x2).
"""
    (ROOT / "RESULTS_B.md").write_text(md)

    plan = json.loads((OUT_DIR / "hybrid_plan.json").read_text())
    rows = []
    for p in PROBLEMS:
        fam = plan[p]
        r = master[(master.problem_type == p) & (master.family == fam) & (master.rate == 0.05)].iloc[0]
        rows.append({"check": p, "family": f"hybrid ({fam} first, LLM on semantic/PII)" if p in
                     ("complaint_descriptor", "resolution_status", "pii") else fam,
                     "evidence": f"recall {r.recall:.2f}, precision {r.precision:.2f}, FA {r.fa_per_m_rows:,.0f}/M, ${r.total_usd_per_m:.4f}/M rows",
                     "auditability": AUDIT[fam], "determinism": DETERM[fam], "maintenance": MAINT[fam]})
    (ROOT / "DECISION_MATRIX.md").write_text("# DECISION_MATRIX rows (Project B)\n\n" + fmt(pd.DataFrame(rows)) + "\n")
    print("wrote RESULTS_B.md and DECISION_MATRIX.md")


if __name__ == "__main__":
    main()
