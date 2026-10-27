"""Domain-rule and validation tests for the extracted engine."""
from __future__ import annotations

import io
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import (
    InspectionError,
    ReferenceError,
    combine_inspections,
    gang_bounds,
    gang_yield,
    individual_wafer_status,
    list_products,
    load_reference,
    read_inspection,
    stacked_summary,
    valid_spring_keys,
    validate_inspection,
)
from tests.conftest import BACKEND, make_inspection

TINY = "TEST-PROD"


def _tiny(tiny_reference_dir):
    ref, center = load_reference(TINY, tiny_reference_dir)
    return ref, center, valid_spring_keys(ref)


def _all_good(ref) -> dict:
    return {(int(d), int(s)): "Good" for d, s in zip(ref.Die_Num, ref.Spring_Num)}


# --------------------------------------------------------------------------- no Streamlit anywhere
def test_engine_has_no_streamlit_or_plotly_imports():
    engine_dir = BACKEND / "engine"
    for path in engine_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "streamlit" not in text, path
        assert "plotly" not in text, path
    code = "import sys, engine; mods = [m for m in sys.modules if m.startswith(('streamlit', 'plotly'))]; print(mods)"
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


# --------------------------------------------------------------------------- reference
def test_bundled_reference_centering(reference):
    ref, center = reference
    # bounding-box midpoint of the source extents, as documented
    assert center == pytest.approx((71.245, -0.5015))
    assert center[0] == pytest.approx((ref.X.min() + ref.X.max()) / 2)
    assert center[1] == pytest.approx((ref.Y.min() + ref.Y.max()) / 2)
    assert ref.x.min() == pytest.approx(-ref.x.max())
    assert ref.y.min() == pytest.approx(-ref.y.max())
    assert list(ref.columns) == ["Die_Num", "Spring_Num", "X", "Y", "x", "y"]


def test_tiny_reference_strips_parenthetical_headers_and_centers(tiny_reference_dir):
    ref, center, _ = _tiny(tiny_reference_dir)
    assert len(ref) == 20 and ref.Die_Num.nunique() == 2
    # X spans 10.5 .. 25.0 ; Y spans 80 .. 98
    assert center == pytest.approx(((10.5 + 25.0) / 2, (80.0 + 98.0) / 2))
    assert ref.x.min() == pytest.approx(-ref.x.max())
    bounds = gang_bounds(ref)
    assert list(bounds.index) == [1, 2]
    assert list(bounds.columns) == ["xmin", "xmax", "ymin", "ymax"]


def test_list_products_and_missing_reference(tiny_reference_dir, tmp_path):
    assert list_products(tiny_reference_dir) == [TINY]
    assert "152-900530D" in list_products(BACKEND / "coordinates")  # other layouts may be saved there
    # an open workbook leaves an Excel lock file behind; it is not a product
    (tiny_reference_dir / "~$TEST-PROD.xlsx").write_bytes(b"lock")
    assert list_products(tiny_reference_dir) == [TINY]
    assert load_reference(TINY, tiny_reference_dir)[0].shape[0] == 20
    assert list_products(tmp_path / "nope") == []
    with pytest.raises(ReferenceError, match="No reference found for NOPE"):
        load_reference("NOPE", tiny_reference_dir)


def test_reference_duplicate_keys_rejected(tmp_path):
    ref_dir = tmp_path / "coordinates"
    ref_dir.mkdir()
    pd.DataFrame({"Die_Num": [1, 1], "Spring_Num": [1, 1], "X": [0, 1], "Y": [0, 1]}).to_csv(ref_dir / "DUP.csv", index=False)
    with pytest.raises(ReferenceError, match="Duplicate spring keys in reference"):
        load_reference("DUP", ref_dir)


def test_reference_missing_columns_rejected(tmp_path):
    ref_dir = tmp_path / "coordinates"
    ref_dir.mkdir()
    pd.DataFrame({"Die_Num": [1], "Spring_Num": [1], "X": [0]}).to_csv(ref_dir / "BAD.csv", index=False)
    with pytest.raises(ReferenceError, match="Reference must contain"):
        load_reference("BAD", ref_dir)
    # Die_Num + X + Y without Spring_Num is a valid DIE layout, not an error
    pd.DataFrame({"Die_Num": [1], "X": [0], "Y": [0]}).to_csv(ref_dir / "DIEONLY.csv", index=False)
    assert len(load_reference("DIEONLY", ref_dir)[0]) == 1


