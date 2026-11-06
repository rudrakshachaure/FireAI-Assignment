"""Shared config, paths, the Alert type and small helpers used by every module."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SEED = 42
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5000"))

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
CACHE_DIR = ROOT / "data" / "llm_cache"
OUT_DIR = ROOT / "eval" / "out"
PROFILE_OUT = ROOT / "profile" / "out"

# NYC 311 Service Requests from 2010 to Present (Socrata). The download script re-checks this id.
DATASET_ID = "erm2-nwe9"
SOCRATA_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
METADATA_URL = f"https://data.cityofnewyork.us/api/views/{DATASET_ID}.json"

# The columns we keep (Socrata field names). [HUMAN] confirm against the metadata printed by the downloader.
COLUMNS = [
    "unique_key", "created_date", "closed_date", "agency", "complaint_type", "descriptor",
    "incident_zip", "incident_address", "borough", "status", "resolution_description",
    "latitude", "longitude",
]
TEXT_COLS = ["agency", "complaint_type", "descriptor", "incident_address", "borough", "status",
             "resolution_description"]
CRITICAL = ["unique_key", "created_date", "agency", "complaint_type", "descriptor", "incident_zip",
            "borough", "latitude", "longitude", "status"]
NYC_BBOX = (40.45, 41.00, -74.30, -73.65)  # lat_min, lat_max, lon_min, lon_max
BOROUGHS = {
    "BRONX",
    "BROOKLYN",
    "MANHATTAN",
    "QUEENS",
    "STATEN ISLAND",
}
PROBLEMS = [
    "schema_column", "type_change", "date_format", "latlon_swap", "exact_dup", "near_dup",
    "null_spike", "closed_before_created", "zip_borough", "complaint_descriptor",
    "resolution_status", "pii",
]
BATCH_LEVEL = {"schema_column", "type_change", "null_spike"}
RATES = [0.001, 0.01, 0.05, 0.2]

# ---- cost assumptions (all editable) ----
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
PRICE_IN_PER_M = 0.10    # USD per 1M input tokens, gemini-2.5-flash-lite list price
PRICE_OUT_PER_M = 0.40   # USD per 1M output tokens
PRICE_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
PRICE_DATE = "2026-10-20 (read via third-party mirrors; [HUMAN] re-check on the official page)"
CPU_USD_PER_HOUR = 0.05  # assumed price of one vCPU-hour (cloud spot-ish); change if you disagree


@dataclass
class Alert:
    """What every detector returns."""
    problem_type: str
    level: str                       # "row" or "batch"
    row_ids: list[int]
    score: float
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class GroundTruth:
    """Kept by the injector and the evaluator only. Detectors never receive this."""
    problem_type: str
    level: str
    row_ids: list[int] | None        # None = batch-level problem
    params: dict[str, Any] = field(default_factory=dict)


# ---- small helpers ----
def to_typed(df: pd.DataFrame) -> pd.DataFrame:
    """Raw Socrata strings -> the typed contract: datetimes and floats, everything else text."""
    df = df.copy()
    for c in ("created_date", "closed_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in ("latitude", "longitude"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def parse_dt(s: pd.Series) -> pd.Series:
    """Parse a date column that may be datetimes or a mix of text formats."""
    if s.dtype.kind == "M":
        return s
    return pd.to_datetime(s, errors="coerce", format="mixed")


def norm_text(s: pd.Series) -> pd.Series:
    """lower-case, collapse whitespace."""
    return s.fillna("").astype(str).str.lower().str.split().str.join(" ")


def km(lat1, lon1, lat2, lon2):
    """Rough distance in km, good enough around New York."""
    return np.sqrt(((lat1 - lat2) * 111.0) ** 2 + ((lon1 - lon2) * 84.2) ** 2)


def modal_map(df: pd.DataFrame, key: str, val: str) -> dict:
    """key -> most common val."""
    counts = df.dropna(subset=[key, val]).groupby([key, val]).size().reset_index(name="n")
    best = counts.sort_values("n").drop_duplicates(key, keep="last")
    return dict(zip(best[key], best[val]))


def load_batches(name: str) -> list[pd.DataFrame]:
    """name = 'reference' or 'heldout'. Files are stored in time order; we slice them into batches."""
    df = pd.read_parquet(CLEAN_DIR / f"{name}.parquet")
    return [df.iloc[i:i + BATCH_SIZE].reset_index(drop=True)
            for i in range(0, len(df) - BATCH_SIZE + 1, BATCH_SIZE)]
