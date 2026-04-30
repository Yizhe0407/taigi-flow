# Phase 4：Barge-in + 自說話抑制（Week 5）

> **目標**：使用者可以打斷 Agent，且 Agent 不會被自己的 TTS 回音誤觸發。
>
> **前置**：Phase 3 完成（P3-01 ~ P3-06 全部 [x]）
>
> **交付物**：5 個壓力測試案例全通過；無殘音、無狀態卡死；DB `wasBargedIn` 欄位正確標記
>
> **對應 plan.md**：[§3.2 Barge-in 狀態機](../docs/plan.md#32-barge-in-狀態機完整實作)、[§3.3 AEC](../docs/plan.md#33-aecacoustic-echo-cancellation策略)

---

## ⚠️ Phase 重點

**Barge-in 最常見的 bug 不是「偵測不到」，而是「誤觸發」**——被自己的 TTS 回音、被短促雜音、被環境音樂觸發。本 Phase 的驗收重點是**正確的誤判抑制**，不是「能打斷」。

**現況盤點**（2026-04-30 對 main 驗證）：
- `rtc.AudioSource` 已內建 `clear_queue()` / `wait_for_playout()` 方法 → 不需要自幹 audio publisher
- `PiperTTS.clear_queue()` 已存在（`worker/pipeline/tts.py:187`）→ 設定 `_clear_event`，合成執行緒下個 chunk 自動跳出
- `SileroVAD.update_thresholds()` 已存在（`worker/audio/vad.py:14`）→ 可在狀態轉換時動態調整門檻
- `_run_llm_tts` 採用 `asyncio.gather(_produce, _consume)`（commit `47aa8a4`）→ cancel 外層 Task 會自動連帶 cancel 兩個子 task 與所有 TTS sub-tasks（已寫在 except 區塊）
- `process_utterance` 由 `AudioProcessor._spawn()` 包成獨立 `asyncio.Task` → 拿到 task handle 即可 cancel
- 前端 `web/apps/playground/src/app/page.tsx` line 121、206 已啟用 `echoCancellation/noiseSuppression/autoGainControl`
- 還沒做：狀態機、跨層的 state 共享、cancellation 觸發點、self-speech 抑制邏輯

**本 Phase 禁止**：
- ❌ 引入聲學級 AEC（`speexdsp` / `webrtc-audio-processing` Python binding）→ 過度工程，留給 Phase 7+
- ❌ 加入 RAG/Tool call → Phase 6
- ❌ 把 `PipelineRunner._run_llm_tts` 拆成更多 task pool → Phase 4 不重構，只加 cancellation hook

---

## 任務清單

### P4-01：VoiceController 純狀態機

- [ ] **依賴**：無
- [ ] **檔案**：`worker/audio/voice_controller.py`、`worker/tests/test_voice_controller.py`
- [ ] **參照**：`docs/plan.md §3.2`（狀態轉換表）
- [ ] **輸入規格**：
  ```python
  from __future__ import annotations
  import enum
  import logging
  import time
  from collections.abc import Callable
  from dataclasses import dataclass, field

  class VoiceState(enum.Enum):
      IDLE = "idle"            # 等待使用者開口
      LISTENING = "listening"  # ASR 進行中（VAD 已觸發 START）
      THINKING = "thinking"    # ASR 完成、LLM 生成中
      SPEAKING = "speaking"    # TTS 正在輸出音訊
      BARGED_IN = "barged_in"  # 清理中（即將回 LISTENING）

  # 合法轉換表（unfounded transitions raise ValueError or log warning）
  _TRANSITIONS: dict[VoiceState, set[VoiceState]] = {
      VoiceState.IDLE:       {VoiceState.LISTENING},
      VoiceState.LISTENING:  {VoiceState.THINKING, VoiceState.IDLE},
      VoiceState.THINKING:   {VoiceState.SPEAKING, VoiceState.IDLE, VoiceState.BARGED_IN},
      VoiceState.SPEAKING:   {VoiceState.IDLE, VoiceState.BARGED_IN},
      VoiceState.BARGED_IN:  {VoiceState.LISTENING, VoiceState.IDLE},
  }

  @dataclass
  class VoiceController:
      """純狀態機 + 自說話抑制時間戳。不做 I/O；轉換動作由 P4-02 / P4-03 注入。"""

      _state: VoiceState = VoiceState.IDLE
      _last_tts_output_ts: float = 0.0
      _on_change: list[Callable[[VoiceState, VoiceState], None]] = field(default_factory=list)

      @property
      def state(self) -> VoiceState: ...

      def transition(self, new_state: VoiceState) -> None:
          """改變狀態。非法轉換 log warning + 強制轉換（不 raise，避免讓對話流程崩潰）。"""

      def is_speaking(self) -> bool: ...
      def mark_tts_output(self) -> None:
          """記錄此刻為「最後一次推送 TTS frame 的時間」。給自說話抑制用。"""
      def time_since_last_tts_ms(self) -> float: ...

      def on_change(self, cb: Callable[[VoiceState, VoiceState], None]) -> None:
          """註冊狀態變化 callback。多個 callback 依註冊順序呼叫。callback 不可 await。"""
  ```
- [ ] **實作細節**：
  - `transition()` 收到非法轉換時 `logger.warning(...)` 後仍套用新狀態（fail-soft，避免 mid-call crash）
  - 轉換動作（cancel task / clear queue）**不在這個 class 內**，由外部註冊 callback
  - `mark_tts_output()` 用 `time.perf_counter()`，與 `LatencyTimer` 對齊
  - 不需要鎖（asyncio 單執行緒）
- [ ] **測試必須涵蓋**（`test_voice_controller.py`，至少 7 case）：
  - 初始狀態為 `IDLE`
  - 合法轉換 `IDLE → LISTENING → THINKING → SPEAKING → IDLE` 全綠
  - 合法 barge-in 路徑 `SPEAKING → BARGED_IN → LISTENING`
  - 非法轉換（如 `IDLE → SPEAKING`）log warning 後仍轉換
  - `on_change` callback 收到正確 (old, new) 參數，多個 callback 都被呼叫
  - `mark_tts_output` + `time_since_last_tts_ms`：用 `monkeypatch.setattr(time, "perf_counter", ...)` 驗證精確
  - `is_speaking()` 只在 `SPEAKING` 為 True
- [ ] **驗收**：
  - `uv run pytest worker/tests/test_voice_controller.py -v` 全綠
  - `uv run pyright worker/audio/voice_controller.py` strict 通過
- [ ] **Commit**：`feat(worker): add voice controller fsm`

---

### P4-02：把 VoiceController 串入 PipelineRunner 與 AudioProcessor

- [ ] **依賴**：P4-01
- [ ] **檔案**：
  - `worker/session/components.py`（擴充：加入 `voice_controller` 欄位）
  - `worker/session/runner.py`（在關鍵點呼叫 `transition()`）
  - `worker/audio/processor.py`（在 VAD 事件中讀取 state）
- [ ] **參照**：`docs/plan.md §3.2` 狀態轉換表
- [ ] **`AgentComponents` 擴充**：
  ```python
  @dataclasses.dataclass
  class AgentComponents:
      ...
      voice_controller: VoiceController  # 新增
  ```
  在 `build_components()` 直接 `voice_controller = VoiceController()`，不需設定參數。
- [ ] **`PipelineRunner` 變更**：
  - 建構子讀 `self._vc = components.voice_controller`
  - `process_utterance` 內各階段做 transition：
    | 時機 | 轉換 |
    |------|------|
    | 函式開頭（已通過 `_pipeline_busy` 檢查） | `IDLE → LISTENING`（若已是 LISTENING 則 no-op） |
    | ASR 成功取得非空 `user_text` 後 | `LISTENING → THINKING` |
    | `_run_llm_tts` 內首個 `_play_pcm_bytes` 之前 | `THINKING → SPEAKING` |
    | `finally` 區塊（正常結束） | `SPEAKING → IDLE` 或 `THINKING → IDLE`（依當下狀態決定） |
  - `_play_pcm_bytes` 內每次 `capture_frame` 之後呼叫 `self._vc.mark_tts_output()`（給 P4-04 用）
- [ ] **`AudioProcessor` 變更**：
  - 建構子接收 `voice_controller: VoiceController`
  - VAD `START_OF_SPEECH` 事件處理：
    - 若 `vc.state == IDLE`：照舊（什麼都不做，等 END_OF_SPEECH）
    - 若 `vc.state == SPEAKING`：**這就是 barge-in 觸發點**，留給 P4-03 處理（本 task 只 log，不真的中斷）
    - 若 `vc.state in (LISTENING, THINKING)`：log info 標記為「使用者連續說話」，不轉狀態
  - VAD `END_OF_SPEECH`：在 `_spawn(runner.process_utterance(...))` 之前呼叫 `vc.transition(LISTENING)`（VAD 確認確實是有效 utterance）
- [ ] **驗收**：
  - 與 Playground 對話一輪，log 應依序出現：
    ```
    [vc] IDLE → LISTENING (vad end_of_speech)
    [vc] LISTENING → THINKING (asr done)
    [vc] THINKING → SPEAKING (first audio)
    [vc] SPEAKING → IDLE (turn end)
    ```
  - DB `InteractionLog.wasBargedIn` 欄位仍為 `false`（barge-in 邏輯尚未啟用）
  - `uv run pyright worker/session/ worker/audio/processor.py` strict 通過
- [ ] **Commit**：`feat(worker): wire voice controller state transitions into pipeline`

---

### P4-03：Barge-in 觸發與六步清理序列

- [ ] **依賴**：P4-02
- [ ] **檔案**：
  - `worker/audio/voice_controller.py`（擴充：加入 `on_barge_in()` 方法）
  - `worker/session/runner.py`（擴充：暴露 `cancel_current_turn()`、`barged_in` 標記、handle CancelledError 寫 log）
  - `worker/audio/processor.py`（擴充：VAD START 在 SPEAKING 狀態觸發 barge-in）
- [ ] **參照**：`docs/plan.md §3.2` 「打斷時的清理順序」
- [ ] **`PipelineRunner` 變更**：
  - 建構子初始化 `self._current_turn_task: asyncio.Task[None] | None = None`
  - `process_utterance` 函式開頭把自己的 task 綁定：`self._current_turn_task = asyncio.current_task()`
  - 新增 instance var `self._was_barged_in: bool = False`，每輪開頭重置為 False
  - `process_utterance` 的外層 `try` 加上 `except asyncio.CancelledError:` 區塊：
    ```python
    except asyncio.CancelledError:
        self._was_barged_in = True
        # finally 仍會執行 log_turn 寫入 wasBargedIn=True
        raise
    ```
  - `finally` 區塊呼叫 `log_turn` 時帶 `was_barged_in=self._was_barged_in`
  - 新增 method：
    ```python
    def cancel_current_turn(self) -> None:
        """同步呼叫；標記 barged_in 並 cancel 當前 turn task。Audio cleanup 由 VoiceController.on_barge_in 執行。"""
        if self._current_turn_task is None or self._current_turn_task.done():
            return
        self._was_barged_in = True
        self._current_turn_task.cancel()
    ```
- [ ] **`VoiceController.on_barge_in()` 規格**：
  ```python
  async def on_barge_in(
      self,
      *,
      runner: "PipelineRunner",
      tts: "PiperTTS | None",
      audio_source: "rtc.AudioSource",
  ) -> None:
      """
      六步清理序列（順序不可換）：
        1. audio_source.clear_queue()         # 立刻丟棄已 enqueued 的 frame
        2. tts.clear_queue() if tts else None # 設定 _clear_event；合成執行緒下個 chunk 跳出
        3. runner.cancel_current_turn()        # cancel asyncio.gather → cascade cancel 所有 TTS subtask
        4. # 不需手動 flush splitter — splitter 是 _run_llm_tts 內 local var，task cancel 時自然消失
        5. # log_turn 由 process_utterance 的 finally 寫，wasBargedIn=True 已由 cancel_current_turn 設定
        6. self.transition(VoiceState.BARGED_IN)
      呼叫端應在 await 此函式後再 transition(LISTENING)（等 cancellation 真正完成）。
      """
  ```
- [ ] **`AudioProcessor` 變更**：
  - 在 `_consume_vad` 的 `START_OF_SPEECH` 分支：
    ```python
    if vc.state == VoiceState.SPEAKING:
        # 可能是 barge-in，但要先確認不是自說話（P4-04 會強化判斷；本 task 先做基本版）
        time_since_tts_ms = vc.time_since_last_tts_ms()
        if time_since_tts_ms < 200:
            logger.info("VAD START suppressed (self-speech, %.0fms since tts)", time_since_tts_ms)
            continue
        logger.info("Barge-in detected, triggering cleanup")
        await vc.on_barge_in(runner=self._runner, tts=self._runner._tts, audio_source=self._runner._audio_source)
        # 接下來這次 utterance 由後續 END_OF_SPEECH 走正常流程
    ```
  - **重要**：`on_barge_in` 是 async，VAD consumer loop 內可以 await（不會 block 其他 audio frames，因為 frame loop 在另一個 task）
- [ ] **`process_utterance` 取消後的 transition**：
  - 在 `finally` 區塊末尾，若 `self._was_barged_in == True`：`vc.transition(LISTENING)`（讓下次 VAD START 不會被當 barge-in）
  - 否則照舊 `vc.transition(IDLE)`
- [ ] **測試必須涵蓋**（`test_runner_errors.py` 擴充或新增 `test_barge_in.py`，至少 4 case）：
  - 用 fake LLM yield 永遠不結束 → `runner.cancel_current_turn()` → `process_utterance` 在合理時間內結束（< 100ms）
  - cancel 之後 `log_turn` 被呼叫且 `was_barged_in=True`
  - cancel 之後 `tts.clear_queue` 被呼叫一次
  - cancel 之後 `audio_source.clear_queue` 被呼叫一次
  - VoiceState 在 cancel 後最終回到 LISTENING（透過 finally）
- [ ] **驗收**：
  - 手動測試：與 agent 對話，agent 開口後立即「啊！」打斷 → agent 應在 < 500ms 內停止
  - DB log 對應輪次 `wasBargedIn=true`
  - log 沒有 `unhandled exception` 錯誤
- [ ] **Commit**：`feat(worker): implement barge-in cleanup sequence`

---

### P4-04：動態 VAD 門檻（自說話抑制強化）

- [ ] **依賴**：P4-03
- [ ] **檔案**：
  - `worker/audio/processor.py`（擴充：在狀態進入/離開 SPEAKING 時調整門檻）
  - 可選：`worker/audio/voice_controller.py`（加入 `vad_threshold_for_state()` helper）
- [ ] **參照**：`docs/plan.md §3.3` `vad_threshold_dynamic`
- [ ] **策略**：
  - **P4-03 已做基本「200ms 內忽略 VAD START」軟性規則**，本 task 加強為動態門檻
  - 在 `VoiceController.on_change` 註冊 callback，狀態變更時呼叫 `vad.update_thresholds(...)`：
    | 狀態 | activation_threshold | min_speech_duration |
    |------|---------------------|---------------------|
    | 非 SPEAKING（IDLE/LISTENING/THINKING） | 0.5（預設） | 0.3 |
    | SPEAKING | 0.75 | 0.5 |
- [ ] **實作細節**：
  - 在 `AudioProcessor.__init__` 註冊 callback：
    ```python
    vc.on_change(self._apply_vad_thresholds)
    def _apply_vad_thresholds(self, old: VoiceState, new: VoiceState) -> None:
        if new == VoiceState.SPEAKING:
            self._vad.update_thresholds(activation_threshold=0.75, min_speech_duration=0.5)
        elif old == VoiceState.SPEAKING:
            self._vad.update_thresholds(activation_threshold=0.5, min_speech_duration=0.3)
    ```
  - 不要在 BARGED_IN 重設門檻（避免 BARGED_IN → LISTENING 跳兩次）；只在進入/離開 SPEAKING 時調
- [ ] **測試必須涵蓋**：
  - VoiceController on_change callback 在 `IDLE → LISTENING → THINKING → SPEAKING` 序列下，`vad.update_thresholds` 只被呼叫 1 次（且帶 0.75）
  - `SPEAKING → IDLE` 時被呼叫第 2 次（帶 0.5）
- [ ] **驗收**：
  - 手動測試：把喇叭外放（不戴耳機）讓 agent 說話，自己不發聲。觀察 log 不應出現「Barge-in detected」（被 0.75 門檻擋下）
  - 反向測試：刻意說「啊」打斷，仍能正確觸發 barge-in（usermic prob > 0.75）
- [ ] **Commit**：`feat(worker): dynamic vad threshold for self-speech suppression`

---

### P4-05：前端 AEC 設定確認

- [ ] **依賴**：無（可與 P4-01 並行）
- [ ] **檔案**：`web/apps/playground/src/app/page.tsx`
- [ ] **現況**：line 121、line 206 兩處已設定 `echoCancellation/noiseSuppression/autoGainControl: true`，**本 task 主要是驗證**
- [ ] **要做**：
  - 在 `getUserMedia` 與 `LiveKitRoom` 兩處 audio 設定旁加註解，標明三項都必須為 true，未來不可關閉
  - （可選）打開 Chrome DevTools `chrome://webrtc-internals/`，與 agent 對話後檢查：
    - `googEchoCancellation` 為 enabled
    - `googEchoCancellationAEC3` 為 enabled
- [ ] **驗收**：
  - 手動：戴耳機 vs 喇叭外放各測一次，外放時不應有明顯回音觸發 barge-in（搭配 P4-04 的軟性規則）
  - codebase grep `echoCancellation` 兩處都為 true
- [ ] **Commit**：`chore(playground): document and lock webrtc aec settings`

---

### P4-06：Barge-in 壓力測試與報告

- [ ] **依賴**：P4-03、P4-04、P4-05
- [ ] **檔案**：`docs/phase-4-bargein-report.md`
- [ ] **5 個壓力測試案例**（每案例執行 ≥ 3 次，記錄成功/失敗）：

  | # | 案例 | 預期行為 |
  |---|------|----------|
  | 1 | Agent 說話中途使用者打斷 | Agent 在 < 500ms 內停止；下一輪正常對話 |
  | 2 | Agent 說話時喇叭外放（自我回灌） | **不**觸發 barge-in；agent 把話說完 |
  | 3 | 快速連續 3 次打斷（每次間隔 1 秒） | 狀態機無卡死；3 次都觸發；無殘音 |
  | 4 | Agent 剛開口 < 200ms 即被打斷 | 觸發成功；無 race condition crash |
  | 5 | 打斷後立即說新問題（< 1 秒內） | 新對話正常進行；DB log 連續兩輪 |

- [ ] **每個案例記錄**：
  - 觸發時間、停止時間、`latency_first_audio` 的下一輪表現
  - DB 對應輪次的 `wasBargedIn` 值
  - 是否有殘音（聽感判斷）
  - log 中是否出現 unhandled exception
- [ ] **報告內容**（`docs/phase-4-bargein-report.md`）：
  - 測試環境、麥克風型號、使用耳機/喇叭
  - 5 個案例表格（success rate）
  - 觀察到的問題與調整（如有）
- [ ] **驗收**：
  - 5 個案例 success rate ≥ 80%（即每個 ≥ 3 次中至少 3 次成功，或 ≥ 4 次中 ≥ 4 次）
  - 案例 2 必須 100% 成功（自說話抑制是核心驗收）
  - 無殘音、無 worker crash、無 playground 斷線
  - 報告 commit
- [ ] **Commit**：`docs(phase-4): add barge-in stress test report`

---

## Phase 4 完成標準

- [ ] P4-01 ~ P4-06 全部 [x]
- [ ] `uv run pytest` 全綠，新增的 test case ≥ 12 個
- [ ] `uv run pyright` strict 通過
- [ ] DB `InteractionLog.wasBargedIn` 欄位在打斷輪次正確標記為 `true`
- [ ] 案例 2（自說話抑制）100% 通過
- [ ] 5 個案例平均 success rate ≥ 80%

## 常見陷阱

- ❌ **以為 audio_source 還在播 → 強制 disconnect** → `clear_queue()` 已足夠丟棄 buffered frame，不需要 disconnect track
- ❌ **`tts.clear_queue` 後立刻又呼叫 `synthesize`** → `_clear_event` 還沒被新 `synthesize` 重置會直接跳出。`tts.synthesize` 開頭已 `_clear_event.clear()`，但要確認 cancel 完成後再啟新 turn
- ❌ **VAD START 在 SPEAKING 一定觸發 barge-in** → 必須先檢查 `time_since_last_tts_ms < 200` 與動態門檻，否則自說話會誤觸發
- ❌ **改 VAD 門檻時 forget 重置** → SPEAKING 結束後沒重置會讓下次 IDLE 用 0.75，使用者要更大聲才被偵測
- ❌ **在 VoiceController 內做 I/O** → controller 應該保持純粹（state + timestamp），所有 I/O 由 callback / 外層 method 注入
- ❌ **cancel 之後忘記等 task done** → cancel 是 async signal，必須 `await task` 或在 finally 內讓 task 自己結束。本 phase 用 finally 結構確保
- ❌ **把 splitter 變成 instance var 然後忘記在 cancel 時 flush** → 目前 splitter 是 `_run_llm_tts` local，cancel 時 task 結束自動清理；不要為了「方便 flush」改成 instance var
