import path from "path";

import { prisma } from "@taigi-flow/db";
import { error, handleError, ok } from "@/lib/api";
import { deleteUploadedFile } from "@/app/api/knowledge/_lib/files";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string; jobId: string }> };

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId, jobId } = await params;

    const job = await prisma.ingestJob.findUnique({ where: { id: jobId } });
    if (!job || job.collectionId !== collectionId) return error("Job not found", 404);
    if (job.status === "processing") return error("Job 正在處理中，無法刪除", 409);

    const srcName = path.basename(job.filePath);
    await prisma.$transaction(async (tx) => {
      await tx.$executeRaw`
        DELETE FROM "KnowledgeChunk"
        WHERE "collectionId" = ${collectionId}
          AND (
            metadata->>'jobId' = ${jobId}
            OR (metadata->>'jobId' IS NULL AND metadata->>'source' = ${srcName})
          )
      `;
      await tx.ingestJob.delete({ where: { id: jobId } });
    });

    await deleteUploadedFile(job.filePath);

    return ok({ deleted: true });
  } catch (err) {
    return handleError(err);
  }
}
