"""Spring Wafer Intelligence - FastAPI service.

Thin wrapper over ``engine/``: endpoints validate inputs, hold uploaded
inspection data in in-memory sessions, call the engine and marshal its
DataFrames / arrays into JSON. No analysis logic lives here.

Charts are returned as **underlying arrays** (spring coordinates + status
codes, per-spring stacked metrics, the smoothed rate grid, zone / sector /
hotspot / recurrence / gang tables); the React frontend draws them.
"""
from __future__ import annotations

import io
import math
import os
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine import (
    STATES,
    CloudPcsAdapterError,
    InspectionError,
    ReferenceError,
    combine_inspections,
    gang_bounds,
    gang_yield,
    header_metrics,
    individual_wafer_status,
    list_products,
    load_reference,
    read_cloudpcs_xml,
    read_inspection,
    signature_indicators,
    spatial_analysis,
    stacked_summary,
    valid_spring_keys,
)
from engine.gang_yield import GANG_YIELD_RULE, SCRAP_THRESHOLD

ROOT = Path(__file__).resolve().parent
REF_DIR = Path(os.environ.get("REF_DIR", ROOT / "coordinates"))
EXAMPLES_DIR = ROOT / "examples"
EXAMPLES_PRODUCT = "152-900530D"
DEFAULT_STATIC_DIR = ROOT.parent / "frontend" / "dist"
DEFAULT_CORS = "http://localhost:5187,http://127.0.0.1:5187"
MAX_SESSIONS = 20
MAX_CACHED_ANALYSES = 40
STATE_CODE = {s: i for i, s in enumerate(STATES)}

CAVEATS = {
    "scope": "Exploratory screening utility, not a validated manufacturing release decision system.",
    "signatures": "Edge enrichment, sector asymmetry and local hotspots are descriptive signatures, not causal diagnoses. A recurring pattern can reflect product design, process, metrology, inspection coverage or wafer registration.",
    "spiral": "Spiral recognition is not automatically implemented or validated.",
    "registration": "The coordinate center is the bounding-box midpoint of the reference extents and notch-down orientation is assumed; validate registration and orientation against physical wafer fiducials before production use.",
    "line_width": "The physical spring footprint is 4.0 x 0.4 mm; the rendered segment spans 4 mm in X but its line thickness is screen-pixel-based, not the physical 0.4 mm footprint.",
    "uninspected": "Missing spring observations are not counted as Good; they remain uninspected and are excluded from rates.",
    "stacked_map": "The stacked map draws never-inspected springs at zero for rendering only; the table makes missing coverage explicit.",
    "recurrence": "Exact binomial enrichment tests with Benjamini-Hochberg exploratory q-values; interpret cautiously because spatial and wafer-level observations may not be independent.",
    "heatmap": "Gaussian-smoothed defect counts divided by Gaussian-smoothed inspection exposure. Blank areas have insufficient coverage. Patterns are exploratory; adjacent pixels are statistically dependent.",
    "export": "Coordinates are product-referenced; severity and defect observations are inspection-file values, never synthesized by the application.",
    "synthetic": "The bundled example wafers are explicitly simulated; do not interpret them as measured yield.",
}

app = FastAPI(title="Spring Wafer Intelligence", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", DEFAULT_CORS).split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- sessions / caches
@dataclass
class Session:
    product: str
    data: pd.DataFrame
    wafers: list[str]
    files: list[dict[str, Any]]
    source: str  # "upload" | "synthetic_examples"
    metadata: pd.DataFrame | None = None
    analyses: "OrderedDict[tuple, dict]" = field(default_factory=OrderedDict)


_SESSIONS: "OrderedDict[str, Session]" = OrderedDict()
_LOCK = Lock()


def _store(session: Session) -> str:
    session_id = uuid.uuid4().hex
    with _LOCK:
        _SESSIONS[session_id] = session
        while len(_SESSIONS) > MAX_SESSIONS:
            _SESSIONS.popitem(last=False)
    return session_id


def _session(session_id: str) -> Session:
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="The inspection session expired. Upload the files again or reload the synthetic examples.")
    return session


@lru_cache(maxsize=16)
def _reference(product: str, ref_dir: str):
    """Parsed reference per product (cached): (ref, center, valid_keys, gang_bounds)."""
    ref, center = load_reference(product, ref_dir)
    return ref, center, valid_spring_keys(ref), gang_bounds(ref)


def _reference_or_422(product: str):
    try:
        return _reference(product, str(REF_DIR))
    except ReferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --------------------------------------------------------------------------- response models
class ProductsResponse(BaseModel):
    products: list[str]
    examples_product: str
    examples_available: bool


class GangBounds(BaseModel):
    die: int
    xmin: float
    xmax: float
    ymin: float
    ymax: float


