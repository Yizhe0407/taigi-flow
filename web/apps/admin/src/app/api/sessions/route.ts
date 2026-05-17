import { prisma } from "@taigi-flow/db";
import { sessionBatchDeleteSchema, sessionListQuerySchema } from "@taigi-flow/types";
import { handleError, ok, parseJson } from "@/lib/api";
import { deleteSessionsBatch } from "@/lib/services/session.service";

export const dynamic = "force-dynamic";

const STALE_MS = 2 * 60 * 60 * 1000;

export async function GET(req: Request): Promise<Response> {
  try {
    const url = new URL(req.url);
    const query = sessionListQuerySchema.parse(Object.fromEntries(url.searchParams));

    const where: Record<string, unknown> = {};
    if (query.agentProfileId) where.agentProfileId = query.agentProfileId;

    if (query.status === "ended") {
      where.endedAt = { not: null };
    } else if (query.status === "active") {
      where.endedAt = null;
      where.startedAt = { gte: new Date(Date.now() - STALE_MS) };
    } else if (query.status === "stale") {
      where.endedAt = null;
      where.startedAt = { lt: new Date(Date.now() - STALE_MS) };
    }

    const orderBy = [
      query.sortBy === "turnCount"
        ? { logs: { _count: query.sortDir } }
        : { startedAt: query.sortDir },
      { id: "asc" as const },
    ];

    const sessions = await prisma.session.findMany({
      where,
      orderBy,
      take: query.limit + 1,
      ...(query.cursor && { cursor: { id: query.cursor }, skip: 1 }),
      include: {
        agentProfile: { select: { id: true, name: true } },
        _count: { select: { logs: true } },
      },
    });

    const hasMore = sessions.length > query.limit;
    const items = hasMore ? sessions.slice(0, -1) : sessions;
    const nextCursor = hasMore ? (items[items.length - 1]?.id ?? null) : null;

    return ok({ items, nextCursor });
  } catch (err) {
    return handleError(err);
  }
}

export async function DELETE(req: Request): Promise<Response> {
  try {
    const body = await parseJson(req, sessionBatchDeleteSchema);
    const deleted = await deleteSessionsBatch(body.ids);
    return ok({ deleted });
  } catch (err) {
    return handleError(err);
  }
}
