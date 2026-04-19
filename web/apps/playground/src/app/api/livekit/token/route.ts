import { AccessToken } from "livekit-server-sdk";
import { NextResponse } from "next/server";

export async function POST() {
  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const wsUrl = process.env.LIVEKIT_URL;

  if (!apiKey || !apiSecret || !wsUrl) {
    return NextResponse.json(
      { error: "Server misconfigured" },
      { status: 500 }
    );
  }

  const identity = `user-${Math.random().toString(36).substring(7)}`;

  const at = new AccessToken(apiKey, apiSecret, {
    identity: identity,
    name: identity,
  });

  at.addGrant({
    roomJoin: true,
    room: "playground",
    canPublish: true,
    canSubscribe: true,
  });

  const token = await at.toJwt();

  return NextResponse.json({ token, url: wsUrl });
}