# --------------------------------------------------------------------------- inspection validation
def test_read_inspection_csv_roundtrip(tiny_reference_dir, tmp_path):
    ref, _, keys = _tiny(tiny_reference_dir)
    statuses = _all_good(ref)
    statuses[(1, 2)] = "Low"; statuses[(1, 3)] = "medium"; statuses[(2, 4)] = "KILLER"
    frame = make_inspection(TINY, "W1", statuses)
    frame.loc[frame.Defect_Severity == "medium", "Defect_Severity"] = "medium"
    path = tmp_path / "W1.csv"
    frame.to_csv(path, index=False)
    out = read_inspection(path, TINY, keys)
    assert list(out.columns) == ["Wafer_ID", "Die_Num", "Spring_Num", "Status"]
    by_key = dict(zip(zip(out.Die_Num, out.Spring_Num), out.Status))
    assert by_key[(1, 2)] == "Low" and by_key[(1, 3)] == "Med" and by_key[(2, 4)] == "Killer" and by_key[(1, 1)] == "Good"
    assert out.Wafer_ID.unique().tolist() == ["W1"]


def test_wafer_id_falls_back_to_filename_stem(tiny_reference_dir):
    ref, _, keys = _tiny(tiny_reference_dir)
    frame = make_inspection(TINY, "ignored", _all_good(ref)).drop(columns=["Wafer_ID"])
    buf = io.BytesIO(frame.to_csv(index=False).encode())
    out = read_inspection(buf, TINY, keys, name="LOT7_WAFER_03.csv")
    assert out.Wafer_ID.unique().tolist() == ["LOT7_WAFER_03"]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda f: f.assign(Product="OTHER"), "product mismatch; expected TEST-PROD"),
        (lambda f: f.assign(Defect_Severity=np.where(f.Defect.eq("Y"), "High", "")), "Y defects require Low, Med, or Killer severity"),
        (lambda f: f.assign(Defect_Severity=""), "Y defects require Low, Med, or Killer severity"),
        (lambda f: pd.concat([f, f.iloc[[0]]], ignore_index=True), "duplicate Die_Num/Spring_Num"),
        (lambda f: f.assign(Die_Num=np.where(f.index == 0, 99, f.Die_Num)), "inspection contains unknown spring keys"),
        (lambda f: f.assign(Spring_Num=np.where(f.index == 0, 11, f.Spring_Num)), "inspection contains unknown spring keys"),
        (lambda f: f.assign(Defect=np.where(f.index == 0, "maybe", f.Defect)), "Defect must be Y or N"),
        (lambda f: f.assign(Die_Num=np.where(f.index == 0, 1.5, f.Die_Num)), "invalid Die_Num"),
        (lambda f: f.assign(Spring_Num=np.where(f.index == 0, "x", f.Spring_Num.astype(str))), "invalid Spring_Num"),
        (lambda f: f.drop(columns=["Defect_Severity"]), "missing \\['Defect_Severity'\\]"),
        (lambda f: f.assign(Wafer_ID=np.where(f.index == 0, "W2", "W1")), "one Wafer_ID per file required"),
    ],
)
def test_validation_rejections(tiny_reference_dir, mutate, message):
    ref, _, keys = _tiny(tiny_reference_dir)
    statuses = _all_good(ref)
    statuses[(1, 5)] = "Killer"
    frame = mutate(make_inspection(TINY, "W1", statuses))
    with pytest.raises(InspectionError, match=message):
        validate_inspection(frame, "W1.csv", TINY, keys)


def test_validation_messages_are_prefixed_with_the_file_name(tiny_reference_dir):
    ref, _, keys = _tiny(tiny_reference_dir)
    with pytest.raises(InspectionError, match=r"^lot9\.csv: product mismatch"):
        validate_inspection(make_inspection("WRONG", "W1", _all_good(ref)), "lot9.csv", TINY, keys)


def test_combine_rejects_duplicate_keys_across_files(tiny_reference_dir):
    ref, _, keys = _tiny(tiny_reference_dir)
    a = validate_inspection(make_inspection(TINY, "W1", _all_good(ref)), "a.csv", TINY, keys)
    b = validate_inspection(make_inspection(TINY, "W1", _all_good(ref)), "b.csv", TINY, keys)
    with pytest.raises(InspectionError, match="Duplicate wafer/spring keys across input files"):
        combine_inspections([a, b])
    c = validate_inspection(make_inspection(TINY, "W2", _all_good(ref)), "c.csv", TINY, keys)
    assert len(combine_inspections([a, c])) == 40


