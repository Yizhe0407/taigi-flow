import { prisma } from "@taigi-flow/db";
import { handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string }> };

const CHUNK_PAGE_SIZE = 500;

export async function GET(req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId } = await params;
    const url = new URL(req.url);
    const offset = Math.max(0, parseInt(url.searchParams.get("offset") ?? "0", 10) || 0);
    const limit = CHUNK_PAGE_SIZE + 1; // fetch one extra to detect hasMore

    const chunks = await prisma.$queryRaw<
      { id: string; content: string; metadata: unknown; createdAt: Date }[]
    >`
      SELECT id, content, metadata, "createdAt"
      FROM "KnowledgeChunk"
      WHERE "collectionId" = ${collectionId}
      ORDER BY "createdAt" ASC
      LIMIT ${limit} OFFSET ${offset}
    `;

    const hasMore = chunks.length > CHUNK_PAGE_SIZE;
    return ok({ items: hasMore ? chunks.slice(0, CHUNK_PAGE_SIZE) : chunks, hasMore, offset });
  } catch (err) {
    return handleError(err);
  }
}
