# Phase 4：Barge-in + AEC（Week 5）

> **前置**：Phase 3 完成
>
> **交付物**：支援使用者打斷、不會自我誤觸發的擬真對話體驗
>
> **對應 plan.md**：[§3.2 Barge-in 狀態機](../docs/plan.md#32-barge-in-狀態機完整實作)、[§3.3 AEC](../docs/plan.md#33-aecacoustic-echo-cancellation策略)

---

## ⚠️ Phase 重點

Barge-in 最常見的 bug 不是「偵測不到」，而是「誤觸發」（被自己的 TTS 回音觸發、被短促雜音觸發）。本 Phase 的驗收重點是**正確的誤判抑制**，不只是「能打斷」。

---

## 任務清單

### P4-01：Voice Controller FSM

- [ ] **檔案**：`worker/audio/voice_controller.py`
- [ ] **參照**：`docs/plan.md §3.2` 的狀態機表
- [ ] **內容**：實作 IDLE / LISTENING / THINKING / SPEAKING / BARGED_IN 五個狀態與轉換
- [ ] **測試**：針對每個狀態轉換寫 unit test
- [ ] **Commit**：`feat(worker): implement voice controller fsm`

### P4-02：動態 VAD 門檻

- [ ] **檔案**：`worker/audio/vad.py`（擴充）
- [ ] **參照**：`docs/plan.md §3.3` 的 `vad_threshold_dynamic`
- [ ] **內容**：SPEAKING 狀態且剛送出音訊 < 200ms 內，提高 VAD 觸發門檻
- [ ] **Commit**：`feat(worker): add dynamic vad threshold for self-speech suppression`

### P4-03：完整清理序列

- [ ] **檔案**：`worker/audio/voice_controller.py`（擴充）
- [ ] **參照**：`docs/plan.md §3.2` 的 `on_barge_in` 範例
- [ ] **內容**：實作六步清理序列（停音訊 → 清 TTS → 取消 LLM → flush splitter → 寫 log → 重置 buffer）
- [ ] **關鍵**：順序正確，不可調換
- [ ] **Commit**：`feat(worker): add barge-in cleanup sequence`

### P4-04：前端 AEC 確認

- [ ] **檔案**：`web/apps/playground/src/lib/livekit.ts`
- [ ] **內容**：確認 `echoCancellation / noiseSuppression / autoGainControl` 都為 true
- [ ] **Commit**：`chore(playground): ensure webrtc aec settings`

### P4-05：Barge-in 壓力測試

- [ ] **測試案例**：
  - 案例 1：使用者在 Agent 說話中途打斷，Agent 應立即停止
  - 案例 2：Agent 說話時自己的聲音回灌（喇叭外放），應**不**觸發 barge-in
  - 案例 3：快速連續 3 次打斷，狀態機不卡死
  - 案例 4：Agent 剛開口 < 200ms 被打斷，處理正常
  - 案例 5：打斷後立即開始新問題，新對話正常進行
- [ ] **驗收**：5 個案例各執行 3 次都通過
- [ ] **Commit**：`test: barge-in stress test cases`

## Phase 4 完成標準

- [ ] 5 個壓力測試案例全部通過
- [ ] 無殘音、無狀態卡死
- [ ] InteractionLog 正確標記 `wasBargedIn`