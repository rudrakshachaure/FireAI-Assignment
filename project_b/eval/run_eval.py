"""Task 4 (rules + stats): problem_type x family x rate -> eval/out/master.csv

For every cell we measure: recall, precision, false alarms on CLEAN held-out batches (+ bootstrap CI),
throughput (rows/sec, single process), compute $/M rows and explainability.
Environment: N_EVAL_BATCHES (default 6), N_CLEAN_BATCHES (default 10).
"""
from __future__ import annotations

import json
import os
import platform
import time

import numpy as np
import pandas as pd

from common import BATCH_LEVEL, BATCH_SIZE, OUT_DIR, PROBLEMS, RATES, SEED, load_batches
from detectors.reference import get_reference
from detectors.registry import DETECTORS
from eval.cost import compute_usd_per_m
from eval.metrics import bootstrap_ci, explain_score, flagged_rows, safe_run
from injector import build_context, inject

N_EVAL = int(os.getenv("N_EVAL_BATCHES", "6"))
N_CLEAN = int(os.getenv("N_CLEAN_BATCHES", "10"))


def run_family(family: str, held, ref, ctx) -> list[dict]:
    out = []
    for ptype in PROBLEMS:
        det, is_batch = DETECTORS[family][ptype], ptype in BATCH_LEVEL
        # ---- clean batches: false alarms + throughput ----
        vals, secs, errors = [], 0.0, 0
        for b in held[:N_CLEAN]:
            t0 = time.perf_counter()
            alerts, err = safe_run(det, b, ref)
            secs += time.perf_counter() - t0
            errors += err is not None
            vals.append(int(len(alerts) > 0) if is_batch else len(flagged_rows(alerts)))   # batches or rows flagged
        scale = 1e6 / BATCH_SIZE
        fa_per_m, (lo, hi) = float(np.mean(vals) * scale), tuple(x * scale for x in bootstrap_ci(vals))
        rows_per_sec = len(vals) * BATCH_SIZE / secs

        # ---- injected batches ----
        for rate in RATES:
            tp = truth_n = flag_n = held_tp = held_n = 0
            expl = []
            for i in range(N_EVAL):
                src = held[(N_CLEAN + i) % len(held)]
                bad, truth = inject(src, ptype, rate, SEED + 7919 * i + int(rate * 10000), ctx)
                alerts, err = safe_run(det, bad, ref)
                errors += err is not None
                expl += [explain_score(a, list(bad.columns)) for a in alerts[:10]]
                if is_batch:
                    hit = int(len(alerts) > 0)
                    tp, truth_n, flag_n = tp + hit, truth_n + 1, flag_n + hit
                else:
                    fl, tr = flagged_rows(alerts), set(truth.row_ids)
                    tp, truth_n, flag_n = tp + len(fl & tr), truth_n + len(tr), flag_n + len(fl)
                    if ptype == "resolution_status":
                        h = set(truth.params["heldout_row_ids"])
                        held_tp, held_n = held_tp + len(fl & h), held_n + len(h)
            fp = np.mean(vals) * N_EVAL if is_batch else None     # batch-level: false batches at same count
            denom = (tp + fp) if is_batch else flag_n
            out.append({
                "problem_type": ptype, "family": family, "mode": "all_rows", "rate": rate,
                "recall": tp / truth_n if truth_n else np.nan, "precision": tp / denom if denom else np.nan,
                "recall_heldout_templates": held_tp / held_n if held_n else np.nan,
                "fa_per_m_rows": fa_per_m, "fa_ci_low": lo, "fa_ci_high": hi,
                "fa_unit": "batches" if is_batch else "rows", "rows_per_sec": rows_per_sec,
                "compute_usd_per_m": compute_usd_per_m(rows_per_sec), "llm_usd_per_m": 0.0,
                "total_usd_per_m": compute_usd_per_m(rows_per_sec),
                "explain_mean": float(np.mean(expl)) if expl else np.nan, "errors": errors,
            })
        print(f"{family:5s} {ptype:22s} recall@5%={out[-2]['recall']:.2f} fa/M={fa_per_m:,.0f} rows/s={rows_per_sec:,.0f}")
    return out


def side_effects(held, ref, ctx) -> pd.DataFrame:
    """Does injecting problem X make the rule detector for problem Y fire? (log, 5% rate, one batch)"""
    rows = []
    base = held[0]
    for x in PROBLEMS:
        bad, _ = inject(base, x, 0.05, SEED, ctx)
        for y in PROBLEMS:
            if x == y:
                continue
            a0, _ = safe_run(DETECTORS["rules"][y], base, ref)
            a1, _ = safe_run(DETECTORS["rules"][y], bad, ref)
            extra = (len(a1) > 0) - (len(a0) > 0) if y in BATCH_LEVEL else len(flagged_rows(a1)) - len(flagged_rows(a0))
            if extra:
                rows.append({"injected": x, "also_triggers_rule": y, "extra_flagged": extra})
    return pd.DataFrame(rows, columns=["injected", "also_triggers_rule", "extra_flagged"])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    held, ref_batches = load_batches("heldout"), load_batches("reference")
    ref = get_reference()
    ctx = build_context(pd.concat(ref_batches, ignore_index=True))   # injector also learns only from reference
    rows = run_family("rules", held, ref, ctx) + run_family("stats", held, ref, ctx)
    pd.DataFrame(rows).to_csv(OUT_DIR / "master.csv", index=False)
    side_effects(held, ref, ctx).to_csv(OUT_DIR / "injection_side_effects.csv", index=False)
    try:
        ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (ValueError, OSError, AttributeError):
        ram = float("nan")
    (OUT_DIR / "system_info.json").write_text(json.dumps({
        "cpu": platform.processor() or platform.machine(), "cores": os.cpu_count(), "ram_gb": round(ram, 1),
        "python": platform.python_version(), "batch_size": BATCH_SIZE, "n_eval_batches": N_EVAL,
        "n_clean_batches": N_CLEAN}, indent=2))


if __name__ == "__main__":
    main()
