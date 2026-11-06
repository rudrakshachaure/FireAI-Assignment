"""THE rounding policy. Everything rounds through these two functions.

Policy (documented in RESULTS_A.md):
  * Intermediate rupee amounts (slab tax per slab, HRA terms, surcharge, cess)
    are rounded half-up to a whole rupee via div_half_up.
  * Taxable income is rounded to the nearest 10 (Sec 288A) and the final tax to
    the nearest 10 (Sec 288B) via round_to_nearest_10; 5 rounds up.
"""
from __future__ import annotations


def div_half_up(numerator: int, denominator: int) -> int:
    """numerator/denominator rounded half-up to an integer (non-negative inputs)."""
    if denominator <= 0 or numerator < 0:
        raise ValueError("div_half_up expects numerator >= 0 and denominator > 0")
    return (2 * numerator + denominator) // (2 * denominator)


def round_to_nearest_10(x: int) -> int:
    """Sec 288A / 288B: nearest multiple of 10, remainder >= 5 rounds up."""
    if x < 0:
        raise ValueError("round_to_nearest_10 expects x >= 0")
    return ((x + 5) // 10) * 10
