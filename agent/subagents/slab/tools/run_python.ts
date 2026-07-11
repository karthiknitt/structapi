import { defineTool } from "eve/tools";
import { z } from "zod";

export default defineTool({
  description:
    "Execute a Python 3 program inside the isolated sandbox and return its " +
    "stdout, stderr, and exit code. Use this for ALL computation — never " +
    "compute or guess numbers yourself. The iscodes design library is at " +
    "/workspace/iscodes (import with `from iscodes... import ...`; cwd is " +
    "/workspace). numpy and matplotlib (Agg) are preinstalled; there is no " +
    "network access. Files written under /workspace persist across calls " +
    "within the session. Write plots to /workspace/out/<name>.png.",
  inputSchema: z.object({
    code: z.string().min(1).describe("Python 3 source to execute."),
    filename: z
      .string()
      .default("program.py")
      .describe("Path under /workspace to write the code to before running."),
  }),
  outputSchema: z.object({
    stdout: z.string(),
    stderr: z.string(),
    exitCode: z.number(),
  }),
  async execute({ code, filename }, ctx) {
    const sandbox = await ctx.getSandbox();
    await sandbox.writeTextFile({ path: filename, content: code });
    const result = await sandbox.run({
      command: `python3 ${sandbox.resolvePath(filename)}`,
    });
    return {
      stdout: result.stdout,
      stderr: result.stderr,
      exitCode: result.exitCode,
    };
  },
});
