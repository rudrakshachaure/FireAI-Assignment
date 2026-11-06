import pytest

from detectors.registry import DETECTORS
from eval.metrics import flagged_rows
from injector import inject

EASY = ["date_format", "latlon_swap", "exact_dup", "closed_before_created", "zip_borough", "complaint_descriptor"]


@pytest.mark.parametrize("ptype", EASY)
def test_rule_finds_injection_and_is_quiet_on_clean(batches, ctx, ref, ptype):
    det = DETECTORS["rules"][ptype]
    assert det(batches[5], ref) == [], "false alarm on a clean synthetic batch"
    out, truth = inject(batches[5], ptype, 0.1, 3, ctx)
    found, expected = flagged_rows(det(out, ref)), set(truth.row_ids)
    assert len(found & expected) / len(expected) >= 0.9


def test_schema_and_type_rules(batches, ctx, ref):
    for ptype in ("schema_column", "type_change"):
        out, _ = inject(batches[5], ptype, 0.2, 3, ctx)
        assert DETECTORS["rules"][ptype](out, ref) and not DETECTORS["rules"][ptype](batches[5], ref)


def test_pii_rule_catches_easy_cases(batches, ctx, ref):
    out, truth = inject(batches[5], "pii", 0.2, 3, ctx)
    easy = {i for i, k in truth.params["kinds"].items() if k.startswith("easy")}
    assert easy <= flagged_rows(DETECTORS["rules"]["pii"](out, ref))


def test_every_detector_returns_alert_shape(batches, ref):
    for fam in DETECTORS.values():
        for det in fam.values():
            for a in det(batches[5], ref):
                assert a.level in ("row", "batch") and isinstance(a.row_ids, list) and a.explanation
