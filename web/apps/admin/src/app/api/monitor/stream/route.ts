import { prisma } from "@taigi-flow/db";

export const dynamic = "force-dynamic";

const POLL_INTERVAL_MS = 1000;
const STALE_SESSION_THRESHOLD_MS = 2 * 60 * 60 * 1000;

function sseChunk(event: string, data: unknown): Uint8Array {
  return new TextEncoder().encode(
    `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
  );
}

export async function GET(): Promise<Response> {
  const state = { closed: false };

  const stream = new ReadableStream({
    async start(controller) {
      let cursor = new Date();

      // Prime cursor to "now" so we don't flood with old turns on connect.
      // Send the last 20 turns as initial snapshot, then stream new ones.
      try {
        const snapshot = await prisma.interactionLog.findMany({
          orderBy: { createdAt: "desc" },
          take: 20,
          include: {
            session: {
              select: {
                agentProfile: { select: { name: true } },
              },
            },
          },
        });
        cursor = snapshot[0]?.createdAt ?? cursor;
        // Send oldest-first so UI can append in order
        controller.enqueue(sseChunk("snapshot", snapshot.reverse()));
      } catch {
        // Non-fatal — just start streaming from now
      }

      while (!state.closed) {
        await new Promise<void>((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (state.closed) break;

        try {
          // New turns since last poll
          const newTurns = await prisma.interactionLog.findMany({
            where: { createdAt: { gt: cursor } },
            orderBy: { createdAt: "asc" },
            include: {
              session: {
                select: { agentProfile: { select: { name: true } } },
              },
            },
          });

          if (newTurns.length > 0) {
            cursor = newTurns[newTurns.length - 1]!.createdAt;
            for (const turn of newTurns) {
              controller.enqueue(sseChunk("turn", turn));
            }
          }

          // Stats update every poll cycle
          const [activeSessions, recent] = await Promise.all([
            prisma.session.count({
              where: {
                endedAt: null,
                startedAt: { gte: new Date(Date.now() - STALE_SESSION_THRESHOLD_MS) },
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
          const errorRate =
            recent.length > 0
              ? Math.round(
                  (recent.filter((l) => l.errorFlag !== null).length / recent.length) * 1000,
                ) / 10
              : 0;

          controller.enqueue(
            sseChunk("stats", { activeSessions, avgFirstAudioMs: avgFirstAudio, errorRate }),
          );
        } catch (err) {
          controller.enqueue(sseChunk("error", { message: String(err) }));
        }
      }

      try { controller.close(); } catch { /* already closed */ }
    },

    cancel() {
      state.closed = true;
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
