"""Capture pre-port golden values from the ORIGINAL Streamlit app.

The analysis functions are lifted verbatim out of
``reference-source/spring_wafer_app/app.py`` with the Python AST (no edits,
no Streamlit install needed: ``st.cache_data`` is replaced by an identity
decorator, which is the only Streamlit symbol those functions touch). The
inline gang-yield / header-metric code from the Streamlit tabs is reproduced
here character for character.

Usage (from ``backend/``)::

    .venv/Scripts/python tests/tools/capture_golden.py

Writes ``tests/fixtures/golden.json``. Re-run only if the reference app or the
bundled synthetic examples legitimately change (they should not).
"""
from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
REFERENCE_APP = REPO / "reference-source" / "spring_wafer_app" / "app.py"
OUT = BACKEND / "tests" / "fixtures" / "golden.json"
PRODUCT = "152-900530D"
FUNCTIONS = ["load_reference", "read_inspection", "stacked_summary", "spatial_analysis", "signature_indicators"]


class _StStub:
    """Minimal stand-in: ``@st.cache_data(show_spinner=False)`` -> identity."""

    @staticmethod
    def cache_data(*_args, **_kwargs):
        return lambda fn: fn


def load_original_functions() -> dict:
    source = REFERENCE_APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    first_def = min(n.lineno for n in tree.body if isinstance(n, ast.FunctionDef))
    # Imports plus the module constants above the first def (ROOT, REF_DIR, COLORS, ...);
    # the Streamlit page code below the functions is never executed.
    keep = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) or (isinstance(n, ast.Assign) and n.lineno < first_def)]
    keep += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    # Drop the streamlit / plotly imports and the module-level st.* calls.
    keep = [
        n for n in keep
        if not (isinstance(n, ast.Import) and any(a.name in ("streamlit", "plotly.graph_objects") for a in n.names))
    ]
    module = ast.Module(body=keep, type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"__file__": str(REFERENCE_APP), "st": _StStub()}
    exec(compile(module, str(REFERENCE_APP), "exec"), ns)  # trusted repo file
    ns["REF_DIR"] = BACKEND / "coordinates"
    return ns


def _num(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) else f
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    return v


def _cols(df: pd.DataFrame, cols: list[str]) -> dict:
    return {c: [_num(v) for v in df[c].tolist()] for c in cols}


def capture_scenario(ns: dict, ref, data: pd.DataFrame, selected: list[str], bandwidth: float) -> dict:
    selected_data = data[data.Wafer_ID.isin(selected)]
    stack = ns["stacked_summary"](ref, selected_data, selected)
    observations = len(selected_data)
    bad = (selected_data.Status != "Good").sum()
    bins, rate, baseline, tests, peaks = ns["spatial_analysis"](stack, selected_data, selected, bandwidth)
    zones, messages = ns["signature_indicators"](stack, selected_data, selected)
    # --- verbatim from the Streamlit "Gang yield" tab ---
    g = selected_data.assign(Bad=lambda d: d.Status.ne("Good")).groupby(["Wafer_ID", "Die_Num"]).agg(Inspected=("Bad", "size"), Bad=("Bad", "sum")).reset_index()
    expected = ref.groupby("Die_Num").size().rename("Total_Springs").reset_index()
    g = g.merge(expected, on="Die_Num"); g["Bad_Pct"] = g.Bad / g.Total_Springs
    g["Complete_Inspection"] = g.Inspected.eq(g.Total_Springs)
    g["Disposition"] = np.select([g.Bad_Pct > .60, ~g.Complete_Inspection], ["SCRAP", "INCOMPLETE"], default="PASS")
    g = g.sort_values(["Wafer_ID", "Die_Num"]).reset_index(drop=True)
    # --- individual wafer status counts (verbatim: one.Status.value_counts()) ---
    individual = {}
    for wafer in selected:
        one = selected_data[selected_data.Wafer_ID == wafer]
        merged = ref.merge(one[["Die_Num", "Spring_Num", "Status"]], on=["Die_Num", "Spring_Num"], how="left")
        individual[wafer] = {
            "status_counts": {k: int(v) for k, v in one.Status.value_counts().items()},
            "rendered_status_counts": {k: int(v) for k, v in merged.Status.fillna("Uninspected").value_counts().items()},
        }
    tests_sorted = tests.sort_values(["q", "Defects"], ascending=[True, False])
    tests_cols = ["Die_Num", "Spring_Num", "Inspected", "Defects", "q"] + (["p"] if "p" in tests.columns else [])
    return {
        "wafers": selected,
        "bandwidth": bandwidth,
        "header": {
            "wafers": len(selected),
            "springs_in_reference": int(len(ref)),
            "observations": int(observations),
            "bad": int(bad),
            "defect_rate": float(bad / observations) if observations else None,
        },
        "stacked": _cols(stack, ["Die_Num", "Spring_Num", "Inspected", "Defects", "Killer", "Defect_Rate"]),
        "stacked_uninspected_count": int((stack.Inspected == 0).sum()),
        "spatial": {
            "bins": [float(b) for b in bins],
            "baseline": float(baseline),
            "rate": [[_num(v) for v in row] for row in rate],
            "rate_finite_cells": int(np.isfinite(rate).sum()),
            "rate_nanmean": float(np.nanmean(rate)) if np.isfinite(rate).any() else None,
            "rate_nanmax": float(np.nanmax(rate)) if np.isfinite(rate).any() else None,
            "peaks": peaks.to_dict(orient="records"),
            "recurrence_rows": int(len(tests)),
            "recurrence_sorted": _cols(tests_sorted, tests_cols),
            "recurrence_top100": _cols(tests_sorted.head(100), tests_cols),
        },
        "signature": {
            "zones": [
                {"zone": str(r.zone), "Inspected": int(r.Inspected), "Defects": int(r.Defects), "Defect_Rate": float(r.Defect_Rate)}
                for r in zones.itertuples()
            ],
            "messages": list(messages),
        },
        "gang_yield": {
            "rows": _cols(g, ["Wafer_ID", "Die_Num", "Inspected", "Bad", "Total_Springs", "Bad_Pct", "Complete_Inspection", "Disposition"]),
            "scrapped": int((g.Disposition == "SCRAP").sum()),
        },
        "individual": individual,
    }


