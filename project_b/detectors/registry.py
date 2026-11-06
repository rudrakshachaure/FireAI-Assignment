"""One place that maps (family, problem_type) -> detector function."""
from detectors.rules import checks as r
from detectors.stats import checks as s

DETECTORS = {
    "rules": {n: getattr(r, n) for n in (
        "schema_column", "type_change", "date_format", "latlon_swap", "exact_dup", "near_dup", "null_spike",
        "closed_before_created", "zip_borough", "complaint_descriptor", "resolution_status", "pii")},
    "stats": {n: getattr(s, n) for n in (
        "schema_column", "type_change", "date_format", "latlon_swap", "exact_dup", "near_dup", "null_spike",
        "closed_before_created", "zip_borough", "complaint_descriptor", "resolution_status", "pii")},
}
