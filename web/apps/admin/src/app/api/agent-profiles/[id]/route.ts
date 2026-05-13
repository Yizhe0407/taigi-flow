import { prisma } from "@taigi-flow/db";
import { agentProfileUpdateSchema } from "@taigi-flow/types";
import { error, handleError, ok, parseJson } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: { id: string } };

export async function GET(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const profile = await prisma.agentProfile.findUnique({ where: { id: params.id } });
    if (!profile) return error("AgentProfile not found", 404);
    return ok(profile);
  } catch (err) {
    return handleError(err);
  }
}

export async function PUT(req: Request, { params }: Ctx): Promise<Response> {
  try {
    const input = await parseJson(req, agentProfileUpdateSchema);
    const profile = await prisma.agentProfile.update({
      where: { id: params.id },
      data: {
        ...(input.name !== undefined && { name: input.name }),
        ...(input.description !== undefined && { description: input.description }),
        ...(input.systemPrompt !== undefined && { systemPrompt: input.systemPrompt }),
        ...(input.voiceConfig !== undefined && { voiceConfig: input.voiceConfig }),
        ...(input.ragConfig !== undefined && { ragConfig: input.ragConfig ?? undefined }),
        ...(input.tools !== undefined && { tools: input.tools }),
        ...(input.isActive !== undefined && { isActive: input.isActive }),
      },
    });
    return ok(profile);
  } catch (err) {
    return handleError(err);
  }
}

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    await prisma.agentProfile.delete({ where: { id: params.id } });
    return ok({ ok: true });
  } catch (err) {
    return handleError(err);
  }
}
