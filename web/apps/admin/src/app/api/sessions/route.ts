import { prisma } from "@taigi-flow/db";
import { sessionListQuerySchema } from "@taigi-flow/types";
import { handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(req: Request): Promise<Response> {
  try {
    const url = new URL(req.url);
    const query = sessionListQuerySchema.parse(Object.fromEntries(url.searchParams));

    const where = query.agentProfileId ? { agentProfileId: query.agentProfileId } : {};

    const sessions = await prisma.session.findMany({
      where,
      orderBy: { startedAt: "desc" },
      take: query.limit + 1,
      ...(query.cursor && { cursor: { id: query.cursor }, skip: 1 }),
      include: {
        agentProfile: { select: { id: true, name: true } },
        _count: { select: { logs: true } },
      },
    });

    const hasMore = sessions.length > query.limit;
    const items = hasMore ? sessions.slice(0, -1) : sessions;
    const nextCursor = hasMore ? items[items.length - 1]?.id ?? null : null;

    return ok({ items, nextCursor });
  } catch (err) {
    return handleError(err);
  }
}
