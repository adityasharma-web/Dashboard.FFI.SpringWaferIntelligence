"""CloudPCS XML adapter tests, on a small synthetic fixture built in the real export's shape."""
from __future__ import annotations

import io
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from engine import CloudPcsAdapterError, GradingMap, InspectionError, load_grading_map, read_cloudpcs_xml
from engine.xml_adapter import DEFAULT_GRADING_MAP_PATH, parse_cloudpcs_rows

COLUMNS = [
    "REGION", "TECHNOLOGY", "PROCESS", "PRODUCT", "PRODUCTGROUP", "SAMPLEID", "PRODUCTTYPE", "DIE_NUM", "SPRING_NUM",
    "ROI", "WAFER_X_DEFECT_NUM", "WAFER_Y_DEFECT_NUM", "UPLOAD_TIMESTAMP", "SPRING_GRADING", "DEFECT_CODE",
    "LOT_REJECT_CODE", "COMMENTS", "SCRAP_STAGE", "EVENT_ID", "SPRING_EVENT_TIME", "DATACOLLECTIONDISPOSITION",
]
TINY = "TEST-PROD"


def build_cloudpcs_xml(rows: list[dict[str, str]]) -> bytes:
    """Same structure as the customer export: HEADER doc + DATA doc with ColHeads / ColTypes / Rows array, one line."""
    def field(name: str, value: str) -> str:
        return f'<Field name="{name}"><String>{escape(value)}</String></Field>'

    head = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Document xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" name="cloudPCSXmlDoc">'
        '<Document name="HEADER">' + field("CONTROLJOBTYPE", "DATACOLLECT") + field("VERSION", "1.1") + '</Document>'
        '<Document name="DATA">'
        f'<Field name="ColHeads"><Array size="{len(COLUMNS)}" type="String">' + "".join(f"<String>{c}</String>" for c in COLUMNS) + '</Array></Field>'
        f'<Field name="ColTypes"><Array size="{len(COLUMNS)}" type="String">' + "".join("<String>TEXT</String>" for _ in COLUMNS) + '</Array></Field>'
        f'<Field name="Rows"><Array size="{len(rows)}" type="Document">'
    )
    body = "".join('<Document name="Rows">' + "".join(field(c, row.get(c, "")) for c in COLUMNS) + '</Document>' for row in rows)
    tail = '</Array></Field></Document></Document>'
    return (head + body + tail).encode("utf-8")


def make_rows(product: str = TINY, sample: str = "W295098.1", dies=(1, 2), springs=range(1, 11), grading="GOOD", code="") -> list[dict[str, str]]:
    rows = []
    for die in dies:
        for spring in springs:
            rows.append({
                "REGION": "Livermore", "TECHNOLOGY": "T15.5A", "PROCESS": "3845S2CMP", "PRODUCT": product,
                "PRODUCTGROUP": "VPS", "SAMPLEID": sample, "PRODUCTTYPE": "E", "DIE_NUM": str(die), "SPRING_NUM": str(spring),
                "ROI": "NONE", "WAFER_X_DEFECT_NUM": "0.0", "WAFER_Y_DEFECT_NUM": "0.0", "UPLOAD_TIMESTAMP": "2026-02-28T12:03:16.000Z",
                "SPRING_GRADING": grading, "DEFECT_CODE": code, "LOT_REJECT_CODE": code, "COMMENTS": "fixture",
                "SCRAP_STAGE": "3845S2CMP", "EVENT_ID": "3164934", "SPRING_EVENT_TIME": "2026-10-08 07:01:58.0",
                "DATACOLLECTIONDISPOSITION": "SUCCESS",
            })
    return rows


MAPPED = GradingMap(by_grading={"GOOD": "Good", "MINOR": "Low"}, by_grading_and_code={"SCRAP|2H": "Killer", "DEFECT|1A": "Med"})


def test_default_grading_map_is_empty_and_explicit():
    assert DEFAULT_GRADING_MAP_PATH.is_file()
    gm = load_grading_map()
    assert gm.is_empty
    with pytest.raises(CloudPcsAdapterError, match="Unmapped SPRING_GRADING value 'SCRAP' \\(DEFECT_CODE '2H'\\)"):
        gm.resolve("SCRAP", "2H")


def test_grading_map_rejects_unknown_targets():
    with pytest.raises(CloudPcsAdapterError, match="not one of"):
        GradingMap(by_grading={"GOOD": "Pass"})


def test_grading_map_from_file(tmp_path: Path):
    p = tmp_path / "map.json"
    p.write_text('{"by_grading": {"GOOD": "Good"}, "by_grading_and_code": {"SCRAP|2H": "Killer"}}', encoding="utf-8")
    gm = load_grading_map(p)
    assert gm.resolve("GOOD", "") == "Good"
    assert gm.resolve("SCRAP", "2H") == "Killer"
    with pytest.raises(CloudPcsAdapterError, match="'SCRAP' \\(DEFECT_CODE '9Z'\\)"):
        gm.resolve("SCRAP", "9Z")  # combo-only mapping does not leak to other codes
    assert load_grading_map(tmp_path / "missing.json").is_empty


def test_parse_streams_rows_and_headers(tmp_path: Path):
    rows = make_rows()
    path = tmp_path / "export.xml"
    path.write_bytes(build_cloudpcs_xml(rows))
    heads, parsed = parse_cloudpcs_rows(path)
    assert heads == COLUMNS
    assert len(parsed) == 20
    assert parsed[0]["PRODUCT"] == TINY and parsed[0]["SPRING_GRADING"] == "GOOD"
    with pytest.raises(CloudPcsAdapterError, match="Not a CloudPCS"):
        parse_cloudpcs_rows(io.BytesIO(b"<root><x/></root>"))


