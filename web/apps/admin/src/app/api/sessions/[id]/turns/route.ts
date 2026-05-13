import { prisma } from "@taigi-flow/db";
import { turnFilterSchema } from "@taigi-flow/types";
import { handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { id } = await params;
    const url = new URL(req.url);
    const filter = turnFilterSchema.parse(Object.fromEntries(url.searchParams));

    const where: Record<string, unknown> = { sessionId: id };
    if (filter.bargedIn !== undefined) where.wasBargedIn = filter.bargedIn;
    if (filter.hasError !== undefined) {
      where.errorFlag = filter.hasError ? { not: null } : null;
    }
    if (filter.minLatencyMs !== undefined) {
      where.latencyTotal = { gte: filter.minLatencyMs };
    }

    const turns = await prisma.interactionLog.findMany({
      where,
      orderBy: { turnIndex: "asc" },
    });
    return ok({ items: turns });
  } catch (err) {
    return handleError(err);
  }
}
