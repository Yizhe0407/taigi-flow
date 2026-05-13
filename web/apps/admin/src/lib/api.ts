import { NextResponse } from "next/server";
import { ZodError, type ZodSchema } from "zod";

export function ok<T>(data: T, init?: ResponseInit): NextResponse {
  return NextResponse.json(data, init);
}

export function error(message: string, status = 400, extra?: unknown): NextResponse {
  return NextResponse.json({ error: message, details: extra }, { status });
}

export async function parseJson<T>(req: Request, schema: ZodSchema<T>): Promise<T> {
  const body = await req.json().catch(() => null);
  return schema.parse(body);
}

export function handleError(err: unknown): NextResponse {
  if (err instanceof ZodError) {
    return error("Validation failed", 400, err.flatten());
  }
  if (err instanceof Error) {
    if (err.message.includes("Record to") || err.message.includes("not found")) {
      return error(err.message, 404);
    }
    if (err.message.includes("Unique constraint")) {
      return error("Duplicate entry", 409, err.message);
    }
    return error(err.message, 500);
  }
  return error("Unknown error", 500);
}
