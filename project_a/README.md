# Project A: Rules vs LLMs, India salaried income tax

Run from the repo root (the folder containing `project_a/`).

```
pip install -r requirements.txt
make all            # tests + impl A (+ C if frozen) + summary, no API key needed
export GEMINI_API_KEY=...
make all-llm        # also impl B (sampled) + parser eval, cached in .cache/llm
python -m streamlit run project_a/app.py
```

## Status vs the brief
| Task | State |
|---|---|
| 1 Test suite | `tests/oracle.py` + `tests/gen_cases.py` -> 221 cases in `data/tests_200.jsonl`; 50 NL cases (16 clarification) in `data/nl_descriptions_50.jsonl`; `data/official_calc_checks.csv` has 36 rows **[HUMAN] fill official columns**, then `make official-check` |
| 2a Impl A | done, 221/221 vs oracle |
| 2b Impl B | code written, **not run** (needs key + quota) |
| 2c Impl C | `compile_rules.py` + `review_diff.py` + `REVIEW.md` template; **[HUMAN] review -> copy to `frozen/`** |
| 3 Parser | LLM extraction + rule validation; deterministic layer unit-tested; LLM part **not run** |
| 4 Eval | `eval/run_eval.py`, `parser_eval.py`, `report.py`; only impl A measured |
| 5 FY 2025-26 | not started on purpose (stopwatch helper in `changes_fy2526/`) |
| 6 RESULTS_A.md | skeleton only; paste numbers from `eval/out/summary.md` |

