# Phase 1：純文字對話鏈（Week 2）

> **目標**：在完全不碰 LiveKit 與語音的情況下，打通 `文字輸入 → LLM → 切句 → 字典 → Taibun → 文字輸出 + DB log` 的完整鏈路。
>
> **前置**：Phase 0 完成
>
> **交付物**：一個 CLI 工具，可以跟 Agent 進行純文字對話，所有中間結果寫入 DB
>
> **對應 plan.md**：[§3.4 記憶](../docs/plan.md#34-滑動視窗記憶管理)、[§4.3 Splitter](../docs/plan.md#43-smart-sentence-splitter)、[§4.4 文字處理鏈](../docs/plan.md#44-文字處理鏈hanloflow--字典替換--taibun)
>
> **對應 ADR**：[001-sliding-window-memory](../docs/adr/001-sliding-window-memory.md)、[003-postgres-over-env](../docs/adr/003-postgres-over-env.md)

---

## ⚠️ Phase 重點

**為什麼要先做純文字？** 語音層（WebRTC、VAD、音訊 chunk）debug 困難、錯誤訊息模糊。先在純文字環境把核心邏輯（記憶、切句、字典、轉換）磨到穩定，Phase 2 再把語音殼套上去。很多團隊一開始就卡在 WebRTC 連不上，結果兩個月後還在 debug 基礎建設。

本 Phase **禁止**：接入 LiveKit、實作 VAD、實作 TTS、實作 ASR

---

## 任務清單

### P1-01：實作 SlidingWindowMemory

- [ ] **依賴**：P0-05
- [ ] **檔案**：`worker/pipeline/memory.py`、`worker/tests/test_memory.py`
- [ ] **輸入規格**：
  ```python
  class SlidingWindowMemory:
      def __init__(self, max_turns: int = 12, system_prompt: str = "") -> None: ...
      def add(self, role: Literal["user", "assistant"], content: str) -> None: ...
      def to_messages(self) -> list[dict[str, str]]: ...
      def clear(self) -> None: ...
      def __len__(self) -> int: ...  # 回傳當前 turn 數
  ```
- [ ] **實作細節**：照 `docs/plan.md §3.4` 的範例
- [ ] **測試必須涵蓋**：
  - 空記憶時 `to_messages()` 只回傳 system prompt
  - 新增 5 輪後，`to_messages()` 回傳 1 + 10 則訊息
  - 超過 `max_turns` 時，最舊的 user+assistant **成對**被丟棄（不能留孤兒 assistant）
  - `clear()` 後完全重置
  - 設定 `max_turns=3` 並加入 4 輪，確認第 1 輪被丟棄
- [ ] **驗收**：
  - `uv run pytest worker/tests/test_memory.py -v` 全綠，至少 5 個 test case
  - Pyright strict 通過
- [ ] **Commit**：`feat(worker): add sliding window memory with unit tests`

---

### P1-02：實作 SmartSplitter

- [ ] **依賴**：P0-05
- [ ] **檔案**：`worker/pipeline/splitter.py`、`worker/tests/test_splitter.py`
- [ ] **輸入規格**：
  ```python
  class SmartSplitter:
      STRONG_BREAKS: ClassVar[set[str]] = {"。", "！", "？", "\n"}
      MEDIUM_BREAKS: ClassVar[set[str]] = {"，", "；", "："}
      WEAK_BREAKS: ClassVar[set[str]] = {" ", "、"}
      MIN_CHARS_FOR_MEDIUM: ClassVar[int] = 6
      MAX_BUFFER_CHARS: ClassVar[int] = 40

      def __init__(self) -> None: ...
      def feed(self, token: str) -> list[str]: ...
      def flush(self) -> str: ...
  ```
- [ ] **實作細節**：照 `docs/plan.md §4.3` 的演算法
- [ ] **測試必須涵蓋**（至少 15 個 case）：
  - 單一強斷點：`feed("你好。")` 應切出 `["你好。"]`
  - 中斷點 + 字數不足：`feed("好，")` 不切（< 6 字）
  - 中斷點 + 字數足夠：`feed("請問今天天氣，")` 應切
  - 多 token 累積：逐字餵 `"你好，我是 Claude。"` 最終切成兩句
  - 超長句強制切：餵 45 字無標點，在第 40 字強切
  - `flush()` 回傳剩餘 buffer
  - 空字串 `feed("")` 不出錯
  - 連續強斷點 `feed("好。。。")` 不產生空字串
  - 只有空白：`feed("   ")` 視為無意義，不切
  - 英文混雜：`feed("use Python.")` 切點處理正常
- [ ] **驗收**：
  - `uv run pytest worker/tests/test_splitter.py -v` 全綠
  - 至少 15 個 test case
- [ ] **Commit**：`feat(worker): add smart sentence splitter with edge case tests`

---

### P1-03：實作 LLM 客戶端

- [ ] **依賴**：P0-05、P1-01
- [ ] **檔案**：`worker/pipeline/llm.py`、`worker/tests/test_llm.py`
- [ ] **輸入規格**：
  ```python
  class LLMClient:
      def __init__(self, base_url: str, api_key: str, model: str) -> None: ...
      async def stream(
          self,
          messages: list[dict[str, str]],
          tools: list[dict] | None = None,
          timeout: float = 15.0,
      ) -> AsyncIterator[str]: ...  # yield text tokens
  ```
- [ ] **實作細節**：
  - 使用 `openai` SDK（OpenAI 相容介面）
  - Stream 模式
  - 超時拋 `asyncio.TimeoutError`
  - 支援 `asyncio.CancelledError`（被 barge-in 取消時要乾淨退出）
  - **首次 token 超時 5 秒**則拋 `TimeoutError`（讓 worker 可播 fallback）
- [ ] **測試**：
  - 使用 `pytest-httpserver` 或 mock，不打真實 API
  - 驗證：基本串流、超時、取消、tool call 格式
- [ ] **驗收**：
  - `uv run pytest worker/tests/test_llm.py -v` 全綠
  - 至少 4 個 test case
- [ ] **Commit**：`feat(worker): add streaming llm client with timeout and cancellation`

---

### P1-04：包裝 HanloFlow 與 Taibun

- [ ] **依賴**：P0-05
- [ ] **檔案**：`worker/pipeline/text_processor.py`、`worker/tests/test_text_processor.py`
- [ ] **前置**：
  - 先在 `pyproject.toml` 加入 HanloFlow 與 Taibun 依賴
  - 若這兩個套件有安裝問題（很可能有），**先停下來問人類**，不要自作主張換套件
- [ ] **輸入規格**：
  ```python
  @dataclass
  class ProcessResult:
      hanlo: str
      taibun: str

  class TextProcessor:
      def __init__(
          self,
          profile_id: str | None = None,
          db_session: AsyncSession | None = None,
      ) -> None: ...
      async def load_dictionary(self) -> None: ...  # 從 DB 載入並排序
      def process(self, zh_text: str) -> ProcessResult: ...
      def _apply_dictionary(self, text: str) -> str: ...
  ```
- [ ] **實作細節**：照 `docs/plan.md §4.4` 範例
  - 字典排序：`priority DESC, len(term) DESC`
  - 字典替換在 HanloFlow 之前（用 `⟨...⟩` 保護標記）
  - 啟動時一次性載入，不每次查 DB
- [ ] **測試**：
  - 一般繁中轉換
  - 字典命中（手動塞 fixture）
  - 字典優先級：同詞多條目，priority 高的先匹配
  - 長詞優先：「公車路線」先於「公車」
  - 空字串不出錯
- [ ] **驗收**：
  - `uv run pytest worker/tests/test_text_processor.py -v` 全綠
  - 至少 6 個 test case
- [ ] **Commit**：`feat(worker): add text processor with hanloflow, taibun and dictionary`

---

### P1-05：InteractionLog 寫入封裝

- [ ] **依賴**：P0-06
- [ ] **檔案**：`worker/db/repositories.py`（擴充）、`worker/tests/test_interaction_log.py`
- [ ] **輸入規格**：
  ```python
  class InteractionLogRepository:
      def __init__(self, session_factory) -> None: ...
      async def create_session(
          self,
          agent_profile_id: str,
          livekit_room: str,
      ) -> str: ...  # 回傳 session_id
      async def log_turn(
          self,
          session_id: str,
          turn_index: int,
          user_asr_text: str,
          llm_raw_text: str,
          hanlo_text: str | None,
          taibun_text: str,
          latencies: dict[str, int] | None = None,
          was_barged_in: bool = False,
          error_flag: str | None = None,
      ) -> None: ...
      async def end_session(self, session_id: str) -> None: ...
  ```
- [ ] **測試**：
  - 建立 session → 寫 turn → 結束 session
  - 驗證 DB 中資料正確（turn_index 連續、時間戳存在）
- [ ] **驗收**：
  - `uv run pytest worker/tests/test_interaction_log.py -v` 全綠
  - 能在 `prisma studio` 看到寫入的資料
- [ ] **Commit**：`feat(worker): add interaction log repository`

---

### P1-06：整合為 CLI 對話工具

- [ ] **依賴**：P1-01 ~ P1-05 全部完成
- [ ] **檔案**：`worker/cli.py`
- [ ] **功能**：
  ```bash
  uv run python -m worker.cli --profile "公車站長"
  ```
  - 進入互動 REPL
  - 使用者輸入文字 → 送 LLM → 串流印出 LLM 回覆、每段切句、對應漢羅、對應台羅
  - 每輪寫入 InteractionLog
  - `Ctrl+C` 優雅退出，呼叫 `end_session`
- [ ] **輸出格式範例**：
  ```
  You > 請問 307 公車到站時間
  Assistant >
    [LLM]     根據最新資料，307 公車
    [CHUNK]   「根據最新資料，307 公車」
    [HANLO]   根據最新資料, saⁿ-khòng-tshit 公車
    [TAIBUN]  kin-kù tsuè-sin tsu-liāu, saⁿ-khòng-tshit kong-tshia
    [LLM]     大約 5 分鐘後到站。
    [CHUNK]   「大約 5 分鐘後到站。」
    ...
  [Latency] ASR end N/A | LLM first tok 342ms | Total 1203ms
  ```
- [ ] **驗收**：
  - 能至少進行 10 輪對話，記憶視窗正常運作（問「我剛剛問什麼？」能答出）
  - 每輪都有寫入 InteractionLog（`SELECT COUNT(*) FROM "InteractionLog";` 會增加）
  - 中斷後重跑，能建立新 session 不污染舊資料
- [ ] **Commit**：`feat(worker): add cli for text-only conversation testing`

---

### P1-07：字典熱更新機制（基礎版）

- [ ] **依賴**：P1-04
- [ ] **檔案**：`worker/pipeline/text_processor.py`（擴充）
- [ ] **需求**：當後台新增字典條目，worker 不重啟也能生效
- [ ] **實作方式**（選一種，簡單優先）：
  - **方案 A（簡單）**：每次 `process()` 檢查 DB 最新 `updatedAt`，若比快取新則重載
  - **方案 B（進階）**：用 Redis pub/sub，後台寫入時發 invalidate 訊號
- [ ] **建議**：先做方案 A，若觀察到 DB 查詢延遲過高再改 B
- [ ] **測試**：
  - 載入後手動插入新字典條目 → 下一次 `process()` 應命中新條目
- [ ] **驗收**：
  - CLI 運行中，在另一個 terminal 用 `psql` 新增字典條目，下一輪對話立即生效
- [ ] **Commit**：`feat(worker): add dictionary hot reload mechanism`

---

### P1-08：撰寫 Phase 1 完成報告

- [ ] **依賴**：P1-01 ~ P1-07
- [ ] **檔案**：`docs/phase-1-report.md`
- [ ] **內容**：
  - 各模組的介面與職責簡述
  - 已知限制與 Phase 2 待處理事項
  - 關鍵測試案例的結果（可附截圖 / log 片段）
  - 如果遇到套件問題（HanloFlow / Taibun），記錄解法
- [ ] **驗收**：
  - 文件存在且完整
  - 能讓 Phase 2 的開發者（可能是組員，可能是未來的自己）快速上手
- [ ] **Commit**：`docs: add phase 1 completion report`

---

## Phase 1 完成標準

- [ ] P1-01 ~ P1-08 全部打勾
- [ ] `uv run pytest` 全綠，總 test case 數 ≥ 30
- [ ] Pyright strict 模式通過
- [ ] CLI 能進行 10 分鐘以上的穩定對話
- [ ] InteractionLog 寫入正確無遺漏
- [ ] 字典熱更新驗證通過

## 常見陷阱

**❌ 禁止**：在本 Phase 引入 LiveKit / VAD / TTS / ASR 相關程式碼

**❌ 禁止**：為了追求「更好的記憶效果」引入 summary 機制（見 ADR-001）

**❌ 禁止**：擅自替換 HanloFlow / Taibun（見 CLAUDE.md 定案決策）

**✅ 遇到問題該做的**：
- 套件衝突 → 停下來問人類
- 測試寫不出來 → 可能是介面設計不合理，重新設計介面
- DB schema 不夠用 → 停下來問人類，不要擅自改