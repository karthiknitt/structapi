# StructAgent + structapi — IS-Code Structural Design

> A multi-agent structural engineering system: an LLM orchestrator that routes to 8
> specialist subagents, over a deterministic IS-code calculation engine the agents
> cannot hallucinate around.

**[Architecture](docs/PLANFORGE-INTEGRATION.md)** · **[Consumer app (live)](https://planforge-mauve.vercel.app)** · **[Consumer repo](https://github.com/karthiknitt/planforge)**

![StructAgent architecture: two front doors — an Eve agent layer for humans and structapi for service callers — over one deterministic python/iscodes calculation core](docs/assets/architecture.svg)

**The design principle:** the agents decide *what* to design and in what order; the
`iscodes` library decides *what the numbers are*. No LLM sits in the calculation path, so
results are reproducible and every check traces to an IS clause. The v1 response envelope
is frozen by a golden fixture (`python/tests/fixtures/beam_envelope_v1.json`) and CI fails
on any drift.

Try the live engine — no clone required:

```bash
curl -s https://structapi-912195238699.us-central1.run.app/v1/health
# {"status":"ok","api_version":"1","iscodes_version":"0.3.0"}
```

Two runnable products in one repo, sharing the **`iscodes`** IS-code engine:

1. **StructAgent** — a multi-agent NL design app built on [Eve](https://eve.dev) (Vercel's durable agent framework), self-hosted per the [vercel-labs/steve](https://github.com/vercel-labs/steve) pattern: Postgres durability, Docker sandboxes with deny-all egress, TUI + authenticated web UI, models via OpenRouter.
2. **structapi** — a deterministic FastAPI REST service over the same engine for backend callers (used by [PlanForge](https://github.com/karthiknitt/planforge); live on Cloud Run). Current release: **v0.2.0** (envelope stays `api_version: "1"` — v0.2.0 is additive-only: `data.violations[]` + `data.grid_lines` on `/v1/design/building`).

An **orchestrator** agent delegates to **8 specialist subagents** — `loads`, `beam`, `column`, `footing`, `slab`, `tank`, `sump`, `mixdesign` — each carrying a Limit State Method skill (clause-referenced procedure with runnable snippets) backed by the pure-Python `iscodes` library (numpy + matplotlib, 94 tests). Outputs: SFD/BMD PNGs (Indian convention — BMD on tension side, sagging positive), P-M interaction diagrams, pressure diagrams, clause-referenced PDF/markdown reports, and BOQ-shaped quantities.

## Codes implemented
IS 456:2000 (LSM) · SP 16 · IS 875 Parts 1-3 (wind 2015) · IS 1893 Part 1:2016 · IS 13920:2016 · IS 3370 Parts 1-4 (2021) · IS 10262:2019 · IS 6403:1981

## Documentation index
| Doc | Contents |
|---|---|
| [SETUP.md](SETUP.md) | **Complete new-machine runbook** for the StructAgent app: prerequisites, copy/clone, env, Google OAuth (optional), DB + auth migrations, seeded test users, sandbox image, model settings, smoke tests, troubleshooting |
| [docs/DEPLOY-TELEGRAM.md](docs/DEPLOY-TELEGRAM.md) | Self-hosted production runbook for the private, owner-only Telegram bot channel (`agent/channels/telegram.ts`) — VM prerequisites, @BotFather setup, reverse proxy + TLS, webhook registration |
| [docs/PLANFORGE-INTEGRATION.md](docs/PLANFORGE-INTEGRATION.md) | Architecture decision + phased plan for the PlanForge integration; the frozen structapi v1 envelope contract |
| `/docs` on a running structapi | Auto-generated OpenAPI reference for every endpoint |
| [AGENTS.md](AGENTS.md) / agent `instructions.md` files | Eve agent behavior; per-specialist rules |
| `planforge:structapi-service/VENDORED.md` | Why/how structapi is vendored into PlanForge for Cloud Run deploys (WIF repo-lock) + refresh procedure |
| `python/tests/fixtures/beam_envelope_v1.json` | Contract-freeze golden fixture — CI fails on any v1 envelope drift |

## Layout
```
agent/                  orchestrator (instructions.md, agent.ts — OpenRouter)
agent/subagents/<id>/   specialist: agent.ts, instructions.md, skills/, tools/, sandbox/
python/iscodes/         calculation library (single source; synced into sandboxes)
python/structapi/       FastAPI REST facade (v1 envelope, API-key, rate limits)
python/tests/           pytest suite (worked examples + API contract tests)
scripts/                sync-workspace.mjs, seed-users.ts
sandbox-image/          agent sandbox image: eve base + numpy/matplotlib/reportlab
structapi.Dockerfile    slim service image for structapi (Cloud Run-ready)
docker-compose.yml      postgres:16 (port 5544) + structapi service
app/                    Next.js web UI (chat, /settings model picker, /outputs)
.github/workflows/      ci.yml (3 jobs) + release-image.yml (GHCR on tags)
```

## Environment variables (complete reference)

### StructAgent app (`.env`, template in `.env.example`)
| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | ✅ | Model access for orchestrator + subagents (openrouter.ai/keys) |
| `OPENROUTER_MODEL` | — | Orchestrator model (default `anthropic/claude-sonnet-5`; overridden by `config/models.json` from /settings) |
| `OPENROUTER_SUBAGENT_MODEL` | — | Cheaper model for the 8 specialists (defaults to orchestrator model) |
| `WORKFLOW_POSTGRES_URL` | ✅ for durability | `postgres://world:world@localhost:5544/world`; unset ⇒ builds work but no durable world |
| `WORKFLOW_TARGET_WORLD` | — | `@workflow/world-postgres` (workflow CLI default backend) |
| `WORKFLOW_QUEUE_NAMESPACE` | ✅ | **Must be exactly `eve`** (queue prefix match) |
| `BETTER_AUTH_SECRET` | ✅ | Session signing (`openssl rand -base64 32`) |
| `BETTER_AUTH_URL` | — | Origin of the web UI (default `http://localhost:3001`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | Google OAuth (optional — email/password + seeded users work without) |
| `AUTH_DATABASE_URL` | — | Separate auth DB (defaults to `WORKFLOW_POSTGRES_URL`) |

### structapi service
| Variable | Required | Purpose |
|---|---|---|
| `STRUCTAPI_KEYS` | ✅ in prod | Comma-separated API keys; **unset = OPEN dev mode** (logged loudly) |
| `STRUCTAPI_RATE_LIMIT` | — | Requests/min per key (default 60; 0 disables) |
| `PORT` | — | Listen port (default 8080; Cloud Run sets it) |

### PlanForge side (GitHub secrets/vars on `karthiknitt/planforge`)
| Name | Kind | Purpose |
|---|---|---|
| `STRUCTURAL_API_URL` | secret | structapi base URL (`https://structapi-…-uc.a.run.app`) |
| `STRUCTURAL_API_KEY` | secret | Must equal one entry of the service's `STRUCTAPI_KEYS` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` / `GCP_SERVICE_ACCOUNT` | secret | Existing WIF deploy auth (repo-locked to planforge) |
| `GCP_PROJECT_ID` / `GCP_REGION` | variable | `thermal-well-451906-b0` / `us-central1` |

## Running StructAgent (full runbook: SETUP.md)
```bash
pnpm install && cp .env.example .env         # fill the ✅ vars above
pnpm db:up && pnpm db:migrate && pnpm auth:migrate && pnpm seed:users
pnpm sandbox:build && pnpm sync
pnpm dev     # durable agent host :2000 (or `pnpm tui`)
pnpm web     # authenticated web UI :3001
```

## Running structapi (independent of the agent app — no Node/Eve/Postgres)
```bash
pip install -r python/requirements-api.txt
pnpm api:dev                      # dev: uvicorn :8080
# prod: docker build -f structapi.Dockerfile -t structapi . && docker run -p 8080:8080 -e STRUCTAPI_KEYS=<key> structapi
curl -s localhost:8080/v1/health
```
Headline endpoint `POST /v1/design/building`: column grid + storeys + location in → full structural design, clause-referenced checks, BOQ quantities, consolidated PDF out. Tagged releases publish `ghcr.io/karthiknitt/structapi:<version>` via CI.

## Where data lives
| Data | Location |
|---|---|
| Agent definitions, skills, tools | `agent/**` (code, in git) |
| Conversations, durable runs, queues | Postgres container (`workflow` schema), volume `structagent-pgdata` |
| Users, sessions, OAuth accounts | Same Postgres (BetterAuth tables) |
| Sandbox scratch (`/workspace`) | Ephemeral per-session Docker containers |
| Exported artifacts (PNG/PDF) | `outputs/<sessionId>/` on host, served at `/outputs/*` (auth) |
| Model selection | `config/models.json` (written by /settings; host restart applies) |
| structapi | Stateless — artifacts returned inline (base64) |

## Auth
Web UI gated by **BetterAuth** — email/password (no verification; `pnpm seed:users` creates test accounts, see SETUP.md) and optional Google OAuth. `/`, `/eve/*`, `/outputs/*`, `/api/models` all require a session (Next 16 `proxy.ts` + server-side checks). structapi uses `x-api-key`.

## Known risks & watch items (radar)

**Engineering / correctness**
- **BIS verification is outstanding**: long code tables (IS 456 Table 26, IS 3370-4 coefficients, IS 10262 tables, IS 875-3 k2) were transcribed during research. A licensed engineer must verify them against official BIS copies before any professional/approval use. Every report carries this disclaimer — keep it in downstream UIs and PDFs.
- **v1 building-chain simplifications** (echoed in every result's `assumptions`): beams designed simply-supported on the worst span; portal-frame lateral distribution; steel mass from Ast×length×1.10. Conservative, not optimal.
- **Grid extraction (PlanForge)** handles regular/near-regular grids only; irregular layouts set `confident: false` — surface that flag, never hide it. Tuning knob: `CLUSTER_TOL` in `structural_grid.py`.

**Operational**
- **Beta-version tower**: eve 0.15.0 + `@workflow/world-postgres` 5.0.0-beta.19 + ai 7 beta + Next 16. Do not float versions; the pins are deliberate (`WORKFLOW_QUEUE_NAMESPACE=eve` and the world-postgres pin are hard runtime requirements).
- **Vendored-copy drift** (mitigated): Cloud Run deploys build from `planforge/structapi-service/` (WIF is repo-locked), vendored at v0.1.0 — procedure in `VENDORED.md`. Planforge's `verify-structapi-vendor.yml` now byte-diffs the vendored copy against the pinned tag on every push/PR (fails CI on drift) plus a weekly freshness issue if a newer structapi tag exists. Requires the one-time `STRUCTAPI_SYNC_TOKEN` secret (fine-grained PAT, contents:read on structapi) — until set, the check soft-skips with a warning.
- **Rate-limit state is per-instance** (in-process token bucket). With Cloud Run autoscaling the effective limit multiplies by instance count.
- **Cold starts**: structapi runs `min-instances=0`; first call after idle adds ~5-10 s. Bump to 1 if users notice.
- **Open registration** on the StructAgent web UI (email/password, no verification): anyone who reaches port 3001 can register and consume OpenRouter credits. Gate registration before exposing beyond localhost/LAN. Never expose the eve host (port 2000, unauthenticated) beyond localhost.
- **Seeded demo passwords are in this repo** (scripts/seed-users.ts, SETUP.md) — repo must stay private until they're rotated/externalized.
- **Key rotation**: the structapi API key lives only in the planforge secret + Cloud Run env. To rotate: `openssl rand -hex 32`, set both, re-dispatch both deploy workflows.
- **`outputs/` grows unbounded** (per-session PNGs/PDFs); add a purge job once usage is regular.
- **Contract freeze**: `beam_envelope_v1.json` fails CI on any v1 envelope drift — breaking changes go to `/v2`. Copy the fixture into PlanForge's test suite so both repos fail on the same drift.
- **Untested seam**: the OpenRouter wiring in the agent app compiles/builds but has never made a live call (no key on the build machine). First `eve dev` session with a real key is the proof; fallback is `@openrouter/ai-sdk-provider`.

## Recommended next features
- **Structural DXF sheets** — framing plans via ezdxf (PlanForge already ships it), matching their CAD export layers.
- **BOQ merge in PlanForge** — append structapi steel/concrete quantities into their existing BOQ engine line items (shapes already align; small follow-up PR).
- **Foundations beyond isolated/combined footings** — raft (IS 2950), piles, plus staircases and lintel/sunshade modules.
- **Table 12/13 continuity in the building chain** — replace the worst-span-SS beam envelope with proper continuous-beam design; then frame analysis (stiffness method) for irregular grids.
- **GCS artifact URLs** (structapi v2) — replace inline base64 once payloads exceed ~5 MB; enables artifact retention/history.
- **Per-session model selection** via eve's `defineDynamic` — model switching without restarting the agent host.
- **Eve-session API keys** — expose the NL agent to services (BetterAuth `apiKey` plugin on the Next proxy) if PlanForge wants a "talk to the structural engineer" mode beyond tool calls.
- **rcdesign cross-validation in CI** — pin `rcdesign` as a dev dependency and assert beam Mu / column P-M agreement as an independent oracle.
- **IS 875-2:2023 imposed-load revision** — `tables.py` is versioned per code edition; adopting the 2023 values is a data swap.

## Licence & disclaimer

Licensed MIT — see [LICENSE](LICENSE).

> **Disclaimer:** Code table values are transcribed from the standards during
> research; verify against official BIS copies before professional use. Output is
> intended for **preliminary design and estimation only** and is not a substitute for
> review, stamping, and sign-off by a licensed structural engineer. Do not use it as
> the sole basis for construction.
