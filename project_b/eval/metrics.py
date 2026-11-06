"""Metrics helpers: safe detector runs, flagged rows, deterministic explainability rubric, bootstrap CI."""
from __future__ import annotations

import numpy as np

from common import Alert


def safe_run(det, df, ref):
    """Run a detector; a crash becomes an error string instead of killing the whole evaluation."""
    try:
        return det(df, ref), None
    except Exception as e:  # noqa: BLE001
        return [], repr(e)


def flagged_rows(alerts: list[Alert]) -> set[int]:
    return {i for a in alerts if a.level == "row" for i in a.row_ids}


def explain_score(alert: Alert, columns: list[str]) -> int:
    """Deterministic rubric (0-2):
    0 = the explanation names no column;  1 = it names a column;
    2 = it names a column AND quotes the offending value or the expected value/rule (from evidence)."""
    text = alert.explanation.lower()
    if not any(c.lower() in text for c in columns if len(c) > 3):
        return 0
    ev = alert.evidence
    values = [str(ev[k]) for k in ("value", "expected", "rule") if ev.get(k) not in (None, "")]
    values += [v for v in ev.get("row_values", []) if len(v) > 2 and v != "nan"]   # LLM: any quoted row value
    return 2 if any(v.lower() in text for v in values) else 1


def bootstrap_ci(values, n: int = 1000, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap CI of the mean over batches."""
    v = np.asarray(values, float)
    if len(v) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = [rng.choice(v, len(v), replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
