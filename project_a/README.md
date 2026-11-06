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

## Decisions to be ready to defend
* **Rounding**: one module, `rounding.py`. Intermediates half-up to rupee; 288A income and 288B tax to nearest 10.
* **Interface additions**: `employer_nps` (80CCD(2), included) and `TraceLine.kind` (income vs tax lines so both totals can be checked).
* **87A marginal relief** is reported inside `rebate`; `marginal_relief` is surcharge relief only.
* **Impl C reuses impl A's engine** (documented): it measures compile quality of the data file, not arithmetic.
* **Impl B has no calculator tool**; rule text retrieved by topic (`rules_text/__init__.py`), no vector DB.
* **Cache key** = (model, temperature, system, schema, rule-text hash, prompt). `--no-cache` equivalent is `use_cache=False`, used only in the determinism test.
* **Parser split**: LLM extracts raw quotes + period; rules normalise units (`amounts.py`), look up metro city, detect contradictions, and ask ONE question (`validate.py`). Unmentioned deductions are never defaulted silently: either the person says "none", or we ask; partial mentions produce visible `assumptions`.

## Unverified until you act
Clause text/URLs (`make rules-check --strict`), metro list, surcharge tiers, official-calculator parity, Gemini limits and prices. See QUESTIONS.md. Nothing here claims "verified against the official calculator".
