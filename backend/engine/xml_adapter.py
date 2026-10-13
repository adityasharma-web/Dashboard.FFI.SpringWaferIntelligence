"""CloudPCS XML ingestion adapter.

Converts a CloudPCS ``DATACOLLECT`` export (``Document[name=DATA]`` with
``Field[name=ColHeads]`` and ``Field[name=Rows]/Array/Document[name=Rows]``)
into the engine's normalized inspection frame and applies the engine's key
rules (integer keys, no duplicates, every key in the reference, one wafer per
frame), so uniqueness and key validation are identical to CSV uploads.

Status rule (defined by the customer, 2026-10-13):

* ``SPRING_GRADING`` not equal to ``SCRAP`` -> ``Good``.
* ``SPRING_GRADING == SCRAP`` -> defective; the spring's ``Status`` is its
  ``DEFECT_CODE`` (e.g. ``H8``, ``XL``). The export carries no severity, so
  there is no Low/Med/Killer here: the engine's "bad" test is simply
  ``Status != 'Good'`` and works unchanged on code statuses.
* A SCRAP spring with a blank ``DEFECT_CODE`` gets the literal status
  ``UNCODED`` rather than an invented code.

Column mapping::

    PRODUCT        -> Product     (must have a coordinate reference)
    SAMPLEID       -> Wafer_ID
    DIE_NUM        -> Die_Num
    SPRING_NUM     -> Spring_Num
    SPRING_GRADING / DEFECT_CODE -> Status (rule above)
    COMMENTS, SCRAP_STAGE, PROCESS, LOT_REJECT_CODE, EVENT_ID, SPRING_EVENT_TIME
                   -> carried through as metadata (one row per export row)

Parsing is streaming (``iterparse``) so a ~70 MB single-line export does not
need a DOM; only the row tuples are kept.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import IO

import pandas as pd

from .inspection import OUTPUT_COLUMNS, validate_keys
from .reference import DEFAULT_REF_DIR, ReferenceError, list_products, load_reference, valid_spring_keys

SCRAP_GRADING = "SCRAP"
UNCODED_STATUS = "UNCODED"
REQUIRED_XML_COLUMNS = ("PRODUCT", "SAMPLEID", "DIE_NUM", "SPRING_NUM", "SPRING_GRADING", "DEFECT_CODE")
METADATA_COLUMNS = ("COMMENTS", "SCRAP_STAGE", "PROCESS", "LOT_REJECT_CODE", "EVENT_ID", "SPRING_EVENT_TIME")


class CloudPcsAdapterError(ValueError):
    """The export cannot be ingested. ``str(err)`` is specific and actionable."""


def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def parse_cloudpcs_rows(source: str | Path | IO[bytes]) -> tuple[list[str], list[dict[str, str]]]:
    """Stream the export; return ``(column_headers, rows)``. Rows are ``{column: string}``.

    Only ``Document[name=Rows]`` elements and the ``ColHeads`` array are kept;
    every other element is discarded as soon as it closes.
    """
    col_heads: list[str] = []
    rows: list[dict[str, str]] = []
    for _event, elem in ET.iterparse(source, events=("end",)):
        tag = _local(elem.tag)
        if tag == "Field" and elem.get("name") == "ColHeads" and not col_heads:
            col_heads = [s.text or "" for s in elem.iter() if _local(s.tag) == "String"]
            elem.clear()
        elif tag == "Document" and elem.get("name") == "Rows":
            row: dict[str, str] = {}
            for fld in elem:
                if _local(fld.tag) != "Field":
                    continue
                value = next((c.text for c in fld if c.text is not None), None)
                row[fld.get("name", "")] = "" if value is None else value
            rows.append(row)
            elem.clear()
    if not col_heads and not rows:
        raise CloudPcsAdapterError("Not a CloudPCS DATACOLLECT export: no ColHeads and no Rows documents found.")
    return col_heads, rows


def grading_to_status(grading: pd.Series, defect_code: pd.Series) -> pd.Series:
    """Apply the customer's rule: not SCRAP -> Good; SCRAP -> its DEFECT_CODE (blank -> UNCODED)."""
    is_scrap = grading.str.strip().str.upper().eq(SCRAP_GRADING)
    code = defect_code.str.strip()
    code = code.where(code.ne(""), UNCODED_STATUS)
    return code.where(is_scrap, "Good")


def _geometry_summary(frame: pd.DataFrame) -> str:
    gangs = frame.Die_Num.nunique()
    per_gang = frame.groupby("Die_Num").Spring_Num.nunique()
    return f"{gangs} gangs x up to {int(per_gang.max())} springs"


