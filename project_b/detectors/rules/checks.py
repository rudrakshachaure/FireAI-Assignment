"""Family (a): rules / schema. Cheap, deterministic, explainable. Every function: (df, ref) -> list[Alert]."""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import NYC_BBOX, Alert, norm_text, parse_dt
from detectors.reference import Reference
from patterns import AT_DOT, CLOSED_WORDS, EMAIL, ISO_DT, PENDING_WORDS, PHONE, SPACED_DIGITS


def _row_alert(ptype: str, mask, df: pd.DataFrame, text_fn, **evidence) -> list[Alert]:
    """One alert holding all flagged rows; the explanation describes the first flagged row."""
    ids = np.flatnonzero(np.asarray(mask))
    if len(ids) == 0:
        return []
    text, ev = text_fn(int(ids[0]))
    return [Alert(ptype, "row", [int(i) for i in ids], 1.0, f"{len(ids)} rows: {text}", {**evidence, **ev})]


def schema_column(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    missing = [c for c in ref.columns if c not in df.columns]
    extra = [c for c in df.columns if c not in ref.columns]
    if not missing and not extra:
        return []
    text = f"column contract broken: missing columns {missing}, unexpected columns {extra}"
    return [Alert("schema_column", "batch", [], 1.0, text,
                  {"column": (missing + extra)[0], "value": str(extra), "expected": str(missing)})]


def type_change(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    alerts = []
    for c in ref.columns:
        if c in df.columns and df[c].dtype.kind != ref.dtype_kinds[c]:
            text = f"column {c} has dtype kind '{df[c].dtype.kind}' but the contract says '{ref.dtype_kinds[c]}'"
            alerts.append(Alert("type_change", "batch", [], 1.0, text,
                                {"column": c, "value": df[c].dtype.kind, "expected": ref.dtype_kinds[c]}))
    return alerts


def date_format(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    s = df["created_date"]
    if s.dtype.kind == "M":
        return []
    bad = s.notna() & ~s.astype(str).str.match(ISO_DT)
    return _row_alert("date_format", bad, df, lambda i: (
        f"created_date {s.iat[i]!r} is not ISO 8601 (expected like 2023-05-01T12:30:00)",
        {"column": "created_date", "value": str(s.iat[i]), "expected": "YYYY-MM-DDTHH:MM:SS"}))


def latlon_swap(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    lat, lon = pd.to_numeric(df.latitude, errors="coerce"), pd.to_numeric(df.longitude, errors="coerce")
    la0, la1, lo0, lo1 = NYC_BBOX
    in_box = lat.between(la0, la1) & lon.between(lo0, lo1)
    swapped_in_box = lon.between(la0, la1) & lat.between(lo0, lo1)
    return _row_alert("latlon_swap", ~in_box & swapped_in_box, df, lambda i: (
        f"latitude {lat.iat[i]} and longitude {lon.iat[i]} look swapped (latitude should be {la0}..{la1})",
        {"column": "latitude", "value": str(lat.iat[i]), "expected": f"{la0}..{la1}"}))


def exact_dup(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    hashes = pd.util.hash_pandas_object(df, index=False)
    dup = hashes.duplicated(keep="first")
    return _row_alert("exact_dup", dup, df, lambda i: (
        f"row repeats an earlier row exactly (unique_key {df['unique_key'].iat[i]})",
        {"column": "unique_key", "value": str(df["unique_key"].iat[i]), "rule": "row hash must be unique"}))


def near_dup(df: pd.DataFrame, ref: Reference, gap_s: int = 900) -> list[Alert]:
    """Same agency/type/descriptor/address/lat/long after lower-casing + whitespace cleanup, within 15 min."""
    key = (df.agency.astype(str) + "|" + df.complaint_type.astype(str) + "|" + norm_text(df.descriptor) + "|" +
           norm_text(df.incident_address) + "|" + pd.to_numeric(df.latitude, errors="coerce").round(4).astype(str) +
           "|" + pd.to_numeric(df.longitude, errors="coerce").round(4).astype(str))
    d = pd.DataFrame({"k": key, "t": parse_dt(df.created_date), "pos": np.arange(len(df))})
    first_pos = d.groupby("k")["pos"].transform("min")
    first_t = d.groupby("k")["t"].transform("first")
    close = (d.t - first_t).abs().dt.total_seconds() <= gap_s
    return _row_alert("near_dup", (d.pos != first_pos) & close, df, lambda i: (
        f"row {i} (created_date {d.t.iat[i]}) has the same content as an earlier row within {gap_s}s",
        {"column": "created_date", "value": str(d.t.iat[i]), "rule": f"same content within {gap_s}s"}))


def null_spike(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    alerts, rates = [], df.isna().mean()
    for c in ref.columns:
        if c in df.columns and rates[c] > ref.null_limit[c]:
            ids = np.flatnonzero(df[c].isna().to_numpy())
            text = f"column {c} is {rates[c]:.1%} null, above the reference limit {ref.null_limit[c]:.1%}"
            alerts.append(Alert("null_spike", "batch", [int(i) for i in ids], float(rates[c]), text,
                                {"column": c, "value": f"{rates[c]:.1%}", "expected": f"{ref.null_limit[c]:.1%}"}))
    return alerts


def closed_before_created(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    created, closed = parse_dt(df.created_date), parse_dt(df.closed_date)
    return _row_alert("closed_before_created", closed < created, df, lambda i: (
        f"closed_date {closed.iat[i]} is before created_date {created.iat[i]}",
        {"column": "closed_date", "value": str(closed.iat[i]), "expected": f">= {created.iat[i]}"}))


def zip_borough(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    exp = df.incident_zip.map(ref.zip_borough)
    bad = exp.notna() & df.borough.notna() & (exp != df.borough)
    return _row_alert("zip_borough", bad, df, lambda i: (
        f"incident_zip {df.incident_zip.iat[i]} belongs to {exp.iat[i]} but borough is {df.borough.iat[i]}",
        {"column": "incident_zip", "value": str(df.incident_zip.iat[i]), "expected": str(exp.iat[i])}))


def complaint_descriptor(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    unseen = np.array([p not in ref.pairs for p in zip(df.complaint_type, df.descriptor)])
    return _row_alert("complaint_descriptor", unseen, df, lambda i: (
        f"descriptor {df.descriptor.iat[i]!r} was never seen with complaint_type {df.complaint_type.iat[i]!r}",
        {"column": "descriptor", "value": str(df.descriptor.iat[i]), "expected": "a pair seen in clean data"}))


def resolution_status(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    closed = df.status.eq("Closed")
    res = df.resolution_description.fillna("")
    bad = (closed & res.str.contains(PENDING_WORDS)) | (~closed & res.str.contains(CLOSED_WORDS))
    return _row_alert("resolution_status", bad, df, lambda i: (
        f"resolution_description says {res.iat[i][:60]!r} but status is {df.status.iat[i]!r}",
        {"column": "resolution_description", "value": res.iat[i][:60], "expected": f"text consistent with {df.status.iat[i]}"}))


def pii(df: pd.DataFrame, ref: Reference) -> list[Alert]:
    text = df.descriptor.fillna("") + " " + df.resolution_description.fillna("")
    hit = pd.Series(False, index=df.index)
    for pat in (PHONE, SPACED_DIGITS, EMAIL, AT_DOT):
        hit |= text.str.contains(pat)

    def why(i: int):
        m = next(m for p in (PHONE, SPACED_DIGITS, EMAIL, AT_DOT) if (m := p.search(text.iat[i])))
        return (f"resolution_description contains personal data pattern {m.group(0)!r}",
                {"column": "resolution_description", "value": m.group(0), "rule": "no phone numbers or emails"})
    return _row_alert("pii", hit, df, why)
