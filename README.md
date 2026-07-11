# StructAgent — IS-Code Structural Design Agent

A multi-agent RCC structural design system built on [Eve](https://eve.dev) (Vercel's durable agent framework), self-hosted per the [vercel-labs/steve](https://github.com/vercel-labs/steve) pattern: Postgres durability, Docker sandboxes with deny-all egress, TUI + web UI, models via OpenRouter.

An **orchestrator** agent delegates to **8 specialist subagents** — `loads`, `beam`, `column`, `footing`, `slab`, `tank`, `sump`, `mixdesign` — each carrying a Limit State Method skill (IS-code clause-referenced procedure with runnable snippets) backed by the pure-Python **`iscodes`** calculation library (numpy + matplotlib, 60 worked-example tests). Outputs: SFD/BMD PNGs (Indian convention — BMD on tension side, sagging positive), P-M interaction diagrams, pressure diagrams, and clause-referenced design reports.

## Codes implemented
IS 456:2000 (LSM) · SP 16 · IS 875 Parts 1-3 (wind 2015) · IS 1893 Part 1:2016 · IS 13920:2016 · IS 3370 Parts 1-4 (2021) · IS 10262:2019 · IS 6403:1981

## Layout
```
agent/                  orchestrator (instructions.md, agent.ts — OpenRouter)
agent/subagents/<id>/   specialist: agent.ts, instructions.md, skills/, tools/, sandbox/
python/iscodes/         calculation library (single source; synced into sandboxes)
python/tests/           pytest worked-example suite
scripts/sync-workspace.mjs   sync iscodes -> every sandbox workspace
sandbox-image/          Docker image: eve base + numpy/matplotlib (deny-all egress)
docker-compose.yml      postgres:16 for the durable workflow world (port 5544)
app/                    Next.js web UI (chat + inline PNG artifacts)
outputs/                PNGs exported from sandboxes land here per session
```

## Running (Docker-independent parts)
```bash
pnpm install
cp .env.example .env         # set OPENROUTER_API_KEY (+ OPENROUTER_MODEL)
node scripts/sync-workspace.mjs
pnpm tui                     # Eve TUI on port 2000
pnpm web                     # Next.js UI on port 3001 (separate terminal)
pnpm exec pytest -q python/tests   # or: cd python && python -m pytest
```

## Docker phase (pending Docker Desktop install)
```bash
pnpm db:up                   # postgres:16 on :5544
pnpm db:migrate              # workflow-postgres-setup
docker build -t structagent-sandbox:latest sandbox-image/
pnpm dev                     # durable host (WORKFLOW_POSTGRES_URL enables the world)
```
Until Docker exists, `eve build` / TUI startup work, but any tool call that
needs the sandbox will fail — the specialists' `run_python` requires the
`structagent-sandbox:latest` image and Docker Engine.

## Environment variables (.env)
`OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `anthropic/claude-sonnet-4.5`),
`OPENROUTER_SUBAGENT_MODEL` (optional cheaper model for specialists),
`WORKFLOW_POSTGRES_URL`, `WORKFLOW_QUEUE_NAMESPACE=eve` (must stay `eve`).

> **Disclaimer:** Code table values are transcribed from the standards during
> research; verify against official BIS copies before professional use. This
> tool is not a substitute for a licensed structural engineer.
