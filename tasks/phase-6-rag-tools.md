# Phase 6：RAG（Week 7）

> **前置**：Phase 5 完成
>
> **交付物**：Agent 能查知識庫（自然語言文件，PDF / MD / TXT）
>
> **方向**：本 Phase **純 RAG**。Function Calling 基礎 + 公車資料底層 + Tools 全部移到 Phase 6.4
>
> **對應 plan.md**：`AgentProfile.ragConfig`

---

## 現況盤點

**已存在**
- `AgentProfile.ragConfig` Json?, `tools` Json（schema 已就位）
- `KnowledgeChunk` 表 + `Unsupported("vector(1536)")` 欄位
- `worker/pipeline/llm.py:45` `stream()` 已接 `tools` 參數
- `worker/tools/__init__.py` 空殼

**缺**
- `worker/pipeline/rag.py`
- `web/apps/admin/src/app/knowledge/**`
- pgvector HNSW index migration + 維度從 1536 → 1024

**移到 Phase 6.4**
- `worker/tools/base.py`、`worker/tools/__init__.py` registry
- function calling 迴圈（`pipeline/llm.py` 擴）
- TDX realtime tool

---

## 什麼內容適合放 RAG（重要！）

**RAG 的本質**：用 embedding 做**語意相似度**檢索。適合「使用者用自然語言問、答案藏在一段文字裡」的場景。

### ✅ 適合放 RAG（自然語言、語意檢索）

| 類型 | 範例 | 為何適合 |
|------|------|---------|
| 路線/景點**介紹** | 「Y02 北港虎尾線經過北港朝天宮，是雲林重要的觀光路線…」 | 自然語言描述 |
| 票價/優惠**規則** | 「敬老票須年滿 65 歲、持證上車…」 | 規則文字、條件多 |
| **公告 / 異動**通知 | 「3/22 起 Y02 暫時停駛斗六大學站」 | 時間性說明 |
| **FAQ** | 「Q: 雨天會誤點嗎？A: …」 | 問答配對天生適合語意檢索 |
| **觀光景點**介紹 | 「北港朝天宮：媽祖信仰中心，每年農曆三月遶境…」 | 配合地圖 phase 6.5 |
| 地方**文史 / 文化**素材 | 「斗六舊稱『斗六門』，名稱由來…」 | 台語 agent 講地方故事 |
| **使用說明 / 教學** | 「如何用悠遊卡搭雲林客運：…」 | 步驟說明 |

### ❌ 不適合放 RAG（結構化、時效性、精確查詢）

| 你的檔案 | 為何不適合 | 應改走 |
|---------|-----------|--------|
| `route.json` 路線元資料 | 結構化、需精確 JOIN | PostgreSQL 表 + `tools/bus.py` 查詢 tool |
| `stop.json` 站點 | 結構化 + 經緯度 | PostgreSQL 表（可考慮 PostGIS geography 欄位） |
| `stop_of_route.json` 路線停靠序列 | 關聯資料 | DB 關聯表 |
| `schedule.json` 班表 | 結構化、會變動 | DB 表 + 定期同步 |
| `realtime.json` 即時到站 | 每分鐘變 | **不存任何地方**，TDX API 即時打 |

### 三種資料的處理流程對照

```
自然語言 PDF/MD ──→ chunk + embed ──→ KnowledgeChunk ──→ RAG 檢索（本 Phase）
結構化 JSON     ──→ importer    ──→ DB 表           ──→ Bus tool（Phase 6.4）
即時 API        ──→ HTTP 直打 TDX                    ──→ Tool call（Phase 6.4）
```

### 本 Phase 應蒐集的 RAG 內容（建議）

- 雲林觀光局景點介紹（PDF / 網頁爬）
- 客運官網 FAQ 頁
- 路線**敘述性**介紹（不是元資料 JSON，是「Y02 北港虎尾線是…」這種描述）
- 地方文史素材（搭配台語 agent 講地方故事的特色）

> 你已蒐集的雲林客運 JSON / zip / realtime → 全部走 Phase 6.4，不在本 Phase。

---

## Embedding 模型選型（開源，速度 × 準確率 Pareto）

**需求**：開源、台語/中文準確率高、單 worker 進程 CPU 可跑、延遲 <100ms

| 模型 | 參數量 | 維度 | CPU 延遲* | MTEB-zh | 備註 |
|------|--------|------|-----------|---------|------|
| **Qwen3-Embedding-0.6B** ★ | 600M | 1024 | ~80ms | top tier（2025 mid 發布即登頂） | 主推 |
| **BGE-M3** | 568M | 1024 | ~50ms | 強（成熟、文件多） | 備援 |
| `multilingual-e5-large-instruct` | 560M | 1024 | ~50ms | 強，但中文略遜 BGE-M3 | — |
| `multilingual-e5-small` | 118M | 384 | ~10ms | 中，犧牲準確率換速度 | 低資源時備援 |

*單句 ~50 字、CPU 單執行緒估值，實測為準

