-- EnableExtension
CREATE EXTENSION IF NOT EXISTS vector;

-- CreateTable
CREATE TABLE "AgentProfile" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "systemPrompt" TEXT NOT NULL,
    "voiceConfig" JSONB NOT NULL,
    "ragConfig" JSONB,
    "tools" JSONB NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "AgentProfile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Session" (
    "id" TEXT NOT NULL,
    "agentProfileId" TEXT NOT NULL,
    "livekitRoom" TEXT NOT NULL,
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "endedAt" TIMESTAMP(3),

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "InteractionLog" (
    "id" TEXT NOT NULL,
    "sessionId" TEXT NOT NULL,
    "turnIndex" INTEGER NOT NULL,
    "userAsrText" TEXT NOT NULL,
    "llmRawText" TEXT NOT NULL,
    "hanloText" TEXT,
    "taibunText" TEXT NOT NULL,
    "latencyAsrEnd" INTEGER,
    "latencyLlmFirstTok" INTEGER,
    "latencyFirstAudio" INTEGER,
    "latencyTotal" INTEGER,
    "wasBargedIn" BOOLEAN NOT NULL DEFAULT false,
    "errorFlag" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "InteractionLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PronunciationEntry" (
    "id" TEXT NOT NULL,
    "profileId" TEXT,
    "term" TEXT NOT NULL,
    "replacement" TEXT NOT NULL,
    "priority" INTEGER NOT NULL DEFAULT 0,
    "note" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "PronunciationEntry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "KnowledgeChunk" (
    "id" TEXT NOT NULL,
    "collectionId" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "metadata" JSONB NOT NULL,
    "embedding" vector(1536),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "KnowledgeChunk_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "AgentProfile_name_key" ON "AgentProfile"("name");

-- CreateIndex
CREATE INDEX "Session_livekitRoom_idx" ON "Session"("livekitRoom");

-- CreateIndex
CREATE INDEX "InteractionLog_sessionId_turnIndex_idx" ON "InteractionLog"("sessionId", "turnIndex");

-- CreateIndex
CREATE INDEX "PronunciationEntry_term_idx" ON "PronunciationEntry"("term");

-- CreateIndex
CREATE UNIQUE INDEX "PronunciationEntry_profileId_term_key" ON "PronunciationEntry"("profileId", "term");

-- CreateIndex
CREATE INDEX "KnowledgeChunk_collectionId_idx" ON "KnowledgeChunk"("collectionId");

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_agentProfileId_fkey" FOREIGN KEY ("agentProfileId") REFERENCES "AgentProfile"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "InteractionLog" ADD CONSTRAINT "InteractionLog_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES "Session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
