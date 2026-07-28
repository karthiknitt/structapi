# StructAgent + structapi — Handover

Short working-state notes. Longer status in [Status.md](Status.md); architecture in
[docs/PLANFORGE-INTEGRATION.md](docs/PLANFORGE-INTEGRATION.md); full app runbook in
[SETUP.md](SETUP.md).

## Current branch

`chore/public-release-prep` — public release + documentation work. `main` is at the
`v0.3.1` footing fix.

## In flight

Done: MIT LICENSE, engineering disclaimer, gitleaks scan + allowlist, env-ignore
hardening, README rewritten to lead with the agent architecture, integration doc marked
shipped with verified live state.

Not done: per-directory `CLAUDE.md` files for `python/iscodes/` and `agent/`, architecture
SVGs (need approval before committing).

**Decided against:** publishing runnable API examples against the live service. Reviewers
evaluate through the PlanForge website instead. Copy-pasteable requests would invite
unmetered traffic on a `$0`-tier Cloud Run service and require issuing a working API key.
The v1 envelope shape stays documented in §3 of `docs/PLANFORGE-INTEGRATION.md`, and
`/docs` on a running instance serves the full OpenAPI reference for self-hosters.

**Publishing is human-gated.** Do not change repo visibility without explicit approval —
it is irreversible in practice.

## Gotchas

- **Tests need `PYTHONPATH`.** Packages live under `python/`; run pytest from that
  directory with `PYTHONPATH=.` or collection fails with
  `ModuleNotFoundError: No module named 'iscodes'`.
- **The live service lags the tag.** Cloud Run serves iscodes 0.3.0; `v0.3.1` is
  published but not rolled out.
- **`WORKFLOW_QUEUE_NAMESPACE` must be exactly `eve`** — the queue prefix match depends
  on it.
- **Never mutate v1 envelope fields.** Breaking changes go to `/v2`. The golden fixture
  `python/tests/fixtures/beam_envelope_v1.json` fails CI on drift, and PlanForge's
  vendored copy is byte-diffed against the pinned tag.
- **PlanForge vendors this repo.** Changes here that alter the envelope require a
  re-vendor on the PlanForge side.

## Companion repo

Consumer: [karthiknitt/planforge](https://github.com/karthiknitt/planforge), branch
`chore/public-release-prep`, worktree `~/projects/PlanForge-release`.
