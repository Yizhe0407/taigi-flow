# Phase 6：RAG + Tools（Week 7）

> **前置**：Phase 5 完成
>
> **交付物**：Agent 能查知識庫、能呼叫外部 API
>
> **警告**：本 Phase 範圍較彈性，若時程壓力大可砍到最小
>
> **對應 plan.md**：`AgentProfile.ragConfig`、`tools` 設計

---

## 任務清單

### P6-01：RAG 文件上傳與索引

- [ ] **檔案**：`web/apps/admin/src/app/knowledge/**`
- [ ] **功能**：
  - 上傳 PDF / MD / TXT
  - 後端切塊（按段落或固定字數）
  - 呼叫 embedding API（OpenAI `text-embedding-3-small` 或本地模型）
  - 寫入 `KnowledgeChunk` 表
- [ ] **Commit**：`feat(admin): add knowledge base upload and indexing`

### P6-02：RAG 檢索整合

- [ ] **檔案**：`worker/pipeline/rag.py`
- [ ] **功能**：
  - 每個 user turn 先做 embedding
  - pgvector 做 cosine similarity 檢索
  - 取 top-K 塞進 LLM prompt
- [ ] **設計問題**：何時觸發檢索？方案：
  - A. 每輪都檢索（簡單但浪費）
  - B. 讓 LLM 用 function call 決定（複雜但精準）
  - 建議先做 A，可用再改 B
- [ ] **Commit**：`feat(worker): integrate rag retrieval`

### P6-03：Tool 基礎類別

- [ ] **檔案**：`worker/tools/base.py`
- [ ] **內容**：定義 `BaseTool` 介面（name、description、parameters、execute）
- [ ] **Commit**：`feat(worker): add tool base class`

### P6-04：TDX Tool 實作

- [ ] **檔案**：`worker/tools/tdx.py`
- [ ] **功能**：公車路線查詢、到站時間查詢
- [ ] **Commit**：`feat(worker): implement tdx transportation tool`

### P6-05：Function Calling 整合

- [ ] **檔案**：`worker/pipeline/llm.py`（擴充）
- [ ] **功能**：LLM 決定呼叫 tool 時，worker 執行並回傳結果給 LLM 繼續生成
- [ ] **Commit**：`feat(worker): add function calling support`

## Phase 6 完成標準

- [ ] 問「307 公車現在到哪了？」能正確呼叫 TDX 並用台語回答
- [ ] 知識庫檢索結果反映在回應中

## 時程壓力時的取捨

若 Phase 5 拖延到本週，可砍至：
- 只做 P6-03 + P6-04 + P6-05（有 tool 沒 RAG）
- 或只做 P6-01 + P6-02（有 RAG 沒 tool）