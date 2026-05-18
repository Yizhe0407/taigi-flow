-- EnableExtension: pg_trgm for fuzzy bus stop name search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- HNSW index for KnowledgeChunk vector similarity search (replaces seq scan)
CREATE INDEX IF NOT EXISTS "KnowledgeChunk_embedding_hnsw_idx"
  ON "KnowledgeChunk"
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- AddColumns: RAG quality metrics to InteractionLog
ALTER TABLE "InteractionLog"
  ADD COLUMN "ragHitCount"  INTEGER,
  ADD COLUMN "ragTopSim"    DOUBLE PRECISION,
  ADD COLUMN "latencyRagMs" INTEGER;
