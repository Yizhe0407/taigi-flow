import path from "path";

import { prisma } from "@taigi-flow/db";
import { error, handleError, ok } from "@/lib/api";
import { deleteUploadedFile, parseChunkMetadata } from "@/app/api/knowledge/_lib/files";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string; chunkId: string }> };

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId, chunkId } = await params;

    const chunk = await prisma.$queryRaw<
      { id: string; metadata: unknown }[]
    >`
      SELECT id, metadata
      FROM "KnowledgeChunk"
      WHERE id = ${chunkId} AND "collectionId" = ${collectionId}
      LIMIT 1
    `;
    const target = chunk[0];
    if (!target) return error("Chunk not found", 404);

    const metadata = parseChunkMetadata(target.metadata);
    const result = await prisma.$transaction(async (tx) => {
      const deleted = await tx.$executeRaw`
        DELETE FROM "KnowledgeChunk"
        WHERE id = ${chunkId} AND "collectionId" = ${collectionId}
      `;
      if (deleted === 0) {
        throw new Error("Chunk not found");
      }

      let job =
        metadata.jobId
          ? await tx.ingestJob.findFirst({
              where: { id: metadata.jobId, collectionId },
              select: { id: true, filePath: true },
            })
          : null;

      if (!job && metadata.source) {
        const jobs = await tx.ingestJob.findMany({
          where: { collectionId },
          select: { id: true, filePath: true },
        });
        job = jobs.find((item) => path.basename(item.filePath) === metadata.source) ?? null;
      }

      if (!job) {
        return { jobDeleted: false, jobId: null, filePath: null, remainingChunks: null };
      }

      const sourceName = path.basename(job.filePath);
      const remaining = await tx.$queryRaw<{ count: bigint }[]>`
        SELECT COUNT(*)::bigint AS count
        FROM "KnowledgeChunk"
        WHERE "collectionId" = ${collectionId}
          AND (
            metadata->>'jobId' = ${job.id}
            OR (metadata->>'jobId' IS NULL AND metadata->>'source' = ${sourceName})
          )
      `;
      const remainingChunks = remaining[0] ? Number(remaining[0].count) : 0;

      if (remainingChunks === 0) {
        await tx.ingestJob.delete({ where: { id: job.id } });
        return {
          jobDeleted: true,
          jobId: job.id,
          filePath: job.filePath,
          remainingChunks,
        };
      }

      await tx.ingestJob.update({
        where: { id: job.id },
        data: { chunkCount: remainingChunks },
      });

      return {
        jobDeleted: false,
        jobId: job.id,
        filePath: null,
        remainingChunks,
      };
    });

    if (result.filePath) {
      await deleteUploadedFile(result.filePath);
    }

    return ok({ deleted: true, ...result });
  } catch (err) {
    return handleError(err);
  }
}
