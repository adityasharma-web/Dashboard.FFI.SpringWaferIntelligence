"""Die-only layouts: one row per die, no spring level (engine, adapter and API)."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import app
from engine import (
    CloudPcsAdapterError,
    InspectionError,
    ReferenceError,
    gang_yield,
    list_layouts,
    load_reference,
    preview_layout,
    read_cloudpcs_xml,
    save_layout,
    stacked_summary,
    valid_spring_keys,
    validate_inspection,
)
from engine.reference import layout_kind
from tests.conftest import BACKEND
from tests.test_xml_adapter import TINY, build_cloudpcs_xml, make_rows

client = TestClient(app)

# The shape of the customer's 159-511159A.csv: "Die #, X, Y" in micrometres, wafer-centered.
DIE_CSV = b"Die #,X,Y\n1,-21032.51,72552.7859\n2,0,72552.7859\n3,21032.51,72552.7859\n4,-21032.51,62188.1022\n5,0,62188.1022\n6,21032.51,62188.1022\n7,0,0\n"


# --------------------------------------------------------------------------- parsing
def test_die_only_layout_parses_as_die_kind_with_micrometre_conversion():
    ref, center, summary = preview_layout("159-511159A.csv", DIE_CSV)
    assert layout_kind(ref) == "die" and ref.attrs["units"] == "um->mm"
    assert list(ref.columns) == ["Die_Num", "Spring_Num", "X", "Y", "x", "y"]
    assert ref.Spring_Num.eq(1).all() and len(ref) == 7
    assert ref.X.max() == pytest.approx(21.03251) and ref.Y.max() == pytest.approx(72.5527859)
    assert summary.kind == "die" and summary.units == "um->mm"
    assert summary.springs == 7 and summary.gangs == 7 and summary.springs_per_gang_min == 1
    assert summary.pitch_x_mm == pytest.approx(21.03251) and summary.pitch_y_mm == pytest.approx(10.3646837)
    assert any("micrometres" in w for w in summary.warnings)
    assert not any("Spring_Num 1" in w for w in summary.warnings)
    assert center == pytest.approx((0.0, 72.5527859 / 2))


def test_die_only_duplicate_and_column_aliases():
    with pytest.raises(ReferenceError, match="Duplicate die numbers"):
        preview_layout("d.csv", b"Die #,X,Y\n1,0,0\n1,1,1\n")
    ref, _, summary = preview_layout("d.csv", b"DIE_NUM,x_um,y_um\n1,0,0\n2,5000,0\n")
    assert layout_kind(ref) == "die" and summary.units == "um->mm" and summary.pitch_x_mm == pytest.approx(5.0)
    ref, _, summary = preview_layout("d.csv", b"Gang Number,Spring Number,X (mm),Y (mm)\n1,1,0,0\n1,2,0,0.18\n")
    assert layout_kind(ref) == "spring" and summary.units == "mm" and summary.pitch_x_mm is None


def test_spring_layouts_are_unchanged(reference):
    ref, center = reference
    assert layout_kind(ref) == "spring" and ref.attrs["units"] == "mm"
    assert len(ref) == 20952 and center == pytest.approx((71.245, -0.5015))


def test_die_layout_saves_with_kind_and_resolves(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    item = save_layout(ref_dir, name="159-511159A", products=["159-511159A"], filename="159-511159A.csv", payload=DIE_CSV)
    assert item["summary"]["kind"] == "die"
    assert json.loads((ref_dir / "layouts.json").read_text())["layouts"][0]["kind"] == "die"
    ref, _ = load_reference("159-511159A", ref_dir)
    assert layout_kind(ref) == "die" and len(ref) == 7
    assert list_layouts(ref_dir)[0]["summary"]["kind"] == "die"


def test_example_die_layout_file():
    path = BACKEND / "examples" / "layouts" / "EXAMPLE-DIE-LAYOUT.csv"
    ref, _center, summary = preview_layout(path.name, path.read_bytes())
    assert summary.kind == "die" and summary.units == "um->mm" and summary.max_radius_mm < 100
    assert summary.gangs == len(ref) and summary.gangs > 50


# --------------------------------------------------------------------------- inspections without a spring level
def _die_reference(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    ref_dir.mkdir()
    (ref_dir / "DIE-PROD.csv").write_bytes(b"Die #,X,Y\n1,-21032.51,0\n2,0,0\n3,21032.51,0\n4,0,10364.6837\n")
    ref, _ = load_reference("DIE-PROD", ref_dir)
    return ref_dir, ref, valid_spring_keys(ref)


def test_die_only_inspection_without_spring_column(tmp_path: Path):
    _ref_dir, ref, keys = _die_reference(tmp_path)
    frame = pd.DataFrame({"Product": "DIE-PROD", "Wafer_ID": "W1", "Die_Num": [1, 2, 3], "Defect": ["N", "Y", "N"], "Defect_Severity": ["", "Killer", ""]})
    with pytest.raises(InspectionError, match="missing"):
        validate_inspection(frame, "W1.csv", "DIE-PROD", keys)
    out = validate_inspection(frame, "W1.csv", "DIE-PROD", keys, die_only=True)
    assert out.Spring_Num.eq(1).all() and out.Status.tolist() == ["Good", "Killer", "Good"]
    stack = stacked_summary(ref, out, ["W1"])
    assert stack.Inspected.tolist() == [1, 1, 1, 0] and stack.Defects.tolist() == [0, 1, 0, 0]
    g = gang_yield(ref, out).set_index("Die_Num")
    assert g.loc[2, "Disposition"] == "SCRAP" and g.loc[1, "Disposition"] == "PASS" and g.loc[2, "Total_Springs"] == 1
    assert 4 not in g.index  # die 4 uninspected: no row, never Good
    blank = frame.assign(Spring_Num="")
    assert validate_inspection(blank, "W1.csv", "DIE-PROD", keys, die_only=True).Spring_Num.eq(1).all()


def test_die_layout_cloudpcs_export_without_spring_num(tmp_path: Path):
    ref_dir, _ref, _keys = _die_reference(tmp_path)
    rows = make_rows(product="DIE-PROD", dies=(1, 2, 3), springs=[""], grading="GOOD")
    rows[1]["SPRING_GRADING"], rows[1]["DEFECT_CODE"] = "SCRAP", "H8"
    product, frames, _ = read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), ref_dir=ref_dir)
    assert product == "DIE-PROD" and frames[0].Spring_Num.eq(1).all()
    assert frames[0].Status.tolist() == ["Good", "H8", "Good"]


def test_spring_layout_cloudpcs_export_still_needs_spring_num(tiny_reference_dir):
    rows = make_rows(product=TINY, springs=[""])
    with pytest.raises((CloudPcsAdapterError, InspectionError)):
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), ref_dir=tiny_reference_dir)


# --------------------------------------------------------------------------- API
@pytest.fixture
def layout_dir(tmp_path, monkeypatch):
    import shutil
    import app as app_module
    ref_dir = tmp_path / "coordinates"
    ref_dir.mkdir()
    shutil.copy(BACKEND / "coordinates" / "152-900530D.xlsx", ref_dir / "152-900530D.xlsx")
    monkeypatch.setattr(app_module, "REF_DIR", ref_dir)
    app_module._reference.cache_clear()
    yield ref_dir
    app_module._reference.cache_clear()


def test_die_layout_end_to_end(layout_dir):
    die_csv = (BACKEND / "examples" / "layouts" / "EXAMPLE-DIE-LAYOUT.csv").read_bytes()
    res = client.post("/api/layouts/preview", files=[("file", ("EXAMPLE-DIE-LAYOUT.csv", die_csv, "text/csv"))])
    assert res.status_code == 200, res.text
    preview = res.json()
    assert preview["kind"] == "die" and preview["pitch"]["x"] == pytest.approx(21.03251) and preview["summary"]["units"] == "um->mm"
    res = client.post("/api/layouts", data={"name": "DIE-DEMO", "products": "159-511159A"}, files=[("file", ("EXAMPLE-DIE-LAYOUT.csv", die_csv, "text/csv"))])
    assert res.status_code == 200, res.text
    assert res.json()["summary"]["kind"] == "die"
    ref = client.get("/api/reference/159-511159A").json()
    assert ref["kind"] == "die" and ref["pitch"]["y"] == pytest.approx(10.364684) and ref["spring_count"] == ref["gang_count"]
    n = ref["gang_count"]
    # a die-level inspection: no Spring_Num column at all
    rows = pd.DataFrame({
        "Product": "159-511159A", "Wafer_ID": "WD1", "Die_Num": list(range(1, n + 1)),
        "Defect": ["Y" if i % 7 == 0 else "N" for i in range(n)], "Defect_Severity": ["Killer" if i % 7 == 0 else "" for i in range(n)],
    })
    res = client.post("/api/inspections", data={"product": "159-511159A"}, files=[("files", ("WD1.csv", rows.to_csv(index=False).encode(), "text/csv"))])
    assert res.status_code == 200, res.text
    analysis = client.post("/api/analyze", json={"session_id": res.json()["session_id"]}).json()
    assert analysis["header"]["observations"] == n
    assert analysis["gang_yield"]["scrapped"] == sum(1 for i in range(n) if i % 7 == 0)
    assert all(r["total_springs"] == 1 for r in analysis["gang_yield"]["rows"])
    assert client.get("/api/reference/152-900530D").json()["kind"] == "spring"
    assert client.delete("/api/layouts/DIE-DEMO").status_code == 200
