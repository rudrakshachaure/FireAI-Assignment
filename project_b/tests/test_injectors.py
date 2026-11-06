import numpy as np
import pandas as pd
import pytest

from injector import inject

IN_PLACE = ["latlon_swap", "closed_before_created", "zip_borough", "complaint_descriptor",
            "resolution_status", "pii"]


@pytest.mark.parametrize("ptype", IN_PLACE)
def test_only_claimed_rows_change(batches, ctx, ptype):
    orig = batches[5]
    out, truth = inject(orig, ptype, 0.05, 1, ctx)
    ids = np.array(truth.row_ids)
    assert len(out) == len(orig) and len(ids) > 0
    a, b = orig.astype(str), out.astype(str)
    assert a.drop(index=ids).equals(b.drop(index=ids)), "rows outside ground truth were modified"
    assert (a.iloc[ids].to_numpy() != b.iloc[ids].to_numpy()).any(axis=1).all(), "a claimed row did not change"


def test_null_spike_only_touches_one_agency(batches, ctx):
    orig = batches[5]
    out, truth = inject(orig, "null_spike", 0.5, 1, ctx)
    changed = (orig.isna() != out.isna()).any(axis=1)
    assert set(np.flatnonzero(changed)) <= set(truth.row_ids)
    assert (out.loc[changed, "agency"] == truth.params["agency"]).all()


@pytest.mark.parametrize("ptype", ["exact_dup", "near_dup"])
def test_duplicates_are_appended(batches, ctx, ptype):
    orig = batches[5]
    out, truth = inject(orig, ptype, 0.05, 1, ctx)
    n = len(orig)
    assert truth.row_ids == list(range(n, len(out)))
    assert out.iloc[:n].astype(str).equals(orig.astype(str))


def test_date_format_switches_after_k(batches, ctx):
    out, truth = inject(batches[5], "date_format", 0.1, 1, ctx)
    k = truth.params["switch_row"]
    assert out.created_date.iloc[:k].str.match(r"^\d{4}-\d{2}-\d{2}T").all()
    assert out.created_date.iloc[k:].str.match(r"^\d{2}/\d{2}/\d{4}").all()
    assert truth.row_ids == list(range(k, len(out)))


def test_schema_and_type_changes(batches, ctx):
    out, truth = inject(batches[5], "schema_column", 0.2, 1, ctx)
    assert truth.row_ids is None and list(out.columns) != list(batches[5].columns)
    out, truth = inject(batches[5], "type_change", 0.2, 1, ctx)
    assert out.latitude.map(type).eq(str).sum() > 0 and truth.level == "batch"


def test_same_seed_same_result(batches, ctx):
    a, ta = inject(batches[5], "pii", 0.05, 7, ctx)
    b, tb = inject(batches[5], "pii", 0.05, 7, ctx)
    assert a.equals(b) and ta.row_ids == tb.row_ids