class ReferenceResponse(BaseModel):
    product: str
    spring_count: int
    gang_count: int
    center: dict[str, float]
    die: list[int]
    spring: list[int]
    x: list[float]
    y: list[float]
    gangs: list[GangBounds]
    caveat: str


class FileSummary(BaseModel):
    filename: str
    wafer_id: str
    observations: int


class InspectionsResponse(BaseModel):
    session_id: str
    product: str
    source: str
    wafers: list[str]
    files: list[FileSummary]
    synthetic: bool


class AnalyzeRequest(BaseModel):
    session_id: str
    wafers: list[str] | None = None
    bandwidth: float = Field(default=5.0, ge=2.0, le=15.0)


class HeaderMetrics(BaseModel):
    wafers: int
    springs_in_reference: int
    observations: int
    bad: int
    defect_rate: float | None


class StatusCount(BaseModel):
    status: str
    count: int


class IndividualWafer(BaseModel):
    wafer_id: str
    status_codes: list[int]
    counts: list[StatusCount]
    uninspected: int


class StackedMetrics(BaseModel):
    die: list[int]
    spring: list[int]
    inspected: list[int]
    defects: list[int]
    killer: list[int]
    defect_rate: list[float | None]
    uninspected_springs: int


class Peak(BaseModel):
    X_mm: float
    Y_mm: float
    Local_defect_rate: float
    Excess_vs_global: float


class RecurrenceRow(BaseModel):
    die: int
    spring: int
    inspected: int
    defects: int
    q: float
    p: float | None = None


class SpatialResult(BaseModel):
    bin_edges: list[float]
    bin_centers: list[float]
    rate_grid: list[list[float | None]]
    baseline: float
    peaks: list[Peak]
    recurrence: list[RecurrenceRow]
    recurrence_total_rows: int
    recurrence_min_inspected: int
    recurrence_tested: bool


class ZoneRow(BaseModel):
    zone: str
    inspected: int
    defects: int
    defect_rate: float


class SectorRow(BaseModel):
    sector: str
    defect_rate: float | None
    size: int


class SignatureResult(BaseModel):
    zones: list[ZoneRow]
    sectors: list[SectorRow]
    messages: list[str]


class GangRow(BaseModel):
    wafer_id: str
    die: int
    inspected: int
    bad: int
    total_springs: int
    bad_pct: float
    complete: bool
    disposition: str


class GangYieldResult(BaseModel):
    rows: list[GangRow]
    scrapped: int
    total: int
    threshold: float
    rule: str


class AnalysisResponse(BaseModel):
    session_id: str
    product: str
    source: str
    synthetic: bool
    wafers: list[str]
    bandwidth: float
    states: list[str]
    colors: dict[str, str]
    header: HeaderMetrics
    individual: list[IndividualWafer]
    stacked: StackedMetrics
    spatial: SpatialResult
    signature: SignatureResult
    gang_yield: GangYieldResult
    caveats: dict[str, str]


COLORS = {'Good':'#21a653','Low':'#f4d43b','Med':'#f38a24','Killer':'#df3537','Uninspected':'#aab4c2'}


# --------------------------------------------------------------------------- helpers (marshaling only)
def _nan_to_none(values) -> list[float | None]:
    return [None if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v) for v in values]


def _grid_to_json(rate: np.ndarray) -> list[list[float | None]]:
    # engine orientation is [x_bin, y_bin]; the heatmap wants rows = y, cols = x (what the Streamlit app plotted via rate.T)
    z = rate.T
    return [[None if not np.isfinite(v) else float(v) for v in row] for row in z]


def _ingest_files(product: str, uploads: list[tuple[str, bytes]], source: str) -> InspectionsResponse | JSONResponse:
    ref, _center, keys, _bounds = _reference_or_422(product)
    frames: list[pd.DataFrame] = []
    files: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    metadata_parts: list[pd.DataFrame] = []
    for filename, payload in uploads:
        try:
            if filename.lower().endswith(".xml"):
                xml_product, xml_frames, metadata = read_cloudpcs_xml(io.BytesIO(payload), name=filename, ref_dir=REF_DIR, product=product)
                for frame in xml_frames:
                    frames.append(frame)
                    files.append({"filename": filename, "wafer_id": str(frame.Wafer_ID.iloc[0]), "observations": int(len(frame))})
                metadata_parts.append(metadata)
            else:
                frame = read_inspection(io.BytesIO(payload), product, keys, name=filename)
                frames.append(frame)
                files.append({"filename": filename, "wafer_id": str(frame.Wafer_ID.iloc[0]), "observations": int(len(frame))})
        except (InspectionError, CloudPcsAdapterError, ValueError) as exc:
            errors.append({"filename": filename, "error": str(exc)})
    if not errors and frames:
        try:
            data = combine_inspections(frames)
        except InspectionError as exc:
            errors.append({"filename": "*", "error": str(exc)})
    if errors:
        # Preserve the Streamlit behavior: every error is surfaced and nothing proceeds.
        return JSONResponse(status_code=422, content={"detail": f"{len(errors)} file(s) failed validation; nothing was loaded.", "errors": errors})
    if not frames:
        raise HTTPException(status_code=422, detail="No inspection files were provided.")
    wafers = sorted(data.Wafer_ID.unique())
    session = Session(
        product=product, data=data, wafers=wafers, files=files, source=source,
        metadata=pd.concat(metadata_parts, ignore_index=True) if metadata_parts else None,
    )
    session_id = _store(session)
    return InspectionsResponse(session_id=session_id, product=product, source=source, wafers=wafers, files=[FileSummary(**f) for f in files], synthetic=source == "synthetic_examples")


