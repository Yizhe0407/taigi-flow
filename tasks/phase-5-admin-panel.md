# Phase 5：管理後台（Week 6）

> **前置**：Phase 4 完成
>
> **交付物**：管理者能透過 UI 管理人格、字典、查看日誌
>
> **對應 plan.md**：[§7.3 Admin Panel](../docs/plan.md#73-admin-panel-管理端)

---

## 任務清單

### P5-01：後端 API

- [x] **檔案**：`web/apps/admin/src/app/api/**`
- [x] **內容**：
  - `GET/POST/PUT/DELETE /api/agent-profiles`
  - `GET /api/sessions`、`GET /api/sessions/:id/turns`
  - `GET/POST/PUT/DELETE /api/dictionary`
  - `POST /api/dictionary/from-log`（從 log 一鍵加入字典）
- [x] **Commit**：`feat(admin): add backend api routes` (41a1955)

### P5-02：Agent Profile 管理頁

- [x] **檔案**：`web/apps/admin/src/app/agents/**`
- [x] **功能**：列表、編輯、啟用/停用
- [x] **Commit**：`feat(admin): add agent profile management ui` (ee5958f)

### P5-03：對話日誌檢視頁

- [x] **功能**：
  - 列出最近 session
  - 進入 session 看到逐 turn 的四欄對照（ASR / LLM / Hanlo / Taibun）
  - 可篩選：被打斷的、有錯誤的、延遲 > 2s 的
- [x] **Commit**：`feat(admin): add interaction log viewer` (436a475)

### P5-04：發音字典管理頁

- [x] **功能**：
  - 全域 / Agent 專屬字典分頁
  - 從 log 頁面「一鍵加入字典」串接本頁
  - 批次匯入/匯出 CSV
- [x] **關鍵**：這是整個後台的核心，UX 要好
- [x] **Commit**：`feat(admin): add pronunciation dictionary ui` (994365a)

### P5-05：即時監控儀表板

- [x] **功能**：
  - 當前 active session 數
  - 最近 100 輪平均延遲
  - 錯誤率
- [x] **實作**：輪詢即可，不做 WebSocket
- [x] **Commit**：`feat(admin): add monitoring dashboard` (28f9db4)

## Phase 5 完成標準

- [x] 非技術同學能獨立透過後台新增 Agent 並修正發音

## 實作摘要（2026-05-13）

### 新增檔案

**後端 API**（`web/apps/admin/src/app/api/`）
- `agent-profiles/route.ts` — GET/POST
- `agent-profiles/[id]/route.ts` — GET/PUT/DELETE
- `sessions/route.ts` — GET（支援 cursor 分頁、agentProfileId 篩選）
- `sessions/[id]/turns/route.ts` — GET（支援 bargedIn / hasError / minLatencyMs 篩選）
- `dictionary/route.ts` — GET/POST（支援 profileId=global 或 UUID、term 搜尋）
- `dictionary/[id]/route.ts` — PUT/DELETE
- `dictionary/from-log/route.ts` — POST（依 logId 關聯 session.agentProfileId 決定歸屬）
- `monitor/route.ts` — GET（active sessions、最近 100 輪首音延遲、錯誤率）

**共享套件**
- `web/packages/db/src/index.ts` — Prisma singleton（hot-reload 安全，globalThis 快取）
- `web/packages/types/src/index.ts` — zod input schemas（所有 API 入口驗證）

**UI 頁面**（`web/apps/admin/src/app/`）
- `/agents` — 列表 + 啟用/停用 toggle + 刪除
- `/agents/new` — 建立表單
- `/agents/[id]` — 編輯表單
- `/sessions` — Session 列表（最近 100）
- `/sessions/[id]` — Turn 四欄對照（ASR/LLM/HanLo/Taibun）+ 篩選 + 一鍵加入字典
- `/dictionary` — 全域/Agent 分頁、inline 編輯、CSV 匯入/匯出、搜尋
- `/monitor` — 儀表板，10s 輪詢

### 架構決策
- DB 直存（server component → prisma）vs. fetch API（client component → /api/*）依互動需求選擇
- Tailwind + lucide-react，無外部 UI 元件庫
- CSV 解析自實作（無依賴），支援欄位內引號逸出