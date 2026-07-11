import { defineAgent } from "eve";
import { createOpenAI } from "@ai-sdk/openai";

// OpenRouter wired as an OpenAI-compatible provider (AI SDK v6/v7 style).
const openrouter = createOpenAI({
  baseURL: "https://openrouter.ai/api/v1",
  apiKey: process.env.OPENROUTER_API_KEY ?? "",
});

// The durable-execution "world" (Postgres-backed workflow runtime) is only
// enabled when WORKFLOW_POSTGRES_URL is set, so that `eve build` / `eve dev`
// work on machines without a running Postgres (no Docker locally).
// Set WORKFLOW_POSTGRES_URL (see .env.example) to enable durability.
const usePostgresWorld = Boolean(process.env.WORKFLOW_POSTGRES_URL);

export default defineAgent({
  model: openrouter.chat(
    process.env.OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4.5",
  ),
  // Required for custom (non-AI-Gateway) LanguageModels: eve cannot look up
  // context-window metadata for OpenRouter model ids, so declare it here.
  // 200k tokens = Claude Sonnet 4.5's context window.
  modelContextWindowTokens: 200_000,
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
