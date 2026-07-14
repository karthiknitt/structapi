import { readdir } from "node:fs/promises";
import { join } from "node:path";
import { Pool } from "pg";

// Reuses the same Postgres container as Better Auth (lib/auth.ts) and the
// eve workflow durability layer (WORKFLOW_POSTGRES_URL) — the `workflow`
// schema (workflow_runs / workflow_stream_chunks) lives alongside the auth
// tables in that one Postgres instance. No app code queried this schema
// before; previously the only way in was the `pnpm observe` CLI.
const pool = new Pool({
  connectionString:
    process.env.WORKFLOW_POSTGRES_URL ??
    process.env.AUTH_DATABASE_URL ??
    "postgres://world:world@localhost:5544/world",
});

const OUTPUTS_ROOT = join(process.cwd(), "outputs");

export interface SessionSummary {
  runId: string;
  title: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface SessionMessage {
  role: "user" | "assistant";
  turnId: string;
  text: string;
}

export interface SubagentRun {
  runId: string;
  subagent: string;
  status: string;
}

export interface SessionDetail extends SessionSummary {
  messages: SessionMessage[];
  subagents: SubagentRun[];
  artifacts: { runId: string; files: string[] }[];
}

/**
 * eve's durable stream protocol wraps each event as a length-prefixed
 * "devalue" frame ending in a quoted base64 JSON payload, e.g.
 * `\x00\x00\x01\x19devl[["Uint8Array",1],"<base64>"]`. There's no public
 * decoder for this — reverse-engineered from raw bytes in workflow_stream_chunks.
 */
function decodeChunk(raw: Buffer): { type: string; data: unknown } | null {
  const text = raw.toString("latin1");
  const match = /"([A-Za-z0-9+/=]{20,})"\]\s*$/.exec(text);
  if (!match) return null;
  try {
    const payload = Buffer.from(match[1], "base64").toString("utf-8");
    const obj = JSON.parse(payload);
    return { type: obj.type, data: obj.data };
  } catch {
    return null;
  }
}

export async function listSessions(limit = 50): Promise<SessionSummary[]> {
  const { rows } = await pool.query(
    `SELECT id, status, created_at, updated_at, attributes
     FROM workflow.workflow_runs
     WHERE attributes->>'$eve.type' = 'session'
     ORDER BY created_at DESC
     LIMIT $1`,
    [limit]
  );
  return rows.map((r) => ({
    runId: r.id,
    title: r.attributes?.["$eve.title"] ?? "(untitled session)",
    status: r.status,
    createdAt: r.created_at,
    updatedAt: r.updated_at,
  }));
}

async function listOutputFiles(runId: string): Promise<string[]> {
  try {
    const entries = await readdir(join(OUTPUTS_ROOT, runId));
    return entries.sort();
  } catch {
    return [];
  }
}

export async function getSessionDetail(
  runId: string
): Promise<SessionDetail | null> {
  const { rows: runRows } = await pool.query(
    `SELECT id, status, created_at, updated_at, attributes
     FROM workflow.workflow_runs WHERE id = $1`,
    [runId]
  );
  const run = runRows[0];
  if (!run || run.attributes?.["$eve.type"] !== "session") return null;

  const { rows: childRows } = await pool.query(
    `SELECT id, status, attributes FROM workflow.workflow_runs
     WHERE attributes->>'$eve.root' = $1 AND attributes->>'$eve.type' = 'subagent'
     ORDER BY created_at ASC`,
    [runId]
  );
  const subagents: SubagentRun[] = childRows.map((r) => ({
    runId: r.id,
    subagent: r.attributes?.["$eve.subagent"] ?? "(unknown)",
    status: r.status,
  }));

  const { rows: chunkRows } = await pool.query(
    `SELECT data FROM workflow.workflow_stream_chunks
     WHERE run_id = $1 ORDER BY id ASC`,
    [runId]
  );

  const messages: SessionMessage[] = [];
  for (const row of chunkRows) {
    const decoded = decodeChunk(row.data as Buffer);
    if (!decoded) continue;
    if (decoded.type === "message.received") {
      const d = decoded.data as { message?: string; turnId?: string };
      if (typeof d.message === "string") {
        messages.push({ role: "user", turnId: d.turnId ?? "?", text: d.message });
      }
    } else if (decoded.type === "message.completed") {
      const d = decoded.data as { message?: string; turnId?: string };
      if (typeof d.message === "string") {
        messages.push({ role: "assistant", turnId: d.turnId ?? "?", text: d.message });
      }
    }
  }

  const artifactRunIds = [runId, ...subagents.map((s) => s.runId)];
  const artifacts = (
    await Promise.all(
      artifactRunIds.map(async (id) => ({ runId: id, files: await listOutputFiles(id) }))
    )
  ).filter((a) => a.files.length > 0);

  return {
    runId: run.id,
    title: run.attributes?.["$eve.title"] ?? "(untitled session)",
    status: run.status,
    createdAt: run.created_at,
    updatedAt: run.updated_at,
    messages,
    subagents,
    artifacts,
  };
}