def read_cloudpcs_xml(
    source: str | Path | IO[bytes],
    *,
    name: str = "cloudpcs.xml",
    ref_dir: Path | str = DEFAULT_REF_DIR,
    product: str | None = None,
) -> tuple[str, list[pd.DataFrame], pd.DataFrame]:
    """Ingest one export. Returns ``(product, frames, metadata)``.

    * ``frames`` - one validated engine frame (``Wafer_ID, Die_Num, Spring_Num,
      Status``) per ``SAMPLEID`` (the engine requires one wafer per frame).
      ``Status`` is ``Good`` or a defect code.
    * ``metadata`` - the carried-through columns, one row per export row.

    Rejections, in order, each with a specific message: structural (no rows /
    missing columns), mixed products, ``product`` filter mismatch, no
    coordinate reference for the product, non-integer keys, spring keys not in
    the reference (with a geometry summary), then the standard key validation.
    """
    col_heads, rows = parse_cloudpcs_rows(source)
    if not rows:
        raise CloudPcsAdapterError(f"{name}: the export contains no rows.")
    present = set(col_heads) | set(rows[0].keys())
    missing = [c for c in REQUIRED_XML_COLUMNS if c not in present]
    if missing:
        raise CloudPcsAdapterError(f"{name}: export is missing required columns {missing}.")

    raw = pd.DataFrame(rows)
    for col in REQUIRED_XML_COLUMNS + METADATA_COLUMNS:
        if col not in raw.columns:
            raw[col] = ""
        raw[col] = raw[col].astype(str).str.strip()

    products = sorted(raw.PRODUCT.unique())
    if len(products) != 1:
        raise CloudPcsAdapterError(f"{name}: export mixes products {products}; one product per export is required.")
    xml_product = products[0]
    if product is not None and product != xml_product:
        raise CloudPcsAdapterError(f"{name}: export is for product {xml_product!r}, but {product!r} was selected.")

    available = list_products(ref_dir)
    if xml_product not in available:
        raise CloudPcsAdapterError(
            f"{name}: no coordinate reference for product {xml_product!r} in coordinates/ "
            f"(available: {available or 'none'}). The export cannot be placed on a wafer; "
            "add a PRODUCT.xlsx/.csv coordinate reference for it first."
        )
    try:
        ref, _center = load_reference(xml_product, ref_dir)
    except ReferenceError as exc:
        raise CloudPcsAdapterError(f"{name}: {exc}") from exc
    keys = valid_spring_keys(ref)

    frame = pd.DataFrame({
        "Wafer_ID": raw.SAMPLEID,
        "Die_Num": pd.to_numeric(raw.DIE_NUM, errors="coerce"),
        "Spring_Num": pd.to_numeric(raw.SPRING_NUM, errors="coerce"),
        "Status": grading_to_status(raw.SPRING_GRADING, raw.DEFECT_CODE),
    })
    if frame.Die_Num.isna().any() or frame.Spring_Num.isna().any() or not ((frame.Die_Num % 1 == 0) & (frame.Spring_Num % 1 == 0)).all():
        raise CloudPcsAdapterError(f"{name}: DIE_NUM / SPRING_NUM must be integers.")
    frame[["Die_Num", "Spring_Num"]] = frame[["Die_Num", "Spring_Num"]].astype(int)

    # Geometry check before any partial render: every export key must exist in the reference.
    export_keys = pd.MultiIndex.from_frame(frame[["Die_Num", "Spring_Num"]])
    unknown = ~export_keys.isin(keys)
    if unknown.any():
        raise CloudPcsAdapterError(
            f"{name}: {int(unknown.sum())} of {len(frame)} spring keys are not present in the {xml_product} "
            f"reference (export has {_geometry_summary(frame)}; reference has "
            f"{ref.Die_Num.nunique()} gangs x up to {int(ref.groupby('Die_Num').Spring_Num.nunique().max())} springs). "
            "The export geometry does not match the coordinate reference."
        )

    metadata = raw[["PRODUCT", "SAMPLEID", "DIE_NUM", "SPRING_NUM", "SPRING_GRADING", "DEFECT_CODE", *METADATA_COLUMNS]].copy()
    frames: list[pd.DataFrame] = []
    for wafer_id, part in frame.groupby("Wafer_ID", sort=True):
        frames.append(validate_keys(part.reset_index(drop=True), f"{name}:{wafer_id}", keys)[OUTPUT_COLUMNS])
    return xml_product, frames, metadata
