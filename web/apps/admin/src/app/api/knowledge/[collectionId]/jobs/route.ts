import { prisma } from "@taigi-flow/db";
import { handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ collectionId: string }> };

export async function GET(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId } = await params;
    const jobs = await prisma.ingestJob.findMany({
      where: { collectionId },
      orderBy: { createdAt: "desc" },
      take: 100,
      select: {
        id: true,
        fileName: true,
        filePath: true,
        status: true,
        chunkCount: true,
        error: true,
        createdAt: true,
      },
    });
    return ok(jobs);
  } catch (err) {
    return handleError(err);
  }
}
