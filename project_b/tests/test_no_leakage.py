import inspect
from pathlib import Path

from detectors.registry import DETECTORS
from injector import inject


def test_detectors_only_take_batch_and_reference():
    for fam in DETECTORS.values():
        for det in fam.values():
            params = list(inspect.signature(det).parameters)
            assert params[:2] == ["df", "ref"], f"{det.__name__} must take (df, ref) and nothing about ground truth"


def test_detector_code_never_touches_injector_or_truth():
    for path in Path("detectors").rglob("*.py"):
        src = path.read_text()
        assert "GroundTruth" not in src and "from injector" not in src and "import injector" not in src, path


def test_corrupted_batch_is_a_plain_dataframe(batches, ctx):
    out, _ = inject(batches[5], "pii", 0.05, 1, ctx)
    assert type(out).__name__ == "DataFrame" and not out.attrs
    assert not any(c.lower().startswith(("truth", "_gt", "label")) for c in out.columns)
