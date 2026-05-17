import { prisma } from "@taigi-flow/db";
import { handleError, ok } from "@/lib/api";
import { deleteUploadedFile } from "@/app/api/knowledge/_lib/files";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string }> };

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId } = await params;

    const jobs = await prisma.ingestJob.findMany({
      where: { collectionId },
      select: { filePath: true },
    });

    await prisma.$transaction(async (tx) => {
      await tx.$executeRaw`
        DELETE FROM "KnowledgeChunk" WHERE "collectionId" = ${collectionId}
      `;
      await tx.ingestJob.deleteMany({ where: { collectionId } });
    });

    await Promise.allSettled(jobs.map((job) => deleteUploadedFile(job.filePath)));

    return ok({ deleted: true });
  } catch (err) {
    return handleError(err);
  }
}
