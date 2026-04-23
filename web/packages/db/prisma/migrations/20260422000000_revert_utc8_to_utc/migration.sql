-- Revert column defaults from UTC+8 back to UTC (CURRENT_TIMESTAMP).
-- Also drops the redundant set_utc8_updated_at trigger; Prisma @updatedAt handles updatedAt.

ALTER TABLE "AgentProfile"
ALTER COLUMN "createdAt" SET DEFAULT CURRENT_TIMESTAMP,
ALTER COLUMN "updatedAt" SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE "Session"
ALTER COLUMN "startedAt" SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE "InteractionLog"
ALTER COLUMN "createdAt" SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE "PronunciationEntry"
ALTER COLUMN "createdAt" SET DEFAULT CURRENT_TIMESTAMP,
ALTER COLUMN "updatedAt" SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE "KnowledgeChunk"
ALTER COLUMN "createdAt" SET DEFAULT CURRENT_TIMESTAMP;

DROP TRIGGER IF EXISTS "AgentProfile_set_updated_at_utc8" ON "AgentProfile";
DROP TRIGGER IF EXISTS "PronunciationEntry_set_updated_at_utc8" ON "PronunciationEntry";
DROP FUNCTION IF EXISTS set_utc8_updated_at();
