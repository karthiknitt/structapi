# StructAgent + structapi — Status

**Last updated:** 2026-07-28
**Release:** `v0.3.1` tagged, image published to GHCR
**Current workstream:** public release + documentation overhaul
(companion plan lives in the PlanForge repo:
`docs/plans/2026-07-27-public-release-docs-overhaul.md`)

## Live service

| Component | URL | Health |
|---|---|---|
| structapi | https://structapi-912195238699.us-central1.run.app | `/v1/health` → `{"status":"ok","api_version":"1","iscodes_version":"0.3.0"}` |

> **Deployment gap:** the live Cloud Run revision serves `iscodes` **0.3.0**. Tag `v0.3.1`
> (isolated-footing development-length sizing) is released and its image is published,
> but has not been rolled out. Roll it out before pointing anyone at the live endpoint
> for footing behaviour.

Consumed in production by [PlanForge](https://github.com/karthiknitt/planforge) over the
frozen v1 envelope. PlanForge vendors a pinned copy in `structapi-service/`, byte-diffed
against the tag by CI on every push and PR.

## Test state

- **94 tests, all passing** — verified locally 2026-07-28 (1m55s)
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
