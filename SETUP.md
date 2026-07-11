# StructAgent — new machine setup (Windows + WSL2 + Docker Desktop)

Complete runbook to go from `git clone` to a working authenticated app.
Prereqs on the target machine: Docker Desktop (WSL2 backend, running),
Node.js 24+, Git. Everything else is set up below.

## 1. Clone + install
```bash
git clone <this-repo> structagent && cd structagent
corepack enable && corepack prepare pnpm@latest --activate
pnpm install
```

Python (for running the test suite on the host — optional but recommended):
```bash
python -m pip install numpy matplotlib pytest
pnpm test:py        # expect: 60 passed
```

## 2. Environment
```bash
cp .env.example .env
```
Fill in:
- `OPENROUTER_API_KEY` — from openrouter.ai/keys.
- `BETTER_AUTH_SECRET` — `openssl rand -base64 32` (Git Bash) or
  `npx @better-auth/cli secret`.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — see step 3.
- Leave `WORKFLOW_*` and `BETTER_AUTH_URL` at defaults for local use.

## 3. Google OAuth client (one-time, console.cloud.google.com)
1. Create/select a project → *APIs & Services → Credentials → Create
   Credentials → OAuth client ID → Web application*.
2. Authorized JavaScript origin: `http://localhost:3001`
3. Authorized redirect URI: `http://localhost:3001/api/auth/callback/google`
4. Copy client ID/secret into `.env`. (Configure the OAuth consent screen if
   prompted; External + test users is fine for a demo.)

## 4. Database (Postgres 16 container — serves BOTH eve durability and auth)
```bash
pnpm db:up          # postgres:16 on host port 5544 (user/pass/db = world)
pnpm db:migrate     # workflow durability schema (workflow-postgres-setup)
pnpm auth:migrate   # BetterAuth tables (user/session/account/verification)
pnpm seed:users     # create the test users below
```

**Seeded test users** (email + password sign-in; no email verification):

| Email | Password |
|---|---|
| umashankar@simplicontract.com | StructAgent@2026 |
| engineer@structagent.test | Engineer@123 |
| viewer@structagent.test | Viewer@123 |

Google OAuth (step 3) is optional if you sign in with these. New accounts
can also be created from the sign-in page ("Create one").

## 5. Sandbox image (the specialists' Python runtime; deny-all egress)
```bash
pnpm sandbox:build  # builds structagent-sandbox:latest from sandbox-image/
pnpm sync           # sync python/iscodes into every sandbox workspace
```

## 6. Run
```bash
# Terminal 1 — the durable agent host (port 2000)
pnpm dev            # or `pnpm tui` for the interactive terminal UI

# Terminal 2 — the authenticated web UI (port 3001)
pnpm web
```
Open http://localhost:3001 → redirected to /signin → Google → chat.

Everything under `/`, `/eve/*` (agent sessions), and `/outputs/*` (exported
PNGs) requires a signed-in session. The eve host on port 2000 itself is
unauthenticated (steve pattern, `auth: none()`) — don't expose 2000 beyond
localhost; only the Next app (3001) should be reachable.

## 7. Choosing models (OpenRouter)
Open **http://localhost:3001/settings** (authenticated). Two pickers —
**Orchestrator** (main agent) and **Specialist subagents** (all 8) — listing
the live OpenRouter catalog (fetched from openrouter.ai/api/v1/models, with a
curated fallback). Saving writes `config/models.json`; **restart the agent
host** (`pnpm dev` / `pnpm tui`) to apply. Precedence: config/models.json →
`OPENROUTER_MODEL`/`OPENROUTER_SUBAGENT_MODEL` env → default
(anthropic/claude-sonnet-5).

## 8. Smoke tests
1. In the web UI: *"Design an RCC simply supported beam: span 6 m, live load
   15 kN/m, M25, Fe500, moderate exposure."* → expect clause-referenced
   checks and an inline SFD/BMD PNG (also lands in `outputs/<session>/`).
2. Full chain: *"G+3 office in Chennai, zone III, terrain category 3, medium
   soil, SBC 200 kPa — compute loads and design an interior column and its
   isolated footing."* → loads → column (P-M diagram PNG) → footing
   (pressure diagram PNG).
3. Mix design: *"IS 10262 mix design for M30, severe exposure, 20 mm
   aggregate, 100 mm slump, with superplasticizer."*
4. Durability: kill the `pnpm dev` process mid-design, restart it — the
   session resumes (look for `[world-postgres] Re-enqueued ... on startup`).
5. `pnpm observe` — inspect durable runs.

## Troubleshooting
- **400 "Unhandled queue"** → `WORKFLOW_QUEUE_NAMESPACE` must be exactly `eve`.
- **Runs break mid-flight after a dependency change** → `@workflow/world-postgres`
  must stay pinned to `5.0.0-beta.19` (matches eve 0.15.0's workflow core).
- **`run_python` fails: image not found** → step 5 wasn't run on this machine.
- **`ModuleNotFoundError: iscodes` in the sandbox** → run `pnpm sync`.
- **Auth redirect loop** → `BETTER_AUTH_URL` must match the origin you open
  (http://localhost:3001) and the Google redirect URI must match exactly.
- **eve build error "context window metadata"** → keep
  `modelContextWindowTokens` set in agent.ts files (required for non-gateway
  models like OpenRouter's).
