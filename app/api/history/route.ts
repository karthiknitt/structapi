import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { auth } from "../../../lib/auth";
import { listSessions } from "../../../lib/workflow-db";

async function requireSession() {
  return auth.api.getSession({ headers: await headers() });
}

export async function GET() {
  if (!(await requireSession())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const sessions = await listSessions();
  return NextResponse.json({ sessions });
}
