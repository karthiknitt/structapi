import { createOpenAI } from "@ai-sdk/openai";

// Shared OpenRouter provider for the orchestrator and all subagents.
// OPENROUTER_SUBAGENT_MODEL lets specialists run on a cheaper model than the
// orchestrator; both default to the same model otherwise.
const openrouter = createOpenAI({
  baseURL: "https://openrouter.ai/api/v1",
  apiKey: process.env.OPENROUTER_API_KEY ?? "",
});

export const DEFAULT_MODEL =
  process.env.OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4.5";

export const SUBAGENT_MODEL =
  process.env.OPENROUTER_SUBAGENT_MODEL ?? DEFAULT_MODEL;

export function orchestratorModel() {
  return openrouter.chat(DEFAULT_MODEL);
}

export function subagentModel() {
  return openrouter.chat(SUBAGENT_MODEL);
}

// eve requires explicit context-window metadata for non-gateway models.
export const CONTEXT_WINDOW_TOKENS = 200_000;
