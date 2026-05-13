import { getRedis } from "@/lib/redis";
import { prisma } from "@taigi-flow/db";

export const dynamic = "force-dynamic";

const STALE_THRESHOLD_MS = 2 * 60 * 60 * 1000;
const HEARTBEAT_INTERVAL_MS = 15_000;
// Close SSE after 30 minutes to release the Redis subscriber connection
const MAX_DURATION_MS = 30 * 60_000;

function sseChunk(event: string, data: unknown): Uint8Array {
  return new TextEncoder().encode(
    `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
  );
}

async function fetchStats() {
  const [activeSessions, recent] = await Promise.all([
    prisma.session.count({
      where: {
        endedAt: null,
        startedAt: { gte: new Date(Date.now() - STALE_THRESHOLD_MS) },
      },
    }),
    prisma.interactionLog.findMany({
      orderBy: { createdAt: "desc" },
      take: 100,
      select: { latencyFirstAudio: true, errorFlag: true },
    }),
  ]);

  const withLatency = recent.filter((l) => l.latencyFirstAudio !== null);
  const avgFirstAudio =
    withLatency.length > 0
      ? Math.round(
          withLatency.reduce((s, l) => s + (l.latencyFirstAudio ?? 0), 0) /
            withLatency.length,
        )
      : null;

  return {
    activeSessions,
    avgFirstAudioMs: avgFirstAudio,
    errorRate:
      recent.length > 0
        ? Math.round(
            (recent.filter((l) => l.errorFlag !== null).length /
              recent.length) *
              1000,
          ) / 10
        : 0,
  };
}

export async function GET(): Promise<Response> {
  const state = { closed: false };

  // Each SSE connection gets its own Redis subscriber connection (required for SUBSCRIBE)
  const subscriber = getRedis().duplicate();
  await subscriber.connect();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        if (state.closed) return;
        try {
          controller.enqueue(sseChunk(event, data));
        } catch {
          state.closed = true;
        }
      };

      // Send initial stats snapshot
      try {
        send("stats", await fetchStats());
      } catch { /* non-fatal */ }

      // Heartbeat to keep connection alive and refresh stats
      const heartbeat = setInterval(async () => {
        if (state.closed) return clearInterval(heartbeat);
        send("heartbeat", { ts: Date.now() });
        try { send("stats", await fetchStats()); } catch { /* ignore */ }
      }, HEARTBEAT_INTERVAL_MS);

      // Auto-close after MAX_DURATION_MS
      const maxTimer = setTimeout(() => {
        state.closed = true;
        clearInterval(heartbeat);
        try { controller.close(); } catch { /* ignore */ }
      }, MAX_DURATION_MS);

      // Subscribe to Redis live channel
      try {
        await subscriber.subscribe("taigi:live", (message) => {
          if (state.closed) return;
          try {
            send("live", JSON.parse(message));
          } catch { /* malformed JSON, skip */ }
        });
      } catch (err) {
        send("error", { message: String(err) });
      }

      // Cleanup function stored so cancel() can call it
      (state as typeof state & { cleanup?: () => void }).cleanup = () => {
        clearInterval(heartbeat);
        clearTimeout(maxTimer);
      };
    },

    cancel() {
      state.closed = true;
      (state as typeof state & { cleanup?: () => void }).cleanup?.();
      subscriber.unsubscribe("taigi:live").catch(() => {});
      subscriber.disconnect().catch(() => {});
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}
