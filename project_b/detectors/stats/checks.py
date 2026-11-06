"""Family (b): statistical / ML detectors. Every function: (df, ref) -> list[Alert]."""
from __future__ import annotations

from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from common import Alert, norm_text, parse_dt
from detectors.reference import Reference
from detectors.stats.models import null_spike_cells


def _score_alert(ptype: str, scores: np.ndarray, thr: float, df: pd.DataFrame, col: str, what) -> list[Alert]:
    s = np.nan_to_num(scores, nan=-np.inf)
    ids = np.flatnonzero(s > thr)
    if len(ids) == 0:
        return []
    i = int(ids[np.argmax(s[ids])])
    text = f"{len(ids)} rows: {what(i)} (score {s[i]:.2f} > threshold {thr:.2f})"
    return [Alert(ptype, "row", [int(x) for x in ids], float(s[i]), text,
                  {"column": col, "value": str(df[col].iat[i]), "expected": f"score <= {thr:.2f}"})]


def schema_column(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    """Column-set difference, plus a 'looks like renamed X' guess using null-rate / text-length profiles."""
    unknown = [c for c in df.columns if c not in ref.columns]
    missing = [c for c in ref.columns if c not in df.columns]
    if not unknown and not missing:
        return []
    guesses = {}
    for u in unknown:
        p = ref.stats.profile(df[u])
        dist = lambda m: abs(p[0] - ref.stats.col_profile[m][0]) * 10 + abs(p[1] - ref.stats.col_profile[m][1]) / max(p[1], 1)  # noqa: E731
        if missing:
            guesses[u] = min(missing, key=dist)
    text = f"unexpected columns {unknown} (profile suggests {guesses}), missing columns {missing}"
    return [Alert("schema_column", "batch", [], float(len(unknown) + len(missing)), text,
                  {"column": (missing + unknown)[0], "value": str(unknown), "expected": str(missing)})]


def type_change(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    """Share of python value types per column vs reference (L1 distance)."""
    alerts = []
    for c in ref.columns:
        if c not in df.columns:
            continue
        share = df[c].dropna().map(lambda v: type(v).__name__).value_counts(normalize=True).to_dict()
        ref_share = ref.stats.type_share[c]
        dist = sum(abs(share.get(k, 0) - ref_share.get(k, 0)) for k in set(share) | set(ref_share))
        if dist > 0.5:
            text = f"column {c} value types are {share}, reference was {ref_share}"
            alerts.append(Alert("type_change", "batch", [], float(dist), text,
                                {"column": c, "value": str(share), "expected": str(ref_share)}))
    return alerts


def date_format(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    """Rows whose created_date 'shape' is rare or unseen in the reference."""
    s = df["created_date"]
    if s.dtype.kind == "M":
        return []
    shape = s.astype(str).str.replace(r"\d", "d", regex=True)
    freq = shape.map(ref.stats.shape_freq).fillna(0).to_numpy()
    return _score_alert("date_format", 1 - freq, 1 - 1e-4, df, "created_date", lambda i: f"date shape {shape.iat[i]!r} is rare in reference")


def latlon_swap(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    return _score_alert("latlon_swap", ref.stats.score_latlon(df), ref.stats.thr["latlon"], df, "latitude",
                        lambda i: f"(latitude, longitude) = ({df.latitude.iat[i]}, {df.longitude.iat[i]}) is an outlier")


def _fuzzy_dups(df: pd.DataFrame, ptype: str, max_gap_s: float, min_ratio: float) -> list[Alert]:
    """Blocking by (agency, ZIP); inside a block compare each row with earlier rows (time gap + text ratio)."""
    text = (df.complaint_type.astype(str) + "|" + norm_text(df.descriptor) + "|" + norm_text(df.incident_address) +
            "|" + df.borough.astype(str))
    t = parse_dt(df.created_date).astype("int64").to_numpy() / 1e9
    block = (df.agency.astype(str) + "|" + df.incident_zip.astype(str)).to_numpy()
    flagged = []
    for b in pd.unique(block):
        pos = np.flatnonzero(block == b)
        for a in range(1, len(pos)):
            for p in range(a):
                if abs(t[pos[a]] - t[pos[p]]) <= max_gap_s and \
                        SequenceMatcher(None, text.iat[pos[a]], text.iat[pos[p]]).ratio() >= min_ratio:
                    flagged.append(int(pos[a]))
                    break
    if not flagged:
        return []
    i = flagged[0]
    return [Alert(ptype, "row", flagged, min_ratio, f"{len(flagged)} rows: row {i} is a fuzzy copy of an earlier row in the same ZIP block",
                  {"column": "descriptor", "value": str(df.descriptor.iat[i]), "rule": f"text similarity >= {min_ratio}"})]


def exact_dup(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    return _fuzzy_dups(df, "exact_dup", max_gap_s=0, min_ratio=1.0)


def near_dup(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    return _fuzzy_dups(df, "near_dup", max_gap_s=1800, min_ratio=0.9)


def null_spike(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    """Per-agency z-test of null share vs reference, with a minimum jump of 5 points."""
    alerts = []
    for c in null_spike_cells(df, ref.stats.agency_rate, ref.stats.global_rate):
        if c["z"] > ref.stats.thr["null_z"] and c["share"] - c["p0"] > 0.05:
            ids = np.flatnonzero((df["agency"] == c["agency"]).to_numpy() & df[c["column"]].isna().to_numpy())
            text = (f"agency {c['agency']}: column {c['column']} is {c['share']:.0%} null "
                    f"(reference {c['p0']:.1%}), z={c['z']:.1f}")
            alerts.append(Alert("null_spike", "batch", [int(i) for i in ids], c["z"], text,
                                {"column": c["column"], "value": f"{c['share']:.0%}", "expected": f"{c['p0']:.1%}"}))
    return alerts


def closed_before_created(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    created, closed = parse_dt(df.created_date), parse_dt(df.closed_date)
    return _score_alert("closed_before_created", ref.stats.score_duration(df), ref.stats.thr["duration"], df,
                        "closed_date", lambda i: f"duration {closed.iat[i] - created.iat[i]} is an outlier")


def zip_borough(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    return _score_alert("zip_borough", ref.stats.score_zip(df), ref.stats.thr["zip_dist"], df, "incident_zip",
                        lambda i: f"point is far (km) from the usual location of ZIP {df.incident_zip.iat[i]}")


def complaint_descriptor(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    return _score_alert("complaint_descriptor", ref.stats.score_desc(df), ref.stats.thr["desc"], df, "descriptor",
                        lambda i: f"descriptor {df.descriptor.iat[i]!r} rarely goes with {df.complaint_type.iat[i]!r}")


def resolution_status(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    return _score_alert("resolution_status", ref.stats.score_res(df), ref.stats.thr["res"], df, "resolution_description",
                        lambda i: f"resolution text looks inconsistent with status {df.status.iat[i]!r}")


def pii(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    return _score_alert("pii", ref.stats.score_pii(df), ref.stats.thr["pii"], df, "resolution_description",
                        lambda i: "free text has an unusual digit / capitalised-word pattern")
