import { Prisma, prisma } from "@taigi-flow/db";
import { agentProfileUpdateSchema } from "@taigi-flow/types";
import { error, handleError, ok, parseJson } from "@/lib/api";
import {
  deleteAgentProfileCascade,
  updateAgentProfile,
} from "@/lib/services/agent-profile.service";

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
      ...(input.ragConfig !== undefined && {
        ragConfig: input.ragConfig === null ? Prisma.DbNull : input.ragConfig,
      }),
      ...(input.tools !== undefined && { tools: input.tools }),
      ...(input.isActive !== undefined && { isActive: input.isActive }),
    };

    if (input.isActive === false) {
      const current = await prisma.agentProfile.findUnique({
        where: { id },
        select: { isActive: true },
      });
      if (current?.isActive) {
        const otherActiveCount = await prisma.agentProfile.count({
          where: { isActive: true, id: { not: id } },
        });
        if (otherActiveCount === 0) {
          return error("至少須有一個啟用中的 Role，無法停用", 409);
        }
      }
    }

    const profile = await updateAgentProfile(id, updateData, {
      exclusiveActivation: input.isActive === true,
    });

    return ok(profile);
  } catch (err) {
    return handleError(err);
  }
}

export async function DELETE(_req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { id } = await params;
    const profile = await prisma.agentProfile.findUnique({
      where: { id },
      select: { isActive: true },
    });
    if (!profile) return error("AgentProfile not found", 404);
    if (profile.isActive) {
      return error("無法刪除啟用中的 Role，請先啟用另一個 Role", 409);
    }

    const activeSessionCount = await prisma.session.count({
      where: { agentProfileId: id, endedAt: null },
    });
    if (activeSessionCount > 0) {
      return error(`此 Role 有 ${activeSessionCount} 個進行中 Session，無法刪除`, 409);
    }

    await deleteAgentProfileCascade(id);
    return ok({ ok: true });
  } catch (err) {
    return handleError(err);
  }
}
