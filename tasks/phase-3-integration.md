# Phase 3：完整迴圈整合（Week 4）

> **前置**：Phase 2 完成
>
> **交付物**：能穩定進行 10 分鐘對話、延遲達標、有錯誤降級能力
>
> **對應 plan.md**：[§5 錯誤處理](../docs/plan.md#5-錯誤處理與降級策略)、[§6 觀測性](../docs/plan.md#6-觀測性-observability)

---

## ⚠️ Phase 重點

本 Phase 不加新功能，只把 Phase 2 的「能動」變成「穩定、可觀測、會降級」。

---

## 任務清單

### P3-01：延遲量測埋點

- [ ] **檔案**：`worker/observability/metrics.py`
- [ ] **內容**：為每輪對話記錄 T0/T1/T2/T3，寫入 InteractionLog 的 `latency_*` 欄位
- [ ] **驗收**：`SELECT * FROM "InteractionLog" ORDER BY "createdAt" DESC LIMIT 10` 能看到有效延遲數字
- [ ] **Commit**：`feat(worker): add latency instrumentation`

### P3-02：Fallback 音訊預生成

- [ ] **檔案**：`worker/controller/fallback.py`、`worker/assets/fallback/`
- [ ] **內容**：啟動時用 Piper 預生成 plan §5.1 列出的 5 段 fallback 音訊，載入記憶體
- [ ] **驗收**：能透過 `play_fallback(kind)` 播放對應音訊
- [ ] **Commit**：`feat(worker): add fallback audio pregeneration`

### P3-03：超時與錯誤處理

- [ ] **參照**：`docs/plan.md §5.2、§5.3`
- [ ] **內容**：為 ASR、LLM、TTS、Tool call 各層加上超時與 try/except，失敗時播 fallback
- [ ] **驗收**：
  - 手動斷網測試：LLM 斷線時聽到 `llm_error` fallback
  - 錯誤寫入 InteractionLog 的 `error_flag`
- [ ] **Commit**：`feat(worker): add timeout handling and error fallback`

### P3-04：10 分鐘穩定性驗證

- [ ] **動作**：持續對話 10 分鐘，記錄延遲與錯誤率
- [ ] **驗收**：
  - 平均 `latency_total` < 1.5s
  - 無崩潰
  - Error rate < 5%
- [ ] **Commit**：`test: verify 10-minute stability run`

## Phase 3 完成標準

- [ ] 延遲數字寫入 DB
- [ ] 5 種 fallback 情境都測試過
- [ ] 10 分鐘穩定性通過