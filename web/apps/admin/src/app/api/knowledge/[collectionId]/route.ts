import { prisma } from "@taigi-flow/db";
import { handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string }> };

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId } = await params;
    await prisma.$executeRaw`
      DELETE FROM "KnowledgeChunk" WHERE "collectionId" = ${collectionId}
    `;
    await prisma.ingestJob.deleteMany({ where: { collectionId } });
    return ok({ deleted: true });
  } catch (err) {
    return handleError(err);
  }
}
