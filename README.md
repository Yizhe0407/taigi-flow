# Taigi-Flow

即時台語語音對話 AI Agent，基於 LiveKit 建立完整的語音管線：

```
使用者語音 → STT → LLM → HanloFlow（繁中→台語）→ TTS → 台語語音
```

**[→ 完整使用指南（GETTING_STARTED.md）](GETTING_STARTED.md)**

---

## 架構

| 元件 | 目前實作 | 設定欄位 |
|------|---------|---------|
| 語音傳輸 | LiveKit（自架） | — |
| STT | Qwen3-ASR（HTTP chunk streaming） | — |
| LLM | Non-thinking Qwen3.5 4B via Ollama | `LLM_BACKEND=ollama` |
| 文字轉換 | HanloFlow（繁中→Taibun） | `CONVERTER_BACKEND=hanloflow` |
| TTS | Piper TTS HTTP Server | `TTS_BACKEND=piper` |
| 監控 | Prometheus + Grafana + Tempo | — |

所有元件透過 Protocol 介面定義，換元件只需新增實作 + 改 `.env.local`，不動 Agent 核心程式碼。

---

## 服務端口

| 服務 | 端口 | 說明 |
|------|------|------|
| LiveKit Server | 7880 | WebSocket / HTTP |
| Ollama | 11434 | LLM API |
| Qwen3-ASR | 8001 | STT HTTP chunk API |
| Piper TTS | 5000 | TTS HTTP Server |
| Agent Dashboard | 8090 | Prometheus metrics + `/api/sessions` |
| Prometheus | 9090 | 指標收集 |
| Grafana Tempo | 4317 | OTLP gRPC（Agent 送 trace 用） |
| Grafana Tempo | 3200 | Tempo HTTP API（Grafana 查詢用） |
| Grafana | 3000 | 監控面板（帳號 admin / 密碼 admin） |

---

## 換元件

所有元件都可以透過修改 `.env.local` 切換，不需要改程式碼。

### 換 LLM

```bash
# 使用任何 OpenAI 相容 API（vLLM、LM Studio 等）
LLM_BACKEND=ollama
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=your-model-name
```

### 換 TTS

```bash
TTS_BACKEND=cosyvoice   # 需先在 tts/cosyvoice.py 實作
```

### 跳過台語轉換（除錯用）

```bash
CONVERTER_BACKEND=passthrough   # 直接透傳繁中文字給 TTS
```

### 新增一個 Backend

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

---

## 專案結構

```
taigi-flow/
├── src/taigi_flow/
│   ├── __main__.py         # python -m taigi_flow 入口
│   ├── main.py             # AgentServer — LiveKit Worker 設定與 session 組裝
│   ├── agent.py            # TaigiAgent — 核心管線邏輯（tts_node 覆寫）
│   ├── bootstrap.py        # 啟動輔助（load_env_file，純 stdlib）
│   ├── config.py           # 環境變數設定（pydantic-settings）
│   ├── factory.py          # 根據 config 建立元件實例
│   ├── protocols.py        # 元件介面（TextConverter、Synthesizer）
│   ├── text_safety.py      # TTS 文字過濾（Piper 字母表白名單）
│   ├── stt/
│   │   └── qwen_asr.py     # Qwen3-ASR HTTP chunk streaming
│   ├── llm/
│   │   └── ollama.py       # OllamaLLM — 延長 timeout 的 OpenAI-compatible wrapper
│   ├── tts/
│   │   └── piper.py        # Piper TTS HTTP Server
│   ├── converter/
│   │   ├── hanlo_bridge.py # HanloFlow（繁中→Taibun，預設）
│   │   └── passthrough.py  # 直接透傳（除錯用）
│   ├── prompts/            # 預設 Agent prompt（可透過環境變數覆蓋）
│   ├── tools/
│   │   └── livekit_token.py  # taigi-room-token CLI 工具
│   └── monitoring/
│       ├── metrics.py      # Prometheus 指標
│       ├── traces.py       # OpenTelemetry 追蹤
│       └── dashboard.py    # FastAPI 後台 API
├── hanloflow/              # git submodule（繁中→台語漢字→Taibun）
├── piper-tts-http-server/  # git submodule（Piper TTS HTTP server，聲音模型放 data/ 下）
├── qwen-asr-server/        # Qwen3-ASR HTTP server（FastAPI + transformers）
├── monitoring/
│   ├── prometheus.yml
│   ├── tempo.yml
│   └── grafana/
│       ├── dashboards/     # Grafana dashboard JSON
│       └── provisioning/   # 自動設定 datasource + dashboard
├── Dockerfile              # Agent Worker 容器（生產用）
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

---

## 監控

Agent Worker 啟動後：

- `http://localhost:8090/api/sessions` — 即時活躍 session 列表
- `http://localhost:8090/metrics` — Prometheus 格式指標
- `http://localhost:3000` — Grafana（帳號 admin / 密碼 admin）
  - **Dashboards → Taigi-Flow** — 指標面板
  - **Explore → Tempo** — 每句 `converter.convert` / `tts.synthesize` span

---

## 開發

```bash
# 執行測試
pytest

# 格式檢查 / 自動修正
ruff check src/
ruff format src/
```

---

## 生產部署

```bash
# Agent Worker 一起容器化
docker compose --profile production up -d
```

Agent Worker 的 Dockerfile 會自動把 `hanloflow/` submodule 打包進 image。容器內的 `OTLP_ENDPOINT` 已在 docker-compose 設定為 `http://tempo:4317`，不需要修改 `.env.local`。
