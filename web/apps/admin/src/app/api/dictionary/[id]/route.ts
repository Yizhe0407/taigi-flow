import { prisma } from "@taigi-flow/db";
import { pronunciationUpdateSchema } from "@taigi-flow/types";
import { error, handleError, ok, parseJson } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

export async function PUT(req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { id } = await params;
    const input = await parseJson(req, pronunciationUpdateSchema);

    if (input.profileId) {
      const profile = await prisma.agentProfile.findUnique({ where: { id: input.profileId }, select: { id: true } });
      if (!profile) return error("AgentProfile not found", 404);
    }

    const entry = await prisma.pronunciationEntry.update({
      where: { id },
      data: {
        ...(input.profileId !== undefined && { profileId: input.profileId ?? null }),
        ...(input.term !== undefined && { term: input.term }),
        ...(input.replacement !== undefined && { replacement: input.replacement }),
        ...(input.priority !== undefined && { priority: input.priority }),
        ...(input.note !== undefined && { note: input.note ?? null }),
      },
    });
    return ok(entry);
  } catch (err) {
    return handleError(err);
  }
}

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { id } = await params;
    await prisma.pronunciationEntry.delete({ where: { id } });
    return ok({ ok: true });
  } catch (err) {
    return handleError(err);
  }
}
