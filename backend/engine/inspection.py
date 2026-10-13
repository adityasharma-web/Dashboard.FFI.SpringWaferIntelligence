"""Inspection file reading and validation (moved verbatim from the Streamlit app).

``read_inspection`` keeps the original validation chain, in the original
order, with the original messages: required columns, product match, integer
die/spring, ``Defect`` in {Y, N}, severity required for ``Y`` and normalized
(low / med / medium / killer), duplicate-key rejection, unknown-spring-key
rejection, and exactly one ``Wafer_ID`` per file (filename stem fallback).

The file read and the validation are split into two functions so the CloudPCS
XML adapter can feed its normalized frame through the *same* validation.
"""
from __future__ import annotations

from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {'Product','Die_Num','Spring_Num','Defect','Defect_Severity'}
OUTPUT_COLUMNS = ['Wafer_ID','Die_Num','Spring_Num','Status']


class InspectionError(ValueError):
    """An inspection file failed validation. ``str(err)`` is the user-facing message."""


def _file_name(file, name: str | None) -> str:
    if name is not None:
        return name
    if isinstance(file, (str, Path)):
        return Path(file).name
    return str(getattr(file, 'name', 'inspection'))


def read_inspection(file: str | Path | IO, product: str, valid_keys: pd.MultiIndex, name: str | None = None) -> pd.DataFrame:
    """Read one CSV/XLSX inspection file and return ``Wafer_ID, Die_Num, Spring_Num, Status``.

    ``file`` is a path or a file-like object; ``name`` overrides the filename
    used in messages and as the ``Wafer_ID`` fallback (needed for uploads).
    """
    fname = _file_name(file, name)
    raw = pd.read_excel(file) if fname.lower().endswith('.xlsx') else pd.read_csv(file)
    return validate_inspection(raw, fname, product, valid_keys)


def validate_inspection(raw: pd.DataFrame, fname: str, product: str, valid_keys: pd.MultiIndex) -> pd.DataFrame:
    """The original validation chain, unchanged. ``fname`` is only used for messages / fallback."""
    raw = raw.copy()
    raw.columns=[str(c).strip() for c in raw.columns]
    req=REQUIRED_COLUMNS
    if not req.issubset(raw.columns): raise InspectionError(f'{fname}: missing {sorted(req-set(raw.columns))}')
    raw['Product']=raw.Product.astype(str).str.strip()
    if not raw.Product.eq(product).all(): raise InspectionError(f'{fname}: product mismatch; expected {product}')
    for c in ('Die_Num','Spring_Num'):
        try:
            raw[c]=pd.to_numeric(raw[c],errors='raise')
        except (ValueError, TypeError) as exc:
            # The original let pandas' own message surface; keep that text, prefixed with the file.
            raise InspectionError(f'{fname}: invalid {c} ({exc})') from exc
        if raw[c].isna().any() or not (raw[c]%1==0).all():raise InspectionError(f'{fname}: invalid {c}')
        raw[c]=raw[c].astype(int)
    raw['Defect']=raw.Defect.astype(str).str.strip().str.upper()
    if not raw.Defect.isin(['Y','N']).all():raise InspectionError(f'{fname}: Defect must be Y or N')
    raw['Defect_Severity']=raw.Defect_Severity.fillna('').astype(str).str.strip().str.lower().map({'low':'Low','med':'Med','medium':'Med','killer':'Killer','':'','nan':''})
    bad=raw.Defect.eq('Y')
    if raw.loc[bad,'Defect_Severity'].isna().any() or raw.loc[bad,'Defect_Severity'].eq('').any():
        raise InspectionError(f'{fname}: Y defects require Low, Med, or Killer severity')
    if raw[['Die_Num','Spring_Num']].duplicated().any():raise InspectionError(f'{fname}: duplicate Die_Num/Spring_Num')
    keys=pd.MultiIndex.from_frame(raw[['Die_Num','Spring_Num']])
    if not keys.isin(valid_keys).all():raise InspectionError(f'{fname}: inspection contains unknown spring keys')
    raw['Status']=np.where(bad,raw.Defect_Severity,'Good')
    raw['Wafer_ID']=raw['Wafer_ID'].astype(str).str.strip() if 'Wafer_ID' in raw.columns else Path(fname).stem
    if raw.Wafer_ID.nunique()!=1:raise InspectionError(f'{fname}: one Wafer_ID per file required')
    return raw[OUTPUT_COLUMNS]


def combine_inspections(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate validated per-file frames; reject duplicate wafer/spring keys across files (verbatim rule)."""
    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    data=pd.concat(frames,ignore_index=True)
    if data[['Wafer_ID','Die_Num','Spring_Num']].duplicated().any():
        raise InspectionError('Duplicate wafer/spring keys across input files. Ensure unique Wafer_ID per file.')
    return data
