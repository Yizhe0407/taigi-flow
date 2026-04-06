# Taigi-Flow

即時台語語音對話 AI Agent，基於 LiveKit 建立完整的語音管線：

```
使用者語音 → STT → LLM → HanloFlow（繁中→台語）→ TTS → 台語語音
```

## 架構

| 元件 | 目前實作 | 設定欄位 |
|------|---------|---------|
| 語音傳輸 | LiveKit（自架） | — |
| STT | Qwen3-ASR（HTTP chunk streaming） | `STT_BACKEND=qwen_asr` |
| LLM | Qwen3.5 9B via Ollama | `LLM_BACKEND=ollama` |
| 文字轉換 | HanloFlow（繁中→Taibun） | `CONVERTER_BACKEND=hanloflow` |
| TTS | Piper TTS HTTP Server | `TTS_BACKEND=piper` |
| 監控 | Prometheus + Grafana | — |

所有元件透過 Protocol 介面定義，換元件只需新增實作 + 改 `.env.local`，不動 Agent 核心程式碼。

## 前置需求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Docker](https://docs.docker.com/get-docker/) + Docker Compose

## 快速開始

### 1. Clone 專案（含 HanloFlow submodule）

```bash
git clone --recurse-submodules https://github.com/your-org/taigi-flow.git
cd taigi-flow
```

如果已經 clone 但沒有 submodule：

```bash
git submodule update --init --recursive
```

### 2. 建立虛擬環境並安裝依賴

```bash
uv venv --python 3.12
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

### 3. 設定環境變數

```bash
cp .env.example .env.local
# 編輯 .env.local，至少確認以下欄位：
# - LIVEKIT_API_KEY / LIVEKIT_API_SECRET（開發用預設 devkey/devsecret）
# - PIPER_VOICE（你的 Piper 聲音模型名稱）
```

### 4. 啟動服務層（Docker Compose）

```bash
# 啟動基礎設施（LiveKit、Ollama、Piper TTS）
docker compose up -d livekit-server ollama piper-tts

# 加上監控（Prometheus + Grafana）
docker compose up -d
```

> **Agent Worker 開發時不用 Docker**，直接在本機用 uv 跑（見步驟 6）。
> 生產部署才用 `--profile production` 啟動容器化的 agent（見[生產部署](#生產部署)）。

### 5. 下載 LLM 模型

```bash
./scripts/setup_ollama.sh
# 或手動執行：
# docker compose exec ollama ollama pull qwen3.5:9b
```

### 6. 啟動 Agent Worker（開發）

確認虛擬環境已啟動（`source .venv/bin/activate`），然後：

```bash
python -m taigi_flow.main dev
```

---

## 生產部署

Agent Worker 容器化後可加入 docker-compose 一起管理。

**前提**：clone 時必須帶 submodule：

```bash
git clone --recurse-submodules https://github.com/your-org/taigi-flow.git
```

**啟動（含 Agent Worker container）**：

```bash
docker compose --profile production up -d
```

Agent Worker 的 Dockerfile 會自動把 `hanloflow/` submodule 打包進 image，不需要額外設定。

---

## 服務端口

| 服務 | 端口 | 說明 |
|------|------|------|
| LiveKit Server | 7880 | WebSocket / HTTP |
| Ollama | 11434 | LLM API |
| Piper TTS | 5000 | TTS HTTP Server |
| Agent Dashboard | 9090 | Prometheus metrics + `/api/sessions` |
| Prometheus | 9090 | 指標收集 |
| Grafana | 3000 | 監控面板（帳號 admin / 密碼 admin） |

---

## 換元件

所有元件都可以透過修改 `.env.local` 切換，不需要改程式碼。

### 換 LLM

```bash
# 使用 vLLM 代替 Ollama
LLM_BACKEND=vllm
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=Qwen/Qwen3.5-9B-Instruct
```

新增一個 backend 的步驟：
1. 在 `src/taigi_flow/llm/` 新增實作（或直接用 OpenAI 相容 API 就不需要）
2. 在 `src/taigi_flow/factory.py` 的 `create_llm()` 加一個 `case`
3. 更新 `.env.local`

### 換 STT

```bash
# 換成 FunASR（Paraformer，備用方案）
STT_BACKEND=funasr
FUNASR_WS_URL=ws://localhost:10095
FUNASR_MODE=2pass         # 串流 + 事後校正
FUNASR_CHUNK_SIZE=5,10,5  # 600ms 延遲（8,8,4 = 480ms）

# 換成其他 STT
STT_BACKEND=whisper   # 需先在 stt/whisper.py 實作
```

### 換 TTS

```bash
TTS_BACKEND=cosyvoice   # 需先在 tts/cosyvoice.py 實作
```

### 跳過台語轉換（除錯用）

```bash
CONVERTER_BACKEND=passthrough   # 直接透傳繁中文字給 TTS
```

---

## 專案結構

```
taigi-flow/
├── src/taigi_flow/
│   ├── protocols.py        # 元件介面（TextConverter、Synthesizer）
│   ├── factory.py          # 根據 config 建立元件實例
│   ├── config.py           # 環境變數設定
│   ├── agent.py            # TaigiAgent — 核心管線邏輯
│   ├── main.py             # 入口：AgentServer
│   ├── stt/                # STT 實作
│   │   └── qwen.py
│   ├── llm/                # LLM（目前用 livekit-plugins-openai）
│   ├── tts/                # TTS 實作
│   │   └── piper.py
│   ├── converter/          # 文字轉換器實作
│   │   ├── hanlo_bridge.py
│   │   └── passthrough.py
│   ├── session/state.py    # Session 狀態
│   └── monitoring/
│       ├── metrics.py      # Prometheus 指標
│       └── dashboard.py    # FastAPI 後台 API
├── hanloflow/              # HanloFlow git submodule（繁中→台語漢字→Taibun）
├── Dockerfile              # Agent Worker 容器（生產用）
├── monitoring/
│   └── prometheus.yml
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

---

## 監控後台

Agent Worker 啟動後，監控端點：

- `http://localhost:9090/api/sessions` — 即時活躍 session 列表
- `http://localhost:9090/api/sessions/{id}` — 單一 session 詳情
- `http://localhost:9090/metrics` — Prometheus 格式指標
- `http://localhost:3000` — Grafana 面板

---

## 開發

```bash
# 執行測試
pytest

# 格式檢查
ruff check src/
ruff format src/
```

### 新增一個元件 backend

以新增 Whisper STT 為例：

1. 建立 `src/taigi_flow/stt/whisper.py`，繼承 `livekit.agents.stt.STT`
2. 在 `factory.py` 的 `create_stt()` 加：
   ```python
   case "whisper":
       from taigi_flow.stt.whisper import WhisperSTT
       return WhisperSTT(model=settings.whisper_model)
   ```
3. 在 `config.py` 加對應設定欄位
4. `.env.local` 設定 `STT_BACKEND=whisper`
