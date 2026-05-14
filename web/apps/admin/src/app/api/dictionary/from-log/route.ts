import { pronunciationFromLogSchema } from "@taigi-flow/types";
import { error, handleError, ok, parseJson } from "@/lib/api";
import { upsertEntryFromLog } from "@/lib/services/dictionary.service";

export const dynamic = "force-dynamic";

export async function POST(req: Request): Promise<Response> {
  try {
    const input = await parseJson(req, pronunciationFromLogSchema);
    let result: Awaited<ReturnType<typeof upsertEntryFromLog>>;
    try {
      result = await upsertEntryFromLog(input);
    } catch (e) {
      if (e instanceof Error && e.message === "InteractionLog not found") {
        return error("InteractionLog not found", 404);
      }
      throw e;
    }
    return ok(result.entry, { status: result.created ? 201 : 200 });
  } catch (err) {
    return handleError(err);
  }
}
