import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { auth } from "../../../lib/auth";

const CONFIG_PATH = join(process.cwd(), "config", "models.json");

// Curated fallback shown if the live OpenRouter catalog is unreachable
// (snapshot 2026-07-11).
const FALLBACK_MODELS = [
  { id: "anthropic/claude-sonnet-5", name: "Claude Sonnet 5" },
  { id: "anthropic/claude-opus-4.8", name: "Claude Opus 4.8" },
  { id: "anthropic/claude-opus-4.8-fast", name: "Claude Opus 4.8 Fast" },
  { id: "openai/gpt-5.6-sol", name: "GPT-5.6 Sol" },
  { id: "openai/gpt-5.6-terra", name: "GPT-5.6 Terra" },
  { id: "openai/gpt-5.5", name: "GPT-5.5" },
  { id: "google/gemini-3.5-flash", name: "Gemini 3.5 Flash" },
  { id: "google/gemini-3.1-flash-lite", name: "Gemini 3.1 Flash Lite" },
  { id: "x-ai/grok-4.5", name: "Grok 4.5" },
  { id: "x-ai/grok-4.3", name: "Grok 4.3" },
  { id: "qwen/qwen3.7-max", name: "Qwen 3.7 Max" },
  { id: "z-ai/glm-5.2", name: "GLM 5.2" },
  { id: "mistralai/mistral-medium-3.5", name: "Mistral Medium 3.5" },
];

async function requireSession() {
  const session = await auth.api.getSession({ headers: await headers() });
  return session;
}

async function currentSelection() {
  try {
    return JSON.parse(await readFile(CONFIG_PATH, "utf-8"));
  } catch {
    return { orchestrator: "anthropic/claude-sonnet-5",
             subagents: "anthropic/claude-sonnet-5" };
  }
}

export async function GET() {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  let models = FALLBACK_MODELS;
  let source = "fallback";
  try {
    const res = await fetch("https://openrouter.ai/api/v1/models", {
      headers: process.env.OPENROUTER_API_KEY
        ? { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}` }
        : {},
      next: { revalidate: 3600 },
    });
    if (res.ok) {
      const body = await res.json();
      const list = (body.data ?? [])
        .map((m: { id: string; name?: string; context_length?: number }) => ({
          id: m.id,
          name: m.name ?? m.id,
          context: m.context_length,
        }))
        // text-capable chat models only; drop niche variants for a usable list
        .filter((m: { id: string }) => !/embed|whisper|tts|image|audio/i.test(m.id))
        .sort((a: { id: string }, b: { id: string }) => a.id.localeCompare(b.id));
      if (list.length > 0) {
        models = list;
        source = "openrouter";
      }
    }
  } catch {
    // keep fallback
  }
  return NextResponse.json({
    models,
    source,
    selection: await currentSelection(),
  });
}

export async function POST(req: Request) {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const body = await req.json().catch(() => null);
  const orchestrator = body?.orchestrator;
  const subagents = body?.subagents;
  const valid = (v: unknown) =>
    typeof v === "string" && /^[\w.:-]+\/[\w.:-]+$/.test(v);
  if (!valid(orchestrator) || !valid(subagents)) {
    return NextResponse.json(
      { error: "orchestrator and subagents must be OpenRouter model ids" },
      { status: 400 },
    );
  }
  await mkdir(join(process.cwd(), "config"), { recursive: true });
  await writeFile(
    CONFIG_PATH,
    JSON.stringify({ orchestrator, subagents }, null, 2) + "\n",
  );
  return NextResponse.json({
    ok: true,
    selection: { orchestrator, subagents },
    note: "Restart the agent host (pnpm dev / pnpm tui) to apply.",
  });
}
