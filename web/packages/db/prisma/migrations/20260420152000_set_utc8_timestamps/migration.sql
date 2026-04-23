ALTER TABLE "AgentProfile"
ALTER COLUMN "createdAt" SET DEFAULT (CURRENT_TIMESTAMP + INTERVAL '8 hours'),
ALTER COLUMN "updatedAt" SET DEFAULT (CURRENT_TIMESTAMP + INTERVAL '8 hours');

ALTER TABLE "Session"
ALTER COLUMN "startedAt" SET DEFAULT (CURRENT_TIMESTAMP + INTERVAL '8 hours');

ALTER TABLE "InteractionLog"
ALTER COLUMN "createdAt" SET DEFAULT (CURRENT_TIMESTAMP + INTERVAL '8 hours');

ALTER TABLE "PronunciationEntry"
ALTER COLUMN "createdAt" SET DEFAULT (CURRENT_TIMESTAMP + INTERVAL '8 hours'),
ALTER COLUMN "updatedAt" SET DEFAULT (CURRENT_TIMESTAMP + INTERVAL '8 hours');

ALTER TABLE "KnowledgeChunk"
ALTER COLUMN "createdAt" SET DEFAULT (CURRENT_TIMESTAMP + INTERVAL '8 hours');

CREATE OR REPLACE FUNCTION set_utc8_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW."updatedAt" = CURRENT_TIMESTAMP + INTERVAL '8 hours';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS "AgentProfile_set_updated_at_utc8" ON "AgentProfile";
CREATE TRIGGER "AgentProfile_set_updated_at_utc8"
BEFORE INSERT OR UPDATE ON "AgentProfile"
FOR EACH ROW
EXECUTE FUNCTION set_utc8_updated_at();

DROP TRIGGER IF EXISTS "PronunciationEntry_set_updated_at_utc8" ON "PronunciationEntry";
CREATE TRIGGER "PronunciationEntry_set_updated_at_utc8"
BEFORE INSERT OR UPDATE ON "PronunciationEntry"
FOR EACH ROW
EXECUTE FUNCTION set_utc8_updated_at();
