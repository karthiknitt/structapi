import { readFile } from "node:fs/promises";
import { join, normalize } from "node:path";
import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { auth } from "../../../lib/auth";

// Serves generated design artifacts (PNGs, PDFs) from the repo-root
// `outputs/<runId>/<file>` directory. proxy.ts already gates `/outputs/:path*`
// on cookie presence; this route does the real session check plus a
// path-traversal guard, per the pattern in app/api/models/route.ts.
const OUTPUTS_ROOT = join(process.cwd(), "outputs");

const CONTENT_TYPES: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".pdf": "application/pdf",
};

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { path: segments } = await params;
  if (segments.some((s) => s === ".." || s.includes("/") || s.includes("\\"))) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  const filePath = normalize(join(OUTPUTS_ROOT, ...segments));
  if (!filePath.startsWith(OUTPUTS_ROOT)) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  const ext = filePath.slice(filePath.lastIndexOf(".")).toLowerCase();
  const contentType = CONTENT_TYPES[ext];
  if (!contentType) {
    return NextResponse.json({ error: "Unsupported file type" }, { status: 415 });
  }

  try {
    const data = await readFile(filePath);
    return new NextResponse(new Uint8Array(data), {
      headers: { "Content-Type": contentType },
    });
  } catch {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
}
