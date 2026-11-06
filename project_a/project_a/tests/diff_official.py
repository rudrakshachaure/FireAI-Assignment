"""Diff official-calculator values (filled by hand) against the oracle.
Exit 1 on any mismatch, exit 2 if nothing is filled yet. Usage:
  python -m project_a.tests.diff_official"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

CSV = Path(__file__).resolve().parents[1] / "data" / "official_calc_checks.csv"


def main() -> int:
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    filled = mismatches = 0
    for r in rows:
        if not r["official_tax_old"].strip() and not r["official_tax_new"].strip():
            continue
        filled += 1
        for reg in ("old", "new"):
            off, orc = r[f"official_tax_{reg}"].strip(), r[f"oracle_tax_{reg}"]
            if off != "" and int(off) != int(orc):
                mismatches += 1
                print(f"MISMATCH {r['case_id']} {reg}: official={off} oracle={orc}  (screenshot {r['screenshot_ref'] or '?'})")
    print(f"{filled}/{len(rows)} rows filled, {mismatches} mismatch(es)")
    if filled == 0:
        print("NOT VERIFIED: fill official_tax_old/new first [HUMAN]")
        return 2
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
