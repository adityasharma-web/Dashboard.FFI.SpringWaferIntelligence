"""API contract tests: the service is a thin wrapper and must return the engine's numbers."""
from __future__ import annotations

import io
import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import app
from tests.conftest import BACKEND, make_inspection
from tests.test_xml_adapter import build_cloudpcs_xml, make_rows

client = TestClient(app)
PRODUCT = "152-900530D"


@pytest.fixture(scope="module")
def examples_session() -> dict:
    res = client.post("/api/examples")
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture(scope="module")
def analysis(examples_session) -> dict:
    res = client.post("/api/analyze", json={"session_id": examples_session["session_id"], "bandwidth": 5.0})
    assert res.status_code == 200, res.text
    return res.json()


def test_health_and_products():
    assert client.get("/api/health").json() == {"status": "ok"}
    body = client.get("/api/products").json()
    assert PRODUCT in body["products"]  # other layouts may have been saved through the Layouts page
    assert body["examples_product"] == PRODUCT and body["examples_available"] is True


def test_reference_endpoint(golden):
    res = client.get(f"/api/reference/{PRODUCT}")
    assert res.status_code == 200
    body = res.json()
    assert body["spring_count"] == 20952 and body["gang_count"] == 108
    assert body["center"] == {"x": pytest.approx(71.245), "y": pytest.approx(-0.5015)}
    assert len(body["x"]) == len(body["y"]) == len(body["die"]) == len(body["spring"]) == 20952
    assert len(body["gangs"]) == 108 and {"die", "xmin", "xmax", "ymin", "ymax"} <= set(body["gangs"][0])
    assert "Notch down assumed" in body["caveat"]
    assert body["x"][:5] == pytest.approx(golden["reference"]["first_rows"]["x"])
    assert client.get("/api/reference/NOPE").status_code == 422


def test_examples_are_labeled_synthetic(examples_session):
    assert examples_session["synthetic"] is True and examples_session["source"] == "synthetic_examples"
    assert examples_session["wafers"] == [f"SYNTH_WAFER_{i:02d}" for i in range(1, 7)]
    assert [f["observations"] for f in examples_session["files"]] == [20952] * 6


def test_analyze_matches_golden(analysis, golden):
    g = golden["scenarios"]["all_six_bw5"]
    assert analysis["synthetic"] is True
    assert analysis["header"]["observations"] == g["header"]["observations"] == 125712
    assert analysis["header"]["bad"] == g["header"]["bad"]
    assert analysis["header"]["defect_rate"] == pytest.approx(g["header"]["defect_rate"])
    assert analysis["stacked"]["inspected"] == g["stacked"]["Inspected"]
    assert analysis["stacked"]["defects"] == g["stacked"]["Defects"]
    assert analysis["stacked"]["killer"] == g["stacked"]["Killer"]
    assert analysis["stacked"]["die"] == g["stacked"]["Die_Num"] and analysis["stacked"]["spring"] == g["stacked"]["Spring_Num"]
    for a, e in zip(analysis["stacked"]["defect_rate"], g["stacked"]["Defect_Rate"]):
        assert (a is None and e is None) or a == pytest.approx(e)
    assert analysis["spatial"]["baseline"] == pytest.approx(g["spatial"]["baseline"])
    assert analysis["spatial"]["peaks"] == g["spatial"]["peaks"]
    # the API grid is the transpose (rows = y bins) of the engine grid
    grid = analysis["spatial"]["rate_grid"]
    assert len(grid) == 102 and len(grid[0]) == 102  # 103 edges from -102 to 102 -> 102 cells
    finite = sum(1 for row in grid for v in row if v is not None)
    assert finite == g["spatial"]["rate_finite_cells"]
    for i in range(102):
        for j in range(102):
            e = g["spatial"]["rate"][i][j]
            a = grid[j][i]
            assert (a is None and e is None) or a == pytest.approx(e)
    top = g["spatial"]["recurrence_top100"]
    rec = analysis["spatial"]["recurrence"]
    assert len(rec) == 100 and analysis["spatial"]["recurrence_total_rows"] == g["spatial"]["recurrence_rows"]
    assert analysis["spatial"]["recurrence_tested"] is True and analysis["spatial"]["recurrence_min_inspected"] == 5
    assert [r["die"] for r in rec] == top["Die_Num"] and [r["spring"] for r in rec] == top["Spring_Num"]
    assert [r["q"] for r in rec] == pytest.approx(top["q"])
    assert [r["p"] for r in rec] == pytest.approx(top["p"])
    zones = analysis["signature"]["zones"]
    assert [z["zone"] for z in zones] == [z["zone"] for z in g["signature"]["zones"]]
    assert [z["defect_rate"] for z in zones] == pytest.approx([z["Defect_Rate"] for z in g["signature"]["zones"]])
    assert analysis["signature"]["messages"] == g["signature"]["messages"]
    assert len(analysis["signature"]["sectors"]) == 12
    gy = analysis["gang_yield"]
    assert gy["scrapped"] == g["gang_yield"]["scrapped"] and gy["total"] == 648 and gy["threshold"] == 0.6
    assert [r["disposition"] for r in gy["rows"]] == g["gang_yield"]["rows"]["Disposition"]
    assert [r["bad_pct"] for r in gy["rows"]] == pytest.approx(g["gang_yield"]["rows"]["Bad_Pct"])
    assert "> 60%" in gy["rule"]
    ind = {w["wafer_id"]: w for w in analysis["individual"]}
    assert set(ind) == set(g["wafers"])
    for wafer, exp in g["individual"].items():
        assert {c["status"]: c["count"] for c in ind[wafer]["counts"]} == exp["status_counts"]
        assert len(ind[wafer]["status_codes"]) == 20952 and ind[wafer]["uninspected"] == 0
    assert analysis["states"] == ["Good", "Low", "Med", "Killer", "Uninspected"]
    assert analysis["colors"]["Good"] == "#21a653" and analysis["colors"]["Uninspected"] == "#aab4c2"
    assert "not a validated manufacturing release decision system" in analysis["caveats"]["scope"]
    assert "spiral" in analysis["caveats"]["spiral"].lower()


