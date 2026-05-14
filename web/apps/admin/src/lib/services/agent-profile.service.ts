import { prisma } from "@taigi-flow/db";
import type { Prisma } from "@taigi-flow/db";

/**
 * Cascade-delete an AgentProfile together with all its Sessions and InteractionLogs.
 * Prisma does not set up ON DELETE CASCADE in schema, so we handle it manually.
 */
export async function deleteAgentProfileCascade(id: string): Promise<void> {
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
}

/**
 * Update an AgentProfile. When exclusiveActivation is true, deactivates all
 * other profiles in the same transaction so only one can be active at a time.
 */
export async function updateAgentProfile(
  id: string,
  data: Prisma.AgentProfileUpdateInput,
  options: { exclusiveActivation: boolean },
) {
  if (options.exclusiveActivation) {
    return prisma.$transaction(async (tx) => {
      await tx.agentProfile.updateMany({
        where: { id: { not: id } },
        data: { isActive: false },
      });
      return tx.agentProfile.update({ where: { id }, data });
    });
  }
  return prisma.agentProfile.update({ where: { id }, data });
}
