import { prisma } from "@taigi-flow/db";
import { ok, handleError } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  try {
    const [activeSessions, recentLogs] = await Promise.all([
      prisma.session.count({ where: { endedAt: null } }),
      prisma.interactionLog.findMany({
        orderBy: { createdAt: "desc" },
        take: 100,
        select: {
          latencyFirstAudio: true,
          latencyTotal: true,
          errorFlag: true,
          createdAt: true,
        },
      }),
    ]);

    const withLatency = recentLogs.filter((l) => l.latencyFirstAudio !== null);
    const avgFirstAudio =
      withLatency.length > 0
        ? Math.round(
            withLatency.reduce((s, l) => s + (l.latencyFirstAudio ?? 0), 0) /
              withLatency.length,
          )
        : null;

    const errorCount = recentLogs.filter((l) => l.errorFlag !== null).length;
    const errorRate =
      recentLogs.length > 0
        ? Math.round((errorCount / recentLogs.length) * 1000) / 10
        : 0;

    return ok({
      activeSessions,
      recentTurns: recentLogs.length,
      avgFirstAudioMs: avgFirstAudio,
      errorRate,
    });
  } catch (err) {
    return handleError(err);
  }
}
