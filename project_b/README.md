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

`make all` = `download -> profile -> eval -> llm -> hybrid -> results`. Each step can run alone (`make eval`, ...).
If you change `PER_MONTH_LIMIT` or `BATCH_SIZE` run `make clean-raw` first. Optional: `export SOCRATA_APP_TOKEN=...`
(faster downloads), `LLM_RPM=10` (free-tier pacing), `N_EVAL_BATCHES`, `N_CLEAN_BATCHES`, `LLM_K_POS`, `LLM_K_NEG`.

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

All generated numbers land in `eval/out/*.csv`. `RESULTS_B.md` only reads them.

## Design choices (to explain live)
- **pandas** is the primary engine: batches are 5,000 rows, so pandas is fast enough and the easiest to read. DuckDB/Spark is the scale-up path.
- **Hand-rolled checks** instead of pandera/Great Expectations: every rule is a few lines, and you can show and change each one.
- **Batches are consecutive in time**, whole batches are assigned to reference or held-out, so duplicate and near-duplicate checks see realistic neighbours.
- **No leakage**: detectors take `(df, ref)` only; thresholds are tuned on the last 20% of reference batches; a test checks that detector code never imports the injector or ground truth.
- LLM numbers come from samples and are extrapolated from measured tokens x list price (`common.py`).

## Unverified / [HUMAN] items
1. Run `make download` once and read the printed dataset check. I did not have network access, so the id `erm2-nwe9` and the column names in `common.COLUMNS` are unverified; the script stops if a column is missing.
2. The code was not run end to end. I only smoke-tested injectors and rule detectors on synthetic data (sklearn, pyarrow, faker and network were unavailable). Run `make test` first and send me any failure.
3. Re-check the Gemini model name and list price on the official pricing page (`common.py`); I only saw third-party mirrors dated October 2026.
4. `CPU_USD_PER_HOUR`, peak factor, utilisation and retention in `eval/scale.py` are my assumptions. Change them if you disagree.
5. Write the design discussion in `RESULTS_B.md` (section marked [HUMAN]) and pin versions with `pip freeze` after a good run.
6. "50M rows/day x 120 customers" is read as 50M rows per day in total. Say if it means per customer.
7. The resolution-vs-status regexes (`patterns.py`) were written before looking at the held-out templates. Keep it that way, or the held-out recall number stops meaning anything.
