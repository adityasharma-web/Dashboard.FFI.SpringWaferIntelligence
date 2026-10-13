# Spring Wafer Intelligence — operational dashboard

Operationalized port of the `spring_wafer_app` Streamlit prototype into the
suite's standard shape: a pure-Python **analysis engine**, a **FastAPI**
service exposing it over typed JSON on a relative `/api`, and a
**React / Vite / TypeScript** frontend on the suite design system — plus an
adapter that ingests the customer's **CloudPCS XML** inspection exports.

```
   browser ── React/TS (Vite build) ── relative /api ── FastAPI (backend/app.py)
                                                             │
                                                      backend/engine/   (pure Python; no Streamlit)
                                                             │
                                          coordinates/ (product references)   examples/ (SYNTHETIC wafers)
```

Spring-level wafer inspection for probe cards: a 200 mm wafer holds gangs
(dies), each gang holds a few hundred microscopic springs, and inspection
grades each spring. Every spring is registered to its physical X/Y position
from a product coordinate reference, and defect patterns are analyzed across
one or many wafers.

> **Exploratory screening utility, not a validated manufacturing release
> decision system.** Spatial signatures are descriptive, not causal; spiral
> recognition is not automated; the coordinate center (bounding-box midpoint)
> and notch-down orientation are assumed and must be validated against
> physical fiducials. These caveats are shown in the UI, not buried here.

## Layout

```
backend/
  engine/
    reference.py      load_reference / list_products / gang_bounds (bounding-box centering)
    inspection.py     read_inspection + validate_inspection (the original validation chain)
    analysis.py       stacked_summary, spatial_analysis, signature_indicators, header metrics
    gang_yield.py     PASS / SCRAP (> 60 %, strictly) / INCOMPLETE disposition
    xml_adapter.py    CloudPCS XML -> normalized frame, explicit grading map
    grading_map.json  SPRING_GRADING / DEFECT_CODE -> status lookup (EMPTY by design)
  app.py              FastAPI endpoints, sessions, caches, JSON marshaling only
  launch.py           one-process launcher (serves the built frontend)
  coordinates/        product coordinate references (152-900530D.xlsx)
  examples/           six SYNTHETIC example wafers for 152-900530D
  tests/              golden parity, domain rules, XML adapter, API contract
    fixtures/golden.json   pre-port values captured from the Streamlit functions
    tools/capture_golden.py  the capture script (reads reference-source/, never the port)
frontend/
  src/api/            client.ts (relative /api), types.ts (payload mirrors)
  src/charts/         waferFigures.ts — Plotly figure builders (wafer, stacked, heatmap)
  src/components/     controls, KPI cards, the five view panels, tables
  src/theme/          suite design tokens (dark default / light), chart color resolution
reference-source/     the original Streamlit app, unmodified (parity reference)
screenshots/          captured verification screenshots
```

## The five views

1. **Individual wafer** — each spring as a 4 mm horizontal segment at its real
   coordinate, colored Good `#21a653` / Low `#f4d43b` / Med `#f38a24` /
   Killer `#df3537` / Uninspected `#aab4c2`, gang outlines + die labels, wafer
   outline (100 mm radius) and notch marker; hover shows die, spring, status.
2. **Stacked wafer** — per-spring defect *frequency* (defects ÷ inspections)
   across the selected wafers; never-inspected springs are drawn at zero for
   rendering only and are explicit in the table.