def test_analyze_subset_matches_golden(examples_session, golden):
    g = golden["scenarios"]["first_three_bw10"]
    res = client.post("/api/analyze", json={"session_id": examples_session["session_id"], "wafers": g["wafers"], "bandwidth": 10.0})
    assert res.status_code == 200
    body = res.json()
    assert body["wafers"] == g["wafers"] and body["bandwidth"] == 10.0
    assert body["header"]["observations"] == g["header"]["observations"]
    assert body["spatial"]["baseline"] == pytest.approx(g["spatial"]["baseline"])
    assert body["spatial"]["peaks"] == g["spatial"]["peaks"]
    assert body["signature"]["messages"] == g["signature"]["messages"]
    # cached re-request is identical
    again = client.post("/api/analyze", json={"session_id": examples_session["session_id"], "wafers": g["wafers"], "bandwidth": 10.0}).json()
    assert again == body


def test_analyze_validation(examples_session):
    sid = examples_session["session_id"]
    assert client.post("/api/analyze", json={"session_id": "nope"}).status_code == 404
    assert client.post("/api/analyze", json={"session_id": sid, "bandwidth": 1.0}).status_code == 422
    assert client.post("/api/analyze", json={"session_id": sid, "bandwidth": 16.0}).status_code == 422
    res = client.post("/api/analyze", json={"session_id": sid, "wafers": ["NOPE"]})
    assert res.status_code == 422 and "Unknown wafer" in res.json()["detail"]


def test_exports(examples_session, golden):
    sid = examples_session["session_id"]
    res = client.get("/api/export/stacked", params={"session_id": sid})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert 'filename="152-900530D_stacked_spring_metrics.csv"' in res.headers["content-disposition"]
    stacked = pd.read_csv(io.StringIO(res.text))
    assert list(stacked.columns) == ["Die_Num", "Spring_Num", "x", "y", "Inspected", "Defects", "Killer", "Defect_Rate"]
    assert len(stacked) == 20952 and stacked.Inspected.tolist() == golden["scenarios"]["all_six_bw5"]["stacked"]["Inspected"]

    res = client.get("/api/export/inspection", params={"session_id": sid, "wafers": ["SYNTH_WAFER_01"]})
    assert res.status_code == 200
    assert 'filename="152-900530D_inspection_normalized.csv"' in res.headers["content-disposition"]
    norm = pd.read_csv(io.StringIO(res.text))
    assert list(norm.columns) == ["Wafer_ID", "Die_Num", "Spring_Num", "Status"]
    assert len(norm) == 20952 and norm.Wafer_ID.unique().tolist() == ["SYNTH_WAFER_01"]


