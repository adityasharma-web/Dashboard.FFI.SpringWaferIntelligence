"""Golden-value parity: the ported engine must reproduce the ORIGINAL Streamlit app's numbers.

``fixtures/golden.json`` was captured by ``tools/capture_golden.py`` directly
from the functions in ``reference-source/spring_wafer_app/app.py`` on the six
bundled synthetic wafers (three scenarios: all six at 5 mm, the first three at
10 mm, a single wafer at 5 mm). Everything the five views display is compared:
header metrics, per-spring stacked metrics, the smoothed rate grid, baseline,
hotspots, the full recurrence table (p and q), zones, indicator messages, the
per-wafer per-gang disposition table and the individual status counts.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from engine import (
    gang_yield,
    header_metrics,
    individual_wafer_status,
    signature_indicators,
    spatial_analysis,
    stacked_summary,
)

SCENARIOS = ["all_six_bw5", "first_three_bw10", "single_wafer_bw5"]


def _assert_float_list(actual, expected, *, rtol=1e-12, atol=0.0):
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected):
        if e is None or (isinstance(e, float) and math.isnan(e)):
            assert a is None or (isinstance(a, float) and math.isnan(a))
        else:
            assert a == pytest.approx(e, rel=rtol, abs=atol)


def _nan_list(series: pd.Series) -> list:
    return [None if pd.isna(v) else float(v) for v in series.tolist()]


def test_reference_matches_golden(reference, golden):
    ref, center = reference
    g = golden["reference"]
    assert len(ref) == g["springs"] == 20952
    assert ref.Die_Num.nunique() == g["gangs"] == 108
    assert center == pytest.approx(tuple(g["center"]))
    assert ref.x.min() == pytest.approx(g["x_min"]) and ref.x.max() == pytest.approx(g["x_max"])
    assert ref.y.min() == pytest.approx(g["y_min"]) and ref.y.max() == pytest.approx(g["y_max"])
    head = ref.head(5)
    for col in ("Die_Num", "Spring_Num", "X", "Y", "x", "y"):
        _assert_float_list(head[col].tolist(), g["first_rows"][col])


def test_wafer_list_matches_golden(example_data, golden):
    assert sorted(example_data.Wafer_ID.unique()) == golden["wafers"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_matches_golden(reference, example_data, golden, scenario):
    ref, _ = reference
    g = golden["scenarios"][scenario]
    selected = g["wafers"]
    bandwidth = g["bandwidth"]
    selected_data = example_data[example_data.Wafer_ID.isin(selected)]

    # header
    header = header_metrics(ref, selected_data, selected)
    assert header["wafers"] == g["header"]["wafers"]
    assert header["springs_in_reference"] == g["header"]["springs_in_reference"]
    assert header["observations"] == g["header"]["observations"]
    assert header["bad"] == g["header"]["bad"]
    assert header["defect_rate"] == pytest.approx(g["header"]["defect_rate"], rel=1e-12)

    # stacked summary (every spring, reference order)
    stack = stacked_summary(ref, selected_data, selected)
    for col in ("Die_Num", "Spring_Num", "Inspected", "Defects", "Killer"):
        assert stack[col].tolist() == g["stacked"][col]
    _assert_float_list(_nan_list(stack.Defect_Rate), g["stacked"]["Defect_Rate"])
    assert int((stack.Inspected == 0).sum()) == g["stacked_uninspected_count"]

    # spatial
    bins, rate, baseline, tests, peaks = spatial_analysis(stack, selected_data, selected, bandwidth)
    assert bins.tolist() == g["spatial"]["bins"]
    assert baseline == pytest.approx(g["spatial"]["baseline"], rel=1e-12)
    expected_rate = np.array([[np.nan if v is None else v for v in row] for row in g["spatial"]["rate"]])
    assert rate.shape == expected_rate.shape
    assert np.array_equal(np.isfinite(rate), np.isfinite(expected_rate))
    assert int(np.isfinite(rate).sum()) == g["spatial"]["rate_finite_cells"]
    np.testing.assert_allclose(rate[np.isfinite(rate)], expected_rate[np.isfinite(expected_rate)], rtol=1e-10)
    assert peaks.to_dict(orient="records") == g["spatial"]["peaks"]

    # recurrence table (full, in the display sort order)
    assert len(tests) == g["spatial"]["recurrence_rows"]
    sorted_tests = tests.sort_values(["q", "Defects"], ascending=[True, False])
    for col in ("Die_Num", "Spring_Num", "Inspected", "Defects"):
        assert sorted_tests[col].tolist() == g["spatial"]["recurrence_sorted"][col]
    _assert_float_list(sorted_tests.q.tolist(), g["spatial"]["recurrence_sorted"]["q"], rtol=1e-10)
    if "p" in g["spatial"]["recurrence_sorted"]:
        assert "p" in tests.columns
        _assert_float_list(sorted_tests.p.tolist(), g["spatial"]["recurrence_sorted"]["p"], rtol=1e-10)
    else:
        assert "p" not in tests.columns

    # signature indicators
    zones, messages, _sectors = signature_indicators(stack, selected_data, selected)
    got = [{"zone": str(r.zone), "Inspected": int(r.Inspected), "Defects": int(r.Defects), "Defect_Rate": float(r.Defect_Rate)} for r in zones.itertuples()]
    for a, e in zip(got, g["signature"]["zones"]):
        assert a["zone"] == e["zone"] and a["Inspected"] == e["Inspected"] and a["Defects"] == e["Defects"]
        assert a["Defect_Rate"] == pytest.approx(e["Defect_Rate"], rel=1e-12)
    assert messages == g["signature"]["messages"]

    # gang yield
    gangs = gang_yield(ref, selected_data)
    for col in ("Wafer_ID", "Die_Num", "Inspected", "Bad", "Total_Springs", "Disposition"):
        assert gangs[col].tolist() == g["gang_yield"]["rows"][col]
    assert gangs.Complete_Inspection.tolist() == g["gang_yield"]["rows"]["Complete_Inspection"]
    _assert_float_list(gangs.Bad_Pct.tolist(), g["gang_yield"]["rows"]["Bad_Pct"])
    assert int((gangs.Disposition == "SCRAP").sum()) == g["gang_yield"]["scrapped"]

    # individual wafer status counts
    for wafer in selected:
        status, counts = individual_wafer_status(ref, selected_data, wafer)
        assert dict(zip(counts.Status, counts.Count.astype(int))) == g["individual"][wafer]["status_counts"]
        assert status.value_counts().astype(int).to_dict() == g["individual"][wafer]["rendered_status_counts"]


def test_golden_headline_numbers(golden):
    """Human-readable pins of the pre-port values (what was compared)."""
    s = golden["scenarios"]["all_six_bw5"]
    assert s["header"] == {"wafers": 6, "springs_in_reference": 20952, "observations": 125712, "bad": 16070, "defect_rate": pytest.approx(0.12783186967035765)}
    assert s["spatial"]["baseline"] == pytest.approx(0.12783186967035765)
    assert s["spatial"]["rate_finite_cells"] == 6036
    assert len(s["spatial"]["peaks"]) == 5
    assert s["gang_yield"]["scrapped"] == 0
    assert [z["zone"] for z in s["signature"]["zones"]] == ["Core (0-35)", "Mid (35-65)", "Outer (65-85)", "Edge (85-100)"]
    assert s["signature"]["messages"][-1].startswith("Spiral patterns require visual and model-based validation")
