# ADR-003: 業務設定入 PostgreSQL，基礎設施保留 .env

- **狀態**：Accepted
- **日期**：2026-04-18
- **決策者**：[專題團隊]

## 背景

傳統做法會把 Agent 人格、系統提示、工具開關都放在 `.env` 檔或 YAML 設定檔中。但本系統需要：

1. 後台管理者能熱更新人格設定，不重啟服務
2. 在對話過程中修正發音字典，即時生效
3. 保留對話日誌以便除錯
4. 支援 RAG 向量檢索

使用檔案設定無法滿足 1–3，且需要額外引入向量 DB 才能滿足 4。

## 決策

採用「雙軌制」：

- **業務層資料進 PostgreSQL + pgvector**
  - `AgentProfile`（人格、系統提示、工具開關、人聲設定）
  - `PronunciationEntry`（發音字典）
  - `InteractionLog`（對話日誌）
  - `KnowledgeChunk`（RAG 向量）
  - `Session`（對話 session 元資料）

- **基礎設施層設定留 `.env`**
  - `DATABASE_URL`
  - `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`
  - `OPENAI_API_KEY`
  - `TDX_CLIENT_ID` / `TDX_CLIENT_SECRET`
  - `ASR_BACKEND`（`qwen3` or `breeze26`）

## 理由

1. **熱更新需求**：Agent 人格、字典、工具開關必須能在不重啟 worker 的情況下修改生效。DB 支援事務性更新 + 應用端快取失效策略，檔案設定做不到。

2. **後台 UI 依賴**：管理者透過 Admin Panel 編輯內容，本質上是 CRUD 操作，DB 是最自然的儲存層。

3. **關聯查詢**：字典可以「全域 / Agent 專屬」分層、InteractionLog 可以按 session 聚合查詢，這些關聯需求檔案設計不適合。

4. **單一 DB 解決多需求**：pgvector 作為 PostgreSQL 擴充，同一個資料庫即可同時支援關聯資料與向量檢索，無須引入 Qdrant / Weaviate。

5. **安全性**：API Key 這類機敏資訊不應進 DB（DB 備份、查詢日誌都可能洩漏），留在 env + 系統環境變數更安全。

## 替代方案

### 全進 DB（包括 API Key）
**優點**：單一事實來源
**缺點**：
- API Key 洩漏風險大（DB dump / backup / 查詢 log）
- Bootstrap 問題：worker 要連 DB 才能取 `DATABASE_URL`，循環依賴
- 啟動順序複雜

### 全用 YAML / TOML 檔
**優點**：版本控管方便、可 diff
**缺點**：
- 不支援熱更新（除非自幹檔案監測機制）
- 並發安全難保證（多寫者衝突）
- RAG 向量需求仍要另一個系統
- 後台 UI 要做檔案編輯會很難用

### 檔案 + Redis
**優點**：熱更新快
**缺點**：
- 多一個儲存系統需維護
- 持久性要額外考量
- 關聯查詢能力弱

## 「業務 vs 基礎設施」的判斷準則

未來新增設定時依此決定放哪：

放 **DB**：
- 非技術人員會調整的（人格、提示詞、字典）
- 需要版本/審計的（誰改了什麼）
- 需要關聯查詢的（日誌、統計）
- 動態內容（RAG 文件）

放 **.env**：
- 機敏資訊（API Key、密碼）
- 部署環境相關（資料庫位址、外部服務 URL）
- 程式啟動時才需要讀的（backend 選擇、功能旗標）
- 變更頻率極低且變更必須重啟服務的

## 後果

✅ **正面**：
- 後台管理功能自然落地
- 單一資料庫涵蓋多需求，部署簡單
- API Key 保持在安全位置

⚠️ **負面**：
- DB schema 設計需要前期投入
- 前端需要管理後台 UI
- 熱更新快取失效機制需要設計（例如透過 Redis pub/sub 通知 worker 清除字典快取）

## 相關文件

- `docs/plan.md §2` — 完整 Prisma schema
- `tasks/phase-0-infrastructure.md` — DB 建置任務
- `tasks/phase-1-text-pipeline.md` — 字典熱載入實作