# Phase 2：語音層接入與 ASR A/B 評估（Week 3）

> **目標**：把語音殼套到 Phase 1 的純文字鏈路上，同時完成 ASR 雙 backend 的實作與評估。
>
> **前置**：Phase 1 完成
>
> **交付物**：能用麥克風講話、聽到台語回應的 Playground；ASR 評估報告
>
> **對應 plan.md**：[§4.1 Chunk 串流](../docs/plan.md#41-chunk-based-串流原則)、[§4.2 ASR 選型](../docs/plan.md#42-asr-選型與抽象介面設計)
>
> **對應 ADR**：[002-asr-dual-backend](../docs/adr/002-asr-dual-backend.md)

---

## ⚠️ Phase 重點

**策略**：先做 Dummy Loop 驗證語音層，**不接 LLM**。確認「麥克風 → VAD → 寫死的台語文字 → Piper → 喇叭」走得通後，再把 Phase 1 的 LLM 鏈路接上去。

**ASR 評估是本 Phase 核心產出之一**，不是附帶工作。

---

## 任務清單

### P2-01：Piper TTS 包裝

- [ ] **檔案**：`worker/pipeline/tts.py`
- [ ] **介面**：
  ```python
  class PiperTTS:
      def __init__(self, model_path: str, speaker_id: int | None = None) -> None: ...
      async def synthesize(self, taibun_text: str) -> AsyncIterator[bytes]: ...
      def clear_queue(self) -> None: ...  # barge-in 用
  ```
- [ ] **驗收**：能輸入台羅字產出 16kHz mono PCM，用 `aplay` 播放正常
- [ ] **Commit**：`feat(worker): wrap piper tts with async interface`

### P2-02：Silero VAD 整合

- [ ] **檔案**：`worker/controller/vad.py`
- [ ] **驗收**：餵音訊 chunk 能正確回報 speech start / end 事件
- [ ] **Commit**：`feat(worker): integrate silero vad`

### P2-03：ASR 抽象介面

- [ ] **檔案**：`worker/pipeline/asr/base.py`
- [ ] **參照**：`docs/plan.md §4.2.2`
- [ ] **驗收**：介面定義清楚，pyright 通過
- [ ] **Commit**：`feat(worker): add base asr interface`

### P2-04：Qwen3-ASR 實作

- [ ] **檔案**：`worker/pipeline/asr/qwen3.py`
- [ ] **參照**：`docs/plan.md §4.2.3`
- [ ] **預設**：使用 0.6B 版本
- [ ] **驗收**：能串流辨識 16kHz PCM，TTFT 可量測
- [ ] **Commit**：`feat(worker): implement qwen3-asr backend`

### P2-05：Breeze-ASR-26 實作

- [ ] **檔案**：`worker/pipeline/asr/breeze.py`
- [ ] **參照**：`docs/plan.md §4.2.4`
- [ ] **注意**：Breeze-26 無原生串流，配合 VAD endpoint 驅動
- [ ] **驗收**：給一段完整音訊能回傳辨識結果
- [ ] **Commit**：`feat(worker): implement breeze-asr-26 backend`

### P2-06：LiveKit Agent 入口

- [ ] **檔案**：`worker/main.py`（擴充）
- [ ] **功能**：使用 `livekit-agents` SDK，能加入 Room、訂閱使用者音訊、發佈 Agent 音訊
- [ ] **驗收**：能以 livekit-cli 連進 Room，看到 agent-worker 的軌道
- [ ] **Commit**：`feat(worker): add livekit agent entry point`

### P2-07：Dummy Loop 驗證

- [ ] **依賴**：P2-01、P2-02、P2-06
- [ ] **內容**：麥克風 → VAD 觸發 → 寫死「你好，我是 Agent」→ Piper TTS → 播放
- [ ] **不接**：ASR、LLM
- [ ] **驗收**：能完整跑通，延遲 < 1.5s
- [ ] **Commit**：`feat(worker): dummy loop for voice layer verification`

### P2-08：Playground 最小版本

- [ ] **檔案**：`web/apps/playground/**`
- [ ] **功能**：
  - 頁面載入時呼叫後端 `POST /api/livekit/token` 取得 token
  - 建立 LiveKit 連線
  - 明確開啟 AEC/NS/AGC（見 plan §3.3）
  - Audio Visualizer 顯示音量
  - 狀態燈號（IDLE / LISTENING / SPEAKING）
- [ ] **驗收**：訪問頁面能跟 agent 對話（目前只會收到 Dummy Loop 的固定回應）
- [ ] **Commit**：`feat(playground): minimal interactive voice ui`

### P2-09：完整語音鏈整合

- [ ] **依賴**：P2-03、P2-04、P2-07
- [ ] **內容**：將 Dummy Loop 的「寫死回應」替換為「ASR → Phase 1 的文字鏈路 → TTS」
- [ ] **驗收**：能進行完整語音對話（非自然流暢，不要求 Barge-in）
- [ ] **Commit**：`feat(worker): wire full voice pipeline end-to-end`

### P2-10：ASR A/B 評估

- [ ] **依賴**：P2-04、P2-05
- [ ] **檔案**：`docs/asr_evaluation.md`、`worker/scripts/eval_asr.py`
- [ ] **動作**：
  - 錄製 30 段台語測試語音（公車路線詢問、數字念法、一般對話、含口音），存在 `eval/audio/`
  - 人工逐字轉譯作為 ground truth，存在 `eval/transcripts/`
  - 寫 `eval_asr.py` 腳本：跑兩個 backend 產出結果，計算 CER、TTFT、GPU 記憶體
  - 寫評估報告，照 `docs/adr/002-asr-dual-backend.md` 的決策準則給出結論
- [ ] **驗收**：
  - 30 段音訊與 ground truth 都在 repo（或在 README 說明如何取得）
  - 評估報告含具體數字、誤辨類型分析、最終推薦
  - 更新 `.env.example` 的 `ASR_BACKEND` 預設值為選定的 backend
- [ ] **Commit**：`docs(asr): add asr evaluation report and select default backend`

---

## Phase 2 完成標準

- [ ] Playground 能進行完整語音對話
- [ ] 平均端到端延遲 < 1.5s
- [ ] ASR 評估報告完成，預設 backend 已鎖定
- [ ] InteractionLog 正確記錄 ASR 結果與延遲時間

## 常見陷阱

- ❌ 跳過 Dummy Loop 直接整合完整鏈路（debug 困難倍增）
- ❌ 選擇 ASR backend 前沒做評估（違反 ADR-002）
- ❌ 前端忘記開 AEC（後續 Barge-in 會踩坑）