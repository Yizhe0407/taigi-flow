# Phase 3：完整迴圈整合（Week 4）

> **目標**：把 Phase 2 的「能動」升級成「穩定、可觀測、會降級」。不新增功能，只補工程品質。
>
> **前置**：Phase 2 完成（P2-01 ~ P2-10 全部 [x]）
>
> **交付物**：能穩定進行 10 分鐘對話、延遲寫入 DB、所有失敗模式都有 fallback 語音
>
> **對應 plan.md**：[§5 錯誤處理](../docs/plan.md#5-錯誤處理與降級策略)、[§6 觀測性](../docs/plan.md#6-觀測性-observability)

---

## ⚠️ Phase 重點

**本 Phase 不做新功能**。所有變動都是為了讓現有流程在異常狀況下仍能優雅處理。

**現況盤點**（實作前必讀，2026-04-28 對 main 驗證）：
- `PipelineRunner.process_utterance`（`worker/session/runner.py`）已有 log 級別的延遲計時，但**未寫入 `InteractionLog`**
- `InteractionLogRepository.log_turn()` 已存在（`worker/db/repositories.py`，Phase 1-05），**僅 `worker/cli.py` 文字路徑串接，語音路徑尚未整合**
- `AgentComponents`（`worker/session/components.py`）**未持有** `log_repo` / `session_id` / `agent_profile_id`
- `build_components()` **不知道 LiveKit room name**（room 名只在 `entrypoint(ctx)` 階段才有 `ctx.room.name`），需新增參數
- Fallback 目前走 `speak_notice()` 即時 Piper 合成，**非預錄快取**；錯誤訊息硬編在 `runner.py` 數處
- 既有超時：`LLMClient.stream`（`worker/pipeline/llm.py`）已有
  - **首 token timeout**：預設 **15 秒**（不是 5s），env `LLM_FIRST_TOKEN_TIMEOUT`（秒，float）
  - **inter-token timeout**：預設 15 秒（`stream(timeout=...)` 參數）
- ASR / TTS / 整體無 timeout 包覆；`error_flag` 從未填入 DB
- Worker `pyproject.toml` 已有 `pytest`、`pytest-asyncio`、`pytest-httpserver`；**無 `freezegun`**（測試請改用 `monkeypatch.setattr(time, "perf_counter", ...)`，避免新增依賴）

**本 Phase 禁止**：
- ❌ 加入 Barge-in（Phase 4 才做）
- ❌ 加入任何 Tool call（Phase 6 才做）
- ❌ 升級 livekit-agents / openai / piper 主版本

---

## 任務清單

### P3-01：LatencyTimer 輔助類

- [x] **依賴**：無
- [x] **檔案**：`worker/observability/metrics.py`、`worker/tests/test_metrics.py`
- [x] **參照**：`docs/plan.md §6.1`
- [x] **輸入規格**：
  ```python
  from dataclasses import dataclass, field
  from typing import Literal

  Stage = Literal["asr_end", "llm_first_tok", "first_audio", "total"]

  @dataclass
  class LatencyTimer:
      """單輪對話的延遲計時器。所有時間以 T0（VAD 終點 / ASR 開始）為原點。

      使用模式：
          timer = LatencyTimer.start()
          ...ASR 完成...
          timer.mark("asr_end")
          ...LLM 首 token 回來...
          timer.mark("llm_first_tok")
          ...TTS 第一個 chunk 送出...
          timer.mark("first_audio")
          timer.finalize()  # 填入 total
          repo.log_turn(..., latencies=timer.as_dict())
      """

      _t0: float = field(default_factory=lambda: 0.0)
      _marks: dict[Stage, int] = field(default_factory=dict)

      @classmethod
      def start(cls) -> "LatencyTimer": ...
      def mark(self, stage: Stage) -> None:
          """記錄此 stage 相對於 T0 的毫秒數。重複呼叫同一個 stage 會覆寫。"""
      def finalize(self) -> None:
          """將 'total' mark 設定為呼叫當下的毫秒數。"""
      def as_dict(self) -> dict[str, int]:
          """回傳符合 InteractionLogRepository.log_turn(latencies=...) 格式的 dict。"""
      def __contains__(self, stage: Stage) -> bool: ...
  ```
- [x] **實作細節**：
  - 內部用 `time.perf_counter()` 取 monotonic 秒數，寫入時轉為毫秒整數
  - `mark()` 只記第一次呼叫；重複 mark 會 log warning 但覆寫舊值（方便 retry 情境）
  - `as_dict()` 只回傳**已 mark** 的 key，未記錄的 stage 不出現（DB 欄位 nullable，缺值表示未到達該階段）
- [x] **測試必須涵蓋**（至少 6 個 case）：
  - `start()` 後立刻 `finalize()`：`total` 應為接近 0 的整數
  - 依序 mark 四個 stage：`as_dict()` 回傳 4 個 key，數值單調遞增
  - 只 mark 前兩個 stage：`as_dict()` 只含 `asr_end` 與 `llm_first_tok`
  - 重複 mark 同一個 stage：第二次值覆寫第一次，log warning
  - `"asr_end" in timer` 判斷正確
  - 用 `monkeypatch.setattr(time, "perf_counter", ...)` 驗證時間計算精確（**不要新增 `freezegun` 依賴**）
- [x] **驗收**：
  - `uv run pytest worker/tests/test_metrics.py -v` 全綠
  - `uv run pyright worker/observability/metrics.py` strict 通過
- [x] **Commit**：`feat(worker): add latency timer for per-turn instrumentation` (42b3bb4)

---

### P3-02：Runner 整合延遲量測與 InteractionLog 寫入

- [x] **依賴**：P3-01
- [x] **檔案**：
  - `worker/session/components.py`（擴充）
  - `worker/session/runner.py`（擴充）
  - `worker/main.py`（串接）
- [x] **參照**：`docs/plan.md §6.1`、`worker/db/repositories.py::InteractionLogRepository.log_turn`
- [x] **`AgentComponents` 擴充**：
  ```python
  @dataclasses.dataclass
  class AgentComponents:
      tts: PiperTTS | None
      asr: BaseASR
      llm: LLMClient
      memory: SlidingWindowMemory
      text_processor: TextProcessor
      audio_source: rtc.AudioSource
      # 新增：
      log_repo: InteractionLogRepository
      session_id: str            # build_components 時呼叫 log_repo.create_session() 取得
      agent_profile_id: str | None  # 給 reload_if_updated / log 用
  ```
- [x] **`build_components()` 變更**：
  - 簽名改為 `async def build_components(livekit_room: str) -> AgentComponents`
  - room name 由 `entrypoint(ctx)` 傳入：`await build_components(ctx.room.name)`（**不要新增 `LIVEKIT_ROOM` env**，real source 是 JobContext）
  - 建立 `log_repo = InteractionLogRepository(async_session_factory)`
  - 取得 `profile_id` 後：`session_id = await log_repo.create_session(profile_id, livekit_room)`
  - 若 `profile_id` 為 `None`（profile 不存在，走現有 `_FALLBACK_SYSTEM_PROMPT` 路徑）：**略過 DB 寫入**並 log warning，讓語音仍可測試；存 `log_repo = None` sentinel + `session_id = ""`
- [x] **`PipelineRunner` 變更**：
  - 建構子接受 `log_repo` 與 `session_id`（可為 `None` / 空字串時停用）
  - 新增 instance var `_turn_index: int = 0`
  - `process_utterance` 流程：
    1. 函式開頭 `timer = LatencyTimer.start()`
    2. `_run_asr` 回傳 final 文字後 `timer.mark("asr_end")`
    3. `_run_llm_tts` 內在首 token 回來時呼叫 callback → `timer.mark("llm_first_tok")`
    4. `speak_taibun` 內第一個 `capture_frame` 前呼叫 callback → `timer.mark("first_audio")`（僅第一次）
    5. finally 區塊呼叫 `timer.finalize()`，若 `log_repo` 非 None：
       ```python
       self._turn_index += 1
       await self._log_repo.log_turn(
           session_id=self._session_id,
           turn_index=self._turn_index,
           user_asr_text=user_text or "",
           llm_raw_text=full_response or "",
           hanlo_text=last_hanlo,   # 最後一句合成文字的 hanlo
           taibun_text=last_taibun,  # 同上
           latencies=timer.as_dict(),
           was_barged_in=False,      # Phase 4 才會變
           error_flag=error_flag,    # 由 P3-05 填
       )
       ```
    6. DB 寫入失敗**不可拖垮對話**：整段包 `try/except`，log error 後吞掉
- [x] **callback 傳遞方式**：
  - 用 `Callable[[], None]` 由 caller 注入，不把 `timer` 物件下傳到 tts/llm（避免耦合）
  - `_run_llm_tts(on_first_token: Callable[[], None])`
  - `speak_taibun(on_first_audio: Callable[[], None])` 內用 `if not _first_audio_fired: cb(); _first_audio_fired = True`
- [x] **驗收**：
  - 與 Playground 對話一輪，觀察 DB：
    ```sql
    SELECT "turnIndex", "latencyAsrEnd", "latencyLlmFirstTok",
           "latencyFirstAudio", "latencyTotal", "errorFlag"
    FROM "InteractionLog"
    ORDER BY "createdAt" DESC LIMIT 10;
    ```
    四個 latency 欄位**皆非 NULL** 且單調遞增，`latencyTotal` 接近 sum
  - Playground 手動測試：把 DB 停掉（`docker compose stop postgres`）後仍能對話，只是沒 log
  - `uv run pyright worker/session/` strict 通過
- [x] **Commit**：`feat(worker): wire latency metrics and interaction log to voice pipeline` (4c27ebc)

---

### P3-03：Fallback 音訊預生成

- [ ] **依賴**：P2-01
- [ ] **檔案**：`worker/audio/fallback.py`、`worker/tests/test_fallback.py`
- [ ] **參照**：`docs/plan.md §5.1`
- [ ] **輸入規格**：
  ```python
  from typing import Literal

  FallbackKind = Literal["asr_timeout", "llm_error", "tts_fail", "tool_error", "general"]

  FALLBACK_TEXTS: dict[FallbackKind, str] = {
      "asr_timeout": "歹勢，我這馬聽無清楚，你閣講一遍好無？",
      "llm_error":   "袂好勢，我拄才頭殼當機，請你閣問一擺。",
      "tts_fail":    "拄才有小可問題，你閣講一擺。",
      "tool_error":  "抱歉，外部資料這馬提無著，等一下才閣試看覓。",
      "general":     "歹勢，出了一个小問題。",
  }

  class FallbackPlayer:
      """啟動時預先用 Piper 合成 5 段音訊到記憶體，執行期直接 replay PCM。"""

      def __init__(self, audio_source: rtc.AudioSource) -> None: ...

      async def pregenerate(
          self, tts: PiperTTS, text_processor: TextProcessor
      ) -> None:
          """對 FALLBACK_TEXTS 五個條目走 text_processor → piper synthesize，
          合併成一份完整 PCM bytes 存 self._audios[kind]。"""

      async def play(self, kind: FallbackKind) -> None:
          """將預錄 PCM 切成 20ms frame 送入 audio_source。
          若該 kind 未預生成（如 Piper init 失敗），log error 後 no-op。"""

      @property
      def is_ready(self) -> bool:
          """True 表示 5 個 kind 皆成功預生成。"""
  ```
- [ ] **實作細節**：
  - 文字須經 `text_processor.process()` 取得 taibun，再交給 `tts.synthesize()`
  - 20ms frame 切分邏輯可抽共用 helper（參考 `PipelineRunner.speak_taibun` 現有作法），**不重複貼整段**
  - 預生成失敗（單一 kind）不影響其他 kind，失敗的 kind 於 `play()` 被呼叫時只 log error
  - 所有 PCM 保留在記憶體（5 段 × ~2 秒 × 16kHz × 2byte ≈ 320KB，不需磁碟快取）
- [ ] **測試必須涵蓋**：
  - `pregenerate` 用 fake TTS（回傳固定 bytes）驗證 5 個 key 都存在於 `_audios`
  - `play` 呼叫後 `audio_source.capture_frame` 被呼叫次數 = PCM 長度 / 640
  - 未預生成的 kind 被 `play` 時 no-op，log error
  - `is_ready` 在 5 個都成功時為 True，任一失敗為 False
  - Piper synthesize 丟例外時，不影響其他 kind 預生成
- [ ] **驗收**：
  - `uv run pytest worker/tests/test_fallback.py -v` 全綠
  - `uv run pyright worker/audio/fallback.py` strict 通過
  - 整合後啟動 Worker log 可見 `fallback pregeneration complete kinds=5`
- [ ] **Commit**：`feat(worker): add fallback audio pregeneration`

---

### P3-04：Runner 整合 Fallback 播放

- [ ] **依賴**：P3-03
- [ ] **檔案**：
  - `worker/session/components.py`（擴充：把 `FallbackPlayer` 加進 `AgentComponents`）
  - `worker/session/runner.py`（把現有 `speak_notice` 即時合成路徑替換為 fallback player）
- [ ] **變更點**：
  - `AgentComponents` 新增欄位 `fallback: FallbackPlayer`
  - `build_components`：
    ```python
    fallback = FallbackPlayer(audio_source)
    if tts is not None:
        await fallback.pregenerate(tts, text_processor)
    ```
  - `PipelineRunner`：
    - 構子接收 `fallback` 並存成 `self._fallback`
    - **移除** `speak_notice` 對即時合成的使用，改成 `await self._fallback.play(kind)`
    - 保留 `speak_notice(text, trace_id)` 作為 tool 結果等動態文字使用（Phase 6 需要），但不再用於錯誤降級
    - 現有呼叫點對照：
      | 原本寫死的錯誤訊息 | 改用的 fallback kind |
      |---|---|
      | `"歹勢，我這馬聽無清楚，你閣講一遍好無？"`（ASR empty/timeout） | `asr_timeout` |
      | `"歹勢，語音辨識服務目前無法連線..."` | `asr_timeout` |
      | `"歹勢，這馬無法回應，請稍後閣試。"` | `llm_error` |
- [ ] **驗收**：
  - 手動測試：對 agent 沉默 → 聽到 `asr_timeout` 台語音訊
  - 觀察啟動 log：`fallback pregeneration complete kinds=5`，且第二次對話觸發 fallback 時**不再**有 `[tts] done` log（證實走預錄路徑）
  - DB log：對應輪次 `errorFlag` 非 NULL
- [ ] **Commit**：`refactor(worker): route error paths through fallback player`

---

### P3-05：超時與錯誤分類處理

- [ ] **依賴**：P3-02、P3-04
- [ ] **檔案**：
  - `worker/session/runner.py`（主要變更）
  - `worker/pipeline/llm.py`（若需要把首 token 預設改 5s，或新增 `LLM_TOTAL_TIMEOUT`）
- [ ] **參照**：`docs/plan.md §5.2 超時門檻表`、`§5.3 try/except 範例`
- [ ] **需落實的超時表**（以 `asyncio.wait_for` / `asyncio.timeout` 包覆，env 可覆寫，**單位統一為秒、float**，與既有 `LLM_FIRST_TOKEN_TIMEOUT` 對齊）：
  | 階段 | 門檻（預設） | env 覆寫 | 逾時動作 | `error_flag` |
  |------|-----------|--------|---------|------------|
  | ASR 整體 | 12s hard cap | `ASR_TIMEOUT` | 播 `asr_timeout`，結束本輪 | `asr_timeout` |
  | LLM 首 token | 5s | `LLM_FIRST_TOKEN_TIMEOUT`（**沿用既有，預設由 15s 改 5s**） | 播 `llm_error`，結束 | `llm_timeout` |
  | LLM 整體生成 | 15s | `LLM_TOTAL_TIMEOUT` | 以已生成內容收尾（不播 fallback） | `llm_partial` |
  | TTS 單 chunk | 2s | `TTS_CHUNK_TIMEOUT` | 中止本句，跳下一句 | `tts_fail`（僅當整輪無音訊產出才記） |
  - **註 1**：ASR partial 3s 無更新門檻（plan §5.2）在 batch 模式下無意義（現 ASR 是 one-shot），只保留整體 cap
  - **註 2**：`LLMClient` 既有預設 15s（見 `worker/pipeline/llm.py:34`），須在本 task 內把預設改 5s 並更新對應測試；env 名稱不變，避免再分裂
- [ ] **error_flag 分類**（寫入 `InteractionLog.errorFlag`）：
  - `asr_timeout` / `asr_api_error`
  - `llm_timeout` / `llm_api_error` / `llm_partial`
  - `tts_fail`
  - `unknown` — 未歸類例外（捕獲後 re-raise 前記錄）
- [ ] **實作骨架**（示意，參照 plan §5.3）：
  ```python
  try:
      async with asyncio.timeout(llm_first_tok_s):
          first_token = await anext(llm_stream)
  except TimeoutError:
      error_flag = "llm_timeout"
      await self._fallback.play("llm_error")
      return  # finally 會寫 log
  except LLMAPIError as e:
      logger.error("[%s][llm] api error: %s", trace_id, e)
      error_flag = "llm_api_error"
      await self._fallback.play("llm_error")
      return
  except asyncio.CancelledError:
      raise  # barge-in 用，Phase 4 才啟用
  ```
- [ ] **測試必須涵蓋**（`worker/tests/test_runner_errors.py`）：
  - 用 fake LLM 回傳 generator 模擬：
    - 立刻 raise `TimeoutError` → `error_flag == "llm_timeout"`，fallback.play 被呼叫 1 次帶 `llm_error`
    - 立刻 raise `LLMAPIError` → `error_flag == "llm_api_error"`
    - 首 token 後 delay 超過整體 timeout → `error_flag == "llm_partial"`，不呼叫 fallback
  - 用 fake ASR 模擬：
    - stream 永不 yield → 12s 後 timeout → `error_flag == "asr_timeout"`，fallback.play 呼叫 `asr_timeout`
    - stream raise Exception → `error_flag == "asr_api_error"`
  - 用 fake TTS 模擬單 chunk 卡住 → 跳過該 chunk 且後續句繼續
- [ ] **手動驗證**：
  - 停掉 LLM server（`docker compose stop ollama` 或改錯 `LLM_BASE_URL`）→ 對話時應在 ~5s 聽到 `llm_error` fallback
  - 停掉 ASR（斷網或改錯 URL）→ 應聽到 `asr_timeout` fallback
  - DB 對應輪次 `errorFlag` 正確填入
- [ ] **驗收**：
  - `uv run pytest worker/tests/test_runner_errors.py -v` 全綠
  - 三種手動斷線情境皆有對應 fallback 音訊與 `errorFlag`
  - 不吞例外：未分類例外 log 完整 traceback 後 re-raise（遵守 CLAUDE.md 錯誤處理規則）
- [ ] **Commit**：`feat(worker): add per-stage timeouts and error classification`

---

### P3-06：10 分鐘穩定性驗證與報告

- [ ] **依賴**：P3-02、P3-04、P3-05
- [ ] **檔案**：`docs/phase-3-stability-report.md`、`worker/scripts/latency_summary.py`
- [ ] **驗證步驟**（SOP，照著跑並截圖放報告）：
  1. 啟動完整系統：`docker compose up` + `pnpm --filter playground dev`
  2. 透過 Playground 連進 Room，與 agent 進行**至少 10 分鐘**自然對話（準備 ≥ 20 組題目：公車路線、數字念法、日常閒聊、刻意觸發錯誤等）
  3. 過程中於 ~第 5 分鐘時**手動拔網一次**（斷 LLM 或 ASR），驗證 fallback 播放正常；恢復後繼續對話
  4. 結束後跑 `uv run python -m worker.scripts.latency_summary --session <session_id>`
- [ ] **`latency_summary.py` 輸出**：
  ```
  Session: <uuid>   Turns: 42   Duration: 10m 23s
  latency_total      avg=1180ms  p50=980ms  p95=1850ms  max=2340ms
  latency_asr_end    avg=280ms   p95=520ms
  latency_llm_first  avg=460ms   p95=980ms
  latency_first_audio avg=380ms  p95=720ms
  Errors: 2/42 (4.8%)
    - llm_timeout: 1
    - asr_timeout: 1
  ```
- [ ] **報告內容**（`docs/phase-3-stability-report.md`）：
  - 測試環境（硬體、網路、模型版本）
  - 對話逐字稿摘要或列出 ≥ 20 個 user turn
  - 上述統計輸出
  - 觀察到的問題與延遲瓶頸分析（指出哪一段最慢）
  - 對照 `plan.md §6.3` 目標：是否達標
- [ ] **驗收**：
  - 平均 `latency_total` < 1500ms
  - 測試過程**無 Worker crash**、**無 Playground 斷線**
  - Error rate < 5%（手動觸發的斷線那 2 次算進去仍需 < 5% 則要 ≥ 40 turn）
  - 5 種 fallback 情境至少出現過 `asr_timeout`、`llm_error` 兩種實測
  - 報告已 commit
- [ ] **Commit**：`docs(phase-3): add stability run report and latency summary script`

---

## Phase 3 完成標準

- [ ] P3-01 ~ P3-06 全部 [x]
- [ ] `uv run pytest` 全綠，新增的 test case ≥ 15 個
- [ ] `uv run pyright` strict 通過
- [ ] DB `InteractionLog` 查詢可見連續多輪完整 latency 與 error 欄位
- [ ] 10 分鐘穩定性報告達標並 commit
- [ ] 5 種 fallback 音訊皆能觸發（可手動、也可腳本）

## 常見陷阱

- ❌ **把 DB 寫入放進 critical path 同步等待** → DB 慢會拖垮對話。必須 `try/except` 包起來吞錯，或之後考慮背景 task（本 Phase 先用前者）
- ❌ **fallback 文字變動不同步 `FALLBACK_TEXTS` 與 runner 呼叫** → 集中在 `worker/audio/fallback.py` 單一 source
- ❌ **超時用 `time.sleep` 或輪詢** → 一律用 `asyncio.wait_for` / `asyncio.timeout`
- ❌ **吞掉未分類例外** → `except Exception as e: logger.exception(...); error_flag = "unknown"; raise` 或降級後重拋
- ❌ **測試用真實 LLM/ASR** → Phase 3 測試全部走 fake/mock，符合 CLAUDE.md 「IO 包裝用 mock 測介面契約」
- ❌ **把 Barge-in 或 Tool call 偷渡進來** → 留給 Phase 4 / 6
