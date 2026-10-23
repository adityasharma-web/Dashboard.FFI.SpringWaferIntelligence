# Handoff — Spring Wafer Intelligence

## 1. What this is

The `spring_wafer_app` Streamlit prototype (spring-level probe-card wafer
inspection, stacked-wafer spatial signatures, gang yield) ported to the suite
stack: a pure-Python engine extracted from `app.py`, a FastAPI service over a
relative `/api`, and a React 18 + TypeScript + Vite frontend on the suite
design system. Same numbers (golden-tested), same domain rules, plus a
CloudPCS XML ingestion adapter.

## 2. Machine setup

```bash
py -3.13 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend
```

## 3. Running

```bash
# terminal 1 — API
backend/.venv/Scripts/python -m uvicorn app:app --app-dir backend --port 8090

# terminal 2 — UI (http://localhost:5187)
npm run dev --prefix frontend -- --port 5187 --strictPort
```

Single-origin deployed shape: `npm run build --prefix frontend`, then start the
API alone — it serves `frontend/dist` at `/`. Docker:
`docker compose up -d --build spring-wafer-intelligence` (host port 8091).

The shared `C:\BDrive\repos\github\.claude\launch.json` has
`spring-wafer-backend` (8090) and `spring-wafer-frontend` (5187) entries for
the desktop app's preview pane. Deep links: `?view=stacked|spatial|gangs|export`
`?theme=dark|light` and `?session=<id>`.

## 4. Tests & checks — run all of these before calling any change done

```bash
backend/.venv/Scripts/python -m pytest -q backend
npm run test --prefix frontend
npm run lint --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
```

## 5. Ground rules

- **The engine must keep reproducing the Streamlit numbers.** `test_golden.py`
  pins them against `tests/fixtures/golden.json`, which was captured from the
  original functions in `reference-source/` — never from the port. If a
  golden test fails, the port drifted; do not regenerate the fixture to make
  it pass.
- **Uninspected ≠ Good**, everywhere: rates exclude missing coverage, the
  individual counts table lists observed statuses only, the stacked map draws
  missing coverage at zero for rendering only and the table says so.
- **Scrap strictly > 60 %** of the *reference* spring count; exactly 60 % is
  not scrap; INCOMPLETE is flagged, and scrap wins over incomplete.
- **No fabricated data.** No invented coordinate references, severities or
  code meanings. The CloudPCS status rule is the customer's (2026-10-13):
  not SCRAP = Good; SCRAP = its DEFECT_CODE. The defect-code palette is
  provisional (by frequency) until a scheme is supplied.
- **No analysis logic in `app.py` or the frontend.** The API marshals engine
  output; the React app renders it. The only frontend-computed pixels are the
  4 mm segment endpoints (x ± 2) and the hover text.
- Keep the caveats visible in the UI (scope banner, registration note,
  line-thickness note, synthetic labels, recurrence caveat).
- No individuals' names in code, comments or deliverables.
- `pandas` is pinned `<3` to match the original app's requirements (pandas 3
  changes string / copy semantics; parity was verified on 2.3.x).

## 6. Data situation

- **Two status models.** CSV/XLSX sessions carry Good/Low/Med/Killer
  (`status_model = severity`). CloudPCS XML sessions carry no severity:
  `status_model = defect_code`, states are `Good` + the session's defect codes
  ranked by count + `Uninspected`, colors come from `DEFECT_CODE_PALETTE` in
  `app.py`. The engine's "bad" test is `Status != Good` either way, so every
  analysis is shared; the Killer column is hidden for XML sessions. Mixing the
  two file kinds in one upload is rejected.
- **Real data that works:** `152-900530D` wafer `W304617.1` (file
  `iXML#152-900530D_WaferYield_DefectMonitor_…MET_W3046171….xml`, 44 MB in
  the EPIC OneDrive folder): 20,952 rows, exact geometry match, 16 defect
  codes, 29.3 % defective, 11 gangs > 60 %, five gangs fully scrapped. Upload
  takes ~5 s. Customer data: never commit it.
