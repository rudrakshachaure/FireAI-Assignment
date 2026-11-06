.PHONY: install cases test eval all all-llm lint rules-check clean-cache
PY ?= python

install:
	$(PY) -m pip install -r requirements.txt

cases:
	$(PY) -m project_a.tests.gen_cases
	$(PY) -m project_a.data.make_nl_descriptions

test:
	$(PY) -m pytest -q project_a/tests

lint:
	ruff check project_a

# Reproduces every reported number that needs no Gemini quota.
all:
	$(PY) -m project_a.run_all

# Also runs impl B (sampled) and the parser eval against Gemini (cached on disk).
all-llm:
	$(PY) -m project_a.run_all --llm

rules-check:
	$(PY) -m project_a.rules_text.verify_rules_text --strict

official-check:
	$(PY) -m project_a.tests.diff_official

clean-cache:
	rm -rf .cache
