import { z } from "zod";
import { error, handleError, ok, parseJson } from "@/lib/api";

export const dynamic = "force-dynamic";

const querySchema = z.object({
  query: z.string().trim().min(1).max(2000),
  topK: z.coerce.number().int().min(1).max(20).default(3),
  threshold: z.coerce.number().min(0).max(1).default(0.7),
});

type Ctx = { params: Promise<{ collectionId: string }> };

export async function POST(req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId } = await params;
    const input = await parseJson(req, querySchema);
    const baseUrl = process.env.RAG_RETRIEVAL_URL ?? "http://127.0.0.1:8765";

    let res: globalThis.Response;
    try {
      res = await fetch(`${baseUrl.replace(/\/$/, "")}/rag/query`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          collectionId,
          query: input.query,
          topK: input.topK,
          threshold: input.threshold,
        }),
        signal: AbortSignal.timeout(30_000),
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "unknown error";
      return error(`RAG retrieval service unavailable: ${message}`, 503);
    }

    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const message =
        data && typeof data.error === "string" ? data.error : "RAG query failed";
      return error(message, res.status);
    }

    return ok(data);
  } catch (err) {
    return handleError(err);
  }
}