- **Real data that does not:** the `152-900405V` export has no coordinate
  reference and different geometry (192 × 291); rejected at the product step.
- **Open with the customer:** defect-code meanings and a house color scheme;
  whether SCRAP_STAGE / EVENT_ID (carried through as metadata, 7 stages on
  W304617.1) should become a second coloring mode.

## 6b. Layouts page (2026-10-22, PM request)

PM ask: "a dedicated page for the layouts, where they can upload a CSV with
coordinates and visualize the map before saving it; create a new page, don't
add to current." Delivered as `#/layouts` (hash routing so the single-origin
deploy keeps working): list / upload-preview / save / delete. Decisions taken
without a PM check-in, flag them if he disagrees:

- CSV or XLSX, four-column schema, one row per spring ("CAB" read as CSV).
- A layout has a name **and** a list of design / product names (designs often
  share a layout). Product names must be unique across layouts.
- Overwrite needs the explicit Replace tick; delete needs a second click.
- Files stay in `backend/coordinates/`; `layouts.json` is the registry.
  Unregistered files are implicit layouts (stem = product) - no migration.
- Saving clears the reference cache so the wafer map sees the new layout
  immediately; the map re-fetches the product list on navigation back.

## 7. Design system

`frontend/src/theme/theme.css` carries the suite tokens (dark default, light
override) copied from the most recent operational dashboard, plus
`--wafer-fill`, `--wafer-edge`, `--gang-outline`, `--gang-label`. Charts
resolve tokens at runtime via `chartColors.ts`. The five spring status colors
are the domain palette and come from the API payload, not the theme. Buttons
follow the house rule: downloads / primary action in accent blue, secondary
in neutral; red/green/yellow are reserved for data, never buttons.

**Known deviation (same as the Overlay port):** charts are Plotly
(`plotly.js-dist-min`, bundled, offline) rather than the suite's recharts — a
21k-segment WebGL wafer map with an aspect-locked disc and a 2 mm heatmap is
not representable in recharts, and the reference implementation is Plotly.

## 8. Feature state

Implemented: Layouts page (upload / preview / save / delete coordinate references), product selector, multi-file upload (CSV / XLSX / CloudPCS XML, defect-code coloring for XML)
with per-file error listing, synthetic examples loader (auto-loaded at
startup, badged), wafer multi-select, gang-outline toggle, 2–15 mm smoothing
slider (debounced re-analysis), four header metrics, the five views, both
CSV exports, light/dark theme.

Deliberately absent (matches the reference, out of scope): auth, persistence
beyond in-memory sessions (20 sessions, 40 cached analyses each), new
statistics, automated spiral detection.

## 9. Gotchas

- Plotly draws `heatmap` and `scattergl` traces in layers *below* SVG scatter
  fills, so the wafer disc is an outline only (as in the reference). A filled
  disc would hide the springs and the heatmap.
- The engine's rate grid is `[x_bin, y_bin]`; the API returns its transpose
  (rows = y bins) ready for the heatmap. 103 bin edges from −102 to 102 →
  102 × 102 cells.
- Vitest aliases `plotly.js-dist-min` to `src/test/plotlyStub.ts`; figure
  tests assert on JSON, not pixels. Headless Chrome screenshots of the
  WebGL views can show a read-back artifact on the right edge under
  SwiftShader; the real browser does not.
- Validation messages are the original Streamlit strings prefixed with the
  file name; non-numeric Die/Spring keep pandas' own message inside.
- `signature_indicators` returns the 12 outer angular sectors as an extra
  (the original computed but did not display them); the UI shows them
  collapsed.

## 10. Working conventions

Tasks arrive as spec markdown; verify against current code first; one branch
per task; screenshots into `screenshots/` for review; nothing pushed or merged
without an explicit decision.