3. **Spatial signatures** — Gaussian-smoothed incidence on a 2 mm grid (blank
   where coverage is insufficient), radial zones, outer angular sectors,
   indicator messages (including "spiral patterns are not labeled
   automatically"), hotspot peaks, and the binomial / Benjamini-Hochberg
   recurrence table with its exploratory caveat.
4. **Gang yield** — per-wafer per-gang bad fraction against the **reference**
   spring count; `SCRAP` when strictly > 60 %, `INCOMPLETE` when not fully
   inspected, else `PASS`; the rule is stated on screen.
5. **Export** — stacked spring metrics and normalized inspection data as CSV.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | liveness |
| `GET /api/products` | products with a coordinate reference in `coordinates/` |
| `GET /api/reference/{product}` | spring coordinates (centered), inferred center, gang bounds |
| `POST /api/inspections` | multipart `product` + `files[]` (CSV / XLSX / CloudPCS XML); returns a session id and the wafer list, or **422 with every per-file error** and nothing loaded |
| `POST /api/examples` | load the bundled **synthetic** wafers into a session (`synthetic: true`) |
| `POST /api/analyze` | `{session_id, wafers?, bandwidth}` → header, individual, stacked, spatial, signature, gang_yield, caveats |
| `GET /api/export/stacked` / `GET /api/export/inspection` | the two CSV exports (`session_id`, repeated `wafers`) |

Charts are returned as **underlying arrays** (coordinates + status codes,
per-spring metrics, the smoothed rate grid oriented rows = y bins, zone /
sector / peak / recurrence / gang tables); the React side draws them with
Plotly. The parsed reference is cached per product and each analysis per
(session, wafer set, bandwidth).

## Run (two processes, same-origin /api via the Vite proxy)

```bash
# terminal 1 — API (http://localhost:8090)
backend/.venv/Scripts/python -m uvicorn app:app --app-dir backend --port 8090

# terminal 2 — UI (http://localhost:5187)
npm run dev --prefix frontend -- --port 5187 --strictPort
```

Setup: `py -3.13 -m venv backend/.venv`, then
`backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt`
and `npm ci --prefix frontend`.

## Run (deployed shape, one origin)

```bash
npm run build --prefix frontend
backend/.venv/Scripts/python -m uvicorn app:app --app-dir backend --port 8090
```

FastAPI serves `frontend/dist` at `/` (mounted after the API routes, skipped if
no build exists; override with `STATIC_DIR`). `backend/launch.py` does the
same and opens the browser (`SPRING_WAFER_PORT`, default 8090).

Docker: `docker compose up -d --build spring-wafer-intelligence` → host port
8091. The optional `ngrok` demo tunnel runs with `--profile demo` and needs
`NGROK_AUTHTOKEN=` in `.env`.

## Tests

```bash
backend/.venv/Scripts/python -m pytest -q backend     # 57 tests: golden parity, domain rules, XML adapter, API
npm run test --prefix frontend                        # vitest: figure geometry, rendering, interactions
npm run lint --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
```

### Golden parity

`backend/tests/fixtures/golden.json` holds the pre-port numbers for the six
synthetic wafers, captured by `tests/tools/capture_golden.py` directly from the
functions in `reference-source/spring_wafer_app/app.py` (lifted by AST; the
only Streamlit symbol they touch, `st.cache_data`, is stubbed to identity).
Three scenarios are pinned — all six wafers at 5 mm, the first three at 10 mm,
one wafer at 5 mm — and `test_golden.py` compares header metrics, every
per-spring stacked metric, the full smoothed rate grid, the baseline, the
hotspot table, the full recurrence table (p and q), zones, indicator messages,
the per-wafer per-gang disposition table and the individual status counts.

Headline values (six wafers, 5 mm): 20,952 springs in 108 gangs, center
(71.245, −0.5015) mm, 125,712 observations, 12.78 % defect rate, 6,036
covered grid cells, 5 hotspots, 0 scrapped gangs, 10 springs with q ≤ 0.05.

## Data

- `coordinates/152-900530D.xlsx` is the only product reference. Add
  `PRODUCT.xlsx` or `.csv` (`Die_Num, Spring_Num, X, Y`; parenthetical header
  descriptions are stripped) to support another product.
- `examples/` are **synthetic**, generated by
  `reference-source/spring_wafer_app/make_examples.py`; the UI labels them as
  such everywhere they appear.
- CloudPCS XML exports are accepted by the upload endpoint (`.xml`). The
  `SPRING_GRADING` / `DEFECT_CODE` → Good/Low/Med/Killer mapping is **not
  defined**: `backend/engine/grading_map.json` is empty and any unmapped value
  is rejected with a message naming it. A product without a coordinate
  reference, or an export whose die/spring keys are not in the reference, is
  rejected with a specific message — nothing is partially rendered.

## Ground rules

- The engine reproduces the Streamlit numbers exactly; do not "improve" the
  statistics, smoothing, thresholds or BH correction. Flag, don't fix.
- Uninspected ≠ Good. Scrap strictly > 60 % of the reference spring count.
- No fabricated data: no invented references, severities or coordinates.
- No analysis logic in the API or the frontend.
- No individuals' names in code, comments or deliverables.
