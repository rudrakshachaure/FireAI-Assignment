import json

import numpy as np

import detectors.llm.client as client_mod
from common import Alert
from detectors.llm.client import BatchVerdict, LLMClient, RowVerdict
from detectors.llm.review import LLMReviewer
from eval.metrics import bootstrap_ci, explain_score
from pipeline.hybrid import choose_plan


def fake_call(prompt, schema):
    if schema is RowVerdict:
        return json.dumps({"flag": True, "reason": "descriptor looks wrong"}), 100, 20
    return json.dumps({"flag": True, "reason": "row 1 bad", "bad_rows": [1]}), 200, 30


def test_cache_and_token_counts(tmp_path, monkeypatch, batches):
    monkeypatch.setattr(client_mod, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(client_mod, "OUT_DIR", tmp_path / "out")
    c = LLMClient(call_fn=fake_call)
    first, second = c.ask("hello", RowVerdict), c.ask("hello", RowVerdict)
    assert not first.cached and second.cached and second.in_tokens == 100
    rev = LLMReviewer(c)
    alerts = rev.review_sample(batches[0], [0, 1, 2], group=3)
    assert alerts[0].row_ids == [1]
    assert rev.usage()["calls"] == 1 and rev.usage()["in_tokens"] == 200
    assert BatchVerdict  # schema exists


def test_no_key_no_cache_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(client_mod, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert LLMClient().ask("x", RowVerdict) is None


def test_explain_rubric():
    cols = ["latitude", "descriptor"]
    none = Alert("x", "row", [1], 1, "something is odd", {"value": "abc"})
    col_only = Alert("x", "row", [1], 1, "latitude is odd", {"value": "abc"})
    full = Alert("x", "row", [1], 1, "latitude abc is odd", {"value": "abc"})
    assert [explain_score(a, cols) for a in (none, col_only, full)] == [0, 1, 2]


def test_bootstrap_ci_contains_mean():
    lo, hi = bootstrap_ci([0, 1, 2, 3, 4])
    assert lo <= 2 <= hi and not np.isnan(lo)


def test_choose_plan_prefers_rules_on_ties():
    import pandas as pd
    from common import PROBLEMS
    rows = [{"problem_type": p, "family": f, "rate": 0.05, "recall": 0.9, "precision": 0.9}
            for p in PROBLEMS for f in ("rules", "stats")]
    plan, _ = choose_plan(pd.DataFrame(rows))
    assert set(plan.values()) == {"rules"}
