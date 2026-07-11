import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  orchestratorModel,
} from "./lib/openrouter.js";

// The durable-execution "world" (Postgres-backed workflow runtime) is only
// enabled when WORKFLOW_POSTGRES_URL is set, so that `eve build` / `eve dev`
// work on machines without a running Postgres.
const usePostgresWorld = Boolean(process.env.WORKFLOW_POSTGRES_URL);

export default defineAgent({
  // Orchestrator model comes from config/models.json (web UI settings page)
  // -> OPENROUTER_MODEL env -> default. See agent/lib/openrouter.ts.
  model: orchestratorModel(),
  // Required for custom (non-AI-Gateway) LanguageModels: eve cannot look up
  // context-window metadata for OpenRouter model ids, so declare it here.
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  ...(usePostgresWorld
    ? {
        experimental: {
          workflow: { world: "@workflow/world-postgres" },
        },
        build: {
          externalDependencies: ["@workflow/world-postgres"],
        },
      }
    : {}),
});
