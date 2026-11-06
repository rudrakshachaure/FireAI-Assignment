"""Task 1: profile the raw 2023 data, rank the REAL issues, build the clean set and split it.

Outputs (profile/out/): null_rate_by_column.csv, null_rate_by_agency.csv, real_issues.csv,
real_issue_examples.csv (redacted), REAL_ISSUES.md, clean_summary.json
Also writes data/clean/reference.parquet and data/clean/heldout.parquet.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from common import (BATCH_SIZE, BOROUGHS, CLEAN_DIR, COLUMNS, CRITICAL, NYC_BBOX, PROFILE_OUT, RAW_DIR,
                    SEED, TEXT_COLS, km, modal_map, norm_text, to_typed)
from patterns import (AT_DOT, CLOSED_WORDS, EMAIL, ISO_DT, MOJIBAKE, PENDING_WORDS, PHONE, SPACED_DIGITS,
                      ZIP5)


def redact(text):
    if not isinstance(text, str):
        return text
    for pat, tag in ((PHONE, "[PHONE]"), (EMAIL, "[EMAIL]"), (SPACED_DIGITS, "[DIGITS]")):
        text = pat.sub(tag, text)
    return text


def build_masks(raw: pd.DataFrame, t: pd.DataFrame) -> dict[str, tuple[pd.Series, str]]:
    """One boolean mask per issue (True = row has the issue) plus the check family that would catch it."""
    masks: dict[str, tuple[pd.Series, str]] = {}

    def add(name: str, mask: pd.Series, family: str) -> None:
        masks[name] = (mask.fillna(False).astype(bool), family)

    for c in CRITICAL:
        add(f"null {c}", raw[c].isna(), "rules (null contract)")
    add("created_date not ISO format", raw.created_date.notna() & ~raw.created_date.astype(str).str.match(ISO_DT),
        "rules (regex)")
    add("lat/long not numeric", (raw.latitude.notna() & t.latitude.isna()) | (raw.longitude.notna() & t.longitude.isna()),
        "rules (dtype)")
    add("closed < created", t.closed_date < t.created_date, "rules (cross-column)")
    add("closed date in the future", t.closed_date > pd.Timestamp.now(), "rules (cross-column)")
    la0, la1, lo0, lo1 = NYC_BBOX
    has_geo = t.latitude.notna() & t.longitude.notna()
    outside = has_geo & ~(t.latitude.between(la0, la1) & t.longitude.between(lo0, lo1))
    add("lat/long zero or outside NYC", outside | (has_geo & ((t.latitude == 0) | (t.longitude == 0))),
        "rules (range) / stats (isolation forest)")
    med = t[has_geo & ~outside].groupby("borough")[["latitude", "longitude"]].median()
    cen = med.reindex(t.borough)
    far = km(t.latitude.to_numpy(), t.longitude.to_numpy(), cen.latitude.to_numpy(), cen.longitude.to_numpy()) > 25
    add("lat/long far from borough centre (>25 km)", pd.Series(far, index=raw.index) & has_geo, "stats (distance)")
    add("invalid ZIP format", raw.incident_zip.notna() & ~raw.incident_zip.astype(str).str.match(ZIP5), "rules (regex)")
    zmap = modal_map(raw, "incident_zip", "borough")
    exp = raw.incident_zip.map(zmap)
    add("ZIP inconsistent with borough", exp.notna() & raw.borough.notna() & (exp != raw.borough),
        "rules (reference map)")
    add("borough missing/unknown", raw.borough.isna() | ~raw.borough.isin(BOROUGHS), "rules (allowed values)")
    add("exact duplicate row", raw.duplicated(keep="first"), "rules (hash)")
    add("duplicate unique_key", raw.duplicated("unique_key", keep="first"), "rules (hash)")
    near_key = pd.DataFrame({
        "a": raw.agency, "c": raw.complaint_type, "d": norm_text(raw.descriptor), "z": raw.incident_zip,
        "ad": norm_text(raw.incident_address), "la": t.latitude.round(4), "lo": t.longitude.round(4),
        "h": t.created_date.dt.floor("h"),
    })
    add("near duplicate (same content, same hour, new key)", near_key.duplicated(keep="first") & t.latitude.notna(),
        "stats (blocking + fuzzy)")
    pair_n = t.groupby(["complaint_type", "descriptor"])["unique_key"].transform("size")
    add("rare complaint_type/descriptor pair (<3 rows)", pair_n < 3, "rules (reference pairs) / stats (TF-IDF+LR)")
    closed = raw.status.eq("Closed")
    add("Status=Closed but closed_date null", closed & t.closed_date.isna(), "rules (cross-column)")
    add("Status!=Closed but closed_date present", ~closed & raw.status.notna() & t.closed_date.notna(),
        "rules (cross-column)")
    res = raw.resolution_description.fillna("")
    add("resolution text contradicts status",
        (closed & res.str.contains(PENDING_WORDS)) | (~closed & res.str.contains(CLOSED_WORDS)),
        "stats (TF-IDF+LR) / LLM")
    ws = pd.Series(False, index=raw.index)
    moj = pd.Series(False, index=raw.index)
    for c in TEXT_COLS:
        s = raw[c].dropna().astype(str)
        ws.loc[s.index] = ws.loc[s.index] | (s != s.str.strip()) | s.str.contains("  ")
        moj.loc[s.index] = moj.loc[s.index] | s.str.contains(MOJIBAKE)
    add("leading/trailing/double whitespace", ws, "rules (regex)")
    add("encoding garbage (mojibake)", moj, "rules (regex)")
    add("borough not upper-case", raw.borough.notna() & (raw.borough != raw.borough.str.upper()), "rules (regex)")
    free = raw.descriptor.fillna("") + " " + raw.resolution_description.fillna("")
    add("PII-like: phone number in free text", free.str.contains(PHONE) | free.str.contains(SPACED_DIGITS),
        "rules (regex)")
    add("PII-like: email in free text", free.str.contains(EMAIL) | free.str.contains(AT_DOT), "rules (regex)")
    return masks


def main() -> None:
    PROFILE_OUT.mkdir(parents=True, exist_ok=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(RAW_DIR / "311_2023.parquet")
    n = len(raw)
    t = to_typed(raw)

    raw.isna().mean().rename("null_rate").to_csv(PROFILE_OUT / "null_rate_by_column.csv")
    raw.isna().groupby(raw["agency"]).mean().to_csv(PROFILE_OUT / "null_rate_by_agency.csv")

    masks = build_masks(raw, t)
    rows, examples = [], []
    for name, (mask, family) in masks.items():
        keys = raw.loc[mask, "unique_key"].head(3).tolist()
        rows.append({"issue": name, "count": int(mask.sum()), "pct": round(100 * mask.mean(), 4),
                     "example_unique_keys": ", ".join(map(str, keys)), "proposed_check_family": family})
        ex = t.loc[mask, COLUMNS].head(3).copy()
        for c in ("descriptor", "resolution_description"):
            ex[c] = ex[c].map(redact)  # never write real-looking PII to disk
        ex.insert(0, "issue", name)
        examples.append(ex)
    issues = pd.DataFrame(rows).sort_values("count", ascending=False)
    issues.to_csv(PROFILE_OUT / "real_issues.csv", index=False)
    pd.concat(examples).to_csv(PROFILE_OUT / "real_issue_examples.csv", index=False)

    # ---- clean set: a row is clean if it has NONE of the issues above ----
    bad = pd.concat([m for m, _ in masks.values()], axis=1).any(axis=1)
    clean = t[~bad].sort_values("created_date").reset_index(drop=True)
    n_batches = len(clean) // BATCH_SIZE
    if n_batches < 4:
        raise SystemExit(f"Only {n_batches} clean batches of {BATCH_SIZE}; lower BATCH_SIZE or download more rows.")
    clean = clean.iloc[: n_batches * BATCH_SIZE]
    order = np.random.RandomState(SEED).permutation(n_batches)   # random assignment of whole batches
    half = n_batches // 2
    for name, ids in (("reference", np.sort(order[:half])), ("heldout", np.sort(order[half:]))):
        part = pd.concat([clean.iloc[i * BATCH_SIZE:(i + 1) * BATCH_SIZE] for i in ids], ignore_index=True)
        part.to_parquet(CLEAN_DIR / f"{name}.parquet", index=False)
        print(f"{name}: {len(ids)} batches, {len(part):,} rows")
    (CLEAN_DIR / "reference_model.joblib").unlink(missing_ok=True)  # old fitted model is now stale

    summary = {"raw_rows": n, "clean_rows_used": len(clean), "batch_size": BATCH_SIZE, "n_batches": n_batches,
               "reference_batches": half, "heldout_batches": n_batches - half, "rows_with_any_issue": int(bad.sum())}
    (PROFILE_OUT / "clean_summary.json").write_text(json.dumps(summary, indent=2))

    md = ["# REAL_ISSUES: problems found in the raw 2023 data\n", f"Raw rows: {n:,}\n",
          issues.to_markdown(index=False), "\n## How 'clean' is defined\n",
          "A row is CLEAN only if it has none of the issues in the table above (every line is treated as an issue). "
          f"That leaves {len(clean):,} rows ({100 * len(clean) / n:.1f}% of raw), sorted by created_date and cut into "
          f"consecutive batches of {BATCH_SIZE}. Whole batches are randomly assigned (seed {SEED}) to REFERENCE "
          "(learn maps, fit models, tune thresholds) or HELDOUT (evaluation only, never tuned on).\n",
          "False-alarm rates are measured on this clean set, so real issues that our definition removes cannot cause "
          "false alarms. This makes false-alarm numbers optimistic compared with raw production data.\n"]
    (PROFILE_OUT / "REAL_ISSUES.md").write_text("\n".join(md))
    print(issues.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