def _select(session: Session, wafers: list[str] | None) -> list[str]:
    selected = list(session.wafers) if not wafers else [w for w in session.wafers if w in set(wafers)]
    unknown = sorted(set(wafers or []) - set(session.wafers))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown wafer id(s) for this session: {unknown}")
    if not selected:
        raise HTTPException(status_code=422, detail="Select at least one wafer.")
    return selected


def _build_analysis(session_id: str, session: Session, selected: list[str], bandwidth: float) -> dict:
    ref, _center, _keys, _bounds = _reference_or_422(session.product)
    selected_data = session.data[session.data.Wafer_ID.isin(selected)]
    stack = stacked_summary(ref, selected_data, selected)
    header = header_metrics(ref, selected_data, selected)
    bins, rate, baseline, tests, peaks = spatial_analysis(stack, selected_data, selected, bandwidth)
    zones, messages, sectors = signature_indicators(stack, selected_data, selected)
    gangs = gang_yield(ref, selected_data)

    individual = []
    for wafer in selected:
        status, counts = individual_wafer_status(ref, selected_data, wafer)
        codes = [STATE_CODE[s] for s in status.tolist()]
        individual.append({
            "wafer_id": wafer,
            "status_codes": codes,
            "counts": [{"status": str(r.Status), "count": int(r.Count)} for r in counts.itertuples()],
            "uninspected": int(sum(1 for c in codes if c == STATE_CODE['Uninspected'])),
        })

    tests_sorted = tests.sort_values(['q','Defects'],ascending=[True,False]).head(100)
    has_p = 'p' in tests.columns
    recurrence = [
        {"die": int(r.Die_Num), "spring": int(r.Spring_Num), "inspected": int(r.Inspected), "defects": int(r.Defects),
         "q": float(r.q), "p": (float(r.p) if has_p else None)}
        for r in tests_sorted.itertuples()
    ]
    min_inspected = max(2, int(np.ceil(.7 * len(selected))))

    return {
        "session_id": session_id,
        "product": session.product,
        "source": session.source,
        "synthetic": session.source == "synthetic_examples",
        "wafers": selected,
        "bandwidth": bandwidth,
        "states": STATES,
        "colors": COLORS,
        "header": header,
        "individual": individual,
        "stacked": {
            "die": stack.Die_Num.astype(int).tolist(),
            "spring": stack.Spring_Num.astype(int).tolist(),
            "inspected": stack.Inspected.astype(int).tolist(),
            "defects": stack.Defects.astype(int).tolist(),
            "killer": stack.Killer.astype(int).tolist(),
            "defect_rate": _nan_to_none(stack.Defect_Rate.tolist()),
            "uninspected_springs": int((stack.Inspected == 0).sum()),
        },
        "spatial": {
            "bin_edges": [float(b) for b in bins],
            "bin_centers": [float(v) for v in (bins[:-1] + bins[1:]) / 2],
            "rate_grid": _grid_to_json(rate),
            "baseline": float(baseline),
            "peaks": peaks.to_dict(orient="records") if len(peaks) else [],
            "recurrence": recurrence,
            "recurrence_total_rows": int(len(tests)),
            "recurrence_min_inspected": min_inspected,
            "recurrence_tested": bool(has_p),
        },
        "signature": {
            "zones": [{"zone": str(r.zone), "inspected": int(r.Inspected), "defects": int(r.Defects), "defect_rate": float(r.Defect_Rate)} for r in zones.itertuples()],
            "sectors": [{"sector": str(r.sector), "defect_rate": (None if pd.isna(r.mean) else float(r.mean)), "size": int(r.size)} for r in sectors.itertuples()],
            "messages": list(messages),
        },
        "gang_yield": {
            "rows": [
                {"wafer_id": str(r.Wafer_ID), "die": int(r.Die_Num), "inspected": int(r.Inspected), "bad": int(r.Bad),
                 "total_springs": int(r.Total_Springs), "bad_pct": float(r.Bad_Pct), "complete": bool(r.Complete_Inspection),
                 "disposition": str(r.Disposition)}
                for r in gangs.itertuples()
            ],
            "scrapped": int((gangs.Disposition == 'SCRAP').sum()),
            "total": int(len(gangs)),
            "threshold": SCRAP_THRESHOLD,
            "rule": GANG_YIELD_RULE,
        },
        "caveats": CAVEATS,
    }


