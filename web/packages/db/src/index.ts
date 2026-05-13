import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";
import { Pool } from "pg";

declare global {
  // eslint-disable-next-line no-var
  var __taigiFlowPrisma: PrismaClient | undefined;
  // eslint-disable-next-line no-var
  var __taigiFlowPgPool: Pool | undefined;
}

function createPrismaClient(): PrismaClient {
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    throw new Error("DATABASE_URL is required");
  }

  const pool = globalThis.__taigiFlowPgPool ?? new Pool({ connectionString: databaseUrl });
  if (process.env.NODE_ENV !== "production") {
    globalThis.__taigiFlowPgPool = pool;
  }

  const adapter = new PrismaPg(pool);
  return new PrismaClient(
    { adapter } as unknown as ConstructorParameters<typeof PrismaClient>[0],
  );
}

export const prisma: PrismaClient =
  globalThis.__taigiFlowPrisma ?? createPrismaClient();

if (process.env.NODE_ENV !== "production") {
  globalThis.__taigiFlowPrisma = prisma;
}

export type {
  AgentProfile,
  Session,
  InteractionLog,
  PronunciationEntry,
  KnowledgeChunk,
  Prisma,
} from "@prisma/client";
