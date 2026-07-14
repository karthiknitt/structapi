import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { auth } from "../../../../lib/auth";
import { getSessionDetail } from "../../../../lib/workflow-db";

async function requireSession() {
  return auth.api.getSession({ headers: await headers() });
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ runId: string }> }
) {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { runId } = await params;
  if (!/^wrun_[A-Za-z0-9]+$/.test(runId)) {
    return NextResponse.json({ error: "Invalid session id" }, { status: 400 });
  }
  const detail = await getSessionDetail(runId);
  if (!detail) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json(detail);
}
