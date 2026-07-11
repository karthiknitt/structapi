import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createOpenAI } from "@ai-sdk/openai";

// Shared OpenRouter provider for the orchestrator and all subagents.
//
// Model selection precedence (checked at agent-host startup):
//   1. config/models.json  — written by the web UI settings page
//   2. OPENROUTER_MODEL / OPENROUTER_SUBAGENT_MODEL env vars
//   3. built-in default
// Changing models via the settings page requires restarting the agent host
// (`pnpm dev` / `pnpm tui`) — eve binds models at startup.
const openrouter = createOpenAI({
  baseURL: "https://openrouter.ai/api/v1",
  apiKey: process.env.OPENROUTER_API_KEY ?? "",
});

const FALLBACK_MODEL = "anthropic/claude-sonnet-5";

function readModelConfig(): { orchestrator?: string; subagents?: string } {
  try {
    const raw = readFileSync(
      join(process.cwd(), "config", "models.json"),
      "utf-8",
    );
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

const fileConfig = readModelConfig();

export const DEFAULT_MODEL =
  fileConfig.orchestrator ?? process.env.OPENROUTER_MODEL ?? FALLBACK_MODEL;

export const SUBAGENT_MODEL =
  fileConfig.subagents ??
  process.env.OPENROUTER_SUBAGENT_MODEL ??
  DEFAULT_MODEL;

export function orchestratorModel() {
  return openrouter.chat(DEFAULT_MODEL);
}

export function subagentModel() {
  return openrouter.chat(SUBAGENT_MODEL);
}

// eve requires explicit context-window metadata for non-gateway models.
// 200k is a safe lower bound across the frontier models offered on OpenRouter.
export const CONTEXT_WINDOW_TOKENS = 200_000;
