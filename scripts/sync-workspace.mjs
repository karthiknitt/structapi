// Sync the single-source Python calc library into every subagent sandbox
// workspace (and the root agent workspace). Run after editing python/iscodes:
//   node scripts/sync-workspace.mjs
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "python", "iscodes");

if (!existsSync(src)) {
  console.error("python/iscodes not found");
  process.exit(1);
}

const targets = [];
const subagentsDir = join(root, "agent", "subagents");
if (existsSync(subagentsDir)) {
  for (const entry of readdirSync(subagentsDir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      targets.push(join(subagentsDir, entry.name, "sandbox", "workspace", "iscodes"));
    }
  }
}
// root agent workspace too (orchestrator can sanity-check numbers)
targets.push(join(root, "agent", "sandbox", "workspace", "iscodes"));

for (const dest of targets) {
  rmSync(dest, { recursive: true, force: true });
  mkdirSync(dest, { recursive: true });
  cpSync(src, dest, {
    recursive: true,
    filter: (p) => !p.includes("__pycache__") && !p.endsWith(".pyc"),
  });
  console.log("synced ->", dest.replace(root, "."));
}
