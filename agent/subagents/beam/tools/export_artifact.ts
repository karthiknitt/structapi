import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { defineTool } from "eve/tools";
import { z } from "zod";

// Copies a file (typically a PNG plot) out of the sandbox to the host
// `outputs/<sessionId>/` directory so the user can open it and the web UI can
// serve it. Returns the host-relative path.
export default defineTool({
  description:
    "Export a file from the sandbox (e.g. /workspace/out/bmd.png) to the " +
    "host outputs folder so the user can view it. Call this for every plot " +
    "or report file you generate. Returns the path to tell the user.",
  inputSchema: z.object({
    sandboxPath: z
      .string()
      .min(1)
      .describe("Path of the file inside the sandbox, e.g. out/sfd_bmd.png"),
    name: z
      .string()
      .optional()
      .describe("Optional output filename; defaults to the sandbox basename."),
  }),
  outputSchema: z.object({ hostPath: z.string(), bytes: z.number() }),
  async execute({ sandboxPath, name }, ctx) {
    const sandbox = await ctx.getSandbox();
    const data = await sandbox.readBinaryFile({ path: sandboxPath });
    if (!data) {
      throw new Error(`file not found in sandbox: ${sandboxPath}`);
    }
    const sessionId = ctx.session?.id ?? "session";
    const base = name ?? sandboxPath.split("/").pop() ?? "artifact.bin";
    const dir = join(process.cwd(), "outputs", String(sessionId));
    mkdirSync(dir, { recursive: true });
    const hostPath = join(dir, base);
    writeFileSync(hostPath, Buffer.from(data));
    return {
      hostPath: hostPath.replace(process.cwd(), "").replace(/\\/g, "/"),
      bytes: data.byteLength,
    };
  },
});
