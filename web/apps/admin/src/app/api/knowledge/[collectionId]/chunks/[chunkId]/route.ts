import { prisma } from "@taigi-flow/db";
import { error, handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string; chunkId: string }> };

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId, chunkId } = await params;
    const deleted = await prisma.$executeRaw`
      DELETE FROM "KnowledgeChunk"
      WHERE id = ${chunkId} AND "collectionId" = ${collectionId}
    `;
    if (deleted === 0) return error("Chunk not found", 404);
    return ok({ deleted: true });
  } catch (err) {
    return handleError(err);
  }
}
