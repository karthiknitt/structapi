# StructAgent × PlanForge — Integration Architecture & Implementation Plan

Status: **live in production** · Owner: StructAgent repo · Designed 2026-07-12 · Shipped 2026-07-12 · Last verified 2026-07-27

## 1. Context

**PlanForge** (github.com/karthiknitt/planforge) generates compliant residential
floor plans for Indian construction (Next.js 16 / Vercel frontend; FastAPI /
Cloud Run backend; Neon Postgres; BetterAuth; ReportLab PDF + ezdxf DXF
exports; Razorpay; agentic Claude chat via Vercel AI SDK).

**StructAgent** (this repo) designs RCC structures per Indian Standards:
the deterministic `python/iscodes` library (IS 456/875/1893/13920/3370/10262,
94 tests) + an Eve multi-agent NL layer + a small authenticated web UI.

**Goal:** PlanForge users go from *floor plan* → *structural design* (framing,
member sizing, foundations, BOQ steel/concrete quantities, approval-ready
structural PDF sheets) without leaving PlanForge. StructAgent stays a
standalone product.

## 2. Architecture decision

**Two front doors, one calculation core** (decided 2026-07-12):

```
                         ┌────────────────────────────────────────────┐
 Humans (NL)  ──────────▶│  Eve agent layer (orchestrator + 8 subagents)  │──┐
 (StructAgent UI/TUI)    └────────────────────────────────────────────┘  │ runs in sandbox
                                                                          ▼
 PlanForge backend ─────▶ ┌──────────────────────────┐        ┌──────────────────┐
 (FastAPI, Cloud Run)     │  structapi (NEW)          │───────▶│  python/iscodes   │
 service-to-service,      │  FastAPI, stateless,      │        │  deterministic    │
 x-api-key                │  JSON in → JSON+artifacts │        │  IS-code engine   │
                          └──────────────────────────┘        └──────────────────┘
 PlanForge chat (Claude) ──▶ tool call → structapi (same contract)
```

Why structapi (deterministic REST) and not the agent API for PlanForge:
- PlanForge's backend is **FastAPI/Python** — it consumes a Python-native
  service naturally; both already use ReportLab.
- Structural design from a known floor plan is **fully parameterized** — no
  NL interpretation needed. Deterministic = same plan in, same design out
  (essential for revision history, approvals, BOQ reproducibility).
- Milliseconds and zero LLM tokens vs 30-60 s and OpenRouter cost per call.
- PlanForge's existing Claude chat can still offer conversational structural
  edits by calling structapi as a *tool* — the LLM stays on their side where
  their UX already is.
- The Eve agent layer remains the standalone product's NL interface and both
  layers call the identical `iscodes` functions → identical numbers.

Explicitly rejected: exposing Eve sessions to PlanForge (non-deterministic,
slow, needs streaming consumption + API-key work on the eve channel for no
benefit when inputs are structured).

## 2a. Shipped state (verified 2026-07-27)

The architecture above is deployed, not aspirational. All three components are live:

| Component | URL | Verify |
|---|---|---|
| structapi | `https://structapi-912195238699.us-central1.run.app` | `curl .../v1/health` → `{"status":"ok","api_version":"1","iscodes_version":"0.3.0"}` |
| PlanForge backend | `https://planforge-backend-912195238699.us-central1.run.app` | `curl .../api/health` → `{"status":"ok","service":"planforge-api"}` |
| PlanForge frontend | `https://planforge-mauve.vercel.app` | browser |

> Version note: the deployed Cloud Run revision serves `iscodes` **0.3.0**. Tag `v0.3.1`
> (isolated-footing development-length sizing) is released and its image published to
> GHCR, but not yet rolled out to the live service.

The PlanForge backend exposes five routes implementing the full loop:

```
POST  /api/projects/{id}/structural/design              request a design
GET   /api/projects/{id}/structural/status              poll progress
POST  /api/projects/{id}/structural/approve             approve a revision
GET   /api/projects/{id}/structural                     fetch current design
GET   /api/projects/{id}/export/structural-drawing-set  export drawings
```

PlanForge-side implementation:

| Concern | File (planforge repo) |
|---|---|
| HTTP client for structapi | `backend/app/services/structagent_client.py` |
| Design request orchestration | `backend/app/services/structural_loop.py` |
| Revision persistence | `backend/app/services/structural_store.py` |
| API routes | `backend/app/api/routes/structural.py` |
| Plinth beam design | `backend/app/services/plinth_beam_design.py` |
| Drawing set export | `backend/app/engine/structural_drawing_set.py` |

Contract freeze: `python/tests/fixtures/beam_envelope_v1.json` (this repo) — CI fails on
any v1 envelope drift. The vendored copy of structapi inside PlanForge
(`structapi-service/`) is byte-diffed against the pinned tag on every push and PR.

