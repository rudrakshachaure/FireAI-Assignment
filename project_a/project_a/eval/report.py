"""Merge eval/out/*_metrics.json into eval/out/summary.md (the ONLY source for RESULTS_A.md numbers)."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "out"


def main() -> None:
    rows = {p.stem.split("_")[0]: json.loads(p.read_text()) for p in sorted(OUT.glob("?_metrics.json"))}
    names = {"a": "A hand-coded rules", "b": "B LLM at runtime", "c": "C LLM-compiled rules"}
    lines = ["| metric | " + " | ".join(names[k] for k in rows) + " |", "|---|" + "---|" * len(rows)]
    for key, label in (("cases", "cases"), ("exact_pct", "rupee-exact % (both regimes)"), ("recommendation_pct", "recommendation %"),
                       ("loud_failures", "loud failures"), ("silent_failures", "silent failures"),
                       ("latency_p50_s", "latency p50 (s)"), ("latency_p95_s", "latency p95 (s)"), ("cpu_ms_mean", "mean CPU ms"),
                       ("usd_per_1000_requests_paid_list_price", "USD / 1000 req (list price)"),
                       ("traceable_rupee_pct", "traceable rupees %"), ("hallucinated_citations", "hallucinated citations"),
                       ("trace_sums_ok_pct", "trace sums to total %")):
        lines.append(f"| {label} | " + " | ".join(str(m.get(key)) for m in rows.values()) + " |")
    lines.append("| determinism (identical over N runs) | " + " | ".join(
        f"{m['determinism']['identical_pct']}% of {m['determinism']['sample']} x{m['determinism']['repeats']}" for m in rows.values()) + " |")
    pm = OUT / "parser_metrics.json"
    if pm.exists():
        lines += ["", "Parser:", "", "```json", pm.read_text(), "```"]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
