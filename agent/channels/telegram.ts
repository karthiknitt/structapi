import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import {
  defaultTelegramAuth,
  resolveTelegramBotToken,
  telegramChannel,
} from "eve/channels/telegram";

// PRIVATE, ALLOWLISTED BOT. Only a private-chat message from a user id in
// TELEGRAM_ALLOWED_USER_IDS (comma-separated; falls back to the single
// TELEGRAM_OWNER_ID) is dispatched to the agent; everything else (groups,
// other senders) is dropped. Text replies use eve's default
// `message.completed` -> sendMessage handler (each completed assistant
// step lands as its own message, which reads as progressive/streaming
// output for a multi-subagent design run). PDF design reports and PNG
// diagrams (SFD/BMD charts, etc.) exported by the specialist subagents
// (via `export_artifact`, into `outputs/<sessionId>/...`) are pushed into
// the chat as Telegram documents once the turn completes. Each caller's
// `profile` memory (agent/memory/profile.ts) is scoped per-user, so
// multiple allowlisted users never share saved facts.
const ALLOWED_USER_IDS = new Set(
  (process.env.TELEGRAM_ALLOWED_USER_IDS ?? process.env.TELEGRAM_OWNER_ID ?? "")
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean),
);
const OUTPUTS_DIR = join(process.cwd(), "outputs");

const turnStartedAt = new Map<string, number>();
const sentAttachmentPaths = new Set<string>();

const ATTACHMENT_MIME: Record<string, string> = {
  ".pdf": "application/pdf",
  ".png": "image/png",
};

function findUnsentAttachments(sinceMs: number): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return; // outputs/ (or a subdir) may not exist yet
    }
    for (const entry of entries) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!entry.isFile()) continue;
      const ext = entry.name.slice(entry.name.lastIndexOf(".")).toLowerCase();
      if (!(ext in ATTACHMENT_MIME)) continue;
      if (sentAttachmentPaths.has(full)) continue;
      if (statSync(full).mtimeMs >= sinceMs) found.push(full);
    }
  };
  walk(OUTPUTS_DIR);
  return found;
}

async function sendTelegramDocument(chatId: string, filePath: string) {
  const token = await resolveTelegramBotToken();
  const ext = filePath.slice(filePath.lastIndexOf(".")).toLowerCase();
  const mime = ATTACHMENT_MIME[ext] ?? "application/octet-stream";
  const form = new FormData();
  form.set("chat_id", chatId);
  form.set(
    "document",
    new Blob([readFileSync(filePath)], { type: mime }),
    filePath.split("/").pop() ?? `attachment${ext}`,
  );
  const res = await fetch(
    `https://api.telegram.org/bot${token}/sendDocument`,
    { method: "POST", body: form },
  );
  if (!res.ok) {
    console.error(
      `[telegram] sendDocument failed (${res.status}) for ${filePath}`,
    );
  }
}

export default telegramChannel({
  botUsername: process.env.TELEGRAM_BOT_USERNAME,
  async onMessage(ctx, message) {
    if (message.chat.type !== "private") return null; // groups unsupported

    if (!message.from || !ALLOWED_USER_IDS.has(String(message.from.id))) {
      await ctx.telegram
        .sendMessage("This is a private bot — it only responds to allowlisted users.")
        .catch(() => {});
      return null;
    }

    return { auth: defaultTelegramAuth(message) };
  },
  events: {
    "turn.started": (data) => {
      turnStartedAt.set(data.turnId, Date.now());
    },
    "turn.completed": async (data, channel) => {
      const startedAt = turnStartedAt.get(data.turnId) ?? Date.now() - 5_000;
      turnStartedAt.delete(data.turnId);

      const chatId = channel.telegram.chatId;
      for (const path of findUnsentAttachments(startedAt - 2_000)) {
        sentAttachmentPaths.add(path);
        await sendTelegramDocument(chatId, path);
      }
    },
  },
});
