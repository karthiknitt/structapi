# Deploying the Telegram bot (production, self-hosted)

A private, owner-only Telegram front door to StructAgent (`agent/channels/telegram.ts`).
Only the Telegram user id in `TELEGRAM_OWNER_ID` gets a response; everyone
else is silently ignored. See [SETUP.md](../SETUP.md) for the local dev
setup this builds on — read that first if you haven't run StructAgent at
all yet.

This is a separate runbook from SETUP.md because it targets a public VM
with a real domain, not `localhost`.

## Why not just `pnpm dev` behind a tunnel

The specialist subagents (`loads`, `beam`, `column`, ...) each run their
calculations inside a Docker sandbox with deny-all egress (the
`vercel-labs/steve` pattern). eve's default deploy target is Vercel, but
Vercel serverless functions can't spin up that Docker sandbox — so this
app needs a host where Docker already runs, which your VM provides.

## 0. Prerequisites on the VM

- Docker + Docker Compose (already installed, per your setup).
- Node.js **24+** — eve 0.49 refuses to run on Node <24. Check with
  `node --version`; install from nodejs.org or your distro's NodeSource
  repo if needed.
- `corepack enable && corepack prepare pnpm@latest --activate`.
- A domain (or subdomain) with DNS already pointed at the VM's public IP —
  Telegram requires an HTTPS webhook URL, so you need real TLS.
- A reverse proxy that can get you automatic TLS. **Caddy** is the
  simplest (one binary, automatic Let's Encrypt certs); nginx + certbot
  works too if you already run nginx.

## 1. Get the code + install

```bash
git clone <this-repo> structagent && cd structagent
pnpm install
```

## 2. Environment

```bash
cp .env.example .env
```

Fill in, at minimum:
- `OPENROUTER_API_KEY` — required once you have credits; until then the
  default model (`openrouter/auto` in `config/models.json`) will fail
  model calls, same as local dev.
- `WORKFLOW_POSTGRES_URL`, `WORKFLOW_TARGET_WORLD`,
  `WORKFLOW_QUEUE_NAMESPACE=eve` — same as SETUP.md step 2.
- `TELEGRAM_BOT_TOKEN` — from @BotFather (see step 3).
- `TELEGRAM_BOT_USERNAME` — the bot's `@username`, without the `@`.
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` — any random string you generate
  yourself (`openssl rand -hex 32`); you'll pass the same value to
  Telegram's `setWebhook` in step 5.
- `TELEGRAM_OWNER_ID` — your numeric Telegram user id (from
  `@userinfobot`). This is personal — it's in `.env` only, never commit it.

`BETTER_AUTH_*` / `GOOGLE_*` are only needed if you're also running the
web UI (`pnpm web`); skip them for a Telegram-only deployment.

## 3. Create the bot with @BotFather

Message [@BotFather](https://t.me/BotFather) on Telegram:
1. `/newbot`, pick a display name and a `_bot`-suffixed username (some
   name ideas: **RCConcrete**, **IS456 Bot**, **BeamForge**).
2. `/setdescription` — e.g. "Private RCC structural design assistant (IS
   456:2000 and related IS codes). Owner-only."
3. Copy the bot token BotFather gives you into `TELEGRAM_BOT_TOKEN`.
4. Optional: `/setprivacy` → Disable, only if you ever plan to add the bot
   to a group (not needed for the owner-only private-chat setup here —
   `agent/channels/telegram.ts` ignores non-private chats regardless).

## 4. Database, sandbox image, build

Same as SETUP.md steps 4–5, run on the VM:

```bash
pnpm db:up
pnpm db:migrate
pnpm sandbox:build
pnpm sync
pnpm build
```

## 5. Run the eve host as a service

Run it directly on the VM host (not containerized — see "Why not just
`pnpm dev`" above; the app itself doesn't need to be in Docker, only the
sandbox does, and `pnpm sandbox:build` already handles that).

Example systemd unit (`/etc/systemd/system/structagent.service`):

```ini
[Unit]
Description=StructAgent eve host
After=network.target docker.service

[Service]
Type=simple
WorkingDirectory=/opt/structagent
EnvironmentFile=/opt/structagent/.env
ExecStart=/usr/bin/pnpm start
Restart=on-failure
User=structagent

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now structagent
```

`pnpm start` (`eve start`) binds to a local port (2000 by default) — keep
it bound to `127.0.0.1` and let the reverse proxy be the only public
listener.

## 6. Reverse proxy with automatic TLS (Caddy)

```caddyfile
# /etc/caddy/Caddyfile
your-domain.example.com {
    reverse_proxy 127.0.0.1:2000
}
```

```bash
sudo systemctl reload caddy
```

Caddy issues and renews the Let's Encrypt certificate automatically. If
you'd rather expose only the Telegram route publicly, replace the single
`reverse_proxy` line with a path-matched one:

```caddyfile
your-domain.example.com {
    handle /eve/v1/telegram* {
        reverse_proxy 127.0.0.1:2000
    }
    respond 404
}
```

## 7. Register the Telegram webhook

Once the service is up and reachable at `https://your-domain.example.com`:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://your-domain.example.com/eve/v1/telegram",
       "secret_token":"'"$TELEGRAM_WEBHOOK_SECRET_TOKEN"'",
       "allowed_updates":["message"]}'
```

Expect `{"ok":true,"result":true,...}`. Verify with:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
```

## 8. Smoke test

1. Message the bot from your own Telegram account (must match
   `TELEGRAM_OWNER_ID`): *"Design an RCC simply supported beam: span 6 m,
   live load 15 kN/m, M25, Fe500."* Expect one or more text replies as the
   orchestrator delegates to the `loads`/`beam` specialists, followed by a
   PDF document landing in the chat once the design report is exported.
2. Ask something off-topic ("what's the weather today?") — expect a short
   refusal, no design attempt (see the scope guardrail in
   `agent/instructions.md`).
3. Have a second Telegram account message the bot — expect either silence
   or a one-line "this is a private bot" reply, and no design output.
4. `journalctl -u structagent -f` to watch logs live while testing.

## Troubleshooting

- **No response at all** — check `getWebhookInfo` for `last_error_message`;
  confirm the systemd service is running (`systemctl status structagent`)
  and Caddy is proxying correctly (`curl -I https://your-domain...`).
- **`eve requires Node.js >=24`** — the VM's Node is too old; install
  Node 24+ and re-run `pnpm install`/`pnpm build`.
- **PDF never arrives, only text** — check the service logs for
  `[telegram] sendDocument failed`; usually a bad `TELEGRAM_BOT_TOKEN` or
  a file-size/permissions issue under `outputs/`.
- **Other Telegram users get a real reply instead of the refusal** —
  double check `TELEGRAM_OWNER_ID` is set in the VM's `.env` (not just
  `.env.example`) and that the systemd unit's `EnvironmentFile` actually
  points at it.
- Everything else (Postgres, sandbox image, model settings) — see
  SETUP.md's troubleshooting section, which still applies.
