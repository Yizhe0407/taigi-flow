import { prisma } from "@taigi-flow/db";
import type { PronunciationEntry } from "@taigi-flow/db";

/**
 * Upsert a PronunciationEntry sourced from an InteractionLog.
 * Resolves profileId from the log's session when not explicitly provided.
 * Returns the entry and whether it was newly created.
 */
type UpsertFromLogInput = {
  logId: string;
  term: string;
  replacement: string;
  priority?: number;
  note?: string | null;
  profileId?: string | null;
};

export async function upsertEntryFromLog(
  input: UpsertFromLogInput,
): Promise<{ entry: PronunciationEntry; created: boolean }> {
  const log = await prisma.interactionLog.findUnique({
    where: { id: input.logId },
    include: { session: { select: { agentProfileId: true } } },
  });
  if (!log) throw new Error("InteractionLog not found");

  const profileId = input.profileId ?? log.session.agentProfileId;
  const priority = input.priority ?? 0;

  const existing = await prisma.pronunciationEntry.findFirst({
    where: { profileId: profileId ?? null, term: input.term },
  });

  const entry = existing
    ? await prisma.pronunciationEntry.update({
        where: { id: existing.id },
        data: {
          replacement: input.replacement,
          priority,
          ...(input.note !== undefined && { note: input.note ?? null }),
        },
      })
    : await prisma.pronunciationEntry.create({
        data: {
          profileId: profileId ?? null,
          term: input.term,
          replacement: input.replacement,
          priority,
          note: input.note ?? null,
        },
      });

  return { entry, created: !existing };
}
