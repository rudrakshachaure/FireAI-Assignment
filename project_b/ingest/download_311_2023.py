"""Download NYC 311 requests created in calendar year 2023 from the official Socrata API.

Re-runnable and resumable: every page is saved as its own parquet file in data/raw/parts/.
If a page file already exists it is not downloaded again.

Usage:  python ingest/download_311_2023.py [--per-month-limit 20000]
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import pandas as pd
import requests

headers = {
    "User-Agent": "ProjectB-DataQuality/1.0"
}

from common import COLUMNS, DATASET_ID, METADATA_URL, RAW_DIR, SOCRATA_URL

PAGE = 50_000
PARTS = RAW_DIR / "parts"


def get_json(url, params=None, retries=6):
    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=180
            )

            response.raise_for_status()
            return response.json()

        except (requests.exceptions.RequestException, ValueError) as e:

            if attempt == retries - 1:
                raise

            wait = 2 ** (attempt + 1)

            print(
                f"Download failed: {e}\n"
                f"Retrying in {wait} seconds..."
            )

            time.sleep(wait)


def check_dataset() -> None:
    """Verify the dataset id and that our columns exist. Stop (do not guess) if they do not."""
    meta = get_json(METADATA_URL)
    fields = {c["fieldName"] for c in meta["columns"]}
    print(f"Dataset {DATASET_ID}: {meta['name']}  ({SOCRATA_URL})")
    missing = [c for c in COLUMNS if c not in fields]
    if missing:
        sys.exit(f"STOP: these columns are not in the dataset: {missing}. Fix COLUMNS in common.py.")


def month_window(m: int) -> str:
    start = f"2023-{m:02d}-01T00:00:00"
    end = f"2023-{m + 1:02d}-01T00:00:00" if m < 12 else "2024-01-01T00:00:00"
    return f"created_date >= '{start}' AND created_date < '{end}'"


def download_month(m: int, per_month_limit: int | None) -> None:
    offset = 0
    while per_month_limit is None or offset < per_month_limit:
        size = PAGE if per_month_limit is None else min(PAGE, per_month_limit - offset)
        part = PARTS / f"{m:02d}_{offset:08d}_{size}.parquet"
        if part.exists():
            n = len(pd.read_parquet(part))
        else:
            rows = get_json(SOCRATA_URL, {
                "$select": ",".join(COLUMNS), "$where": month_window(m),
                "$order": "created_date,unique_key", "$limit": size, "$offset": offset,
            })
            pd.DataFrame(rows, columns=COLUMNS).to_parquet(part, index=False)
            n = len(rows)
        print(f"  2023-{m:02d} offset {offset}: {n} rows")
        if n < size:
            break  # last page of this month
        offset += size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-month-limit", type=int, default=None, help="quick trial: cap rows per month")
    args = ap.parse_args()
    PARTS.mkdir(parents=True, exist_ok=True)
    check_dataset()
    for m in range(1, 13):
        download_month(m, args.per_month_limit)
    files = sorted(PARTS.glob("*.parquet"))
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df.to_parquet(RAW_DIR / "311_2023.parquet", index=False)
    print(f"Saved {len(df):,} rows -> {RAW_DIR / '311_2023.parquet'}")


if __name__ == "__main__":
    main()
