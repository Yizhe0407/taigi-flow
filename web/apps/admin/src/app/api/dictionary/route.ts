import { prisma } from "@taigi-flow/db";
import { pronunciationCreateSchema } from "@taigi-flow/types";
import { z } from "zod";
import { error, handleError, ok, parseJson } from "@/lib/api";

export const dynamic = "force-dynamic";

const querySchema = z.object({
  profileId: z.union([z.literal("global"), z.string().uuid()]).optional(),
  search: z.string().optional(),
});

export async function GET(req: Request): Promise<Response> {
  try {
    const url = new URL(req.url);
    const query = querySchema.parse(Object.fromEntries(url.searchParams));

    const where: Record<string, unknown> = {};
    if (query.profileId === "global") {
      where.profileId = null;
    } else if (query.profileId) {
      where.profileId = query.profileId;
    }
    if (query.search) {
      where.OR = [
        { term: { contains: query.search, mode: "insensitive" } },
        { replacement: { contains: query.search, mode: "insensitive" } },
      ];
    }

    const entries = await prisma.pronunciationEntry.findMany({
      where,
      orderBy: [{ priority: "desc" }, { term: "asc" }],
    });
    return ok({ items: entries });
  } catch (err) {
    return handleError(err);
  }
}

export async function POST(req: Request): Promise<Response> {
  try {
    const input = await parseJson(req, pronunciationCreateSchema);
    const profileId = input.profileId ?? null;

    if (profileId) {
      const profile = await prisma.agentProfile.findUnique({ where: { id: profileId }, select: { id: true } });
      if (!profile) return error("AgentProfile not found", 404);
    }

    const existing = await prisma.pronunciationEntry.findFirst({
      where: { profileId, term: input.term },
    });

    if (existing) {
      const entry = await prisma.pronunciationEntry.update({
        where: { id: existing.id },
        data: {
          replacement: input.replacement,
          priority: input.priority,
          ...(input.note !== undefined && { note: input.note ?? null }),
        },
      });
      return ok(entry);
    }

    const entry = await prisma.pronunciationEntry.create({
      data: {
        profileId,
        term: input.term,
        replacement: input.replacement,
        priority: input.priority,
        note: input.note ?? null,
      },
    });
    return ok(entry, { status: 201 });
  } catch (err) {
    return handleError(err);
  }
}