def test_upload_reports_every_error_and_loads_nothing(reference):
    ref, _ = reference
    good = (BACKEND / "examples" / "SYNTH_WAFER_01.csv").read_bytes()
    wrong_product = good.replace(b"152-900530D", b"152-900405V")
    bad_severity = good.replace(b",Y,Med", b",Y,High", 1)
    res = client.post(
        "/api/inspections",
        data={"product": PRODUCT},
        files=[("files", ("ok.csv", good, "text/csv")), ("files", ("wrong.csv", wrong_product, "text/csv")), ("files", ("sev.csv", bad_severity, "text/csv"))],
    )
    assert res.status_code == 422
    body = res.json()
    errors = {e["filename"]: e["error"] for e in body["errors"]}
    assert set(errors) == {"wrong.csv", "sev.csv"}
    assert "product mismatch" in errors["wrong.csv"] and "Y defects require" in errors["sev.csv"]
    assert "session_id" not in body


def test_upload_duplicate_wafer_across_files_is_rejected():
    good = (BACKEND / "examples" / "SYNTH_WAFER_01.csv").read_bytes()
    res = client.post("/api/inspections", data={"product": PRODUCT}, files=[("files", ("a.csv", good, "text/csv")), ("files", ("b.csv", good, "text/csv"))])
    assert res.status_code == 422
    assert any("Duplicate wafer/spring keys across input files" in e["error"] for e in res.json()["errors"])


def test_upload_success_and_uninspected_flow(reference):
    ref, _ = reference
    full = pd.read_csv(BACKEND / "examples" / "SYNTH_WAFER_02.csv")
    partial = full.iloc[:-500].copy()  # drop the last 500 observations -> uninspected, never Good
    buf = partial.to_csv(index=False).encode()
    res = client.post("/api/inspections", data={"product": PRODUCT}, files=[("files", ("partial.csv", buf, "text/csv"))])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["synthetic"] is False and body["source"] == "upload"
    assert body["files"][0]["observations"] == 20952 - 500
    analysis = client.post("/api/analyze", json={"session_id": body["session_id"]}).json()
    assert analysis["stacked"]["uninspected_springs"] == 500
    assert analysis["individual"][0]["uninspected"] == 500
    assert analysis["individual"][0]["status_codes"].count(4) == 500
    assert sum(1 for v in analysis["stacked"]["defect_rate"] if v is None) == 500
    assert analysis["header"]["observations"] == 20952 - 500
    assert "INCOMPLETE" in {r["disposition"] for r in analysis["gang_yield"]["rows"]}
    assert "Good" not in {c["status"] for c in analysis["individual"][0]["counts"] if c["count"] == 0}


def test_upload_xml_without_reference_is_rejected_with_specific_message():
    xml = build_cloudpcs_xml(make_rows(product="152-900405V", grading="SCRAP", code="2H"))
    res = client.post("/api/inspections", data={"product": "152-900405V"}, files=[("files", ("real.xml", xml, "application/xml"))])
    assert res.status_code == 422
    # the product has no reference at all, so the request fails at the product level
    assert "No reference found for 152-900405V" in res.json()["detail"]


def _real_shaped_xml() -> bytes:
    """One full 152-900530D wafer in the real export's shape: codes by frequency H8 > XL > TT, one UNCODED, rest GOOD."""
    rows = make_rows(product=PRODUCT, sample="W304617.1", dies=range(1, 109), springs=range(1, 195))
    plan = [("H8", 300), ("XL", 200), ("TT", 100)]
    i = 0
    for code, n in plan:
        for _ in range(n):
            rows[i]["SPRING_GRADING"], rows[i]["DEFECT_CODE"] = "SCRAP", code
            i += 1
    rows[i]["SPRING_GRADING"], rows[i]["DEFECT_CODE"] = "SCRAP", ""
    rows[i + 1]["SPRING_GRADING"], rows[i + 1]["DEFECT_CODE"] = "REWORK", "AY"  # not SCRAP -> Good
    return build_cloudpcs_xml(rows)


