# Phase 5：管理後台（Week 6）

> **前置**：Phase 4 完成
>
> **交付物**：管理者能透過 UI 管理人格、字典、查看日誌
>
> **對應 plan.md**：[§7.3 Admin Panel](../docs/plan.md#73-admin-panel-管理端)

---

## 任務清單

### P5-01：後端 API

- [ ] **檔案**：`web/apps/admin/src/app/api/**`
- [ ] **內容**：
  - `GET/POST/PUT/DELETE /api/agent-profiles`
  - `GET /api/sessions`、`GET /api/sessions/:id/turns`
  - `GET/POST/PUT/DELETE /api/dictionary`
  - `POST /api/dictionary/from-log`（從 log 一鍵加入字典）
- [ ] **Commit**：`feat(admin): add backend api routes`

### P5-02：Agent Profile 管理頁

- [ ] **檔案**：`web/apps/admin/src/app/agents/**`
- [ ] **功能**：列表、編輯、啟用/停用
- [ ] **Commit**：`feat(admin): add agent profile management ui`

### P5-03：對話日誌檢視頁

- [ ] **功能**：
  - 列出最近 session
  - 進入 session 看到逐 turn 的四欄對照（ASR / LLM / Hanlo / Taibun）
  - 可篩選：被打斷的、有錯誤的、延遲 > 2s 的
- [ ] **Commit**：`feat(admin): add interaction log viewer`

### P5-04：發音字典管理頁

- [ ] **功能**：
  - 全域 / Agent 專屬字典分頁
  - 從 log 頁面「一鍵加入字典」串接本頁
  - 批次匯入/匯出 CSV
- [ ] **關鍵**：這是整個後台的核心，UX 要好
- [ ] **Commit**：`feat(admin): add pronunciation dictionary ui`

### P5-05：即時監控儀表板

- [ ] **功能**：
  - 當前 active session 數
  - 最近 100 輪平均延遲
  - 錯誤率
- [ ] **實作**：輪詢即可，不做 WebSocket
- [ ] **Commit**：`feat(admin): add monitoring dashboard`

## Phase 5 完成標準

- [ ] 非技術同學能獨立透過後台新增 Agent 並修正發音