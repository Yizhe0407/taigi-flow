import { prisma } from "@taigi-flow/db";
import type { Prisma } from "@taigi-flow/db";
import { deleteUploadedFile } from "@/app/api/knowledge/_lib/files";

/**
 * Cascade-delete an AgentProfile together with all its Sessions and InteractionLogs.
 * Prisma does not set up ON DELETE CASCADE in schema, so we handle it manually.
 */
export async function deleteAgentProfileCascade(id: string): Promise<void> {
  const ingestJobs = await prisma.ingestJob.findMany({
    where: { collectionId: id },
    select: { filePath: true },
  });

  await prisma.$transaction(async (tx) => {
    const sessionIds = (
      await tx.session.findMany({ where: { agentProfileId: id }, select: { id: true } })
    ).map((s) => s.id);
    if (sessionIds.length > 0) {
      await tx.interactionLog.deleteMany({ where: { sessionId: { in: sessionIds } } });
      await tx.session.deleteMany({ where: { id: { in: sessionIds } } });
    }
    await tx.pronunciationEntry.deleteMany({ where: { profileId: id } });
    await tx.$executeRaw`
      DELETE FROM "KnowledgeChunk" WHERE "collectionId" = ${id}
    `;
    await tx.ingestJob.deleteMany({ where: { collectionId: id } });
    await tx.agentProfile.delete({ where: { id } });
  });

  const fileResults = await Promise.allSettled(
    ingestJobs.map((job) => deleteUploadedFile(job.filePath)),
  );
  const failedPaths = ingestJobs
    .map((job, i) => (fileResults[i]!.status === "rejected" ? job.filePath : null))
    .filter(Boolean);
  if (failedPaths.length > 0) {
    console.error("[deleteAgentProfileCascade] failed to delete files:", failedPaths);
  }
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

/**
 * Create an AgentProfile. When the new profile is active, deactivate all
 * others atomically — required because the DB has a partial unique index
 * preventing more than one active profile at a time.
 */
export async function createAgentProfile(data: Prisma.AgentProfileCreateInput) {
  if (data.isActive === true) {
    return prisma.$transaction(async (tx) => {
      await tx.agentProfile.updateMany({
        where: { isActive: true },
        data: { isActive: false },
      });
      return tx.agentProfile.create({ data });
    });
  }
  return prisma.agentProfile.create({ data });
}