def test_upload_xml_uses_the_defect_code_status_model():
    res = client.post("/api/inspections", data={"product": PRODUCT}, files=[("files", ("export.xml", _real_shaped_xml(), "application/xml"))])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status_model"] == "defect_code" and body["synthetic"] is False
    assert body["wafers"] == ["W304617.1"] and body["files"][0]["observations"] == 20952

    analysis = client.post("/api/analyze", json={"session_id": body["session_id"]}).json()
    assert analysis["status_model"] == "defect_code"
    assert analysis["states"] == ["Good", "H8", "XL", "TT", "UNCODED", "Uninspected"]  # by frequency, Good first, Uninspected last
    assert analysis["colors"]["Good"] == "#21a653" and analysis["colors"]["Uninspected"] == "#aab4c2"
    assert analysis["colors"]["H8"] == "#df3537" and analysis["colors"]["XL"] == "#f38a24"
    assert len({analysis["colors"][s] for s in analysis["states"]}) == 6  # all distinct
    assert analysis["status_counts"] == [
        {"status": "Good", "count": 20952 - 601}, {"status": "H8", "count": 300}, {"status": "XL", "count": 200},
        {"status": "TT", "count": 100}, {"status": "UNCODED", "count": 1},
    ]
    assert analysis["header"]["bad"] == 601 and analysis["header"]["defect_rate"] == pytest.approx(601 / 20952)
    codes = analysis["individual"][0]["status_codes"]
    assert codes.count(1) == 300 and codes.count(2) == 200 and codes.count(3) == 100 and codes.count(4) == 1 and codes.count(0) == 20952 - 601
    counts = {c["status"]: c["count"] for c in analysis["individual"][0]["counts"]}
    assert counts == {"Good": 20952 - 601, "H8": 300, "XL": 200, "TT": 100, "UNCODED": 1}
    # the severity-free analyses still run: killer is simply 0, gang yield works on Status != Good
    assert sum(analysis["stacked"]["killer"]) == 0 and sum(analysis["stacked"]["defects"]) == 601
    gang1 = next(r for r in analysis["gang_yield"]["rows"] if r["die"] == 1)
    assert gang1["bad"] == 194 and gang1["disposition"] == "SCRAP"
    assert analysis["gang_yield"]["scrapped"] == 3  # 601 bad springs fill gangs 1-3 (194 each) and spill 19 into gang 4


def test_csv_sessions_keep_the_severity_status_model(examples_session):
    assert examples_session["status_model"] == "severity"
    analysis = client.post("/api/analyze", json={"session_id": examples_session["session_id"]}).json()
    assert analysis["status_model"] == "severity"
    assert analysis["states"] == ["Good", "Low", "Med", "Killer", "Uninspected"]
    assert [c["status"] for c in analysis["status_counts"]] == ["Good", "Low", "Med", "Killer"]


def test_mixing_xml_and_csv_in_one_upload_is_rejected():
    good = (BACKEND / "examples" / "SYNTH_WAFER_01.csv").read_bytes()
    res = client.post("/api/inspections", data={"product": PRODUCT}, files=[("files", ("a.csv", good, "text/csv")), ("files", ("b.xml", _real_shaped_xml(), "application/xml"))])
    assert res.status_code == 422
    assert "cannot be mixed" in res.json()["detail"]


def test_session_lookup(examples_session):
    body = client.get(f"/api/sessions/{examples_session['session_id']}").json()
    assert body == examples_session
    assert client.get("/api/sessions/nope").status_code == 404


@pytest.fixture
def layout_dir(tmp_path, monkeypatch):
    """Point the API at a temp coordinates folder seeded with the bundled reference."""
    import shutil
    import app as app_module
    ref_dir = tmp_path / "coordinates"
    ref_dir.mkdir()
    shutil.copy(BACKEND / "coordinates" / "152-900530D.xlsx", ref_dir / "152-900530D.xlsx")
    monkeypatch.setattr(app_module, "REF_DIR", ref_dir)
    app_module._reference.cache_clear()
    yield ref_dir
    app_module._reference.cache_clear()


