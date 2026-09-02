import { defineMemory } from "eve/memory";
import { byPrincipal } from "eve/memory/scope";
import { fileMemory } from "eve/memory/file";
import { pgFileMemoryBackend } from "../lib/memory-pg-backend.js";

// Owner-only bot — byPrincipal keys this to the single authenticated
// Telegram user (TELEGRAM_OWNER_ID), so it needs no tenant/channel scoping.
// fileMemory() has no default backend for a self-hosted (non-Vercel,
// non-`eve dev`) deployment, so it's given an explicit Postgres-backed one —
// see agent/lib/memory-pg-backend.ts.
export default defineMemory({
  description:
    "Stable facts about the caller across sessions: their name, and any " +
    "standing preferences or project context they've stated (e.g. default " +
    "grades, location, exposure class). Not scratch working data for the " +
    "current design — that lives in the conversation itself.",
  provider: fileMemory({ backend: pgFileMemoryBackend() }),
  scope: byPrincipal,
});
