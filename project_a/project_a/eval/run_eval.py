"""Measure one implementation. Writes eval/out/<impl>_*.csv|json|md.
  python -m project_a.eval.run_eval --impl a
  python -m project_a.eval.run_eval --impl b --sample 40 --det-sample 10 --repeats 10   (uses Gemini quota!)"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import statistics
import time
from pathlib import Path

from .. import llm_client
from ..models import RuleError, TaxInput, TaxOutput
from ..trace import check_trace, traceability, valid_clause_ids
from . import pricing

DATA = Path(__file__).resolve().parents[1] / "data" / "tests_200.jsonl"
OUT = Path(__file__).parent / "out"


def get_impl(name: str):
    if name == "a":
        from ..impl_a_rules import compute
    elif name == "b":
        from ..impl_b_llm_runtime import compute
    elif name == "c":
        from ..impl_c_llm_compiled import compute
    else:
        raise SystemExit("--impl must be a, b or c")
    return compute


def pct(sorted_vals: list[float], p: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1))))] if sorted_vals else 0.0


def digest(out: TaxOutput) -> str:
    return hashlib.sha256(out.model_dump_json().encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--sample", type=int, default=0, help="first N cases (0 = all)")
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--det-sample", type=int, default=0, help="cases used for determinism (0 = same as --sample/all)")
    a = ap.parse_args()
    fn = get_impl(a.impl)
    takes_cache = "use_cache" in inspect.signature(fn).parameters
    cases = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
    if a.sample:
        cases = cases[:a.sample]
    OUT.mkdir(exist_ok=True)

    exact = rec_ok = n_loud = 0
    fails: list[dict] = []
    lat: list[float] = []
    cpu: list[float] = []
    tok_in = tok_out = 0
    backed = unbacked = halluc = 0
    trace_ok = 0
    n_valid = 0
    for c in cases:
        inp = TaxInput.model_validate(c["input"])
        llm_client.drain_calls()
        t0, c0 = time.perf_counter(), time.process_time()
        try:
            out = fn(inp)
        except (RuleError, ValueError) as e:  # LOUD failure
            n_loud += 1
            fails.append({"id": c["id"], "kind": "LOUD", "detail": str(e)[:200]})
            continue
        wall, cpu_t = time.perf_counter() - t0, time.process_time() - c0
        calls = llm_client.drain_calls()
        lat.append(sum(x.latency_s for x in calls) if calls else wall)
        cpu.append(cpu_t)
        tok_in += sum(x.tokens_in for x in calls)
        tok_out += sum(x.tokens_out for x in calls)
        n_valid += 1
        diffs = []
        for reg in ("old", "new"):
            r, e = getattr(out, reg), c["expected"][reg]
            for k in ("taxable_income", "total_tax"):
                if getattr(r, k) != e[k]:
                    diffs.append(f"{reg}.{k}: got {getattr(r, k)} expected {e[k]}")
        rec_match = out.recommended_regime == c["expected"]["recommended_regime"]
        rec_ok += rec_match
        if not rec_match:
            diffs.append(f"recommended: got {out.recommended_regime} expected {c['expected']['recommended_regime']}")
        if diffs:
            fails.append({"id": c["id"], "kind": "SILENT", "detail": "; ".join(diffs)})
        else:
            exact += 1
        tr = traceability(out)
        backed += tr["backed"]
        unbacked += tr["unbacked"]
        halluc += tr["hallucinated_citations"]
        trace_ok += int(not check_trace(out.old) and not check_trace(out.new))

    det = {"sample": 0, "repeats": a.repeats, "identical_pct": None}
    det_cases = cases[:a.det_sample] if a.det_sample else cases
    same = 0
    for c in det_cases:
        inp = TaxInput.model_validate(c["input"])
        try:
            digs = {digest(fn(inp, use_cache=False) if takes_cache else fn(inp)) for _ in range(a.repeats)}
        except (RuleError, ValueError):
            digs = {"error", "error2"}
        same += len(digs) == 1
    det.update(sample=len(det_cases), identical_pct=round(100 * same / max(1, len(det_cases)), 2))

    lat_sorted = sorted(lat)
    n = len(cases)
    cost_per_req = (tok_in * pricing.USD_PER_M_INPUT + tok_out * pricing.USD_PER_M_OUTPUT) / 1e6 / max(1, n_valid)
    total_traced = backed + unbacked
    m = {
        "impl": a.impl, "cases": n, "exact_pct": round(100 * exact / n, 2), "recommendation_pct": round(100 * rec_ok / n, 2),
        "loud_failures": n_loud, "silent_failures": sum(1 for f in fails if f["kind"] == "SILENT"),
        "determinism": det,
        "latency_p50_s": round(pct(lat_sorted, 0.5), 4), "latency_p95_s": round(pct(lat_sorted, 0.95), 4),
        "cpu_ms_mean": round(1000 * statistics.fmean(cpu), 3) if cpu else None,
        "tokens_in_total": tok_in, "tokens_out_total": tok_out,
        "usd_per_1000_requests_paid_list_price": round(cost_per_req * 1000, 4),
        "price_source": f"{pricing.SOURCE_URL} ({pricing.PRICE_DATE})",
        "traceable_rupee_pct": round(100 * backed / total_traced, 2) if total_traced else None,
        "hallucinated_citations": halluc, "trace_sums_ok_pct": round(100 * trace_ok / max(1, n_valid), 2),
        "valid_clause_ids_known": len(valid_clause_ids()),
    }
    (OUT / f"{a.impl}_metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    with open(OUT / f"{a.impl}_failures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "kind", "detail"])
        w.writeheader()
        w.writerows(fails)
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