**結論**：
- **首選 Qwen3-Embedding-0.6B**。MTEB 中文榜單目前 SOTA 級，1024 維對齊規畫
- **備援 BGE-M3**。若 Qwen3 在 sentence-transformers / HF transformers 整合卡關，無痛切換（同維度）
- 兩者 schema 都改 `vector(1024)`，一次 migrate

**Schema migration**（必做）：

```sql
ALTER TABLE "KnowledgeChunk" DROP COLUMN embedding;
ALTER TABLE "KnowledgeChunk" ADD COLUMN embedding vector(1024);
```

Prisma schema 同步改 `Unsupported("vector(1024)")`。

**為何不選 OpenAI**：使用者明示避免付費 API。Qwen3 / BGE-M3 在中文場景已可比擬 `text-embedding-3-small`，無理由犧牲開源原則。

---

## 實作順序

**P6-01 → P6-02**

（Function calling / Tools 全部到 Phase 6.4）

---

## 任務清單

### P6-01：RAG 上傳與索引（核心）

**架構決策**：embedding 跑在 **worker 側**（避免 admin 載 600M 模型 + Node 端無成熟 transformers）

```
Admin（上傳 UI） → 暫存檔案 + 寫 IngestJob → Worker（CLI 或常駐 ingest task） → 切塊 + embed + 寫 KnowledgeChunk
```

兩種接法（擇一）：

| 接法 | 優點 | 缺點 |
|------|------|------|
| **A. Admin 寫 IngestJob 表，Worker 輪詢** | UX 完整、admin 一鍵上傳 | 多一張表 + 輪詢 |
| **B. Admin 上傳 → 顯示 CLI 指令給人類執行** | 零額外服務 | UX 醜，要 ssh 進 worker |

**建議 A**（專題交付需 demo 流暢）。

- [x] **Schema 加 IngestJob**：

  ```prisma
  model IngestJob {
    id           String   @id @default(uuid())
    collectionId String
    filePath     String
    status       String   // pending | processing | done | failed
    error        String?
    chunkCount   Int      @default(0)
    createdAt    DateTime @default(now())
    updatedAt    DateTime @updatedAt
    @@index([status, createdAt])
  }
  ```

- [x] **Admin 路由**：`web/apps/admin/src/app/knowledge/`

  ```
  page.tsx                          # collection list（按 AgentProfile 分組）
  [collectionId]/
    page.tsx                        # chunk list + IngestJob 狀態 + upload form
    upload/route.ts                 # POST multipart → 存檔到 shared volume → 建 IngestJob
    chunks/[chunkId]/route.ts       # DELETE
  ```

- [x] **Worker ingest task**：`worker/worker/ingest/`

  ```
  __init__.py
  runner.py           # 輪詢 IngestJob WHERE status='pending'
  chunker.py          # PDF / MD / TXT → list[Chunk]
  embedder.py         # 載入 Qwen3-Embedding-0.6B（或 BGE-M3），batch encode
  ```

  - 啟動模式：`uv run python -m worker.ingest`（與主 worker 同進程或獨立 process 皆可，建議獨立避免阻塞語音 pipeline）
- [x] **切塊策略**：
  - PDF：`pypdf` → 純文字 → 段落切（`\n\n` 分），每塊 max 500 字
  - MD / TXT：同上，跳過 PDF 步驟
  - 不要硬按字數切（會切壞句子），先按段落、超長再 fallback 字數切
  - **chunk overlap**：相鄰塊重疊 50 字
- [x] **Collection**：string id = profile id 直接綁，不另開 `Collection` 表
- [x] **Embedding 載入**：模型啟動時載入一次（~2GB RAM），常駐記憶體
  - `sentence-transformers` 載 `Qwen/Qwen3-Embedding-0.6B`（或 `BAAI/bge-m3`）
  - batch size 32 / call（CPU 友善）
  - 失敗 retry 3 次（exponential backoff）
- [x] **寫入 pgvector**：SQLAlchemy `text()` + `pgvector.sqlalchemy` 適配器

  ```python
  from pgvector.sqlalchemy import Vector
  await session.execute(
      text("""INSERT INTO "KnowledgeChunk" ... VALUES (..., :vec)"""),
      {"vec": embedding_array}
  )
  ```

  （Worker 用 SQLAlchemy，本就不走 Prisma client，避開 `Unsupported` 問題）

- [x] **Index migration**：

  ```sql
  CREATE INDEX ON "KnowledgeChunk"
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
  ```

  HNSW 比 ivfflat 在小資料集（< 10K chunks）召回率高、建構快。若 pgvector 版本 < 0.5，退回 ivfflat

- [x] **UI 功能**：
  - 上傳後即時看 IngestJob 狀態（pending → processing → done）
  - chunk 列表預覽（content 前 200 字 + metadata.source + 頁碼）
  - 刪除單一 chunk / 整個 collection
- [ ] **Commit**：
  - `feat(db): add ingest job table and bump embedding dim to 1024`
  - `feat(worker): add ingest task with qwen3 / bge-m3 embedder`
  - `feat(admin): add knowledge base upload UI`

