import { prisma } from "@taigi-flow/db";
import { handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string }> };

export async function GET(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId } = await params;
    const chunks = await prisma.$queryRaw<
      { id: string; content: string; metadata: unknown; createdAt: Date }[]
    >`
      SELECT id, content, metadata, "createdAt"
      FROM "KnowledgeChunk"
      WHERE "collectionId" = ${collectionId}
      ORDER BY "createdAt" ASC
    `;
    return ok(chunks);
  } catch (err) {
    return handleError(err);
  }
}
