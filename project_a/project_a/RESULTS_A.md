# RESULTS_A: Rules vs LLMs for India salaried income tax (FY 2024-25)

All metrics below are copied from `eval/out/summary.md` (run of `make all`). Items marked **TBD** are not measured yet. Nothing here is claimed as verified against the official calculator: 0 of 36 rows are filled.

## 1. Headline

Use **deterministic rules for every rupee**. Use the **LLM only to understand messy text** and (offline) to draft rule updates, with a human review and an oracle gate on every Budget.

## 2. Measurements

| Metric | A: hand-coded rules | B: LLM at runtime | C: LLM-compiled, reviewed |
|---|---|---|---|
| Cases | 221 | **20** | 221 |
| Rupee-exact (both regimes) | 100.0% | 35.0% | 100.0% |
| Recommendation correct | 100.0% | 100.0% | 100.0% |
| Loud failures | 0 | 0 | 0 |
| Silent failures | 0 | 13 | 0 |
| Determinism (identical over N runs) | 100% of 221, x10 | 100% of **5**, x3 | 100% of 221, x10 |
| Latency p50 / p95 | 0.0003 s / 0.0005 s | 2.73 s / 4.54 s | 0.0004 s / 0.0007 s |
| Mean CPU per request | 0.424 ms | not meaningful (network + cache) | 0.424 ms |
| Trace sums to total | 100% | 45% | 100% |
| Traceable rupees (valid clause id) | 100% | 100% | 100% |
| Hallucinated citations | 0 | 0 | 0 |
| Cost per 1,000 requests | about $0 (CPU only) | $2.61 (**placeholder prices**) | about $0 at runtime |

Caveats: B was run on 20 cases and only 5 for determinism, so it is not comparable with A and C yet. B's cost uses unverified prices (`eval/pricing.py` still says TODO-VERIFY). C's 100% is after human review: the first frozen copy failed all 221 cases loudly (wrong age-band label `below 60`, and the 60-79 and 80+ slab sets were missing). See `impl_c_llm_compiled/REVIEW.md`.

### Parser (50 descriptions, 16 should trigger a question)

| Metric | Value |
|---|---|
| Field accuracy on cases parsed | 100% |
| Clarification recall (asked when it should) | 93.8% |
| Clarification precision | 51.7% (14 unnecessary questions) |
| Guessed when it should have asked | **1** (critical failure; under investigation) |
| Asked about a field in the gold list | 15 of 15 asked |

## 3. Final design

| Component | Choice | Evidence |
|---|---|---|
| Tax arithmetic (slabs, rebate, surcharge, cess, rounding) | **Rule** | A: 100% exact on 221 cases. B: 35% exact on 20 cases, 13 silent failures |
| Trace and citations | **Rule** | Trace sums to total in 100% (A, C) versus 45% (B): the LLM's own working contradicted its answer |
| Unit normalisation, metro lookup, contradiction checks | **Rule** | Deterministic layer is unit-tested; field accuracy 100% on parsed cases |
| Understanding messy text (English, Hinglish) | **LLM** | Recall 93.8%, field accuracy 100% |
| Deciding whether and what to ask | **Rule** (question text is a template) | Never defaults a number silently; one guess still slipped through |
| Drafting rule updates | **Hybrid**: LLM drafts offline, human reviews, oracle gates | Raw compile failed 221/221 loudly; reviewed file reached 100% |
| Release gate on every Budget | **Rule + human** | Oracle regression plus official-calculator checks |

B's determinism result shows the trap: it can be repeatable and still wrong, so determinism alone is not a quality guarantee.

## 4. Decisions

- **Rounding:** one module (`rounding.py`). Intermediate rupee amounts round half-up; taxable income (Sec 288A) and final tax (Sec 288B) round to the nearest 10.
- **Employer NPS 80CCD(2):** included as an optional input (10% of basic+DA old regime, 14% new). It is one of the few deductions the new regime allows, so leaving it out could flip a recommendation.
- **87A marginal relief** is reported inside `rebate`; `marginal_relief` is surcharge relief only.
- **Impl C reuses impl A's engine** (documented), so C measures the quality of the compiled data file, not the arithmetic.
- **Impl B has no calculator tool**, by design, to measure the LLM computing.
- **80D preventive check-up sub-limit** is not modelled: 80D inputs are totals.

## 5. Cost at 100,000 users

- Rules engine (A or C): CPU only, 0.424 ms per request measured.
- B, if it were deployed: 100,000 requests x $2.61 per 1,000 = about **$261**, using placeholder prices (**TBD**: replace with the official list price and date).
- Parser cost per request: **TBD** (token counts are logged in `.cache/token_log.csv`; not yet summarised).

## 6. How a new Budget flows through

1. A person edits the rules data file and the rule-text excerpts (impl A, and impl C via recompile and review).
2. The oracle is regenerated independently for the new FY.
3. Release gate: all tests for both FYs pass, FY 2024-25 results do not change, and the official-calculator checks are re-run.
4. Rollback: the rules file is versioned in git, so reverting is a one-file change.

The silent-failure study and the guardrail demonstration for FY 2025-26 are **TBD** (Task 5).

## 7. Known residual risks

- The official-calculator check is not done (0 of 36 rows), and the oracle and engine share an author, so errors could correlate.
- Rule excerpts are paraphrases marked PARAPHRASE-UNVERIFIED. The metro list, the old-regime surcharge tiers and the section numbers and URLs are unverified.
- Parser over-asks (precision 51.7%) and has one critical guess, which is not yet fixed.
- B's sample is small (20 cases, 5 for determinism).
- Intermediate rounding may differ from the official calculator by a few rupees on edge cases.
- FY 2025-26 is not yet applied, so the law-change results are not measured.
