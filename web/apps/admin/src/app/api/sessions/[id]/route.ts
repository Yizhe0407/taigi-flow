import { prisma } from "@taigi-flow/db";
import { handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { id } = await params;
    await prisma.$transaction([
      prisma.interactionLog.deleteMany({ where: { sessionId: id } }),
      prisma.session.delete({ where: { id } }),
    ]);
    return ok({ deleted: id });
  } catch (err) {
    return handleError(err);
  }
}
