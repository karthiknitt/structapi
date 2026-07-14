import { getSessionCookie } from "better-auth/cookies";
import { NextRequest, NextResponse } from "next/server";

// Next.js 16 proxy (formerly middleware.ts): optimistic auth gate (cookie
// presence only — edge-safe, no DB call). Real session validation happens
// server-side in the protected route handlers (see
// app/outputs/[...path]/route.ts). Protects the chat UI, exported
// artifacts, the model settings API, and the eve session proxy.
export function proxy(request: NextRequest) {
  const cookie = getSessionCookie(request);
  if (!cookie) {
    const url = new URL("/signin", request.url);
    const p = request.nextUrl.pathname;
    if (p.startsWith("/eve") || p.startsWith("/outputs") ||
        p.startsWith("/api/models") || p.startsWith("/api/history")) {
      return new NextResponse("unauthorized", { status: 401 });
    }
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/",
    "/settings",
    "/history",
    "/eve/:path*",
    "/outputs/:path*",
    "/api/models",
    "/api/history/:path*",
  ],
};
