"""Task 4 (LLM family): per-row, batch-sample and profile modes on SAMPLES (free-tier quotas).

For every row-level problem: 1 batch is corrupted at 5%; we review K_POS affected + K_NEG unaffected rows.
Env: LLM_K_POS / LLM_K_NEG (default 20/20), LLM_GROUP (rows per call in sample mode, default 10), LLM_RPM.
Without GEMINI_API_KEY (and without cached answers) the rows are written with status 'not run'.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from common import BATCH_LEVEL, BATCH_SIZE, OUT_DIR, PROBLEMS, SEED, load_batches
from detectors.llm.client import LLMClient
from detectors.llm.review import LLMReviewer
from detectors.reference import get_reference
from eval.metrics import explain_score
from injector import build_context, inject

K_POS, K_NEG = int(os.getenv("LLM_K_POS", "20")), int(os.getenv("LLM_K_NEG", "20"))
GROUP = int(os.getenv("LLM_GROUP", "10"))


def delta(after: dict, before: dict) -> dict:
    return {k: after[k] - before[k] for k in after}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    held, ref = load_batches("heldout"), get_reference()
    ctx = build_context(pd.concat(load_batches("reference"), ignore_index=True))
    rev, rng, rows = LLMReviewer(LLMClient()), np.random.default_rng(SEED), []

    def record(ptype, mode, n_pos, n_neg, tp, fp, use, rows_per_call, expl):
        ok = use["unavailable"] == 0
        rows.append({"problem_type": ptype, "mode": mode, "n_pos": n_pos, "n_neg": n_neg,
                     "recall": tp / n_pos if ok else np.nan, "fpr": fp / n_neg if ok else np.nan,
                     "calls": use["calls"], "in_tokens": use["in_tokens"], "out_tokens": use["out_tokens"],
                     "rows_per_call": rows_per_call, "explain_mean": float(np.mean(expl)) if expl else np.nan,
                     "status": "ok" if ok else "not run (no GEMINI_API_KEY and no cached answer)"})

    for ptype in [p for p in PROBLEMS if p not in BATCH_LEVEL]:
        bad, truth = inject(held[0], ptype, 0.05, SEED, ctx)
        tr = np.array(truth.row_ids)
        pos = rng.choice(tr, min(K_POS, len(tr)), replace=False)
        neg = rng.choice(np.setdiff1d(np.arange(len(bad)), tr), K_NEG, replace=False)
        ids = [int(i) for i in rng.permutation(np.concatenate([pos, neg]))]
        extra = []   # duplicates need to SEE the partner row: add the originals in sample mode
        if ptype in ("exact_dup", "near_dup"):
            src = dict(zip(truth.row_ids, truth.params["source_rows"]))
            extra = [int(src[int(i)]) for i in pos]
        for mode, run, rpc in (("per_row", lambda: rev.review_rows(bad, ids), 1),
                               ("batch_sample", lambda: rev.review_sample(bad, ids + extra, GROUP), GROUP)):
            before = rev.usage()
            alerts = run()
            use = delta(rev.usage(), before)
            flagged = {i for a in alerts for i in a.row_ids}
            expl = [explain_score(a, list(bad.columns)) for a in alerts if set(a.row_ids) & set(map(int, pos))]
            record(ptype, mode, len(pos), len(neg), len(flagged & set(map(int, pos))),
                   len(flagged & set(map(int, neg))), use, rpc, expl)
            print(rows[-1])

    for ptype in [p for p in PROBLEMS if p in BATCH_LEVEL]:
        before, tp, fp, expl = rev.usage(), 0, 0, []
        for i in range(3):
            bad, _ = inject(held[i], ptype, 0.05, SEED + i, ctx)
            a = rev.review_profile(bad, ref)
            tp += len(a) > 0
            expl += [explain_score(x, list(bad.columns)) for x in a]
            fp += len(rev.review_profile(held[i], ref)) > 0
        record(ptype, "profile", 3, 3, tp, fp, delta(rev.usage(), before), BATCH_SIZE, expl)
        print(rows[-1])
    pd.DataFrame(rows).to_csv(OUT_DIR / "llm_results.csv", index=False)


if __name__ == "__main__":
    main()
