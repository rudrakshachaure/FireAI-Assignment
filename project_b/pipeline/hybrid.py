"""Task 5: hybrid pipeline.

  1. cheap detector per problem type (family chosen from the measured master table) runs on every batch
  2. semantic alerts (complaint_descriptor, resolution_status): LLM re-checks the TOP flagged rows -> cut false alarms
  3. PII: LLM reads a small random sample of rows (names are invisible to regexes)
Budget controls: max LLM calls per batch, rows per call, identical prompts hit the disk cache.

Run:  python -m pipeline.hybrid      -> eval/out/hybrid_*.csv / json
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from common import BATCH_LEVEL, BATCH_SIZE, OUT_DIR, PROBLEMS, SEED, Alert, load_batches
from detectors.llm.client import LLMClient
from detectors.llm.review import LLMReviewer
from detectors.reference import Reference, get_reference
from detectors.registry import DETECTORS
from eval.cost import compute_usd_per_m, llm_usd
from eval.metrics import flagged_rows, safe_run
from injector import build_context, inject

SEMANTIC = ("complaint_descriptor", "resolution_status")


@dataclass
class HybridConfig:
    use_llm: bool = True
    max_llm_calls_per_batch: int = 3
    llm_rows_per_call: int = 20


def choose_plan(master: pd.DataFrame) -> tuple[dict[str, str], pd.DataFrame]:
    """Per problem type: the cheap family with the best F1 at 5% injection (rules win ties within 0.03)."""
    m = master[master.rate == 0.05].copy()
    m["f1"] = (2 * m.recall * m.precision / (m.recall + m.precision)).fillna(0)
    plan, rows = {}, []
    for p in PROBLEMS:
        c = m[m.problem_type == p]
        ok = c[c.f1 >= c.f1.max() - 0.03]
        plan[p] = "rules" if "rules" in set(ok.family) else "stats"
        rows.append({"problem_type": p, "chosen_family": plan[p], **{f"f1_{r.family}": r.f1 for r in c.itertuples()}})
    return plan, pd.DataFrame(rows)


def run_batch(batch: pd.DataFrame, ref: Reference, plan: dict[str, str], cfg: HybridConfig,
              reviewer: LLMReviewer | None, rng: np.random.Generator):
    t0 = time.perf_counter()
    alerts: list[Alert] = []
    for ptype, family in plan.items():
        found, _ = safe_run(DETECTORS[family][ptype], batch, ref)
        alerts += found
    t_compute = time.perf_counter() - t0

    t1, calls_left = time.perf_counter(), cfg.max_llm_calls_per_batch
    if cfg.use_llm and reviewer is not None:
        for a in [a for a in alerts if a.problem_type in SEMANTIC and a.row_ids]:
            if calls_left <= 0:
                break
            top = sorted(a.row_ids, key=lambda i: i)[: cfg.llm_rows_per_call]
            res = reviewer.confirm_rows(batch, top, a.problem_type)
            calls_left -= 1
            if res is not None:                      # drop reviewed rows the LLM did not confirm
                confirmed, reason = res
                a.row_ids = [i for i in a.row_ids if i not in set(top) or i in set(confirmed)]
                a.explanation += f" | LLM: {reason}"
        alerts = [a for a in alerts if a.row_ids or a.level == "batch"]
        if calls_left > 0 and "resolution_description" in batch.columns:
            cand = np.flatnonzero(batch.resolution_description.notna().to_numpy())
            if len(cand):
                pick = sorted(int(i) for i in rng.choice(cand, min(len(cand), cfg.llm_rows_per_call), replace=False))
                alerts += reviewer.review_pii(batch, pick, group=cfg.llm_rows_per_call)
    return alerts, t_compute, time.perf_counter() - t1


def build_stream(held, ctx, n_clean: int = 12):
    """All 12 problem types at 1%, 5%, 20% + clean batches, each on a different held-out batch."""
    items, k = [], 0
    for rate in (0.01, 0.05, 0.2):
        for ptype in PROBLEMS:
            bad, truth = inject(held[k % len(held)], ptype, rate, SEED + k, ctx)
            items.append((bad, truth))
            k += 1
    items += [(held[(k + j) % len(held)], None) for j in range(n_clean)]
    return items


def run_stream(items, ref, plan, cfg, reviewer):
    rng, results = np.random.default_rng(SEED), []
    t_compute = t_llm = 0.0
    for bad, truth in items:
        alerts, tc, tl = run_batch(bad, ref, plan, cfg, reviewer, rng)
        t_compute, t_llm = t_compute + tc, t_llm + tl
        results.append((truth, alerts, len(bad)))
    return results, t_compute, t_llm


def evaluate(results) -> tuple[pd.DataFrame, dict]:
    rows = []
    for p in PROBLEMS:
        tp = tr = fl = 0
        for truth, alerts, _ in results:
            if truth is None or truth.problem_type != p:
                continue
            mine = [a for a in alerts if a.problem_type == p]
            if truth.level == "batch":
                hit = int(len(mine) > 0)
                tp, tr, fl = tp + hit, tr + 1, fl + hit
            else:
                f, t = flagged_rows(mine), set(truth.row_ids)
                tp, tr, fl = tp + len(f & t), tr + len(t), fl + len(f)
        rec = tp / tr if tr else np.nan
        prec = tp / fl if fl else (0.0 if tr else np.nan)   # flagged nothing -> precision 0, not "missing"
        rows.append({"problem_type": p, "recall": rec, "precision": prec,
                     "f1": 2 * rec * prec / (rec + prec) if (rec + prec) else 0.0})
    clean = [(a, n) for t, a, n in results if t is None]
    clean_rows = sum(n for _, n in clean)
    fa_rows = sum(len(flagged_rows(a)) for a, _ in clean)
    fa_batches = sum(int(any(x.level == "batch" for x in a)) for a, _ in clean)
    return pd.DataFrame(rows), {"clean_batches": len(clean), "clean_rows": clean_rows, "fa_rows": fa_rows,
                                "fa_rows_per_m": fa_rows / clean_rows * 1e6, "fa_batches": fa_batches}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plan, plan_df = choose_plan(pd.read_csv(OUT_DIR / "master.csv"))
    plan_df.to_csv(OUT_DIR / "hybrid_plan.csv", index=False)
    (OUT_DIR / "hybrid_plan.json").write_text(json.dumps(plan, indent=2))
    held, ref = load_batches("heldout"), get_reference()
    ctx = build_context(pd.concat(load_batches("reference"), ignore_index=True))
    items = build_stream(held, ctx)
    total_rows = sum(len(b) for b, _ in items)

    summaries, ablation = {}, []
    for name, use_llm in (("hybrid_without_llm", False), ("hybrid_with_llm", True)):
        cfg = HybridConfig(use_llm=use_llm)
        rev = LLMReviewer(LLMClient()) if use_llm else None
        wall0 = time.perf_counter()
        results, t_compute, t_llm = run_stream(items, ref, plan, cfg, rev)
        wall = time.perf_counter() - wall0
        per_type, fa = evaluate(results)
        use = rev.usage() if rev else {"calls": 0, "in_tokens": 0, "out_tokens": 0, "unavailable": 0, "cached_calls": 0}
        compute_per_m = compute_usd_per_m(total_rows / t_compute)
        llm_per_m = llm_usd(use["in_tokens"], use["out_tokens"]) / total_rows * 1e6
        summaries[name] = (per_type, results)
        ablation.append({
            "config": name, "macro_recall": per_type.recall.mean(), "macro_precision": per_type.precision.mean(),
            "macro_f1": per_type.f1.mean(), "clean_fa_rows_per_m": fa["fa_rows_per_m"],
            "clean_batches_with_batch_alert": fa["fa_batches"], "llm_calls": use["calls"],
            "llm_calls_per_batch": use["calls"] / len(items), "llm_in_tokens": use["in_tokens"],
            "llm_out_tokens": use["out_tokens"], "llm_unavailable_calls": use["unavailable"],
            "compute_usd_per_m": compute_per_m, "llm_usd_per_m": llm_per_m,
            "total_usd_per_m": compute_per_m + llm_per_m, "compute_seconds": t_compute, "llm_seconds": t_llm,
            "wall_seconds": wall, "rows": total_rows, "batches": len(items),
            "rows_per_sec_cheap_part": total_rows / t_compute})
        print(name, ablation[-1])

    ab = pd.DataFrame(ablation)
    d_f1 = ab.macro_f1[1] - ab.macro_f1[0]
    d_usd = ab.total_usd_per_m[1] - ab.total_usd_per_m[0]
    ab["f1_gain_per_extra_usd_per_m"] = [np.nan, d_f1 / d_usd if d_usd > 0 else np.nan]
    ab.to_csv(OUT_DIR / "hybrid_ablation.csv", index=False)
    per_type, results = summaries["hybrid_with_llm"]
    nollm = summaries["hybrid_without_llm"][0].set_index("problem_type")
    per_type = per_type.join(nollm[["recall", "precision"]].add_suffix("_no_llm"), on="problem_type")
    per_type["chosen_family"] = per_type.problem_type.map(plan)
    per_type.to_csv(OUT_DIR / "hybrid_per_type.csv", index=False)

    flat = [{"batch_has_problem": t.problem_type if t else "clean", "alert_type": a.problem_type, "level": a.level,
             "rows_flagged": len(a.row_ids), "explanation": a.explanation[:220]}
            for t, alerts, _ in results for a in alerts]
    sample = pd.DataFrame(flat).sample(min(10, len(flat)), random_state=SEED) if flat else pd.DataFrame(flat)
    sample.to_csv(OUT_DIR / "hybrid_sample_alerts.csv", index=False)


if __name__ == "__main__":
    main()
