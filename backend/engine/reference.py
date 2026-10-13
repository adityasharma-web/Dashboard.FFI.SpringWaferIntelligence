"""Product coordinate reference loading (moved verbatim from the Streamlit app).

A reference is ``coordinates/PRODUCT.xlsx`` or ``.csv`` with ``Die_Num``,
``Spring_Num``, ``X``, ``Y`` (parenthetical header descriptions such as
``Die_Num (gang_number)`` are stripped). Coordinates are centered on the
bounding-box midpoint of the source extents; that inferred center is returned
so the UI can state the registration caveat (notch-down orientation and the
center are *assumed*, not measured against fiducials).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

DEFAULT_REF_DIR = Path(__file__).resolve().parents[1] / "coordinates"


class ReferenceError(ValueError):
    """A product has no usable coordinate reference."""


def list_products(ref_dir: Path | str = DEFAULT_REF_DIR) -> list[str]:
    """Products that have a coordinate reference file (verbatim rule from the sidebar)."""
    ref_dir = Path(ref_dir)
    if not ref_dir.is_dir():
        return []
    return sorted({re.split(r' ', p.stem)[0] for p in ref_dir.iterdir() if p.suffix.lower() in ('.xlsx', '.csv')})


def load_reference(product: str, ref_dir: Path | str = DEFAULT_REF_DIR) -> tuple[pd.DataFrame, tuple[float, float]]:
    """Return ``(reference, (cx, cy))``.

    ``reference`` has ``Die_Num, Spring_Num, X, Y`` (source values) and
    ``x, y`` (centered on the bounding-box midpoint ``(cx, cy)``).
    """
    REF_DIR = Path(ref_dir)
    if not REF_DIR.is_dir():
        raise ReferenceError(f'No reference found for {product} in coordinates/')
    matches = [p for p in REF_DIR.iterdir() if p.suffix.lower() in ('.xlsx','.csv') and (p.stem == product or p.stem.startswith(product + ' '))]
    if not matches: raise ReferenceError(f'No reference found for {product} in coordinates/')
    p = sorted(matches, key=lambda x: x.suffix != '.xlsx')[0]
    df = pd.read_excel(p) if p.suffix.lower()=='.xlsx' else pd.read_csv(p)
    df.columns = [re.sub(r'\s*\(.*?\)','',str(c)).strip() for c in df.columns]
    rename = {'Die_Num':'Die_Num','Spring_Num':'Spring_Num','X':'X','Y':'Y','X_Source_mm':'X','Y_Source_mm':'Y'}
    df = df.rename(columns=rename)
    required = {'Die_Num','Spring_Num','X','Y'}
    if not required.issubset(df.columns): raise ReferenceError(f'Reference must contain {required}. Found: {df.columns.tolist()}')
    df = df[['Die_Num','Spring_Num','X','Y']].copy()
    for c in df.columns: df[c]=pd.to_numeric(df[c],errors='raise')
    if df[['Die_Num','Spring_Num']].duplicated().any(): raise ReferenceError('Duplicate spring keys in reference')
    df[['Die_Num','Spring_Num']]=df[['Die_Num','Spring_Num']].astype(int)
    cx=(df.X.min()+df.X.max())/2;cy=(df.Y.min()+df.Y.max())/2
    df['x']=df.X-cx;df['y']=df.Y-cy
    return df, (cx,cy)


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
