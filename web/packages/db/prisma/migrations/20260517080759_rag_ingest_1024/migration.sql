-- AlterTable
ALTER TABLE "AgentProfile" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- AlterTable
ALTER TABLE "PronunciationEntry" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- CreateTable
CREATE TABLE "IngestJob" (
    "id" TEXT NOT NULL,
    "collectionId" TEXT NOT NULL,
    "fileName" TEXT NOT NULL,
    "filePath" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "error" TEXT,
    "chunkCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "IngestJob_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "IngestJob_status_createdAt_idx" ON "IngestJob"("status", "createdAt");

-- CreateIndex
CREATE INDEX "IngestJob_collectionId_idx" ON "IngestJob"("collectionId");
