import { prisma } from "@taigi-flow/db";
import { pronunciationUpdateSchema } from "@taigi-flow/types";
import { handleError, ok, parseJson } from "@/lib/api";

export const dynamic = "force-dynamic";

type Ctx = { params: { id: string } };

export async function PUT(req: Request, { params }: Ctx): Promise<Response> {
  try {
    const input = await parseJson(req, pronunciationUpdateSchema);
    const entry = await prisma.pronunciationEntry.update({
      where: { id: params.id },
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
    await prisma.pronunciationEntry.delete({ where: { id: params.id } });
    return ok({ ok: true });
  } catch (err) {
    return handleError(err);
  }
}
