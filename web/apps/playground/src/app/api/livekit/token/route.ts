import { AccessToken, AgentDispatchClient } from "livekit-server-sdk";
import { NextResponse } from "next/server";

const AGENT_NAME = "taigi-agent";
const ROOM_NAME = "playground";

function toHttpServiceUrl(url: string): string {
  if (url.startsWith("ws://")) {
    return `http://${url.slice("ws://".length)}`;
  }
  if (url.startsWith("wss://")) {
    return `https://${url.slice("wss://".length)}`;
  }
  // Already http:// or https:// — pass through unchanged.
  return url;
}

function resolveClientWsUrl(
  rawWsUrl: string,
  publicWsUrl: string | undefined,
  request: Request
): string {
  if (publicWsUrl) return publicWsUrl;

  const forwardedProto = request.headers.get("x-forwarded-proto");
  const forwardedHost = request.headers.get("x-forwarded-host");
  const host = forwardedHost || request.headers.get("host");
  const isHttpsPage =
    forwardedProto === "https" ||
    (!forwardedProto && request.url.startsWith("https://"));

  if (!isHttpsPage || !rawWsUrl.startsWith("ws://")) {
    return rawWsUrl;
  }

  try {
    const parsed = new URL(rawWsUrl);
    const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);
    if (host && localHosts.has(parsed.hostname)) {
      return `wss://${host}`;
    }
    return rawWsUrl.replace(/^ws:\/\//, "wss://");
  } catch {
    return rawWsUrl.replace(/^ws:\/\//, "wss://");
  }
}

export async function POST(request: Request) {
  try {
    const apiKey = process.env.LIVEKIT_API_KEY;
    const apiSecret = process.env.LIVEKIT_API_SECRET;
    const wsUrl = process.env.LIVEKIT_URL;
    const publicWsUrl = process.env.NEXT_PUBLIC_LIVEKIT_URL;

    if (!apiKey || !apiSecret || !wsUrl) {
      console.error("Missing LiveKit environment variables:", {
        apiKey: !!apiKey,
        apiSecret: !!apiSecret,
        wsUrl: !!wsUrl,
      });
      return NextResponse.json(
        { error: "Server misconfigured" },
        { status: 500 }
      );
    }
    const clientWsUrl = resolveClientWsUrl(wsUrl, publicWsUrl, request);

    const roomName = `${ROOM_NAME}-${crypto.randomUUID().slice(0, 8)}`;
    const identity = `user-${crypto.randomUUID().slice(0, 8)}`;
    const requireDispatch = process.env.LIVEKIT_REQUIRE_DISPATCH === "true";

    const at = new AccessToken(apiKey, apiSecret, {
      identity: identity,
      name: identity,
    });

    at.addGrant({
      roomJoin: true,
      room: roomName,
      canPublish: true,
      canSubscribe: true,
    });

    try {
      const serviceUrl = toHttpServiceUrl(wsUrl);
      const dispatchClient = new AgentDispatchClient(
        serviceUrl,
        apiKey,
        apiSecret
      );
      await dispatchClient.createDispatch(roomName, AGENT_NAME);
    } catch (dispatchError) {
      const dispatchMessage =
        dispatchError instanceof Error
          ? dispatchError.message
          : String(dispatchError);
      if (requireDispatch) {
        console.error("Agent dispatch failed in required mode:", {
          message: dispatchMessage,
          roomName,
        });
        return NextResponse.json(
          { error: `Agent dispatch failed: ${dispatchMessage}` },
          { status: 503 }
        );
      }
      console.warn("Agent dispatch unavailable, continuing without dispatch:", {
        message: dispatchMessage,
        roomName,
      });
      const token = await at.toJwt();
      return NextResponse.json({
        token,
        url: clientWsUrl,
        roomName,
        dispatchStatus: "unavailable" as const,
        dispatchMessage,
      });
    }

    const token = await at.toJwt();

    return NextResponse.json({
      token,
      url: clientWsUrl,
      roomName,
      dispatchStatus: "ok" as const,
      dispatchMessage: null,
    });
  } catch (error) {
    console.error("Error generating LiveKit token:", error);
    return NextResponse.json(
      { error: "Internal Server Error" },
      { status: 500 }
    );
  }
}
