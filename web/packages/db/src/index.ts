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

// Lazy init: defer createPrismaClient() until first property access so that
// importing this module during Next.js build-time page collection (worker_threads
// without inherited env) does not throw before any DB call is made.
let _instance: PrismaClient | undefined;

function getClient(): PrismaClient {
  if (!_instance) {
    _instance = globalThis.__taigiFlowPrisma ?? createPrismaClient();
    if (process.env.NODE_ENV !== "production") {
      globalThis.__taigiFlowPrisma = _instance;
    }
  }
  return _instance;
}

export const prisma = new Proxy({} as PrismaClient, {
  get(_, prop) {
    return Reflect.get(getClient(), prop as string);
  },
}) as PrismaClient;

export { Prisma } from "@prisma/client";

export type {
  AgentProfile,
  Session,
  InteractionLog,
  PronunciationEntry,
  KnowledgeChunk,
} from "@prisma/client";
