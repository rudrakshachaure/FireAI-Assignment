"""Task 2: the 12 corruption injectors.

inject(batch, problem_type, rate, seed, ctx) -> (corrupted_batch, GroundTruth)
Row ids are row POSITIONS in the corrupted batch (RangeIndex). Duplicates are appended at the END of the batch,
so "the later copy" is always the injected one.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from faker import Faker

from common import BATCH_LEVEL, GroundTruth, modal_map


@dataclass
class InjectionContext:
    """Facts learned from CLEAN REFERENCE data only (never from held-out batches)."""
    zip_borough: dict[str, str]
    pairs: set[tuple[str, str]]
    descriptors_by_type: dict[str, list[str]]
    types_by_agency: dict[str, list[str]]


def build_context(clean: pd.DataFrame) -> InjectionContext:
    pairs = set(zip(clean.complaint_type, clean.descriptor))
    desc: dict[str, list[str]] = {}
    for t, d in pairs:
        desc.setdefault(t, []).append(d)
    types_by_agency = clean.groupby("agency")["complaint_type"].unique().map(list).to_dict()
    return InjectionContext(modal_map(clean, "incident_zip", "borough"), pairs, desc, types_by_agency)


def _count(n: int, rate: float) -> int:
    return max(1, int(round(n * rate)))


def _pick(rng: np.random.Generator, candidates: np.ndarray, k: int) -> np.ndarray:
    return np.sort(rng.choice(candidates, min(k, len(candidates)), replace=False))


# ---------------- batch-level (schema) problems ----------------
def inject_schema_column(df, rate, rng, ctx):
    n_cols = max(1, round(rate * 10))
    cols = [str(c) for c in rng.choice([c for c in df.columns if c != "unique_key"], n_cols, replace=False)]
    renamed, dropped = {}, []
    for c in cols:
        if rng.random() < 0.5:
            renamed[c] = "".join(p.title() for p in c.split("_"))  # incident_zip -> IncidentZip
        else:
            dropped.append(c)
    return df.rename(columns=renamed).drop(columns=dropped), None, {"renamed": renamed, "dropped": dropped}


def inject_type_change(df, rate, rng, ctx):
    cols = ["latitude", "longitude"][: 1 if rate < 0.2 else 2]
    for c in cols:
        df[c] = df[c].map(lambda v: None if pd.isna(v) else str(v))  # numbers as strings
    return df, None, {"columns": cols}


# ---------------- row-level problems ----------------
def inject_date_format(df, rate, rng, ctx):
    n = len(df)
    k = n - _count(n, rate)                      # ISO for rows < k, MM/DD/YYYY from row k onwards
    ts = pd.to_datetime(df["created_date"])
    iso = ts.dt.strftime("%Y-%m-%dT%H:%M:%S")
    us = ts.dt.strftime("%m/%d/%Y %H:%M:%S")
    df["created_date"] = np.where(np.arange(n) < k, iso, us)
    return df, np.arange(k, n), {"switch_row": k}


def inject_latlon_swap(df, rate, rng, ctx):
    cand = np.flatnonzero((df.latitude.notna() & df.longitude.notna()).to_numpy())
    ids = _pick(rng, cand, _count(len(df), rate))
    df.loc[ids, ["latitude", "longitude"]] = df.loc[ids, ["longitude", "latitude"]].to_numpy()
    return df, ids, {}


def inject_exact_dup(df, rate, rng, ctx):
    src = _pick(rng, np.arange(len(df)), _count(len(df), rate))
    out = pd.concat([df, df.iloc[src]], ignore_index=True)
    return out, np.arange(len(df), len(out)), {"source_rows": src.tolist()}


def _edit_text(s: str, rng: np.random.Generator) -> str:
    """case change, extra whitespace, or a typo (swap two letters)."""
    s = str(s)
    r = int(rng.integers(4))
    if r == 0:
        return s.lower() if s != s.lower() else s.upper()
    if r == 1:
        return "  " + s + " "
    if r == 2 and len(s) > 3:
        i = int(rng.integers(0, len(s) - 1))
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    return s.replace(" ", "  ", 1) if " " in s else s + " "


def inject_near_dup(df, rate, rng, ctx):
    src = _pick(rng, np.arange(len(df)), _count(len(df), rate))
    copies = df.iloc[src].copy().reset_index(drop=True)
    copies["unique_key"] = copies["unique_key"].astype(str) + "-n"      # new key, same content
    jitter = pd.to_timedelta(rng.integers(1, 301, size=len(copies)), unit="s")  # 1 s .. 5 min
    copies["created_date"] = copies["created_date"] + jitter
    copies["closed_date"] = copies["closed_date"] + jitter
    for i in range(len(copies)):
        col = "descriptor" if rng.random() < 0.5 else "incident_address"
        j = copies.columns.get_loc(col)
        if pd.notna(copies.iat[i, j]):
            copies.iat[i, j] = _edit_text(copies.iat[i, j], rng)
    out = pd.concat([df, copies], ignore_index=True)
    return out, np.arange(len(df), len(out)), {"source_rows": src.tolist()}


NULLABLE_FOR_SPIKE = ["descriptor", "incident_zip", "borough", "incident_address", "resolution_description",
                      "latitude", "longitude"]


def inject_null_spike(df, rate, rng, ctx):
    top = df["agency"].value_counts().index[:5]
    agency = str(rng.choice(top))
    cols = [str(c) for c in rng.choice(NULLABLE_FOR_SPIKE, 3, replace=False)]
    rows = np.flatnonzero((df["agency"] == agency).to_numpy())
    ids = _pick(rng, rows, _count(len(rows), rate))    # rate = share of this agency's rows that lose the 3 values
    df.loc[ids, cols] = None
    return df, ids, {"agency": agency, "columns": cols}


def inject_closed_before_created(df, rate, rng, ctx):
    cand = np.flatnonzero(df["closed_date"].notna().to_numpy())
    ids = _pick(rng, cand, _count(len(df), rate))
    hours = pd.to_timedelta(rng.integers(1, 49, size=len(ids)), unit="h")
    df.loc[ids, "closed_date"] = df.loc[ids, "created_date"].to_numpy() - hours.to_numpy()
    return df, ids, {}


def inject_zip_borough(df, rate, rng, ctx):
    zips = np.array(list(ctx.zip_borough))
    cand = np.flatnonzero((df.incident_zip.notna() & df.borough.notna()).to_numpy())
    ids = _pick(rng, cand, _count(len(df), rate))
    j = df.columns.get_loc("incident_zip")
    for i in ids:
        b = df["borough"].iat[i]
        other = zips[[ctx.zip_borough[z] != b for z in zips]]   # a ZIP that the clean map puts elsewhere
        df.iat[i, j] = str(rng.choice(other))
    return df, ids, {}


def inject_complaint_descriptor(df, rate, rng, ctx):
    """Half 'subtle' swaps (a descriptor from another complaint type of the SAME agency),
    half 'cross-type' swaps (a descriptor from any other complaint type)."""
    m = _count(len(df), rate)
    j = df.columns.get_loc("descriptor")
    changed, kinds = [], {}
    for i in rng.permutation(len(df)):
        if len(changed) >= m:
            break
        t, a = df["complaint_type"].iat[i], df["agency"].iat[i]
        subtle = len(changed) % 2 == 0
        pool = ctx.types_by_agency.get(a, []) if subtle else list(ctx.descriptors_by_type)
        pool = [x for x in pool if x != t]
        if not pool:
            continue
        t2 = pool[int(rng.integers(len(pool)))]
        d = ctx.descriptors_by_type[t2][int(rng.integers(len(ctx.descriptors_by_type[t2])))]
        if (t, d) in ctx.pairs:
            continue                                  # would still be a legal pair: not an injection
        df.iat[i, j] = d
        changed.append(int(i))
        kinds[int(i)] = "subtle" if subtle else "cross"
    return df, np.sort(changed), {"kinds": kinds}


# Templates the injector uses. HELD_OUT ones are phrased differently, so a detector that merely learned
# the template wording would miss them (we report recall on them separately).
CLOSED_SEEN = ["The {agency} closed this complaint.", "This request has been resolved and closed.",
               "The Department closed this complaint after review."]
PENDING_SEEN = ["This complaint is still being investigated.", "Your request is still pending and has not been reviewed.",
                "The agency is still working on this request."]
CLOSED_HELD = ["Crew finished the job at the address and the ticket needs nothing further.",
               "Case wrapped up by the responding unit; nothing outstanding."]
PENDING_HELD = ["Nobody has gone out to the location yet; the ticket sits in the queue.",
                "Report received, awaiting an inspector assignment."]


def inject_resolution_status(df, rate, rng, ctx):
    ids = _pick(rng, np.arange(len(df)), _count(len(df), rate))
    j = df.columns.get_loc("resolution_description")
    held_ids = []
    for i in ids:
        held = rng.random() < 0.3
        is_closed = df["status"].iat[i] == "Closed"
        pool = (PENDING_HELD if held else PENDING_SEEN) if is_closed else (CLOSED_HELD if held else CLOSED_SEEN)
        df.iat[i, j] = pool[int(rng.integers(len(pool)))].format(agency=df["agency"].iat[i])
        if held:
            held_ids.append(int(i))
    return df, ids, {"heldout_row_ids": held_ids}


def inject_pii(df, rate, rng, ctx, seed=0):
    fake = Faker("en_US")
    fake.seed_instance(int(seed))
    cand = np.flatnonzero(df["resolution_description"].notna().to_numpy())
    ids = _pick(rng, cand, _count(len(df), rate))
    j = df.columns.get_loc("resolution_description")
    kinds = {}
    for i in ids:
        digits = f"{int(rng.integers(200, 999))}555{int(rng.integers(0, 100)):02d}01"[:10]
        kind = str(rng.choice(["easy_phone", "easy_email", "hard_spaced", "hard_at_dot", "hard_name"]))
        if kind == "easy_phone":
            extra = f"Caller can be reached at {digits[:3]}-{digits[3:6]}-{digits[6:]}."
        elif kind == "easy_email":
            extra = f"Send updates to {fake.email()}."
        elif kind == "hard_spaced":
            extra = "Call back on " + " ".join(digits) + "."
        elif kind == "hard_at_dot":
            extra = f"Write to {fake.user_name()} at gmail dot com."
        else:
            extra = f"Complainant {fake.name()} spoke to the inspector."
        df.iat[i, j] = f"{df.iat[i, j]} {extra}"
        kinds[int(i)] = kind
    return df, ids, {"kinds": kinds}


INJECTORS = {
    "schema_column": inject_schema_column, "type_change": inject_type_change, "date_format": inject_date_format,
    "latlon_swap": inject_latlon_swap, "exact_dup": inject_exact_dup, "near_dup": inject_near_dup,
    "null_spike": inject_null_spike, "closed_before_created": inject_closed_before_created,
    "zip_borough": inject_zip_borough, "complaint_descriptor": inject_complaint_descriptor,
    "resolution_status": inject_resolution_status, "pii": inject_pii,
}


def inject(batch: pd.DataFrame, problem_type: str, rate: float, seed: int, ctx: InjectionContext):
    rng = np.random.default_rng(seed)
    df = batch.reset_index(drop=True).copy()
    if problem_type == "pii":
        out, ids, params = inject_pii(df, rate, rng, ctx, seed=seed)
    else:
        out, ids, params = INJECTORS[problem_type](df, rate, rng, ctx)
    level = "batch" if problem_type in BATCH_LEVEL else "row"
    truth = GroundTruth(problem_type, level, None if ids is None else [int(i) for i in ids], params)
    return out.reset_index(drop=True), truth
