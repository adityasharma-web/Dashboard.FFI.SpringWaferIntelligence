"""Product coordinate reference ("layout") loading.

A layout is ``coordinates/<name>.xlsx`` or ``.csv`` with ``Die_Num``,
``Spring_Num``, ``X``, ``Y`` (parenthetical header descriptions such as
``Die_Num (gang_number)`` are stripped). Coordinates are centered on the
bounding-box midpoint of the source extents; that inferred center is returned
so the UI can state the registration caveat (notch-down orientation and the
center are *assumed*, not measured against fiducials).

The parsing (``parse_reference``) is the Streamlit app's code verbatim. What
changed in the port is only *which file* a product name resolves to:
``coordinates/layouts.json`` (written by ``engine.layouts``) can map several
design / product names onto one layout file. Files with no registry entry
keep the original behavior (the file stem is the product name).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import IO

import pandas as pd

DEFAULT_REF_DIR = Path(__file__).resolve().parents[1] / "coordinates"
REGISTRY_FILE = "layouts.json"
REFERENCE_SUFFIXES = ('.xlsx', '.csv')


class ReferenceError(ValueError):
    """A product has no usable coordinate reference."""


def _reference_files(ref_dir: Path) -> list[Path]:
    """Candidate layout files. Excel lock files (``~$NAME.xlsx``, present while
    the workbook is open) and dot-files are skipped; the original app did not
    guard against them, which made an open workbook appear as a second product."""
    return [p for p in ref_dir.iterdir() if p.suffix.lower() in REFERENCE_SUFFIXES and not p.name.startswith(('~$', '.'))]


def read_registry(ref_dir: Path | str) -> dict:
    """The layouts registry (``{"layouts": [...]}``); empty when absent or unreadable."""
    path = Path(ref_dir) / REGISTRY_FILE
    if not path.is_file():
        return {"layouts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"layouts": []}
    entries = data.get("layouts") if isinstance(data, dict) else None
    return {"layouts": [e for e in (entries or []) if isinstance(e, dict) and e.get("name") and e.get("file")]}


def registered_files(ref_dir: Path | str) -> set[str]:
    return {e["file"] for e in read_registry(ref_dir)["layouts"]}


def implicit_product(path: Path) -> str:
    """The original rule: a file's product is the first space-separated token of its stem."""
    return re.split(r' ', path.stem)[0]


def list_products(ref_dir: Path | str = DEFAULT_REF_DIR) -> list[str]:
    """Every product / design name that resolves to a layout file."""
    ref_dir = Path(ref_dir)
    if not ref_dir.is_dir():
        return []
    registry = read_registry(ref_dir)
    names: set[str] = set()
    for entry in registry["layouts"]:
        if (ref_dir / entry["file"]).is_file():
            names.update(str(p) for p in (entry.get("products") or [entry["name"]]))
    registered = {e["file"] for e in registry["layouts"]}
    for p in _reference_files(ref_dir):
        if p.name not in registered:
            names.add(implicit_product(p))
    return sorted(names)


def resolve_product(product: str, ref_dir: Path | str = DEFAULT_REF_DIR) -> Path | None:
    """The layout file for ``product``: registry alias first, then the original stem rule."""
    ref_dir = Path(ref_dir)
    if not ref_dir.is_dir():
        return None
    registry = read_registry(ref_dir)
    for entry in registry["layouts"]:
        if product in [str(p) for p in (entry.get("products") or [entry["name"]])]:
            path = ref_dir / entry["file"]
            return path if path.is_file() else None
    registered = {e["file"] for e in registry["layouts"]}
    matches = [p for p in _reference_files(ref_dir) if p.name not in registered and (p.stem == product or p.stem.startswith(product + ' '))]
    if not matches:
        return None
    return sorted(matches, key=lambda x: x.suffix != '.xlsx')[0]


def parse_reference(source: Path | str | IO, suffix: str | None = None) -> tuple[pd.DataFrame, tuple[float, float]]:
    """Parse one layout file (path or file-like + suffix). Verbatim from the original ``load_reference``."""
    ext = (suffix if suffix is not None else Path(str(source)).suffix).lower()
    if ext not in REFERENCE_SUFFIXES:
        raise ReferenceError(f'Reference must be a .xlsx or .csv file (got {ext or "no extension"})')
    df = pd.read_excel(source) if ext == '.xlsx' else pd.read_csv(source)
    df.columns = [re.sub(r'\s*\(.*?\)','',str(c)).strip() for c in df.columns]
    rename = {'Die_Num':'Die_Num','Spring_Num':'Spring_Num','X':'X','Y':'Y','X_Source_mm':'X','Y_Source_mm':'Y'}
    df = df.rename(columns=rename)
    required = {'Die_Num','Spring_Num','X','Y'}
    if not required.issubset(df.columns): raise ReferenceError(f'Reference must contain {required}. Found: {df.columns.tolist()}')
    df = df[['Die_Num','Spring_Num','X','Y']].copy()
    if df.empty: raise ReferenceError('Reference contains no rows')
    for c in df.columns:
        try:
            df[c]=pd.to_numeric(df[c],errors='raise')
        except (ValueError, TypeError) as exc:
            raise ReferenceError(f'Reference column {c} must be numeric ({exc})') from exc
    if df[['Die_Num','Spring_Num','X','Y']].isna().any().any(): raise ReferenceError('Reference contains empty Die_Num / Spring_Num / X / Y values')
    if not ((df.Die_Num % 1 == 0) & (df.Spring_Num % 1 == 0)).all(): raise ReferenceError('Die_Num and Spring_Num must be integers')
    if df[['Die_Num','Spring_Num']].duplicated().any(): raise ReferenceError('Duplicate spring keys in reference')
    df[['Die_Num','Spring_Num']]=df[['Die_Num','Spring_Num']].astype(int)
    cx=(df.X.min()+df.X.max())/2;cy=(df.Y.min()+df.Y.max())/2
    df['x']=df.X-cx;df['y']=df.Y-cy
    return df, (cx,cy)


def load_reference(product: str, ref_dir: Path | str = DEFAULT_REF_DIR) -> tuple[pd.DataFrame, tuple[float, float]]:
    """Return ``(reference, (cx, cy))`` for a product / design name.

    ``reference`` has ``Die_Num, Spring_Num, X, Y`` (source values) and
    ``x, y`` (centered on the bounding-box midpoint ``(cx, cy)``).
    """
    path = resolve_product(product, ref_dir)
    if path is None:
        raise ReferenceError(f'No reference found for {product} in coordinates/')
    return parse_reference(path)


def valid_spring_keys(ref: pd.DataFrame) -> pd.MultiIndex:
    """The ``(Die_Num, Spring_Num)`` key index inspections are validated against."""
    return pd.MultiIndex.from_frame(ref[['Die_Num','Spring_Num']])


def gang_bounds(ref: pd.DataFrame) -> pd.DataFrame:
    """Per-gang extents in centered coordinates (verbatim from ``decorate()``).

    The Streamlit plot pads these by 2 mm in X and 0.2 mm in Y when drawing
    the outline rectangles; that padding is a rendering choice and is applied
    by the frontend, not here.
    """
    return ref.groupby('Die_Num').agg(xmin=('x','min'),xmax=('x','max'),ymin=('y','min'),ymax=('y','max'))
