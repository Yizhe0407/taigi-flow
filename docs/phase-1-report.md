# Phase 1 完成報告：純文字對話鏈

## 模組總覽

### SlidingWindowMemory (`worker/pipeline/memory.py`)

滑動視窗記憶管理。維護 `history: list[dict]`，最多保留 `max_turns * 2` 則訊息（user + assistant 成對）。`to_messages()` 在最前面插入 system prompt。超過上限時從頭丟棄整對，不留孤兒 assistant 訊息。

### SmartSplitter (`worker/pipeline/splitter.py`)

LLM token 串流切句器。優先級：強斷點（`。！？\n`）> 中斷點（`，；：`，需 ≥ 6 字）> 強制切（超過 40 字）。`flush()` 回傳剩餘 buffer，供串流結束或 barge-in 使用。

### LLMClient (`worker/pipeline/llm.py`)

OpenAI-compatible 非同步串流客戶端。首次 token 超時 5 秒，整體超時由 `timeout` 參數控制。支援 `asyncio.CancelledError` 乾淨退出（barge-in 用途）。使用 `frob/qwen3.5-instruct:4b` 透過 Ollama endpoint。

### TextProcessor (`worker/pipeline/text_processor.py`)

文字處理鏈：繁中 → 漢羅（HanloFlow）→ 台羅（Taibun）。字典替換在 HanloFlow 之前，以 `⟨...⟩` 保護標記避免改寫。字典按 `priority DESC, len(term) DESC` 排序，長詞優先。

### InteractionLogRepository (`worker/db/repositories.py`)

DB 寫入封裝。`create_session()` → `log_turn()` → `end_session()` 三步流程。每個方法獨立 session，避免長事務。

### CLI (`worker/cli.py`)

```bash
uv run python -m worker.cli --profile "公車站長"
```

REPL 互動：讀取輸入 → 熱更新字典 → LLM 串流 → 切句 → TextProcessor → 印出結果 → 寫 InteractionLog。`Ctrl+C` 優雅退出並呼叫 `end_session`。

---

## 安裝注意事項

### HanloFlow

HanloFlow (`taigi-converter`) 設計為 CLI 工具，非標準 Python library（pyproject.toml 缺少 packages 設定，安裝後無可匯入模組）。解法：以 git submodule 克隆至 `worker/vendor/hanloflow`，在 `text_processor.py` 動態加入 `sys.path`。

```
worker/vendor/hanloflow  ← git submodule (Yizhe0407/HanloFlow)
```

克隆後需確保 `data/artifacts/` 目錄存在（已含在 repo 中）。

### Python 版本

HanloFlow 要求 `python>=3.12`，worker 原設定 3.11，已升級：
- `.python-version`: `3.11` → `3.12`
- `pyproject.toml`: `requires-python = ">=3.12"`

### Taibun API

```python
from taibun import Converter
c = Converter(system="Tailo", format="mark")
result = c.get("你好")  # → "Lí hó"
```

注意：`c.get("")` 空字串會 IndexError，TextProcessor 已加 guard。

---

## 測試結果

```
40 passed in 8.50s
```

| 測試檔 | 案例數 | 說明 |
|--------|--------|------|
| test_memory.py | 7 | 含孤兒 assistant、overflow、clear |
| test_splitter.py | 16 | 含強/中/弱斷點、超長句、連續斷點 |
| test_llm.py | 4 | 使用 pytest-httpserver mock，含超時、取消 |
| test_text_processor.py | 7 | 含字典命中、優先級、長詞優先 |
| test_interaction_log.py | 4 | 需 DATABASE_URL（PostgreSQL integration）|
| test_db_smoke.py | 3 | Phase 0 既有測試 |

DB integration test 在無 `DATABASE_URL` 時自動 skip，CI 需設定環境變數。

---

## 已知限制與 Phase 2 待處理

1. **TextProcessor 是 sync**：`process()` 阻塞，但 HanloFlow/Taibun 純 CPU，在實測環境下延遲 < 5ms，暫時可接受。Phase 2 若有 event loop 壓力再考慮 threadpool。

2. **LLM 首次 token 超時 = 5s**：本機 Ollama 實測約 500ms-2s，5s 有餘裕。若換用較大模型需調整 `FIRST_TOKEN_TIMEOUT`。

3. **字典熱更新用 polling**：每輪對話觸發一次 DB 查詢（只查 MAX(updatedAt)）。頻率低、開銷小，足夠本專題場景。

4. **CLI 無 ASR 延遲**：`[Latency] ASR end N/A`，Phase 2 接入語音後填入。

5. **`vendor/hanloflow` 為 submodule**：CI pipeline 需 `git submodule update --init` 才能使用。
