# Sentient Spring Wafer Intelligence

Interactive wafer inspection and stacked-wafer spatial analysis, with product-specific spring coordinate registration.

## Install / run

Python 3.10+ recommended:

```bash
cd spring_wafer_app
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit (normally http://localhost:8501).

## Product coordinate references

Place `PRODUCT.xlsx` or `PRODUCT.csv` in `coordinates/`, e.g. `coordinates/152-900530D.xlsx` (included). Supported coordinate columns: `Die_Num`, `Spring_Num`, `X`, `Y`. Original reference headers with parenthetical descriptions are supported. Coordinate units are assumed to be mm. The source's geometric bounding-box midpoint is assumed to be the wafer center; notch down is illustrative. Validate registration/orientation against physical wafer fiducials before production use.

## Inspection input schema

One CSV or XLSX per wafer, with required columns:

| Product | Die_Num | Spring_Num | Defect | Defect_Severity | Wafer_ID (optional) |
|---|---:|---:|---|---|---|
| 152-900530D | 1 | 1 | N | | WAFER_001 |
| 152-900530D | 1 | 2 | Y | Low | WAFER_001 |
| 152-900530D | 1 | 3 | Y | Med | WAFER_001 |
| 152-900530D | 1 | 4 | Y | Killer | WAFER_001 |

- `Defect`: `Y` or `N`. `Defect_Severity`: `Low`, `Med`, or `Killer` required for `Y`; empty permitted for `N`.
- `Wafer_ID` optional; filename stem is used when omitted. One unique wafer ID per file.
- Upload multiple files of **the same Product** and choose which wafers to stack.
- Each `(Wafer_ID, Die_Num, Spring_Num)` must be unique and match the reference.
- Missing spring observations are not counted as Good; they remain uninspected.

## Views

- **Individual wafer:** color-coded 4 mm horizontal spring segments; spring hover IDs; gang outlines and labels; uninspected springs gray.
- **Stacked wafer:** exact per-spring defect frequency (defect observations / inspections), with exposure counts and killer counts.
- **Spatial signatures:** Gaussian-smoothed spatial defect incidence, radial-zone comparison, angular-sector variation, local excess hotspots, exploratory binomial/BH recurrence table.
- **Gang yield:** per-wafer per-gang bad spring fraction using total reference spring count; scrap if **strictly greater** than 60%; incomplete inspections explicitly flagged.
- **Export:** normalized inspection data and stacked metrics.

## Important interpretation and limitations

This tool is an exploratory screening utility, **not a validated manufacturing release decision system**. Edge enrichment, sector asymmetry, and local hotspots are descriptive signatures, not causal diagnoses. Spiral recognition is not automatically implemented or validated. A recurring pattern can reflect product design, process, metrology, inspection coverage, or wafer registration. For production decisions, validate against known-good and known-bad historical lots, verify coordinate center/orientation, and add lot/tool/time metadata and statistical process controls. The physical spring footprint is 4.0 × 0.4 mm; line width in the interactive Plotly renderer is screen-pixel-based, not a physical 0.4 mm footprint.

Synthetic example files in `examples/` are explicitly simulated; do not interpret them as measured yield.
