import { prisma } from "@taigi-flow/db";
import { pronunciationCreateSchema } from "@taigi-flow/types";
import { z } from "zod";
import { handleError, ok, parseJson } from "@/lib/api";

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
    const entry = await prisma.pronunciationEntry.create({
      data: {
        profileId: input.profileId ?? null,
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
