# Open questions (answer before relying on the numbers)

1. **Rupee rounding of intermediates.** Engine rounds each intermediate (slab line, HRA terms, surcharge, cess) half-up to a whole rupee, then Sec 288A/288B to the nearest 10. The official calculator may differ by a few rupees on edge cases. Resolve with `official_calc_checks.csv` [HUMAN].
2. **HRA metro list.** Only Delhi, Mumbai, Kolkata, Chennai are listed (TODO-VERIFY against the current rule for FY 2024-25). Hinglish example "Pune" => non-metro.
3. **Old-regime surcharge tiers** (25% >2Cr, 37% >5Cr) and all section numbers / URLs in `rules_text/clauses.json` are unverified. Excerpts are paraphrases marked PARAPHRASE-UNVERIFIED; replace with verbatim official text (`make rules-check` fails until you do).
4. **80D preventive check-up (5k sub-limit)** is not modelled: `sec_80d_*` inputs are totals. Say so in RESULTS_A.md or add a field.
5. **Employer NPS 80CCD(2)** is INCLUDED (optional `employer_nps`, 10% old / 14% new of basic+DA). State this decision in RESULTS_A.md.
6. **Professional tax / other salary items** are not modelled.
7. **Gemini model + free-tier limits** (`GEMINI_MODEL`, `eval/pricing.py`): TODO-VERIFY before running impl B at scale (221 x 10 repeats is thousands of calls; use --sample/--det-sample).
8. **FY 2025-26** is intentionally absent (Task 5). `fy="2025-26"` raises a LOUD RuleError today.
