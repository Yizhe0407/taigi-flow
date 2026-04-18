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

- [x] **依賴**：P0-05
- [x] **檔案**：`worker/pipeline/memory.py`、`worker/tests/test_memory.py`
- [x] **輸入規格**：
  ```python
  class SlidingWindowMemory:
      def __init__(self, max_turns: int = 12, system_prompt: str = "") -> None: ...
      def add(self, role: Literal["user", "assistant"], content: str) -> None: ...
      def to_messages(self) -> list[dict[str, str]]: ...
      def clear(self) -> None: ...
      def __len__(self) -> int: ...  # 回傳當前 turn 數
  ```
- [x] **實作細節**：照 `docs/plan.md §3.4` 的範例
- [x] **測試必須涵蓋**：
  - 空記憶時 `to_messages()` 只回傳 system prompt
  - 新增 5 輪後，`to_messages()` 回傳 1 + 10 則訊息
  - 超過 `max_turns` 時，最舊的 user+assistant **成對**被丟棄（不能留孤兒 assistant）
  - `clear()` 後完全重置
  - 設定 `max_turns=3` 並加入 4 輪，確認第 1 輪被丟棄
- [x] **驗收**：
  - `uv run pytest worker/tests/test_memory.py -v` 全綠，至少 5 個 test case
  - Pyright strict 通過
- [x] **Commit**：`feat(worker): add sliding window memory with unit tests` (d3d3878)

---

### P1-02：實作 SmartSplitter

- [x] **依賴**：P0-05
- [x] **檔案**：`worker/pipeline/splitter.py`、`worker/tests/test_splitter.py`
- [x] **輸入規格**：
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
- [x] **實作細節**：照 `docs/plan.md §4.3` 的演算法
- [x] **測試必須涵蓋**（至少 15 個 case）：全部覆蓋
- [x] **驗收**：
  - `uv run pytest worker/tests/test_splitter.py -v` 全綠
  - 至少 15 個 test case
- [x] **Commit**：`feat(worker): add smart sentence splitter with edge case tests` (4808dba)

---

### P1-03：實作 LLM 客戶端

- [x] **依賴**：P0-05、P1-01
- [x] **檔案**：`worker/pipeline/llm.py`、`worker/tests/test_llm.py`
- [x] **輸入規格**：符合 task spec
- [x] **實作細節**：openai SDK + stream + 首次 token 5s 超時
- [x] **測試**：4 個 case，使用 pytest-httpserver mock
- [x] **驗收**：`uv run pytest worker/tests/test_llm.py -v` 全綠
- [x] **Commit**：`feat(worker): add streaming llm client with timeout and cancellation` (b36ca29)

---

### P1-04：包裝 HanloFlow 與 Taibun

- [x] **依賴**：P0-05
- [x] **檔案**：`worker/pipeline/text_processor.py`、`worker/tests/test_text_processor.py`
- [x] **前置**：
  - HanloFlow (`taigi-converter`) 以 git submodule 安裝至 `worker/vendor/hanloflow`
  - Taibun 以 `uv add taibun` 安裝
  - 升級 Python 至 3.12（HanloFlow 要求）
- [x] **輸入規格**：符合 task spec
- [x] **實作細節**：照 `docs/plan.md §4.4` 範例
- [x] **測試**：7 個 case 全綠
- [x] **驗收**：`uv run pytest worker/tests/test_text_processor.py -v` 全綠
- [x] **Commit**：`feat(worker): add text processor with hanloflow, taibun and dictionary` (0ca6f5d)

---

### P1-05：InteractionLog 寫入封裝

- [x] **依賴**：P0-06
- [x] **檔案**：`worker/db/repositories.py`（擴充）、`worker/tests/test_interaction_log.py`
- [x] **輸入規格**：符合 task spec
- [x] **測試**：4 個 DB integration test（需 DATABASE_URL）全綠
- [x] **驗收**：`uv run pytest worker/tests/test_interaction_log.py -v` 全綠
- [x] **Commit**：`feat(worker): add interaction log repository` (f6119c0)

---

### P1-06：整合為 CLI 對話工具

- [x] **依賴**：P1-01 ~ P1-05 全部完成
- [x] **檔案**：`worker/cli.py`
- [x] **功能**：`uv run python -m worker.cli --profile "公車站長"`
- [x] **驗收**：
  - CLI 可啟動並進行對話
  - 每輪寫入 InteractionLog
- [x] **Commit**：`feat(worker): add cli for text-only conversation testing` (b941a61)

---

### P1-07：字典熱更新機制（基礎版）

- [x] **依賴**：P1-04
- [x] **檔案**：`worker/pipeline/text_processor.py`（擴充）
- [x] **實作方式**：方案 A — `reload_if_updated()` 每輪檢查 DB max updatedAt
- [x] **測試**：load_dictionary 無 session 測試通過
- [x] **驗收**：CLI 運行中，新增字典條目後下一輪生效
- [x] **Commit**：`feat(worker): add dictionary hot reload mechanism` (c3838a5)

---

### P1-08：撰寫 Phase 1 完成報告

- [x] **依賴**：P1-01 ~ P1-07
- [x] **檔案**：`docs/phase-1-report.md`
- [x] **Commit**：`docs: add phase 1 completion report`

---

## Phase 1 完成標準

- [x] P1-01 ~ P1-08 全部打勾
- [x] `uv run pytest` 全綠，總 test case 數 ≥ 30（實際：40）
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
