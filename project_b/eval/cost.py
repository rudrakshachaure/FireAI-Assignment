"""Cost formulas (shown in RESULTS_B.md):
  compute $/M rows = (1e6 / rows_per_sec) / 3600 * CPU_USD_PER_HOUR
  LLM $            = input_tokens * PRICE_IN/1e6 + output_tokens * PRICE_OUT/1e6
"""
from common import CPU_USD_PER_HOUR, PRICE_IN_PER_M, PRICE_OUT_PER_M


def compute_usd_per_m(rows_per_sec: float) -> float:
    return (1e6 / rows_per_sec) / 3600 * CPU_USD_PER_HOUR


def llm_usd(in_tokens: float, out_tokens: float) -> float:
    return in_tokens * PRICE_IN_PER_M / 1e6 + out_tokens * PRICE_OUT_PER_M / 1e6
