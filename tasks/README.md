# Tasks 目錄

本目錄包含分階段的任務清單，按執行順序排列。

## 使用方式

1. **開發者（人類）**：按 Phase 順序打開對應檔案，依序執行 checkbox。完成一個任務就打勾並 commit。
2. **AI 助手（Claude）**：先讀 `CLAUDE.md`，然後讀當前 Phase 的 task 檔，按順序執行。

## Phase 總覽

| Phase | 檔案 | 週 | 狀態 |
|-------|------|----|------|
| 0 | [phase-0-infrastructure.md](phase-0-infrastructure.md) | W1 | ✅ 完成 |
| 1 | [phase-1-text-pipeline.md](phase-1-text-pipeline.md) | W2 | ✅ 完成 |
| 2 | [phase-2-voice-layer.md](phase-2-voice-layer.md) | W3 | ✅ 完成 |
| 3 | [phase-3-integration.md](phase-3-integration.md) | W4 | ⬜ 未開始 |
| 4 | [phase-4-barge-in.md](phase-4-barge-in.md) | W5 | ⬜ 未開始 |
| 5 | [phase-5-admin-panel.md](phase-5-admin-panel.md) | W6 | ⬜ 未開始 |
| 6 | [phase-6-rag-tools.md](phase-6-rag-tools.md) | W7 | ⬜ 未開始 |
| 7 | [phase-7-polish.md](phase-7-polish.md) | W8 | ⬜ 未開始 |

開始一個 Phase 時把 ⬜ 改成 🏗️（進行中），完成後改成 ✅。

## Task 檔格式約定

每個任務包含以下欄位（視需要選用）：

- **依賴**：需要先完成哪些 task
- **檔案**：主要修改或建立的檔案路徑
- **輸入規格**：函式/類別的介面簽名
- **實作細節**：對應 plan.md 的哪個章節
- **測試必須涵蓋**：哪些 case 必須測
- **驗收**：如何確認任務完成
- **Commit**：commit 訊息建議

## 詳細度策略

- **Phase 0、1、2**：詳細版（每個任務都有完整欄位）
- **Phase 3 以後**：精簡版（只列必要資訊）

**原因**：前期任務詳細度高可以避免起跑踉蹌；後期任務會依前期實際狀況調整，過早展開反而會寫出脫離實情的內容。Phase 3 開工前會依 Phase 2 的實測結果把該 Phase 擴展為詳細版。

## 變更規則

- **task 檔可修改**：發現遺漏或順序錯誤時直接改（與 `plan.md` 是設計文件不同）
- **修改後要 commit**：讓 Git 記錄任務清單的演化
- **AI 助手不可主動修改 task 檔結構**，只能把 checkbox 打勾。結構變動必須人類決定。