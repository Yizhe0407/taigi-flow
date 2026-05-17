-- Resize embedding column from vector(1536) to vector(1024) for Qwen3/BGE-M3.
-- Existing rows (if any) must be re-embedded after this migration.
ALTER TABLE "KnowledgeChunk" DROP COLUMN IF EXISTS embedding;
ALTER TABLE "KnowledgeChunk" ADD COLUMN embedding vector(1024);

-- HNSW index for fast cosine similarity search.
CREATE INDEX IF NOT EXISTS "KnowledgeChunk_embedding_hnsw_idx"
ON "KnowledgeChunk"
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
