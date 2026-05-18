import { NextResponse } from "next/server";
import { deriveAdminToken } from "@/lib/session-token";

// Simple brute-force guard: max 5 attempts per IP per 15 minutes.
const _loginAttempts = new Map<string, { count: number; resetAt: number }>();
const _LOGIN_MAX = 5;
const _LOGIN_WINDOW_MS = 15 * 60_000;

function checkLoginRateLimit(ip: string): boolean {
  const now = Date.now();
  const bucket = _loginAttempts.get(ip);
  if (!bucket || now >= bucket.resetAt) {
    _loginAttempts.set(ip, { count: 1, resetAt: now + _LOGIN_WINDOW_MS });
    return true;
  }
  if (bucket.count >= _LOGIN_MAX) return false;
  bucket.count++;
  return true;
}

export async function POST(req: Request): Promise<Response> {
  const ip =
    req.headers.get("x-real-ip") ??
    req.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
    "unknown";
  if (!checkLoginRateLimit(ip)) {
    return NextResponse.json({ error: "Too many login attempts" }, { status: 429 });
  }

  const secret = process.env.ADMIN_SECRET;
  if (!secret) return NextResponse.json({ error: "Auth not configured" }, { status: 503 });

  const body = await req.json().catch(() => ({})) as Record<string, unknown>;
  if (body.secret !== secret) {
    return NextResponse.json({ error: "密碼錯誤" }, { status: 401 });
  }

  // Store a derived opaque token — not the raw secret — to limit exposure if
  // cookie value leaks through logs or DevTools.
  const token = await deriveAdminToken(secret);
  const res = NextResponse.json({ ok: true });
  res.cookies.set("admin_token", token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  return res;
}

export async function DELETE(): Promise<Response> {
  const res = NextResponse.json({ ok: true });
  res.cookies.delete("admin_token");
  return res;
}
