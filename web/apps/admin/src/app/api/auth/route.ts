import { NextResponse } from "next/server";

export async function POST(req: Request): Promise<Response> {
  const secret = process.env.ADMIN_SECRET;
  if (!secret) return NextResponse.json({ ok: true });

  const body = await req.json().catch(() => ({})) as Record<string, unknown>;
  if (body.secret !== secret) {
    return NextResponse.json({ error: "密碼錯誤" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set("admin_token", secret, {
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
