# ADR 004：Barge-in 自說話抑制策略

**狀態**：已採用（Phase 4，2026-05-02，修訂 2026-05-02）

---

## 背景

Phase 4 實作 barge-in 打斷機制後，`docs/plan.md §3.3` 的兩個 pseudocode 設計直接導致完全無法打斷（100% 失敗率）。本 ADR 記錄實際運作的設計與原始設計的差異。

---

## 決策

### 決策一：移除 200ms 時間門檻

**原始 plan.md §3.3**：
```python
if time_since_tts < 200:  # ms
    return {"prob": 0.75, "min_duration": 500}
```

**問題**：`mark_tts_output()` 在每次 `capture_frame` 後呼叫，每幀 20ms。所以 `time_since_last_tts_ms()` 在 TTS 播放期間永遠是 10–20ms，小於 200ms。門檻永遠成立 → barge-in 永遠被抑制。

**實際實作**：移除時間門檻。Silero VAD 動態門檻（決策二）已足夠處理回音；不需要額外的時間判斷。

---

### 決策二：VAD 動態門檻使用實測值

**原始 plan.md §3.3**：
```
SPEAKING 時：activation_threshold=0.75, min_speech_duration=500ms
```

**問題有兩個**：

1. **Silero VAD 預設 `min_speech_duration` 是 0.05s（50ms），不是 0.3s**。Plan 作者可能誤以為預設是 300ms。將 `min_speech_duration` 設為 500ms 是預設值的 10 倍。加上 Silero 使用指數平滑（ExpFilter α=0.35），從靜音到 smoothed prob 超過 0.75 需要約 192ms（6 幀），再累積 500ms → 打斷觸發大約需要 700ms 持續高置信度語音，實務上不可能。

2. **0.75 activation_threshold 太高**。使用者語音 prob 通常 0.65–0.90；0.75 門檻意味著即使使用者清晰發聲也可能被過濾。

**實際採用值**：

| 狀態 | activation_threshold | min_speech_duration |
|------|---------------------|---------------------|
| THINKING 或 SPEAKING（「忙碌中」）| **0.60** | **0.15s** |
| 其他（離開忙碌狀態後）| 0.50（Silero 預設）| 0.05s（Silero 預設）|

**理由**：
- 0.60 高於有 browser AEC 後的典型 TTS 回音 prob（< 0.40），但低於使用者語音 prob（0.65+）
- 0.15s 比預設（0.05s）長 3 倍，可過濾短暫雜音（如咳嗽），但對真實語音影響很小
- THINKING 期間無 TTS 播放，不需回音抑制，但仍需 0.15s 累積時間防止偶發雜音取消 LLM 生成
- 離開忙碌狀態後回到 Silero 原始預設，不殘留較嚴格的設定

---

## 第一道防線仍是 Browser AEC

Worker 端 VAD 門檻調整只是第二道防線。主要保護來自前端：

```typescript
// getUserMedia 與 LiveKitRoom 兩處都必須保持 true
echoCancellation: true,
noiseSuppression: true,
autoGainControl: true,
```

戴耳機時 browser AEC 通常將 TTS 回音降至 prob < 0.15，0.50 預設門檻就夠。使用喇叭外放時 prob 可能到 0.4–0.5，0.60 門檻提供保護。

---

## 決策三：Barge-in 觸發狀態擴展至 THINKING

**初始實作**僅在 `SPEAKING` 狀態觸發 barge-in。但 FSM 的 `_TRANSITIONS` 表明 `THINKING → BARGED_IN` 是合法轉換，代表原始設計就預期支援此路徑。

**問題**：使用者在 LLM 生成期間說話（`THINKING` 狀態，尚無 TTS 輸出），VAD 事件被靜默忽略。`_pipeline_busy = True` 導致 `END_OF_SPEECH` 後的新 utterance 被丟棄，使用者必須等 agent 說完才能再次說話。

**實際採用**：INFERENCE_DONE 快速路徑和 START_OF_SPEECH fallback 都在 `SPEAKING` 和 `THINKING` 狀態觸發 `transition(BARGED_IN)`。VAD 動態門檻也同步提升至兩個狀態（見決策二修訂）。

---

## 後果

- Barge-in 恢復正常運作（INFERENCE_DONE 快速路徑在 ~64ms 內觸發；START_OF_SPEECH fallback 在 ~150ms 後觸發）
- THINKING 和 SPEAKING 期間都有 0.6/0.15s 門檻保護，防止雜音意外打斷
- 移除時間門檻後，自說話抑制完全依賴 VAD 動態門檻 + browser AEC
- 若未來發現喇叭外放仍有誤觸發，可微調 `activation_threshold`（0.60 → 0.65），不需要恢復時間門檻

---

## 被否決的方案

**方案：保留 200ms 時間門檻，改為「判斷 TTS 是否仍在播放」**
- 可行但複雜：需要額外的 `_tts_is_playing` flag
- 動態門檻已經足夠，不值得增加複雜度
