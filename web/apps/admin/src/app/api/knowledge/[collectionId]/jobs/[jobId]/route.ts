import { prisma } from "@taigi-flow/db";
import { error, handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string; jobId: string }> };

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId, jobId } = await params;

    const job = await prisma.ingestJob.findUnique({ where: { id: jobId } });
    if (!job || job.collectionId !== collectionId) return error("Job not found", 404);

    const srcName = job.filePath.split("/").pop() ?? "";
    await prisma.$executeRaw`
      DELETE FROM "KnowledgeChunk"
      WHERE "collectionId" = ${collectionId}
        AND (
          metadata->>'jobId' = ${jobId}
          OR (metadata->>'jobId' IS NULL AND metadata->>'source' = ${srcName})
        )
    `;
    await prisma.ingestJob.delete({ where: { id: jobId } });

    return ok({ deleted: true });
  } catch (err) {
    return handleError(err);
  }
}
