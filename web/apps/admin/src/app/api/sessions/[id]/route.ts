import { prisma } from "@taigi-flow/db";
import { handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: { id: string } };

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    await prisma.$transaction([
      prisma.interactionLog.deleteMany({ where: { sessionId: params.id } }),
      prisma.session.delete({ where: { id: params.id } }),
    ]);
    return ok({ deleted: params.id });
  } catch (err) {
    return handleError(err);
  }
}