## 3. Contract (v1, frozen envelope)

All endpoints return:
```json
{
  "api_version": "1",
  "ok": true,
  "checks": [{"name": "two-way shear tau_v <= ... (cl 31.6.3)", "ok": true}],
  "data": { "...element-specific results, mm/kN/MPa units as documented..." },
  "artifacts": [
    {"name": "sfd_bmd.png", "content_type": "image/png", "encoding": "base64", "content": "..."},
    {"name": "design_report.pdf", "content_type": "application/pdf", "encoding": "base64", "content": "..."}
  ],
  "code_editions": {"IS456": "2000 (reaffirmed 2021)", "...": "..."},
  "disclaimer": "..."
}
```
Errors: RFC-7807-style `{type, title, status, detail}` + 422 pydantic
validation errors as FastAPI defaults. Breaking changes → `/v2`, never mutate
v1 fields. Artifacts are inline base64 in v1 (simple, stateless); v2 moves to
object-storage URLs (GCS) when payload size warrants.

### Endpoints
| Route | Wraps | Notes |
|---|---|---|
| `GET /v1/health` | — | liveness + iscodes version |
| `POST /v1/calc/loads/combinations` | `loads.combinations` | Table 18 combos |
| `POST /v1/calc/loads/wind` | `loads.wind_pressure` | IS 875-3:2015 |
| `POST /v1/calc/loads/seismic` | `loads.base_shear` | IS 1893:2016 |
| `POST /v1/calc/beam` | `design.beam.design_beam` | + SFD/BMD PNG artifact |
| `POST /v1/calc/column` | `design.column.design_column` | + P-M diagram PNG |
| `POST /v1/calc/footing/isolated` | `design.footing.design_isolated_footing` | + pressure diagram |
| `POST /v1/calc/footing/combined` | `design.footing.design_combined_footing` | + SFD/BMD PNG |
| `POST /v1/calc/slab/one-way` | `design.slab.design_one_way_slab` | |
| `POST /v1/calc/slab/two-way` | `design.slab.design_two_way_slab` | |
| `POST /v1/calc/tank/circular` | `design.tank.*` | |
| `POST /v1/calc/sump` | `design.tank.sump_* + uplift` | |
| `POST /v1/calc/mix` | `design.mix.design_mix` | IS 10262:2019 |
| `POST /v1/design/building` | NEW chain (Phase B) | the PlanForge workhorse |
| `POST /v1/report/pdf` | `pdfreport` | re-render a PDF from a prior result |

Auth: `x-api-key` header checked against `STRUCTAPI_KEYS` (comma-separated;
per-consumer keys → per-consumer usage logs). Optional `x-correlation-id`
echoed in responses and logs (PlanForge passes its project/revision id).
FastAPI auto-publishes OpenAPI at `/docs` — that spec IS the doc PlanForge
devs integrate against.

### `/v1/design/building` input (the plan→structure contract)
```json
{
  "grid": {"x_spacings_m": [3.5, 4.0, 3.5], "y_spacings_m": [4.0, 4.5]},
  "storeys": 2, "storey_height_m": 3.0,
  "occupancy": "residential_room",
  "location": {"city": "chennai", "seismic_zone": "III",
               "terrain_category": 3, "soil": "medium"},
  "sbc_kpa": 200,
  "materials": {"fck": 25, "fy": 500, "exposure": "moderate"},
  "options": {"seismic_detailing": true, "pdf_report": true}
}
```
PlanForge derives `grid` from its generated layout (wall/column lines) —
the mapping from arbitrary room polygons to a regular column grid lives on
the PlanForge side (they own plan semantics); structapi owns everything after
the grid exists. Output: per-element results (slab panels, beams by tributary
width, columns by tributary area + frame moments, isolated footings), steel +
concrete quantity summary (BOQ-ready), one consolidated PDF, all drawings.

### `/v1/design/building` output additions (v0.2.0 — additive to v1)

Two fields were added to `data` for PlanForge's closed design loop (design →
fails → map failure to a solver constraint → re-solve → re-design). Both are
additive; every other `data` field is unchanged, and `api_version` stays
`"1"`.

