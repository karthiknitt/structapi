# agent — Eve multi-agent orchestrator + 8 specialist subagents

Vercel's durable agent framework (Eve) orchestrates structural design via 8 specialist subagents (`loads`, `beam`, `column`, `footing`, `slab`, `tank`, `sump`, `mixdesign`). Each subagent is a Docker sandbox (deny-all egress) with agent.ts, instructions.md, skills/, tools/, sandbox/. Single source of truth: python/iscodes — synced into workspace copies by `scripts/sync-workspace.mjs`.

## Rules

- **Sandbox copies are generated and gitignored.** Never edit `agent/sandbox/workspace/iscodes/` or `agent/subagents/*/sandbox/workspace/iscodes/` directly — they're overwritten on `pnpm sync`. Edit `python/iscodes/` and re-run the sync.
- **Models via OpenRouter.** `config/models.json` (written by `/settings` UI) overrides `OPENROUTER_MODEL` env var for orchestrator and `OPENROUTER_SUBAGENT_MODEL` for the 8 specialists. Both default to `anthropic/claude-sonnet-5` if unset/absent.
- **Queue namespace must be `eve`.** `WORKFLOW_QUEUE_NAMESPACE` controls the durable-workflow queue prefix; it must be exactly `eve` or the queue-prefix match fails and runs hang.

## Gotchas

- Agent instructions (`instructions.md`) encode the orchestration contract — sequence (loads first, then vertical, then column, then footing), batching (subagents share nothing; pass all context explicitly), and seismic zone routing (IS 13920 for zones III-V). Keep them in sync with `agent/instructions.md`. It also carries the RCC-only scope guardrail (refuse anything else) shared by every channel.
- Cold starts: First call after idle adds ~5–10s (structapi) or longer (Eve state load). Agent sandbox spins up from image on first use per session.
- **eve requires Node >=24** (enforced hard since the 0.49.0 upgrade) — `eve dev`/`build`/`start` refuse to run on older Node.
- **Telegram channel** (`agent/channels/telegram.ts`) is a private, allowlisted bot: `onMessage` drops anything not from a private chat with `from.id` in `TELEGRAM_ALLOWED_USER_IDS` (comma-separated; falls back to the single `TELEGRAM_OWNER_ID`). It doesn't touch text delivery (eve's default `message.completed` → `sendMessage` handler is left as-is); it adds a `turn.completed` handler that scans `outputs/**/*.{pdf,png}` for files written since the turn started and pushes each into the chat via a hand-rolled multipart `sendDocument` call (the typed Telegram API helpers only support JSON bodies, not file upload). Each allowlisted user's `profile` memory (`agent/memory/profile.ts`) is scoped per-user via `byPrincipal`, so names/preferences never leak across users. See `docs/DEPLOY-TELEGRAM.md` for the production runbook.
