import { prisma } from "@taigi-flow/db";
import { pronunciationFromLogSchema } from "@taigi-flow/types";
import { error, handleError, ok, parseJson } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST(req: Request): Promise<Response> {
  try {
    const input = await parseJson(req, pronunciationFromLogSchema);

    const log = await prisma.interactionLog.findUnique({
      where: { id: input.logId },
      include: { session: { select: { agentProfileId: true } } },
    });
    if (!log) return error("InteractionLog not found", 404);

    const profileId =
      input.profileId === undefined ? log.session.agentProfileId : input.profileId;

    const existing = await prisma.pronunciationEntry.findFirst({
      where: { profileId: profileId ?? null, term: input.term },
    });

    const entry = existing
      ? await prisma.pronunciationEntry.update({
          where: { id: existing.id },
          data: {
            replacement: input.replacement,
            priority: input.priority,
            ...(input.note !== undefined && { note: input.note ?? null }),
          },
        })
      : await prisma.pronunciationEntry.create({
          data: {
            profileId: profileId ?? null,
            term: input.term,
            replacement: input.replacement,
            priority: input.priority,
            note: input.note ?? null,
          },
        });

    return ok(entry, { status: existing ? 200 : 201 });
  } catch (err) {
    return handleError(err);
  }
}
