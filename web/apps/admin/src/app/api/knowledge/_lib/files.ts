import { unlink } from "fs/promises";

export type ChunkMetadata = {
  jobId?: string;
  source?: string;
};

export function parseChunkMetadata(metadata: unknown): ChunkMetadata {
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    return {};
  }

  const record = metadata as Record<string, unknown>;
  return {
    jobId: typeof record.jobId === "string" ? record.jobId : undefined,
    source: typeof record.source === "string" ? record.source : undefined,
  };
}

export async function deleteUploadedFile(filePath: string): Promise<void> {
  try {
    await unlink(filePath);
  } catch (err) {
    const code = (err as NodeJS.ErrnoException | undefined)?.code;
    if (code !== "ENOENT") throw err;
  }
}
