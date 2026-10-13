"""CloudPCS XML ingestion adapter.

Converts a CloudPCS ``DATACOLLECT`` export (``Document[name=DATA]`` with
``Field[name=ColHeads]`` and ``Field[name=Rows]/Array/Document[name=Rows]``)
into the engine's normalized inspection frame and runs it through the *same*
validation chain as CSV/XLSX uploads (``validate_inspection``), so the
uniqueness and spring-key rules are identical.

Column mapping::

    PRODUCT        -> Product     (must have a coordinate reference)
    SAMPLEID       -> Wafer_ID
    DIE_NUM        -> Die_Num
    SPRING_NUM     -> Spring_Num
    SPRING_GRADING -> status, via the configurable grading map (see below)
    DEFECT_CODE    -> secondary key of the grading map
    COMMENTS, SCRAP_STAGE, PROCESS, LOT_REJECT_CODE, EVENT_ID, SPRING_EVENT_TIME
                   -> carried through as metadata columns

**The grading -> Good/Low/Med/Killer mapping is not defined.** The only values
observed so far are ``SPRING_GRADING = SCRAP`` with ``DEFECT_CODE = 2H``.
``grading_map.json`` is empty by default; an unmapped value raises
``CloudPcsAdapterError`` naming the value. Nothing is ever defaulted.

Parsing is streaming (``iterparse``) so a ~70 MB single-line export does not
need a DOM; only the row tuples are kept.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

import pandas as pd

from .inspection import validate_inspection
from .reference import DEFAULT_REF_DIR, ReferenceError, list_products, load_reference, valid_spring_keys

DEFAULT_GRADING_MAP_PATH = Path(__file__).resolve().parent / "grading_map.json"
ALLOWED_TARGETS = ("Good", "Low", "Med", "Killer")
REQUIRED_XML_COLUMNS = ("PRODUCT", "SAMPLEID", "DIE_NUM", "SPRING_NUM", "SPRING_GRADING", "DEFECT_CODE")
METADATA_COLUMNS = ("COMMENTS", "SCRAP_STAGE", "PROCESS", "LOT_REJECT_CODE", "EVENT_ID", "SPRING_EVENT_TIME")


class CloudPcsAdapterError(ValueError):
    """The export cannot be ingested. ``str(err)`` is specific and actionable."""


@dataclass(frozen=True)
class GradingMap:
    """Explicit lookup from CloudPCS grading to engine status. Empty by default."""

    by_grading_and_code: dict[str, str] = field(default_factory=dict)
    by_grading: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for table_name in ("by_grading_and_code", "by_grading"):
            for key, target in getattr(self, table_name).items():
                if target not in ALLOWED_TARGETS:
                    raise CloudPcsAdapterError(
                        f"grading map entry {table_name}[{key!r}] = {target!r} is not one of {ALLOWED_TARGETS}"
                    )

    def resolve(self, grading: str, defect_code: str) -> str:
        combo = f"{grading}|{defect_code}"
        if combo in self.by_grading_and_code:
            return self.by_grading_and_code[combo]
        if grading in self.by_grading:
            return self.by_grading[grading]
        raise CloudPcsAdapterError(
            f"Unmapped SPRING_GRADING value {grading!r} (DEFECT_CODE {defect_code!r}) in CloudPCS export. "
            "The grading -> Good/Low/Med/Killer mapping is not defined; add it to grading_map.json "
            "(by_grading or by_grading_and_code as 'GRADING|CODE'). No default status is assumed."
        )

    @property
    def is_empty(self) -> bool:
        return not self.by_grading_and_code and not self.by_grading


def load_grading_map(path: Path | str | None = None) -> GradingMap:
    """Load the configurable map (``grading_map.json`` next to this module by default)."""
    p = Path(path) if path is not None else DEFAULT_GRADING_MAP_PATH
    if not p.is_file():
        return GradingMap()
    raw = json.loads(p.read_text(encoding="utf-8"))
    return GradingMap(
        by_grading_and_code={str(k): str(v) for k, v in (raw.get("by_grading_and_code") or {}).items()},
        by_grading={str(k): str(v) for k, v in (raw.get("by_grading") or {}).items()},
    )


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


def _geometry_summary(frame: pd.DataFrame) -> str:
    gangs = frame.Die_Num.nunique()
    per_gang = frame.groupby("Die_Num").Spring_Num.nunique()
    return f"{gangs} gangs x up to {int(per_gang.max())} springs"


def read_cloudpcs_xml(
    source: str | Path | IO[bytes],
    *,
    name: str = "cloudpcs.xml",
    ref_dir: Path | str = DEFAULT_REF_DIR,
    grading_map: GradingMap | None = None,
    product: str | None = None,
) -> tuple[str, list[pd.DataFrame], pd.DataFrame]:
    """Ingest one export. Returns ``(product, frames, metadata)``.

    * ``frames`` - one validated engine frame (``Wafer_ID, Die_Num, Spring_Num,
      Status``) per ``SAMPLEID`` (the engine requires one wafer per frame).
    * ``metadata`` - the carried-through columns, one row per export row.

    Rejections, in order, each with a specific message:
    structural (no rows / missing columns), mixed products, ``product`` filter
    mismatch, no coordinate reference for the product, unmapped grading
    value, spring keys not in the reference, then the standard validation.
    """
    grading_map = grading_map if grading_map is not None else load_grading_map()
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

    # Grading -> status: explicit lookup only; fail loudly on the first unmapped value.
    pairs = raw[["SPRING_GRADING", "DEFECT_CODE"]].drop_duplicates()
    status_lookup = {(g, c): grading_map.resolve(g, c) for g, c in pairs.itertuples(index=False)}
    status = [status_lookup[(g, c)] for g, c in zip(raw.SPRING_GRADING, raw.DEFECT_CODE)]

    frame = pd.DataFrame({
        "Product": raw.PRODUCT,
        "Wafer_ID": raw.SAMPLEID,
        "Die_Num": pd.to_numeric(raw.DIE_NUM, errors="coerce"),
        "Spring_Num": pd.to_numeric(raw.SPRING_NUM, errors="coerce"),
        "Defect": ["N" if s == "Good" else "Y" for s in status],
        "Defect_Severity": ["" if s == "Good" else s for s in status],
    })
    if frame.Die_Num.isna().any() or frame.Spring_Num.isna().any():
        raise CloudPcsAdapterError(f"{name}: DIE_NUM / SPRING_NUM must be integers.")

    # Geometry check before any partial render: every export key must exist in the reference.
    export_keys = pd.MultiIndex.from_frame(frame[["Die_Num", "Spring_Num"]].astype(int))
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
        frames.append(validate_inspection(part, f"{name}:{wafer_id}", xml_product, keys))
    return xml_product, frames, metadata