def main() -> None:
    ns = load_original_functions()
    ref, center = ns["load_reference"](PRODUCT)
    valid_keys = pd.MultiIndex.from_frame(ref[["Die_Num", "Spring_Num"]])
    frames = []
    for path in sorted((BACKEND / "examples").glob("SYNTH_WAFER_*.csv")):
        with open(path, "rb") as fh:
            frames.append(ns["read_inspection"](fh, PRODUCT, valid_keys))
    data = pd.concat(frames, ignore_index=True)
    assert not data[["Wafer_ID", "Die_Num", "Spring_Num"]].duplicated().any()
    wafers = sorted(data.Wafer_ID.unique())
    golden = {
        "product": PRODUCT,
        "reference": {
            "springs": int(len(ref)),
            "gangs": int(ref.Die_Num.nunique()),
            "center": [float(center[0]), float(center[1])],
            "x_min": float(ref.x.min()), "x_max": float(ref.x.max()),
            "y_min": float(ref.y.min()), "y_max": float(ref.y.max()),
            "first_rows": _cols(ref.head(5), ["Die_Num", "Spring_Num", "X", "Y", "x", "y"]),
        },
        "wafers": wafers,
        "scenarios": {
            "all_six_bw5": capture_scenario(ns, ref, data, wafers, 5.0),
            "first_three_bw10": capture_scenario(ns, ref, data, wafers[:3], 10.0),
            "single_wafer_bw5": capture_scenario(ns, ref, data, wafers[:1], 5.0),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(golden, separators=(",", ":")), encoding="utf-8")
    s = golden["scenarios"]["all_six_bw5"]
    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.2f} MB)")
    print("center", golden["reference"]["center"], "springs", golden["reference"]["springs"], "gangs", golden["reference"]["gangs"])
    print("header", s["header"])
    print("baseline", s["spatial"]["baseline"], "finite cells", s["spatial"]["rate_finite_cells"], "peaks", len(s["spatial"]["peaks"]))
    print("zones", s["signature"]["zones"])
    print("messages", s["signature"]["messages"])
    print("scrapped", s["gang_yield"]["scrapped"], "dispositions", pd.Series(s["gang_yield"]["rows"]["Disposition"]).value_counts().to_dict())
    print("recurrence rows", s["spatial"]["recurrence_rows"], "q<=0.05:", sum(1 for q in s["spatial"]["recurrence_sorted"]["q"] if q <= 0.05))


if __name__ == "__main__":
    sys.exit(main())