---

### P6-02：RAG 檢索整合（核心）

- [x] **檔**：`worker/worker/pipeline/rag.py`

  ```python
  class RagRetriever:
      def __init__(self, embedder, db, collection_id, top_k=3, threshold=0.7): ...
      async def retrieve(self, query: str) -> list[str]:
          vec = await self.embedder.embed(query)   # 同 ingest 用的模型
          rows = await db.execute(text("""
              SELECT content, 1 - (embedding <=> :vec::vector) AS sim
              FROM "KnowledgeChunk"
              WHERE "collectionId" = :cid
              ORDER BY embedding <=> :vec::vector
              LIMIT :k
          """), {...})
          return [r.content for r in rows if r.sim >= threshold]
  ```

  **關鍵**：retrieval 端的 embedder 必須與 ingest 端**同一個模型**，否則向量空間不一致 → 檢索全爛

- [x] **注入 prompt**：retriever 結果加在 user message 前（system message 之後）：

  ```
  參考資料：
  1. <chunk1>
  2. <chunk2>
  若以上資料無相關，正常回答即可。
  ```

- [x] **觸發策略**：方案 A（每 turn 都檢索）
  - embedding ~50-80ms + pgvector ~20ms = 100ms 內可接受
  - first_audio 預算（2s）扣除：VAD 500 + ASR 300 + RAG 100 + LLM 400 + TTS 300 = 1.6s，仍在範圍
  - 後續可改 LLM router（方案 B），但 Phase 6 不做
- [x] **啟用條件**：`AgentProfile.ragConfig.enabled === true` 且 `collectionId` 存在
  - 否則 retriever = None，零開銷
- [x] **AgentProfile.ragConfig 結構**：

  ```json
  { "enabled": true, "topK": 3, "threshold": 0.7, "collectionId": "<profile-id>" }
  ```

- [x] **Admin UI 整合**：Agent 編輯頁加 RAG 設定區塊（啟用開關、topK、threshold、選 collection）
- [x] **Log**：每 turn 記 `rag_hit_count`, `rag_top_sim`, `latency_rag_ms`（觀察品質）
- [ ] **Commit**：`feat(worker): integrate rag retrieval into pipeline`

---

## 已知 Gotcha

- **Prisma + pgvector**：`Unsupported("vector(1024)")` 不能用 prisma client 寫入，全走 `$executeRaw` / `$queryRaw`
- **pgvector 字串格式**：embedding 餵入需 `[0.1,0.2,...]` 字串（非 array）
- **ivfflat index 需資料**：index 建立後若資料量 < 1000 chunks，效能差異不明顯；專題規模可接受
- **chunk overlap**：太大（>100 字）會放大重複內容、稀釋 top-K；50 字是經驗值
- **Next.js 16 params**：`/knowledge/[collectionId]/page.tsx` 記得 `const { collectionId } = await params`
- **OpenAI key 不可進 client**：embedding 一定走 `api/embeddings/route.ts` 代理

---

## Embedding 模型操作備忘

**首次啟動**
- Qwen3-Embedding-0.6B：HF 下載 ~1.2GB，啟動載入 ~10s，RAM 占用 ~2GB
- BGE-M3：HF 下載 ~2.2GB，啟動載入 ~15s，RAM 占用 ~3GB
- 模型快取在 `~/.cache/huggingface/`，docker 部署需 mount 持久化

**Qwen3 → BGE-M3 切換**
1. 改 `embedder.py` 內模型名稱（`Qwen/Qwen3-Embedding-0.6B` → `BAAI/bge-m3`）
2. **務必重跑全部 chunks 的 embedding**（向量空間不同）
3. 維度同為 1024，schema 不動

**已既有 chunks 換模型流程**
```bash
# 1. 清空 embedding 欄位
psql -c 'UPDATE "KnowledgeChunk" SET embedding = NULL;'
# 2. 重跑 ingest（讀回 content，重 embed，寫回）
uv run python -m worker.ingest --reembed-all
```

**Inference 加速選項**（若 CPU 不夠快）
- ONNX 匯出：`optimum-cli export onnx --model Qwen/Qwen3-Embedding-0.6B`，速度 ~2x
- GPU 跑：worker 載 CUDA 版 torch，~5-10ms / query
- 不建議量化（int8 對 embedding 品質影響大）

---

## Phase 6 完成標準

- [x] Admin 上傳 1 個 PDF → chunk list 顯示 N 塊、embedding 寫入成功
- [x] Agent 啟用 RAG 後，問 PDF 內容相關問題 → 回答引用 chunk 內容
- [x] `ragConfig.enabled = false` 時零 embedding 呼叫（log 觀察）
- [x] RAG 不相關問題（如「今天天氣？」）不會強行塞參考資料（threshold 過濾）

---

## 時程壓力時的取捨

- **最低限**：完成 P6-01 + P6-02 即收工，進 Phase 6.4
- **全砍**：若 Phase 5 嚴重拖延，整個 Phase 6 跳過、直接進 6.4 / 6.5（plan.md L1089 允許）
