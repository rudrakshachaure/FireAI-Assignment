| metric | A hand-coded rules | B LLM at runtime | C LLM-compiled rules |
|---|---|---|---|
| cases | 221 | 20 | 221 |
| rupee-exact % (both regimes) | 100.0 | 35.0 | 100.0 |
| recommendation % | 100.0 | 100.0 | 100.0 |
| loud failures | 0 | 0 | 0 |
| silent failures | 0 | 13 | 0 |
| latency p50 (s) | 0.0004 | 2.7267 | 0.0003 |
| latency p95 (s) | 0.0007 | 4.5429 | 0.0004 |
| mean CPU ms | 0.495 | 3.125 | 0.283 |
| USD / 1000 req (list price) | 0.0 | 2.6099 | 0.0 |
| traceable rupees % | 100.0 | 100.0 | 100.0 |
| hallucinated citations | 0 | 0 | 0 |
| trace sums to total % | 100.0 | 45.0 | 100.0 |
| determinism (identical over N runs) | 100.0% of 221 x10 | 100.0% of 5 x3 | 100.0% of 221 x10 |

Parser:

```json
{
  "n": 50,
  "clarification_precision": 0.517,
  "clarification_recall": 0.938,
  "guessed_when_should_ask": 1,
  "asked_unnecessarily": 14,
  "field_accuracy_on_ok_cases": 1.0,
  "asked_field_matches_gold": 15
}
```
