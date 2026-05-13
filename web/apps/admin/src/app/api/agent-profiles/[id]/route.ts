import { prisma } from "@taigi-flow/db";
import { agentProfileUpdateSchema } from "@taigi-flow/types";
import { error, handleError, ok, parseJson } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { id } = await params;
    const profile = await prisma.agentProfile.findUnique({ where: { id } });
    if (!profile) return error("AgentProfile not found", 404);
    return ok(profile);
  } catch (err) {
    return handleError(err);
  }
}

export async function PUT(req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { id } = await params;
    const input = await parseJson(req, agentProfileUpdateSchema);

    const updateData = {
      ...(input.name !== undefined && { name: input.name }),
      ...(input.description !== undefined && { description: input.description }),
      ...(input.systemPrompt !== undefined && { systemPrompt: input.systemPrompt }),
      ...(input.voiceConfig !== undefined && { voiceConfig: input.voiceConfig }),
      ...(input.ragConfig !== undefined && { ragConfig: input.ragConfig ?? undefined }),
      ...(input.tools !== undefined && { tools: input.tools }),
      ...(input.isActive !== undefined && { isActive: input.isActive }),
    };

    const profile = await prisma.$transaction(async (tx) => {
      if (input.isActive === true) {
        await tx.agentProfile.updateMany({
          where: { id: { not: id } },
          data: { isActive: false },
        });
      }
      return tx.agentProfile.update({ where: { id }, data: updateData });
    });

    return ok(profile);
  } catch (err) {
    return handleError(err);
  }
}

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { id } = await params;
    await prisma.$transaction(async (tx) => {
      const sessionIds = (
        await tx.session.findMany({ where: { agentProfileId: id }, select: { id: true } })
      ).map((s) => s.id);
      if (sessionIds.length > 0) {
        await tx.interactionLog.deleteMany({ where: { sessionId: { in: sessionIds } } });
        await tx.session.deleteMany({ where: { id: { in: sessionIds } } });
      }
      await tx.agentProfile.delete({ where: { id } });
    });
    return ok({ ok: true });
  } catch (err) {
    return handleError(err);
  }
}
