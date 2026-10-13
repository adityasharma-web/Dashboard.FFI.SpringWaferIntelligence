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
and `?theme=dark|light`.

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
  grading mappings. `engine/grading_map.json` stays empty until the customer
  defines the mapping.
- **No analysis logic in `app.py` or the frontend.** The API marshals engine
  output; the React app renders it. The only frontend-computed pixels are the
  4 mm segment endpoints (x ± 2) and the hover text.
- Keep the caveats visible in the UI (scope banner, registration note,
  line-thickness note, synthetic labels, recurrence caveat).
- No individuals' names in code, comments or deliverables.
- `pandas` is pinned `<3` to match the original app's requirements (pandas 3
  changes string / copy semantics; parity was verified on 2.3.x).

## 6. Data situation (open with the customer)

- The real CloudPCS export (`152-900405V`, 55,872 rows, one wafer) **cannot
  render**: no coordinate reference for that product (`coordinates/` only
  has `152-900530D`), different geometry (192 gangs × 291 springs vs 108 ×
  194), every row `SPRING_GRADING = SCRAP` / `DEFECT_CODE = 2H`, and the XML
  X/Y defect columns are all `0.0`. The adapter rejects it at the product
  step with a specific message; nothing is forced or invented.
- **Open question 1:** the `SPRING_GRADING` / `DEFECT_CODE` →
  Good/Low/Med/Killer mapping. Configure it in
  `backend/engine/grading_map.json` (`by_grading` for grading-only rules,
  `by_grading_and_code` keyed `GRADING|CODE`). Unmapped values fail loudly.
- **Open question 2:** a spring-level export for **`152-900530D`** would work
  immediately — that product has a coordinate reference and 91 wafers exist in
  the yield system.

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

Implemented: product selector, multi-file upload (CSV / XLSX / CloudPCS XML)
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
