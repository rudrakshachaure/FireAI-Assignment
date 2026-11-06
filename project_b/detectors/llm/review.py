"""Family (c): LLM review. Three modes:
  review_rows    one row per call (expensive)
  review_sample  N rows per call
  review_profile compact batch summary per call (batch-level problems)
  confirm_rows   used by the hybrid: re-check rows a cheap detector already flagged
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from common import COLUMNS, Alert
from detectors.llm.client import BatchVerdict, LLMClient, RowVerdict
from detectors.reference import Reference

SYSTEM = (
    "You review NYC 311 service-request records for data-quality problems. Typical problems: wrong or swapped "
    "coordinates, odd date formats, closed date before created date, ZIP code not matching the borough, "
    "complaint type not matching its descriptor, resolution text contradicting the status, duplicated records, and "
    "personal data (phone numbers, emails, person names) in free text. Only flag real problems; ordinary rows must "
    "not be flagged. In the reason, name the column and quote the offending value. Answer in JSON."
)

CHECK_HINTS = {
    "complaint_descriptor": "the descriptor may not belong to the complaint_type",
    "resolution_status": "the resolution_description may contradict the status",
    "near_dup": "the row may be a near duplicate of another record",
}


def render_row(row: pd.Series, cols: list[str]) -> str:
    return " | ".join(f"{c}={'null' if pd.isna(row[c]) else row[c]}" for c in cols if c in row.index)


class LLMReviewer:
    def __init__(self, client: LLMClient):
        self.client = client
        self.calls = self.in_tokens = self.out_tokens = self.cached_calls = self.unavailable = 0

    def _ask(self, prompt: str, schema):
        res = self.client.ask(prompt, schema)
        if res is None:
            self.unavailable += 1
            return None
        self.calls += 1
        self.in_tokens += res.in_tokens
        self.out_tokens += res.out_tokens
        self.cached_calls += int(res.cached)
        return json.loads(res.text)

    def usage(self) -> dict:
        return {"calls": self.calls, "in_tokens": self.in_tokens, "out_tokens": self.out_tokens,
                "cached_calls": self.cached_calls, "unavailable": self.unavailable}

    # ---- mode 1: one row per call ----
    def review_rows(self, batch: pd.DataFrame, row_ids: list[int]) -> list[Alert]:
        cols = [c for c in COLUMNS if c in batch.columns]
        alerts = []
        for i in row_ids:
            line = render_row(batch.iloc[i], cols)
            out = self._ask(f"{SYSTEM}\nRecord: {line}\nIs there a data-quality problem in this record?", RowVerdict)
            if out and out["flag"]:
                alerts.append(Alert("llm_any", "row", [int(i)], 1.0, out["reason"],
                                    {"row_values": [str(batch.iloc[i][c]) for c in cols]}))
        return alerts

    # ---- mode 2: N sampled rows per call ----
    def review_sample(self, batch: pd.DataFrame, row_ids: list[int], group: int = 20) -> list[Alert]:
        return self._grouped(batch, row_ids, group, "Which of these records have a data-quality problem?")

    def review_pii(self, batch: pd.DataFrame, row_ids: list[int], group: int = 20) -> list[Alert]:
        q = "Which of these records contain personal data (phone numbers, emails, person names) in a text field?"
        return self._grouped(batch, row_ids, group, q, ptype="pii")

    def confirm_rows(self, batch: pd.DataFrame, row_ids: list[int], ptype: str) -> tuple[list[int], str] | None:
        """Returns (confirmed row ids, reason) or None if the LLM could not be called."""
        hint = CHECK_HINTS.get(ptype, "the rows may have a data-quality problem")
        before = self.unavailable
        alerts = self._grouped(batch, row_ids, len(row_ids),
                               f"A cheap check flagged these rows: {hint}. Which rows really have the problem?",
                               ptype=ptype)
        if self.unavailable > before:
            return None
        ids = [i for a in alerts for i in a.row_ids]
        return ids, (alerts[0].explanation if alerts else "LLM did not confirm the flagged rows")

    def _grouped(self, batch, row_ids, group, question, ptype="llm_any") -> list[Alert]:
        cols = [c for c in COLUMNS if c in batch.columns]
        alerts = []
        for s in range(0, len(row_ids), group):
            ids = [int(i) for i in row_ids[s:s + group]]
            lines = "\n".join(f"[row {i}] {render_row(batch.iloc[i], cols)}" for i in ids)
            out = self._ask(f"{SYSTEM}\n{question}\nRecords:\n{lines}\nReturn flag, reason and bad_rows "
                            "(the numbers in [row N]).", BatchVerdict)
            if out and out["flag"]:
                bad = [i for i in out["bad_rows"] if i in set(ids)]
                if bad:
                    alerts.append(Alert(ptype, "row", bad, 1.0, out["reason"],
                                        {"row_values": [str(batch.iloc[bad[0]][c]) for c in cols]}))
        return alerts

    # ---- mode 3: compact profile for batch-level problems ----
    def review_profile(self, batch: pd.DataFrame, ref: Reference) -> list[Alert]:
        prof = "; ".join(f"{c} ({batch[c].dtype.kind}, {batch[c].isna().mean():.0%} null)" for c in batch.columns)
        by_agency = batch.isna().groupby(batch["agency"]).mean() if "agency" in batch.columns else None
        worst = ""
        if by_agency is not None:
            top = by_agency.stack().sort_values(ascending=False).head(5)
            worst = "; ".join(f"{a}/{c}: {v:.0%} null" for (a, c), v in top.items())
        sample = "\n".join(render_row(batch.iloc[i], list(batch.columns))
                           for i in np.linspace(0, len(batch) - 1, 3).astype(int))
        prompt = (f"{SYSTEM}\nExpected schema: {ref.profile_text}\nThis batch ({len(batch)} rows): {prof}\n"
                  f"Highest null shares by agency/column: {worst}\nSample rows:\n{sample}\n"
                  "Does the batch look structurally wrong (missing or renamed columns, wrong types, abnormal null "
                  "shares)? Return flag, reason and bad_rows (empty list).")
        out = self._ask(prompt, BatchVerdict)
        if out and out["flag"]:
            return [Alert("llm_any", "batch", [], 1.0, out["reason"], {"row_values": []})]
        return []
