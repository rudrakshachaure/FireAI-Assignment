# Run everything:  make all        (quick trial: make all PER_MONTH_LIMIT=20000)
PY ?= python
export PYTHONPATH := .
LIMIT_ARG = $(if $(PER_MONTH_LIMIT),--per-month-limit $(PER_MONTH_LIMIT),)

.PHONY: all download profile eval llm hybrid results test lint clean-raw
all: download profile eval llm hybrid results

download: data/raw/311_2023.parquet
data/raw/311_2023.parquet:
	$(PY) ingest/download_311_2023.py $(LIMIT_ARG)

profile: data/clean/heldout.parquet
data/clean/heldout.parquet: data/raw/311_2023.parquet
	$(PY) profile/profile_raw.py

eval: eval/out/master.csv
eval/out/master.csv: data/clean/heldout.parquet
	$(PY) -m eval.run_eval

llm: data/clean/heldout.parquet
	$(PY) -m eval.run_llm_eval        # skips politely if there is no GEMINI_API_KEY and no cache

hybrid: eval/out/master.csv
	$(PY) -m pipeline.hybrid

results:
	$(PY) -m eval.make_results

test:
	python -m pytest -q

lint:
	ruff check .

clean-raw:
	rm -rf data/raw data/clean
