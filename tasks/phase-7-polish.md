# Phase 7：打磨與文件（Week 8）

> **前置**：Phase 6 完成（或已決定砍哪些功能）
>
> **交付物**：Demo 就緒、書面報告可交

---

## 任務清單

### P7-01：延遲優化

- [ ] **動作**：
  - 查 InteractionLog 找出最慢的 10% turn
  - 分析瓶頸（ASR？LLM？TTS？網路？）
  - 針對性優化（調整 chunk size、預熱模型、並行處理等）
- [ ] **目標**：P95 延遲 < 2s
- [ ] **Commit**：`perf: optimize slow turn outliers`

### P7-02：Demo 腳本

- [ ] **檔案**：`docs/demo-script.md`
- [ ] **內容**：
  - 3 分鐘、5 分鐘、10 分鐘三種版本
  - 每版本明確的對話流程、預期回應
  - 備援方案（萬一網路/模型當機怎麼 demo）
- [ ] **Commit**：`docs: add demo scripts`

### P7-03：架構圖與時序圖

- [ ] **工具**：建議用 Mermaid（可直接嵌 Markdown）或 draw.io
- [ ] **內容**：
  - 系統架構圖（高階）
  - Barge-in 時序圖
  - 資料流程圖
- [ ] **輸出**：`docs/diagrams/`
- [ ] **Commit**：`docs: add architecture and sequence diagrams`

### P7-04：使用者手冊

- [ ] **檔案**：`docs/user-guide.md`
- [ ] **對象**：Playground 使用者
- [ ] **內容**：如何連接、如何說話、常見問題
- [ ] **Commit**：`docs: add user guide`

### P7-05：部署手冊

- [ ] **檔案**：`docs/deployment.md`
- [ ] **對象**：要重現環境的人
- [ ] **內容**：硬體需求、環境變數、常見問題、回滾步驟
- [ ] **Commit**：`docs: add deployment guide`

### P7-06：專題書面報告

- [ ] **檔案**：視學校格式（docx 或 LaTeX）
- [ ] **對應**：`docs/plan.md 附錄 A` 的章節對照表
- [ ] **必備章節**：
  - 研究動機
  - 系統設計
  - 核心演算法（Barge-in / Splitter / 記憶）
  - 實作細節
  - 實驗結果（ASR 評估、延遲分析）
  - 討論與未來工作
- [ ] **Commit**：`docs: add final project report`

### P7-07：Demo 預演

- [ ] **動作**：
  - 至少 3 次完整預演
  - 記錄每次出現的問題並修正
  - 最後一次在 demo 場地（或類似環境）實測
- [ ] **檢查項目**：
  - 麥克風權限
  - 網路品質
  - 硬體喇叭音量
  - 備用方案
- [ ] **不 commit**（這是準備活動）

## Phase 7 完成標準

- [ ] Demo 能穩定完整跑過
- [ ] 書面報告符合學校格式
- [ ] 所有文件齊全，組員/老師/未來的自己都能獨立理解專案