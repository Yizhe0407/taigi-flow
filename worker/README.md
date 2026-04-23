# Agent Worker

Python-based LiveKit agent worker for the Taigi-Flow system.

## 啟動方式

```bash
cd worker

# 開發模式（自動重載，等待 LiveKit dispatch job）
uv run python -m worker.main dev

# 正式模式
uv run python -m worker.main start
```

Worker 啟動後**不需要指定 room**。當前端用戶按下「Start Conversation」時，LiveKit 會自動 dispatch job 給 idle worker，worker 再連進那個 room。

## 指令說明

| 指令 | 用途 |
|------|------|
| `dev` | 開發用，支援熱重載 |
| `start` | 正式環境 |
| `connect --room <name>` | 直接連進特定 room（debug 用，不走 dispatch） |

## 環境變數

見根目錄 `.env.example`。關鍵變數：

| 變數 | 說明 |
|------|------|
| `LIVEKIT_URL` | LiveKit server WebSocket URL |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `DATABASE_URL` | PostgreSQL 連線字串 |
| `ASR_BACKEND` | `qwen3` 或 `breeze26` |
| `ASR_URL` | ASR HTTP API endpoint |
| `PIPER_MODEL_PATH` | Piper TTS model 路徑（或設 `PIPER_API_URL`） |
| `LLM_BASE_URL` | LLM API base URL（OpenAI-compatible） |
| `LLM_MODEL` | 模型名稱 |

## 文字對話 CLI（不需語音）

```bash
uv run python -m worker.cli --profile "公車站長"
```
