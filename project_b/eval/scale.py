"""Task 6 numbers: project the measured results to 50M rows/day x 120 customers. Every line = value + formula."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from common import BATCH_SIZE, CLEAN_DIR, OUT_DIR
from eval.cost import llm_usd

ROWS_PER_DAY = 50_000_000      # assumption: TOTAL across all customers
CUSTOMERS = 120
PEAK_FACTOR = 5                # assumption: peak is 5x the daily average
UTILISATION = 0.6              # assumption: run cores at 60% for headroom
RETENTION_DAYS = 30            # assumption: keep the data we validated for 30 days


def project() -> pd.DataFrame:
    ab = pd.read_csv(OUT_DIR / "hybrid_ablation.csv").set_index("config")
    with_llm, no_llm = ab.loc["hybrid_with_llm"], ab.loc["hybrid_without_llm"]
    llm_path = OUT_DIR / "llm_results.csv"
    llm = pd.read_csv(llm_path) if llm_path.exists() else pd.DataFrame()

    rps = no_llm.rows_per_sec_cheap_part
    avg_rps = ROWS_PER_DAY / 86400
    peak_rps = avg_rps * PEAK_FACTOR
    cores = math.ceil(peak_rps / (rps * UTILISATION))
    batches = ROWS_PER_DAY / BATCH_SIZE
    calls_batch = with_llm.llm_calls_per_batch
    tok_in = with_llm.llm_in_tokens / max(with_llm.llm_calls, 1)
    tok_out = with_llm.llm_out_tokens / max(with_llm.llm_calls, 1)
    usd_call = llm_usd(tok_in, tok_out)
    calls_day = batches * calls_batch
    ok = llm[(llm.status == "ok") & (llm["mode"] == "per_row")] if len(llm) else llm
    naive = np.nan
    if len(ok):
        per_call = llm_usd(ok.in_tokens.sum() / ok.calls.sum(), ok.out_tokens.sum() / ok.calls.sum())
        naive = per_call * ROWS_PER_DAY      # one LLM call for EVERY row
    parquet_gb = sum(p.stat().st_size for p in CLEAN_DIR.glob("*.parquet")) / 2**30
    n_rows_clean = sum(len(pd.read_parquet(p, columns=["unique_key"])) for p in CLEAN_DIR.glob("*.parquet"))
    bytes_row = parquet_gb * 2**30 / max(n_rows_clean, 1)

    rows = [
        ("rows per day (assumption, all customers)", ROWS_PER_DAY, "given"),
        ("customers", CUSTOMERS, "given; rows per customer per day = rows/customers = %.0f" % (ROWS_PER_DAY / CUSTOMERS)),
        ("average rows/sec needed", avg_rps, "rows_per_day / 86400"),
        ("peak rows/sec needed", peak_rps, f"average x {PEAK_FACTOR} (assumption)"),
        ("measured cheap-path throughput, rows/sec/core", rps, "hybrid stream, LLM time excluded"),
        ("cores needed at peak", cores, f"ceil(peak / (throughput x {UTILISATION} utilisation))"),
        ("batches per day", batches, f"rows_per_day / {BATCH_SIZE}"),
        ("LLM calls per batch (measured)", calls_batch, "hybrid_with_llm run"),
        ("LLM calls per day", calls_day, "batches x calls per batch"),
        ("LLM $ per call (measured tokens x list price)", usd_call, f"{tok_in:.0f} in + {tok_out:.0f} out tokens"),
        ("LLM $ per day", calls_day * usd_call, "calls per day x $ per call"),
        ("LLM $ per day if sample rate doubles", 2 * calls_day * usd_call, "sensitivity: 2x calls (assumption)"),
        ("naive per-row LLM $ per day", naive, "one call per row, tokens from per_row mode"),
        ("latency per batch, cheap path (s)", with_llm.compute_seconds / with_llm.batches, "measured"),
        ("latency per batch, LLM wait (s)", with_llm.llm_seconds / with_llm.batches, "measured, includes free-tier pacing"),
        ("storage bytes per row (parquet)", bytes_row, "clean parquet size / rows"),
        ("storage per day (GB)", bytes_row * ROWS_PER_DAY / 2**30, "bytes_per_row x rows_per_day"),
        (f"storage for {RETENTION_DAYS} days (TB)", bytes_row * ROWS_PER_DAY * RETENTION_DAYS / 2**40, "retention assumption"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "formula_or_assumption"])
