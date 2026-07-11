# StructAgent — IS-Code Structural Design Agent

A multi-agent RCC structural design system built on [Eve](https://eve.dev) (Vercel's durable agent framework), self-hosted per the [vercel-labs/steve](https://github.com/vercel-labs/steve) pattern: Postgres durability, Docker sandboxes with deny-all egress, TUI + web UI, models via OpenRouter.

An **orchestrator** agent delegates to **specialist subagents** — loads, footing, beam, column, slab, tank, sump, mix design — each carrying Limit State Method skills (IS-code clause-referenced procedures) backed by the pure-Python `iscodes` calculation library (numpy + matplotlib). Outputs: SFD/BMD PNGs (Indian convention — BMD on tension side, sagging positive), P-M interaction diagrams, pressure diagrams, and clause-referenced design reports.

## Codes implemented
IS 456:2000 (LSM) · SP 16 · IS 875 Parts 1-3 (incl. wind 2015) · IS 1893 Part 1:2016 · IS 13920:2016 · IS 3370 Parts 1-4 (2021) · IS 10262:2019 · IS 6403:1981

> **Disclaimer:** Code table values are transcribed from research; verify against official BIS copies before professional use. Not a substitute for a licensed structural engineer.

## Status
Under construction. Docker-dependent phases (Postgres durability runtime, sandboxed execution, e2e) are deferred until Docker Desktop is installed — see `plans` / task list.
