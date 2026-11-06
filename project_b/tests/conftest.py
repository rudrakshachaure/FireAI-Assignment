"""Small synthetic 311-like batches so tests run in seconds without downloading anything."""
import numpy as np
import pandas as pd
import pytest

from common import COLUMNS
from detectors.reference import fit_reference
from injector import build_context

BOROUGHS = {"MANHATTAN": (40.78, -73.97, ["10001", "10002", "10003"]), "BROOKLYN": (40.65, -73.95, ["11201", "11211", "11215"]),
            "QUEENS": (40.73, -73.80, ["11101", "11354", "11375"]), "BRONX": (40.85, -73.88, ["10451", "10458", "10460"])}
TYPES = {"NYPD": {"Noise - Residential": ["Loud Music/Party", "Banging/Pounding", "Loud Talking"],
                  "Illegal Parking": ["Blocked Hydrant", "Double Parked Vehicle", "Posted Sign Violation"]},
         "HPD": {"HEAT/HOT WATER": ["ENTIRE BUILDING", "APARTMENT ONLY"], "PLUMBING": ["WATER SUPPLY", "BATHTUB/SHOWER"]},
         "DSNY": {"Missed Collection": ["Trash", "Recycling"], "Dirty Conditions": ["Sidewalk", "Vacant Lot"]}}


def make_batch(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2023-03-01") + pd.Timedelta(days=int(seed) * 2)
    for i in range(n):
        agency = rng.choice(list(TYPES))
        ctype = rng.choice(list(TYPES[agency]))
        desc = rng.choice(TYPES[agency][ctype])
        b = rng.choice(list(BOROUGHS))
        lat0, lon0, zips = BOROUGHS[b]
        created = start + pd.Timedelta(minutes=int(i * 7 + rng.integers(0, 5)))
        closed_flag = rng.random() < 0.7
        rows.append({
            "unique_key": str(50_000_000 + seed * 100_000 + i), "created_date": created,
            "closed_date": created + pd.Timedelta(hours=float(rng.integers(1, 200))) if closed_flag else pd.NaT,
            "agency": agency, "complaint_type": ctype, "descriptor": desc, "incident_zip": str(rng.choice(zips)),
            "incident_address": f"{rng.integers(1, 999)} MAIN ST {i}", "borough": b,
            "status": "Closed" if closed_flag else "Open",
            "resolution_description": f"The {agency} responded to the complaint and took action." if closed_flag
            else f"The {agency} will review your request.",
            "latitude": lat0 + rng.normal(0, 0.01), "longitude": lon0 + rng.normal(0, 0.01)})
    return pd.DataFrame(rows)[COLUMNS]


@pytest.fixture(scope="session")
def batches():
    return [make_batch(500, s) for s in range(6)]


@pytest.fixture(scope="session")
def ctx(batches):
    return build_context(pd.concat(batches[:5], ignore_index=True))


@pytest.fixture(scope="session")
def ref(batches):
    return fit_reference(batches[:5])
