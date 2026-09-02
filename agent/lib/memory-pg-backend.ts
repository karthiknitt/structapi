import { Pool } from "pg";
import {
  MemoryDocumentConflictError,
  type MemoryDocumentBackend,
} from "eve/memory/file";

// fileMemory() has no built-in backend for a self-hosted (non-Vercel,
// non-`eve dev`) deployment — it throws asking for an explicit one. This
// stores the memory document in the same Postgres instance eve already uses
// for durable workflow state (WORKFLOW_POSTGRES_URL), one row per scope key.
let pool: Pool | undefined;
let ensureTable: Promise<void> | undefined;

function getPool(): Pool {
  pool ??= new Pool({ connectionString: process.env.WORKFLOW_POSTGRES_URL });
  return pool;
}

async function ensureSchema(): Promise<void> {
  ensureTable ??= getPool().query(`
    create table if not exists agent_memory_documents (
      key text primary key,
      content text not null,
      version bigint not null default 0,
      updated_at timestamptz not null default now()
    )
  `).then(() => undefined);
  await ensureTable;
}

export function pgFileMemoryBackend(): MemoryDocumentBackend {
  return {
    async read({ key }) {
      await ensureSchema();
      const { rows } = await getPool().query<{ content: string; version: string }>(
        "select content, version from agent_memory_documents where key = $1",
        [key],
      );
      const row = rows[0];
      return row ? { content: row.content, version: row.version } : null;
    },
    async write({ key, content, expectedVersion }) {
      await ensureSchema();
      if (expectedVersion === null) {
        const { rows } = await getPool().query<{ content: string; version: string }>(
          `insert into agent_memory_documents (key, content, version)
           values ($1, $2, 0)
           on conflict (key) do nothing
           returning content, version`,
          [key, content],
        );
        if (rows.length === 0) throw new MemoryDocumentConflictError(key);
        return { content: rows[0].content, version: rows[0].version };
      }

      const { rows } = await getPool().query<{ content: string; version: string }>(
        `update agent_memory_documents
         set content = $2, version = version + 1, updated_at = now()
         where key = $1 and version = $3::bigint
         returning content, version`,
        [key, content, expectedVersion],
      );
      if (rows.length === 0) throw new MemoryDocumentConflictError(key);
      return { content: rows[0].content, version: rows[0].version };
    },
  };
}
