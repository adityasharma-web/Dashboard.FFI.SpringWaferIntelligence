"""Spring Wafer Intelligence analysis engine.

Pure Python / pandas / numpy / scipy. No Streamlit, no Plotly, no FastAPI.
The functions are the ones from the original Streamlit ``app.py`` moved over
essentially verbatim (see ``reference-source/spring_wafer_app/app.py``); the
only additions are the thin helpers the API needs (product listing, gang
bounds, header metrics, gang yield extracted from the Streamlit tab) and the
CloudPCS XML adapter.

Domain rules preserved here and protected by ``tests/``:

* Missing spring observations stay *Uninspected* and are never counted as Good.
* Gang scrap when bad springs / total reference springs in the gang is
  strictly greater than 60 %; incomplete inspections are flagged INCOMPLETE.
* The coordinate center is the bounding-box midpoint of the reference and is
  reported so the UI can show the registration caveat.
"""
from .analysis import (
    STATES,
    header_metrics,
    individual_wafer_status,
    signature_indicators,
    spatial_analysis,
    stacked_summary,
)
from .gang_yield import SCRAP_THRESHOLD, gang_yield
from .inspection import InspectionError, combine_inspections, read_inspection, validate_inspection, validate_keys
from .reference import ReferenceError, gang_bounds, list_products, load_reference, valid_spring_keys
from .xml_adapter import CloudPcsAdapterError, grading_to_status, read_cloudpcs_xml

__all__ = [
    "STATES",
    "SCRAP_THRESHOLD",
    "CloudPcsAdapterError",
    "InspectionError",
    "ReferenceError",
    "combine_inspections",
    "gang_bounds",
    "gang_yield",
    "header_metrics",
    "individual_wafer_status",
    "list_products",
    "grading_to_status",
    "load_reference",
    "read_cloudpcs_xml",
    "read_inspection",
    "signature_indicators",
    "spatial_analysis",
    "stacked_summary",
    "valid_spring_keys",
    "validate_inspection",
    "validate_keys",
]
