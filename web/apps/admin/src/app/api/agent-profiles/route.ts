import { prisma } from "@taigi-flow/db";
import { agentProfileCreateSchema } from "@taigi-flow/types";
import { handleError, ok, parseJson } from "@/lib/api";
import { createAgentProfile } from "@/lib/services/agent-profile.service";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  try {
    const profiles = await prisma.agentProfile.findMany({
      orderBy: { createdAt: "desc" },
    });
    return ok(profiles);
  } catch (err) {
    return handleError(err);
  }
}

export async function POST(req: Request): Promise<Response> {
  try {
    const input = await parseJson(req, agentProfileCreateSchema);
    const profile = await createAgentProfile({
      name: input.name,
      description: input.description ?? null,
      systemPrompt: input.systemPrompt,
      voiceConfig: input.voiceConfig,
      ragConfig: input.ragConfig ?? undefined,
      tools: input.tools ?? [],
      isActive: input.isActive,
    });
    return ok(profile, { status: 201 });
  } catch (err) {
    return handleError(err);
  }
}
