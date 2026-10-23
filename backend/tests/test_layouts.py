"""Layout registry tests: preview, save, alias resolution, replace, delete, implicit files."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from engine import (
    LayoutError,
    ReferenceError,
    delete_layout,
    list_layouts,
    list_products,
    load_reference,
    preview_layout,
    resolve_product,
    save_layout,
)
from tests.conftest import BACKEND


def csv_bytes(dies=(1, 2), springs=range(1, 11), scale=1.0) -> bytes:
    rows = [{"Die_Num (gang_number)": d, "Spring_Num (spring_number)": s, "feature": "A", "X": (10.0 * d + 0.5 * s) * scale, "Y": (100.0 - 2.0 * s) * scale} for d in dies for s in springs]
    return pd.DataFrame(rows).to_csv(index=False).encode()


def test_preview_parses_without_writing(tmp_path: Path):
    ref, center, summary = preview_layout("MY LAYOUT.csv", csv_bytes())
    assert len(ref) == 20 and summary.springs == 20 and summary.gangs == 2
    assert summary.springs_per_gang_min == summary.springs_per_gang_max == 10
    assert (summary.center_x, summary.center_y) == pytest.approx(((10.5 + 25.0) / 2, (80.0 + 98.0) / 2))
    assert summary.warnings == []
    assert list(tmp_path.iterdir()) == []


def test_preview_warns_on_out_of_wafer_and_uneven_gangs():
    _, _, summary = preview_layout("big.csv", csv_bytes(scale=10.0))  # still mm (< 1000), but spanning beyond the wafer edge
    assert any("outside the 200 mm wafer" in w for w in summary.warnings)
    _, _, summary = preview_layout("um.csv", csv_bytes(scale=1000.0))  # micrometres: converted, back inside the wafer
    assert any("micrometres" in w for w in summary.warnings) and not any("outside" in w for w in summary.warnings)
    rows = pd.DataFrame({"Die_Num": [1, 1, 2, 3], "Spring_Num": [1, 2, 1, 1], "X": [0, 1, 2, 3], "Y": [0, 1, 2, 3]})
    _, _, summary = preview_layout("uneven.csv", rows.to_csv(index=False).encode())
    assert any("same spring count" in w for w in summary.warnings)


@pytest.mark.parametrize("filename, payload, message", [
    ("layout.txt", b"x", "must be .csv or .xlsx"),
    ("layout.csv", b"Die_Num,Spring_Num,X\n1,1,0\n", "Reference must contain"),
    ("layout.csv", b"Die_Num,Spring_Num,X,Y\n1,1,0,0\n1,1,1,1\n", "Duplicate spring keys"),
    ("layout.csv", b"Die_Num,Spring_Num,X,Y\n1,1.5,0,0\n", "must be integers"),
    ("layout.csv", b"Die_Num,Spring_Num,X,Y\n1,1,abc,0\n", "must be numeric"),
    ("layout.csv", b"Die_Num,Spring_Num,X,Y\n", "contains no rows"),
])
def test_preview_rejections(filename, payload, message):
    with pytest.raises((LayoutError, ReferenceError), match=message):
        preview_layout(filename, payload)


def test_save_registers_and_resolves_aliases(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    item = save_layout(ref_dir, name="LAYOUT-A", products=["152-900111A", "152-900111B", " 152-900111A "], filename="upload.csv", payload=csv_bytes())
    assert (ref_dir / "LAYOUT-A.csv").is_file()
    assert item["products"] == ["152-900111A", "152-900111B"]
    assert item["summary"]["springs"] == 20 and item["implicit"] is False and item["source_filename"] == "upload.csv"
    registry = json.loads((ref_dir / "layouts.json").read_text())
    assert registry["layouts"][0]["name"] == "LAYOUT-A"
    assert list_products(ref_dir) == ["152-900111A", "152-900111B"]
    assert resolve_product("152-900111B", ref_dir) == ref_dir / "LAYOUT-A.csv"
    assert resolve_product("LAYOUT-A", ref_dir) is None  # the layout name itself is not a product unless listed
    ref, center = load_reference("152-900111A", ref_dir)
    assert len(ref) == 20
    with pytest.raises(ReferenceError, match="No reference found for NOPE"):
        load_reference("NOPE", ref_dir)


def test_products_default_to_the_layout_name(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    item = save_layout(ref_dir, name="152-900222C", products=[], filename="c.csv", payload=csv_bytes())
    assert item["products"] == ["152-900222C"]
    assert list_products(ref_dir) == ["152-900222C"]


def test_replace_required_and_product_conflicts(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    save_layout(ref_dir, name="L1", products=["P1"], filename="a.csv", payload=csv_bytes())
    with pytest.raises(LayoutError, match="already exists"):
        save_layout(ref_dir, name="l1", products=["P1"], filename="b.csv", payload=csv_bytes())
    with pytest.raises(LayoutError, match="already belong to layout 'L1'"):
        save_layout(ref_dir, name="L2", products=["P1", "P2"], filename="b.csv", payload=csv_bytes())
    replaced = save_layout(ref_dir, name="L1", products=["P1", "P3"], filename="c.csv", payload=csv_bytes(dies=(1, 2, 3)), replace=True)
    assert replaced["summary"]["gangs"] == 3 and replaced["products"] == ["P1", "P3"]
    assert [l["name"] for l in list_layouts(ref_dir)] == ["L1"]
    assert list_products(ref_dir) == ["P1", "P3"]


def test_replace_with_different_extension_removes_old_file(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    save_layout(ref_dir, name="L1", products=["P1"], filename="a.csv", payload=csv_bytes())
    xlsx = tmp_path / "a.xlsx"
    pd.read_csv(pd.io.common.BytesIO(csv_bytes())).to_excel(xlsx, index=False)
    save_layout(ref_dir, name="L1", products=["P1"], filename="a.xlsx", payload=xlsx.read_bytes(), replace=True)
    assert (ref_dir / "L1.xlsx").is_file() and not (ref_dir / "L1.csv").exists()
    assert len(load_reference("P1", ref_dir)[0]) == 20


def test_invalid_names_and_bad_files_write_nothing(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    with pytest.raises(LayoutError, match="Layout name must be"):
        save_layout(ref_dir, name="../evil", products=[], filename="a.csv", payload=csv_bytes())
    with pytest.raises(LayoutError, match="may only contain"):
        save_layout(ref_dir, name="ok", products=["bad/name"], filename="a.csv", payload=csv_bytes())
    with pytest.raises(ReferenceError, match="Duplicate spring keys"):
        save_layout(ref_dir, name="ok", products=[], filename="a.csv", payload=b"Die_Num,Spring_Num,X,Y\n1,1,0,0\n1,1,1,1\n")
    assert not (ref_dir / "ok.csv").exists() and not (ref_dir / "layouts.json").exists()


def test_implicit_file_is_listed_and_can_be_replaced_or_deleted(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    ref_dir.mkdir()
    shutil.copy(BACKEND / "coordinates" / "152-900530D.xlsx", ref_dir / "152-900530D.xlsx")
    items = list_layouts(ref_dir)
    assert [i["name"] for i in items] == ["152-900530D"] and items[0]["implicit"] is True
    assert items[0]["summary"]["springs"] == 20952 and items[0]["summary"]["gangs"] == 108
    assert list_products(ref_dir) == ["152-900530D"]
    with pytest.raises(LayoutError, match="already exists"):
        save_layout(ref_dir, name="152-900530D", products=[], filename="x.csv", payload=csv_bytes())
    # a registered layout cannot steal the implicit product name either
    with pytest.raises(LayoutError, match="already belong to layout '152-900530D'"):
        save_layout(ref_dir, name="other", products=["152-900530D"], filename="x.csv", payload=csv_bytes())
    removed = delete_layout(ref_dir, "152-900530D")
    assert removed["file"] == "152-900530D.xlsx" and not (ref_dir / "152-900530D.xlsx").exists()
    assert list_layouts(ref_dir) == [] and list_products(ref_dir) == []
    with pytest.raises(LayoutError, match="No layout named"):
        delete_layout(ref_dir, "152-900530D")


def test_list_reports_unparseable_files(tmp_path: Path):
    ref_dir = tmp_path / "coordinates"
    ref_dir.mkdir()
    (ref_dir / "broken.csv").write_bytes(b"Die_Num,Spring_Num,X\n1,1,0\n")
    (ref_dir / "~$lock.xlsx").write_bytes(b"lock")
    items = list_layouts(ref_dir)
    assert len(items) == 1 and items[0]["name"] == "broken" and "Reference must contain" in items[0]["error"]
    assert list_products(ref_dir) == ["broken"]  # listed, but load_reference will fail with the same message
    with pytest.raises(ReferenceError, match="Reference must contain"):
        load_reference("broken", ref_dir)


def test_bundled_reference_unchanged_by_registry_layer(reference):
    ref, center = reference
    assert len(ref) == 20952 and center == pytest.approx((71.245, -0.5015))
