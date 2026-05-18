import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { deriveAdminToken } from "@/lib/session-token";

export async function proxy(req: NextRequest) {
  const secret = process.env.ADMIN_SECRET;
  if (!secret) {
    // Fail-closed: no secret configured means auth is broken, not disabled.
    // Return 503 so misconfigured deployments are obviously broken, not silently open.
    const { pathname } = req.nextUrl;
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Admin auth not configured" }, { status: 503 });
    }
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  const { pathname } = req.nextUrl;
  if (pathname === "/login" || pathname.startsWith("/api/auth")) {
    return NextResponse.next();
  }

  const cookieToken = req.cookies.get("admin_token")?.value;
  const expected = await deriveAdminToken(secret);
  if (cookieToken !== expected) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
