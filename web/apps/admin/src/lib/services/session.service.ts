import { prisma } from "@taigi-flow/db";

/**
 * Batch-delete sessions and their child InteractionLogs atomically.
 * Returns the number of sessions deleted.
 */
export async function deleteSessionsBatch(ids: string[]): Promise<number> {
  await prisma.$transaction([
    prisma.interactionLog.deleteMany({ where: { sessionId: { in: ids } } }),
    prisma.session.deleteMany({ where: { id: { in: ids } } }),
  ]);
  return ids.length;
}