def _layout_csv(dies=(1, 2), springs=range(1, 11)) -> bytes:
    rows = [{"Die_Num (gang_number)": d, "Spring_Num (spring_number)": s, "X": 10.0 * d + 0.5 * s, "Y": 100.0 - 2.0 * s} for d in dies for s in springs]
    return pd.DataFrame(rows).to_csv(index=False).encode()


def test_layouts_list_preview_save_delete(layout_dir):
    body = client.get("/api/layouts").json()
    assert [l["name"] for l in body["layouts"]] == ["152-900530D"]
    assert body["layouts"][0]["implicit"] is True and body["layouts"][0]["summary"]["gangs"] == 108

    res = client.post("/api/layouts/preview", files=[("file", ("152-900777Z layout.csv", _layout_csv(), "text/csv"))])
    assert res.status_code == 200, res.text
    preview = res.json()
    assert preview["suggested_name"] == "152-900777Z layout"
    assert preview["summary"]["springs"] == 20 and preview["summary"]["gangs"] == 2 and preview["summary"]["warnings"] == []
    assert len(preview["x"]) == 20 and len(preview["gangs"]) == 2 and "Notch down assumed" in preview["caveat"]
    assert client.get("/api/layouts").json()["layouts"][0]["name"] == "152-900530D"  # preview stored nothing
    assert len(client.get("/api/layouts").json()["layouts"]) == 1

    res = client.post("/api/layouts", data={"name": "LAYOUT-Z", "products": "152-900777Z, 152-900777Y\n152-900777X"}, files=[("file", ("z.csv", _layout_csv(), "text/csv"))])
    assert res.status_code == 200, res.text
    saved = res.json()
    assert saved["name"] == "LAYOUT-Z" and saved["products"] == ["152-900777Z", "152-900777Y", "152-900777X"] and saved["implicit"] is False
    assert client.get("/api/products").json()["products"] == ["152-900530D", "152-900777X", "152-900777Y", "152-900777Z"]
    ref = client.get("/api/reference/152-900777Y").json()
    assert ref["spring_count"] == 20 and ref["gang_count"] == 2

    # replace required; product conflict rejected
    res = client.post("/api/layouts", data={"name": "layout-z", "products": "152-900777Z"}, files=[("file", ("z.csv", _layout_csv(), "text/csv"))])
    assert res.status_code == 422 and "already exists" in res.json()["detail"]
    res = client.post("/api/layouts", data={"name": "OTHER", "products": "152-900777Z"}, files=[("file", ("z.csv", _layout_csv(), "text/csv"))])
    assert res.status_code == 422 and "already belong to layout 'LAYOUT-Z'" in res.json()["detail"]
    res = client.post("/api/layouts", data={"name": "LAYOUT-Z", "products": "152-900777Z", "replace": "true"}, files=[("file", ("z3.csv", _layout_csv(dies=(1, 2, 3)), "text/csv"))])
    assert res.status_code == 200 and res.json()["summary"]["gangs"] == 3
    assert client.get("/api/reference/152-900777Z").json()["gang_count"] == 3  # cache invalidated
    assert client.get("/api/reference/152-900777Y").status_code == 422  # alias removed by the replace

    res = client.delete("/api/layouts/LAYOUT-Z")
    assert res.status_code == 200 and res.json()["file"] == "LAYOUT-Z.csv"
    assert client.get("/api/products").json()["products"] == ["152-900530D"]
    assert client.delete("/api/layouts/LAYOUT-Z").status_code == 404


def test_layout_preview_rejects_bad_files(layout_dir):
    res = client.post("/api/layouts/preview", files=[("file", ("bad.csv", b"Die_Num,Spring_Num,X\n1,1,0\n", "text/csv"))])
    assert res.status_code == 422 and "Reference must contain" in res.json()["detail"]
    res = client.post("/api/layouts/preview", files=[("file", ("bad.txt", b"x", "text/plain"))])
    assert res.status_code == 422 and "must be .csv or .xlsx" in res.json()["detail"]
    res = client.post("/api/layouts", data={"name": "../x"}, files=[("file", ("ok.csv", _layout_csv(), "text/csv"))])
    assert res.status_code == 422 and "Layout name must be" in res.json()["detail"]


def test_static_mount_not_required_for_api():
    assert client.get("/api/health").status_code == 200