# --------------------------------------------------------------------------- uninspected != Good
def test_uninspected_springs_are_never_counted_as_good(tiny_reference_dir):
    ref, _, keys = _tiny(tiny_reference_dir)
    statuses = _all_good(ref)
    statuses[(1, 1)] = "Killer"
    omitted = {(1, 9), (1, 10), (2, 10)}
    w1 = validate_inspection(make_inspection(TINY, "W1", statuses, omit=omitted), "W1.csv", TINY, keys)
    w2 = validate_inspection(make_inspection(TINY, "W2", statuses, omit={(2, 10)}), "W2.csv", TINY, keys)
    data = combine_inspections([w1, w2])

    stack = stacked_summary(ref, data, ["W1", "W2"])
    row = stack.set_index(["Die_Num", "Spring_Num"])
    assert row.loc[(2, 10), "Inspected"] == 0 and math.isnan(row.loc[(2, 10), "Defect_Rate"])
    assert row.loc[(1, 9), "Inspected"] == 1 and row.loc[(1, 9), "Defect_Rate"] == 0.0
    assert row.loc[(1, 1), "Inspected"] == 2 and row.loc[(1, 1), "Defects"] == 2 and row.loc[(1, 1), "Killer"] == 2 and row.loc[(1, 1), "Defect_Rate"] == 1.0
    # rates ignore missing coverage entirely: 2 defects / 36 observations, not / 40 springs
    assert stack.Inspected.sum() == 36
    assert stack.Defects.sum() / stack.Inspected.sum() == pytest.approx(2 / 36)

    status, counts = individual_wafer_status(ref, data, "W1")
    assert len(status) == len(ref)
    assert status.value_counts().to_dict() == {"Good": 16, "Uninspected": 3, "Killer": 1}
    assert dict(zip(counts.Status, counts.Count)) == {"Good": 16, "Killer": 1}  # observed only; no Good for the missing ones

    gangs = gang_yield(ref, data).set_index(["Wafer_ID", "Die_Num"])
    assert gangs.loc[("W1", 1), "Disposition"] == "INCOMPLETE" and gangs.loc[("W1", 1), "Inspected"] == 8 and gangs.loc[("W1", 1), "Total_Springs"] == 10
    assert gangs.loc[("W1", 2), "Disposition"] == "INCOMPLETE"
    assert gangs.loc[("W2", 1), "Disposition"] == "PASS"


# --------------------------------------------------------------------------- scrap boundary (strictly > 60 %)
def test_scrap_boundary_exactly_60_percent_is_not_scrap(tiny_reference_dir):
    ref, _, keys = _tiny(tiny_reference_dir)
    statuses = _all_good(ref)
    for s in range(1, 7):  # 6 of 10 bad in gang 1 -> 0.60 exactly
        statuses[(1, s)] = "Low"
    data = validate_inspection(make_inspection(TINY, "W1", statuses), "W1.csv", TINY, keys)
    g = gang_yield(ref, data).set_index("Die_Num")
    assert g.loc[1, "Bad_Pct"] == pytest.approx(0.60)
    assert g.loc[1, "Disposition"] == "PASS"
    assert g.loc[2, "Disposition"] == "PASS"


def test_scrap_boundary_just_above_60_percent_is_scrap(tiny_reference_dir):
    ref, _, keys = _tiny(tiny_reference_dir)
    statuses = _all_good(ref)
    for s in range(1, 8):  # 7 of 10 bad -> 0.70
        statuses[(1, s)] = "Med"
    data = validate_inspection(make_inspection(TINY, "W1", statuses), "W1.csv", TINY, keys)
    g = gang_yield(ref, data).set_index("Die_Num")
    assert g.loc[1, "Disposition"] == "SCRAP"
    assert int((g.Disposition == "SCRAP").sum()) == 1


def test_scrap_uses_reference_total_and_wins_over_incomplete(tiny_reference_dir):
    """7 bad springs observed out of 8 inspected (10 in the reference): 7/10 > 0.60 -> SCRAP even though incomplete."""
    ref, _, keys = _tiny(tiny_reference_dir)
    statuses = _all_good(ref)
    for s in range(1, 8):
        statuses[(1, s)] = "Killer"
    data = validate_inspection(make_inspection(TINY, "W1", statuses, omit={(1, 9), (1, 10)}), "W1.csv", TINY, keys)
    g = gang_yield(ref, data).set_index("Die_Num")
    assert g.loc[1, "Inspected"] == 8 and g.loc[1, "Bad"] == 7 and g.loc[1, "Total_Springs"] == 10
    assert g.loc[1, "Bad_Pct"] == pytest.approx(0.70)
    assert not g.loc[1, "Complete_Inspection"]
    assert g.loc[1, "Disposition"] == "SCRAP"
    # 6 bad of 8 inspected would be 75 % of the *inspected* springs but only 60 % of the reference -> not scrap
    statuses[(1, 7)] = "Good"
    data = validate_inspection(make_inspection(TINY, "W1", statuses, omit={(1, 9), (1, 10)}), "W1.csv", TINY, keys)
    g = gang_yield(ref, data).set_index("Die_Num")
    assert g.loc[1, "Bad_Pct"] == pytest.approx(0.60) and g.loc[1, "Disposition"] == "INCOMPLETE"


def test_bundled_examples_have_no_scrap_and_full_coverage(reference, example_data):
    ref, _ = reference
    g = gang_yield(ref, example_data)
    assert len(g) == 6 * 108
    assert g.Complete_Inspection.all()
    assert (g.Disposition == "PASS").all()
    assert (g.Total_Springs == 194).all()
