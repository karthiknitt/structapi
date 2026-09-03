# StructAgent + structapi — Status

**Last updated:** 2026-09-03
**Release:** `v0.4.0` tagged, image published to GHCR (`latest` + `0.4.0`), rolled out to
Cloud Run
**Current workstream:** G+1 practice alignment sprint (`docs/plans/2026-08-04-g1-practice-alignment.md`,
execution plan `docs/plans/2026-08-05-g1-practice-alignment-execution.md`) — **complete**,
all 24 tasks (PA-1..PD-6, Phases 1-4) merged to `main` and released as v0.4.0.

## Live service

| Component | URL | Health |
|---|---|---|
| structapi | https://structapi-912195238699.us-central1.run.app | `/v1/health` → `{"status":"ok","api_version":"1","iscodes_version":"0.4.0"}` |

No deployment gap — the live Cloud Run revision matches the tagged/vendored release.

Consumed in production by [PlanForge](https://github.com/karthiknitt/planforge) over the
frozen v1 envelope. PlanForge vendors a pinned copy in `structapi-service/`, byte-diffed
against the tag by CI on every push and PR. Pinned at **v0.4.0** (`structapi-service/VENDORED.md`).

## Test state

- **328 tests, all passing** — verified locally 2026-09-03 (5m22s)
- CI green on `main`; contract freeze enforced by
  `python/tests/fixtures/beam_envelope_v1.json` (CI fails on any v1 envelope drift)

Run locally:

```bash
uv venv .venv && uv pip install --python .venv -r python/requirements-api.txt
cd python && PYTHONPATH=. ../.venv/bin/python -m pytest tests -q
```

The packages live under `python/`, so `PYTHONPATH=.` from that directory is required —
without it collection fails with `ModuleNotFoundError: No module named 'iscodes'`.

## Codes implemented

IS 456:2000 (LSM) · SP 16 · IS 875 Parts 1–3 (wind 2015) · IS 1893 Part 1:2016 ·
IS 13920:2016 · IS 3370 Parts 1–4 (2021) · IS 10262:2019 · IS 6403:1981

## Public release readiness

| Item | State |
|---|---|
| MIT LICENSE | ✅ added 2026-07-27 |
| Engineering disclaimer | ✅ preliminary-design-only wording in README |
| Secret scan | ✅ `gitleaks` over full history (22 commits) — no real credentials; 1 false positive allowlisted |
| Env-file ignores | ✅ `.env.production` / `.env.staging` / `.env.*.local` added |
| CI | ✅ green (unaffected by the Actions quota block hitting PlanForge) |
| Visibility | ⏳ still private — publishing is human-gated |