def _analysis(session_id: str, wafers: list[str] | None, bandwidth: float) -> dict:
    session = _session(session_id)
    selected = _select(session, wafers)
    key = (tuple(selected), float(bandwidth))
    with _LOCK:
        cached = session.analyses.get(key)
    if cached is not None:
        return cached
    result = _build_analysis(session_id, session, selected, bandwidth)
    with _LOCK:
        session.analyses[key] = result
        while len(session.analyses) > MAX_CACHED_ANALYSES:
            session.analyses.popitem(last=False)
    return result


def _csv_response(frame: pd.DataFrame, filename: str) -> Response:
    return Response(content=frame.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# --------------------------------------------------------------------------- endpoints
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/products", response_model=ProductsResponse)
def products() -> ProductsResponse:
    found = list_products(REF_DIR)
    return ProductsResponse(products=found, examples_product=EXAMPLES_PRODUCT, examples_available=EXAMPLES_PRODUCT in found and any(EXAMPLES_DIR.glob("*.csv")))


@app.get("/api/reference/{product}", response_model=ReferenceResponse)
def reference(product: str) -> ReferenceResponse:
    ref, center, _keys, bounds = _reference_or_422(product)
    return ReferenceResponse(
        product=product,
        spring_count=int(len(ref)),
        gang_count=int(ref.Die_Num.nunique()),
        center={"x": float(center[0]), "y": float(center[1])},
        die=ref.Die_Num.astype(int).tolist(),
        spring=ref.Spring_Num.astype(int).tolist(),
        x=[float(v) for v in ref.x.tolist()],
        y=[float(v) for v in ref.y.tolist()],
        gangs=[GangBounds(die=int(die), xmin=float(b.xmin), xmax=float(b.xmax), ymin=float(b.ymin), ymax=float(b.ymax)) for die, b in bounds.iterrows()],
        caveat=f"Coordinate center inferred from extents: X={center[0]:.3f}, Y={center[1]:.3f} mm. Notch down assumed.",
    )


@app.post("/api/inspections", response_model=InspectionsResponse, responses={422: {"description": "Per-file validation errors"}})
async def upload_inspections(
    product: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
):
    uploads = [(f.filename or "inspection", await f.read()) for f in files]
    return _ingest_files(product, uploads, "upload")


@app.post("/api/examples", response_model=InspectionsResponse)
def load_examples():
    """Load the bundled SYNTHETIC example wafers (explicitly simulated data)."""
    paths = sorted(EXAMPLES_DIR.glob("*.csv"))
    if not paths:
        raise HTTPException(status_code=404, detail="No bundled example files are available.")
    return _ingest_files(EXAMPLES_PRODUCT, [(p.name, p.read_bytes()) for p in paths], "synthetic_examples")


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze(request: AnalyzeRequest):
    return _analysis(request.session_id, request.wafers, request.bandwidth)


@app.get("/api/export/stacked")
def export_stacked(session_id: str, wafers: Annotated[list[str] | None, Query()] = None) -> Response:
    session = _session(session_id)
    selected = _select(session, wafers)
    ref, _center, _keys, _bounds = _reference_or_422(session.product)
    stack = stacked_summary(ref, session.data[session.data.Wafer_ID.isin(selected)], selected)
    return _csv_response(stack[['Die_Num','Spring_Num','x','y','Inspected','Defects','Killer','Defect_Rate']], f"{session.product}_stacked_spring_metrics.csv")


@app.get("/api/export/inspection")
def export_inspection(session_id: str, wafers: Annotated[list[str] | None, Query()] = None) -> Response:
    session = _session(session_id)
    selected = _select(session, wafers)
    selected_data = session.data[session.data.Wafer_ID.isin(selected)]
    return _csv_response(selected_data, f"{session.product}_inspection_normalized.csv")


# Serve the built React frontend (single-origin, relative /api). Mounted after
# the API routes; skipped when no build exists (backend-only test runs).
_STATIC_DIR = Path(os.environ.get("STATIC_DIR", DEFAULT_STATIC_DIR))
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8090, reload=False)