**`data.violations[]`** — always present (`[]` when `ok: true`, never absent).
One entry per FAILING check remaining in the returned design (a member that
passed after the chain's own section-size iteration produces no entry):

```json
{
  "member_type": "beam",
  "axis": "y",
  "grid_ref": "beam line axis=y, grid indices=[1], span 12.00 m",
  "span_m": 12.0,
  "check": "shear (cl 40)",
  "actual": 4.525521,
  "limit": 2.8,
  "unit": "MPa",
  "remedy_hint": "add_grid_line"
}
```

| Field | Type | Meaning |
|---|---|---|
| `member_type` | `"beam"\|"column"\|"slab"\|"footing"` | which chain stage failed |
| `axis` | `"x"\|"y"\|null` | grid axis the member spans (beams only; `null` for columns/slabs/footings) |
| `grid_ref` | string | human-readable locator — grid-line indices for beams, panel description for slabs, column/footing class otherwise |
| `span_m` | float\|null | governing span (beams/slabs); `null` for columns/footings |
| `check` | string | the exact clause-referenced check name from `checks[]` (same string, not re-derived) |
| `actual` / `limit` | float\|null | the real computed values behind the check (utilisation vs allowable, stress vs limit, etc.) — sourced from the design function's own internals, never parsed out of `check`. `null` only when the underlying value is non-finite (e.g. an unbounded biaxial interaction ratio) or the chain hit a hard sentinel failure (footing depth never converged) |
| `unit` | string | unit of `actual`/`limit` (`"MPa"`, `"mm"`, `"mm2"`, `"kNm"`, `"%"`, `"ratio"`, `"kPa"`, or `""` when not applicable) |
| `remedy_hint` | enum | see below |

`remedy_hint` — one of `reduce_span`, `increase_section`, `add_grid_line`,
`increase_sbc`, `increase_grade`, `review_inputs`:

| Failure pattern | `remedy_hint` |
|---|---|
| Beam moment/shear/ductile-pt failing after the chain's own D-iteration maxed out (span too long for any section it tried) | `add_grid_line` |
| Beam over-reinforced (`Ast > Ast_max`) or deflection L/d exceeded | `reduce_span` |
| Beam IS 13920 min-width failure | `increase_section` |
| Column steel %, slenderness, biaxial interaction, IS 13920 min-width failing after the chain's own dia/section iteration maxed out | `increase_section` |
| Column bar-count/dia or tie-dia detailing shortfall | `review_inputs` |
| Slab flexure/shear failing after the chain's own depth-iteration maxed out | `add_grid_line` |
| Slab deflection L/d exceeded | `reduce_span` |
| Slab bar-spacing detailing shortfall | `review_inputs` |
| Footing bearing pressure > SBC, or depth never converged for shear | `increase_sbc` |
| Footing two-way/one-way shear or development length failing at max depth | `increase_section` |
| Footing column-base bearing stress exceeded | `increase_grade` |
| Footing net uplift (`q_min < 0`) | `review_inputs` |
| Anything not mapped above | `review_inputs` |

**`data.grid_lines`** — cumulative grid-line coordinates (m), starting at
0.0, derived from the input spacings:

```json
{"x_coords_m": [0.0, 3.5, 7.5, 11.0], "y_coords_m": [0.0, 4.0, 8.5]}
```

Every sized member also carries enough positional reference to place it on
this grid without re-deriving geometry from spacings:
- **Beams** (`data.beams[*]`): `axis` (`"x"`/`"y"`), `grid_line_indices`
  (perpendicular grid-line indices this beam design applies to — beams are
  deduplicated by span/tributary-width, so one entry can cover several
  physical lines), `span_indices` (bay positions along each such line).
- **Columns** (`data.columns[*]`): `grid_intersections` — list of
  `[x_index, y_index]` grid-line intersections belonging to that class
  (`corner`/`edge`/`interior`), alongside the existing `count`.
- **Footings** (`data.footings[*]`): inherit the same `grid_intersections`
  as their parent column class (one footing per column).
- **Slabs** (`data.slabs[*]`): `panel_indices` — list of `[i, j]` grid-cell
  indices sharing that panel design.

## 4. Implementation phases

### Phase A — structapi service (this repo) — ~1 session
1. `python/structapi/` package: `main.py` (FastAPI app, API-key dependency,
   correlation-id middleware), `schemas.py` (pydantic v2 models mirroring
   each iscodes function signature — field names/units IDENTICAL to the
   Python API), `routes/` (one module per element), `artifacts.py`
   (matplotlib → PNG bytes → base64; PdfReport → PDF bytes; also optional
   write-through to `outputs/api/<correlation-id>/`).
2. Reuse: every route is a thin adapter — validate → call iscodes → wrap
   envelope. NO engineering logic in structapi (single source of truth stays
   iscodes; enforced by review).
3. `python/requirements-api.txt` (fastapi, uvicorn, pydantic ≥2 + existing
   requirements.txt), `structapi.Dockerfile` (python:3.12-slim; no eve, no
   node), docker-compose service `structapi` (port 8080), npm script
   `api:dev": "cd python && uvicorn structapi.main:app --port 8080 --reload"`.
4. Tests `python/tests/test_structapi.py` (FastAPI TestClient): happy path
   per endpoint (assert envelope shape + a known number), auth 401, 422 on
   bad units, artifact base64 round-trip (decode → %PDF/PNG magic bytes),
   determinism (two identical calls → identical `data`).
5. SETUP.md + README: run/deploy instructions; `.env.example` +=
   `STRUCTAPI_KEYS=`.

### Phase B — building design chain (this repo) — the real engineering — ~1 session
1. `python/iscodes/design/building.py`:
   - Loads: slab DL (self+finish) + occupancy IL (IS 875-2), wind (875-3 by
     city/terrain), seismic (1893 by zone/soil, storey weights from takedown),
     Table 18 combos.
   - Slabs: panel classification per grid cell (one/two-way, Table 26 case
     from edge continuity) → design each unique panel.
   - Beams: tributary trapezoid/triangle loads from adjacent panels + wall
     allowance; continuous-beam coefficients (Table 12/13) where valid;
     design envelope per unique beam line (grouped by span/loading).
   - Columns: tributary gravity + frame lateral moments via portal-frame
     approximation (storey shear from 1893 distribution → column moments);
     biaxial design; IS 13920 overlay for zones III-V.
   - Footings: service + factored column reactions → isolated footings
     (flag combined when spacing/overlap demands).
   - Output: `BuildingDesign` dataclass — per-element results, quantity
     takeoff (steel kg by dia, concrete m³ by element class — matches
     PlanForge BOQ line-item shape), figures, consolidated PdfReport.
2. Grouping/economy: identical members deduplicated (design once, count n).
3. Tests: 2-storey 3×2-bay reference building — hand-checked column load
   takedown, storey shear, and quantity sanity bands; determinism test.

### Phase C — machine access hardening (this repo) — small
1. Per-key rate limiting (slowapi) + structured request logs (key, corr-id,
   endpoint, duration).
2. CORS: explicit allowlist (PlanForge backend origin not needed — server-to-
   server; keep CORS closed).
3. Version pinning doc: envelope freeze policy; contract tests that fail on
   accidental field renames.
4. (Deferred, only if PlanForge wants NL later) BetterAuth `apiKey` plugin on
   the Next proxy to expose Eve sessions to services.

### Phase D — PlanForge-side changes (their repo; PR-ready spec)
1. `backend/app/services/structagent_client.py`: httpx async client
   (STRUCTAPI_URL, STRUCTAPI_KEY from env), typed pydantic mirrors of the v1
   envelope, retry (idempotent POSTs) + 30 s timeout.
2. Grid extraction: `backend/app/engine/structural_grid.py` — derive column
   grid from their layout solver output (wall intersections → grid lines →
   spacings). This is the one nontrivial mapping and it belongs to them
   (they own plan semantics).
3. New route `POST /api/projects/{id}/structural-design` → builds the
   building-chain payload from project data (city → zone/terrain via their
   compliance config), calls structapi, stores result JSON + artifacts
   against the project revision.
4. Frontend: "Structural" tab per project — checks table (their ShadCN),
   inline SFD/BMD/P-M images, PDF download; regenerate button per revision.
5. BOQ merge: append structapi steel/concrete quantities to their existing
   BOQ engine output (line-item shape matched in Phase B).
6. Chat tool: register `design_structure` tool in their Vercel AI SDK chat →
   calls the same backend route (so chat and button share one path).
7. Deploy: structapi container → Cloud Run (same project/region as their
   backend), key in GCP Secret Manager; GitHub Action in THIS repo publishes
   the image on tag.

### Phase E — later / optional
- Artifacts to GCS + signed URLs (drop base64) when payloads exceed ~5 MB.
- DXF structural drawings (ezdxf — PlanForge already ships it) for framing
  plans matching their CAD export.
- Raft/pile foundations, staircase design, lintel/sunshade modules.
- Eve-session API keys if PlanForge adds a "talk to the structural engineer"
  NL mode instead of tool calls.

## 5. Sequencing & effort

| Phase | Where | Depends on | Size |
|---|---|---|---|
| A structapi | this repo | nothing (iscodes done) | M |
| B building chain | this repo | A (routes exist) — engineering can start in parallel | L |
| C hardening | this repo | A | S |
| D PlanForge changes | planforge repo | A+B deployed to a URL | M |
| E extensions | both | D live | — |

Standalone app is untouched by A-C (additive only); Docker Phase 7 of
SETUP.md remains the standalone runbook and structapi adds one more
`docker compose` service to it.

## 6. Risks
- **Grid extraction is the integration's hard part** — real floor plans are
  not regular grids. Mitigation: v1 supports regular + slightly irregular
  spacings only; PlanForge surfaces "structural grid needs review" when
  extraction confidence is low.
- **Load/height assumptions**: residential defaults hidden in the chain must
  be echoed back in `data.assumptions` so PlanForge can display them.
- **BIS verification disclaimer** must surface in PlanForge UI/PDFs, not just
  our envelope (their users are exactly the audience that might submit these
  for approval).
- **Contract drift**: contract tests in both repos against the same recorded
  fixtures (golden JSON) — update in lockstep.