def test_adapter_converts_fixture_to_normalized_frame(tiny_reference_dir):
    rows = make_rows()
    rows[1]["SPRING_GRADING"], rows[1]["DEFECT_CODE"] = "SCRAP", "2H"   # (1,2) -> Killer
    rows[2]["SPRING_GRADING"], rows[2]["DEFECT_CODE"] = "DEFECT", "1A"  # (1,3) -> Med
    rows[3]["SPRING_GRADING"] = "MINOR"                                  # (1,4) -> Low
    rows[3]["COMMENTS"] = "Partial plating on all the gangs"
    product, frames, metadata = read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), name="export.xml", ref_dir=tiny_reference_dir, grading_map=MAPPED)
    assert product == TINY
    assert len(frames) == 1
    frame = frames[0]
    assert list(frame.columns) == ["Wafer_ID", "Die_Num", "Spring_Num", "Status"]
    assert frame.Wafer_ID.unique().tolist() == ["W295098.1"]
    by_key = dict(zip(zip(frame.Die_Num, frame.Spring_Num), frame.Status))
    assert by_key[(1, 1)] == "Good" and by_key[(1, 2)] == "Killer" and by_key[(1, 3)] == "Med" and by_key[(1, 4)] == "Low"
    assert len(frame) == 20 and frame.Die_Num.dtype.kind == "i"
    # metadata carried through, not discarded
    assert {"COMMENTS", "SCRAP_STAGE", "PROCESS", "LOT_REJECT_CODE", "EVENT_ID", "SPRING_EVENT_TIME", "SPRING_GRADING", "DEFECT_CODE"} <= set(metadata.columns)
    assert metadata.COMMENTS.iloc[3] == "Partial plating on all the gangs"
    assert len(metadata) == 20


def test_adapter_splits_multiple_sampleids_into_wafers(tiny_reference_dir):
    rows = make_rows(sample="W1") + make_rows(sample="W2")
    _, frames, _ = read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), ref_dir=tiny_reference_dir, grading_map=MAPPED)
    assert [f.Wafer_ID.iloc[0] for f in frames] == ["W1", "W2"]


def test_unmapped_grading_value_fails_loudly_naming_the_value(tiny_reference_dir):
    rows = make_rows(grading="SCRAP", code="2H")  # the only values seen in the real export
    with pytest.raises(CloudPcsAdapterError) as err:
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), ref_dir=tiny_reference_dir, grading_map=GradingMap())
    msg = str(err.value)
    assert "Unmapped SPRING_GRADING value 'SCRAP'" in msg and "DEFECT_CODE '2H'" in msg and "No default status is assumed" in msg
    # the default (empty) map behaves identically
    with pytest.raises(CloudPcsAdapterError, match="Unmapped SPRING_GRADING value 'SCRAP'"):
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), ref_dir=tiny_reference_dir)


def test_product_without_reference_is_rejected(tiny_reference_dir):
    rows = make_rows(product="152-900405V")
    with pytest.raises(CloudPcsAdapterError, match="no coordinate reference for product '152-900405V'"):
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), name="real.xml", ref_dir=tiny_reference_dir, grading_map=MAPPED)


def test_geometry_mismatch_is_rejected_before_any_render(tiny_reference_dir):
    rows = make_rows(dies=(1, 2, 3), springs=range(1, 13))  # 3 gangs x 12 springs vs reference 2 x 10
    with pytest.raises(CloudPcsAdapterError) as err:
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), name="geo.xml", ref_dir=tiny_reference_dir, grading_map=MAPPED)
    msg = str(err.value)
    assert "spring keys are not present in the TEST-PROD reference" in msg
    assert "export has 3 gangs x up to 12 springs" in msg and "reference has 2 gangs x up to 10 springs" in msg


def test_product_filter_and_mixed_products(tiny_reference_dir):
    rows = make_rows()
    with pytest.raises(CloudPcsAdapterError, match="export is for product 'TEST-PROD', but 'OTHER' was selected"):
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), ref_dir=tiny_reference_dir, grading_map=MAPPED, product="OTHER")
    rows[0]["PRODUCT"] = "SOMETHING-ELSE"
    with pytest.raises(CloudPcsAdapterError, match="mixes products"):
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), ref_dir=tiny_reference_dir, grading_map=MAPPED)


def test_missing_required_columns_and_empty_export(tiny_reference_dir):
    rows = make_rows()
    for r in rows:
        r.pop("SPRING_GRADING")
    xml = build_cloudpcs_xml(rows).replace(b"<String>SPRING_GRADING</String>", b"")
    xml = xml.replace(b'<Field name="SPRING_GRADING"><String></String></Field>', b"")
    with pytest.raises(CloudPcsAdapterError, match="missing required columns \\['SPRING_GRADING'\\]"):
        read_cloudpcs_xml(io.BytesIO(xml), ref_dir=tiny_reference_dir, grading_map=MAPPED)
    with pytest.raises(CloudPcsAdapterError, match="contains no rows"):
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml([])), ref_dir=tiny_reference_dir, grading_map=MAPPED)


def test_adapter_preserves_engine_uniqueness_rule(tiny_reference_dir):
    rows = make_rows() + make_rows(dies=(1,), springs=[1])  # duplicate (1,1) within the same SAMPLEID
    with pytest.raises(InspectionError, match="duplicate Die_Num/Spring_Num"):
        read_cloudpcs_xml(io.BytesIO(build_cloudpcs_xml(rows)), ref_dir=tiny_reference_dir, grading_map=MAPPED)
