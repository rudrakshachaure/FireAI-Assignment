# Project B: Rules vs LLMs for data quality (NYC 311, 2023)

A data-quality layer that sits in front of dashboards. For 12 problem types it compares three detector families
(rules, statistics/ML, Gemini LLM), then combines the winners into a hybrid pipeline and projects its cost to
50M rows/day x 120 customers.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate     # Python 3.10+
pip install -r requirements.txt
export GEMINI_API_KEY=...        # optional: without it the LLM rows say "not run" and everything else still works
make test                        # unit tests on tiny synthetic data, no download needed
make all PER_MONTH_LIMIT=20000   # quick trial: ~240k rows, minutes on a laptop
make all                         # full 2023 (~3M rows, needs ~4 GB RAM and a long download)
python -m streamlit run app.py
```

## Where things are

| Path | What it does |
|---|---|
| `common.py`, `patterns.py` | config, prices, `Alert`/`GroundTruth`, helpers, regexes |
| `ingest/download_311_2023.py` | Socrata download, one parquet file per page, resumable |
| `profile/profile_raw.py` | Task 1: ranked real issues, clean definition, reference/held-out split |
| `injector/injectors.py` | Task 2: the 12 injectors (`inject(batch, type, rate, seed, ctx)`) |
| `detectors/rules/checks.py` | family (a): rules and schema checks |
| `detectors/stats/` | family (b): models (fit on reference only) + detectors |
| `detectors/llm/` | family (c): Gemini client (cache, backoff, token log) + review modes |
| `eval/run_eval.py`, `eval/run_llm_eval.py` | Task 4: metrics, false alarms + CI, throughput, cost, explainability |
| `pipeline/hybrid.py` | Task 5: hybrid + ablation + budget controls |
| `eval/scale.py`, `eval/make_results.py` | Task 6 numbers, `RESULTS_B.md`, `DECISION_MATRIX.md`, heatmap |

