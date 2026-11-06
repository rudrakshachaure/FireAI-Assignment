"""Everything detectors may learn from CLEAN REFERENCE data (never from held-out batches or ground truth)."""
from __future__ import annotations

from dataclasses import dataclass

import joblib
import pandas as pd

from common import CLEAN_DIR, load_batches, modal_map
from detectors.stats.models import StatsModels


@dataclass
class Reference:
    columns: list[str]
    dtype_kinds: dict[str, str]          # column -> numpy dtype kind ('f' float, 'M' datetime, 'O' text)
    zip_borough: dict[str, str]
    pairs: set[tuple[str, str]]          # allowed (complaint_type, descriptor) pairs
    null_limit: dict[str, float]         # max null share per column (max over reference batches + 0.02)
    stats: StatsModels
    profile_text: str                    # compact description of the expected schema (used in the LLM prompt)


def fit_reference(ref_batches: list[pd.DataFrame]) -> Reference:
    k = max(1, len(ref_batches) // 5)                 # last 20% of reference batches = tuning set
    train_b, tune_b = (ref_batches[:-k] or ref_batches), ref_batches[-k:]
    train = pd.concat(train_b, ignore_index=True)
    full = pd.concat(ref_batches, ignore_index=True)
    null_rates = pd.DataFrame([b.isna().mean() for b in ref_batches])
    null_limit = (null_rates.max() + 0.02).to_dict()
    kinds = {c: full[c].dtype.kind for c in full.columns}
    profile = "; ".join(f"{c} ({kinds[c]}, {null_rates[c].mean():.0%} null)" for c in full.columns)
    return Reference(
        columns=list(full.columns), dtype_kinds=kinds, zip_borough=modal_map(full, "incident_zip", "borough"),
        pairs=set(zip(full.complaint_type, full.descriptor)), null_limit=null_limit,
        stats=StatsModels().fit(train, tune_b), profile_text=profile,
    )


def get_reference() -> Reference:
    """Fit once, cache on disk (profile_raw.py deletes the cache when the data is rebuilt)."""
    path = CLEAN_DIR / "reference_model.joblib"
    if path.exists():
        return joblib.load(path)
    ref = fit_reference(load_batches("reference"))
    joblib.dump(ref, path)
    return ref
