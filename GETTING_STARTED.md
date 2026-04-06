# 使用指南

本文從零開始，逐步說明如何在本機完整跑起 Taigi-Flow。

---

## 目錄

1. [前置需求](#1-前置需求)
2. [Clone 專案](#2-clone-專案)
3. [Python 環境](#3-python-環境)
4. [設定環境變數](#4-設定環境變數)
5. [準備模型檔案](#5-準備模型檔案)
6. [啟動基礎服務](#6-啟動基礎服務)
7. [下載 LLM 模型](#7-下載-llm-模型)
8. [啟動 Agent Worker](#8-啟動-agent-worker)
9. [產生 Room Token 並連線測試](#9-產生-room-token-並連線測試)
10. [啟動監控後台](#10-啟動監控後台)
11. [沒有 NVIDIA GPU？](#11-沒有-nvidia-gpu)
12. [常見問題](#12-常見問題)

---

## 1. 前置需求

在開始之前，確認以下工具都已安裝：

| 工具 | 用途 | 安裝說明 |
|------|------|---------|
| Python 3.12+ | Agent Worker 執行環境 | python.org 或系統套件管理器 |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python 套件與虛擬環境管理 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker + Docker Compose | 執行所有服務容器 | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Git | Clone 專案（含 submodule）| git-scm.com |
| NVIDIA GPU + 驅動 | Qwen3-ASR GPU 推論（可選，見[第 11 節](#11-沒有-nvidia-gpu)） | NVIDIA 官方驅動 |

> **Docker Desktop 記憶體設定**：Qwen3-ASR 模型約 3.8GB，建議在 Docker Desktop → Settings → Resources → Memory 調整至 **至少 8GB**，否則容器可能 OOM 崩潰。

---

## 2. Clone 專案

專案包含 HanloFlow git submodule，必須加 `--recurse-submodules`：

```bash
git clone --recurse-submodules https://github.com/your-org/taigi-flow.git
cd taigi-flow
```

如果已經 clone 但忘記帶 submodule 參數：

```bash
git submodule update --init --recursive
```

確認兩個 submodule 都有正確拉下來（目錄不為空）：

```bash
ls hanloflow/
# 應該看到 pipeline.py、converter/ 等檔案

ls piper-tts-http-server/
# 應該看到 Dockerfile、server.py 等檔案
```

---

## 3. Python 環境

建立虛擬環境並安裝所有依賴（含開發工具）：

```bash
uv venv --python 3.12
source .venv/bin/activate      # Linux / macOS
# .venv\Scripts\activate       # Windows PowerShell

uv pip install -e ".[dev]"
```

安裝完成後確認 CLI 指令可以執行：

```bash
taigi-flow --help
taigi-room-token --help
```

---

## 4. 設定環境變數

複製範例設定：

```bash
cp .env.example .env.local
```

用文字編輯器開啟 `.env.local`，確認以下欄位：

```bash
# 元件選擇（預設值通常不需要改）
STT_BACKEND=qwen_asr
LLM_BACKEND=ollama
TTS_BACKEND=piper
CONVERTER_BACKEND=hanloflow

# STT — Qwen3-ASR server 位址
QWEN_ASR_URL=http://localhost:8001

# LLM — Ollama 位址與模型名稱
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=frob/qwen3.5-instruct:4b
LLM_TIMEOUT_SECONDS=120          # 冷啟動慢的機器可以調大

# TTS — Piper server 位址與聲音模型名稱
PIPER_URL=http://localhost:5000
PIPER_VOICE=taigi_epoch1339       # 必須和 data/ 目錄內的 .onnx 名稱對應

# LiveKit — 開發用預設金鑰（和 docker-compose 的 livekit-server 設定一致）
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret

# 監控
METRICS_PORT=8090
ENABLE_TRACING=true
OTLP_ENDPOINT=http://localhost:4317
```

> **開發環境用預設金鑰即可**，`devkey` / `devsecret` 已和 `docker-compose.yml` 的 `livekit-server` 設定對齊，不需要修改。

---

## 5. 準備模型檔案

啟動服務前需要先把模型檔案放到對應目錄。

### 5.1 Qwen3-ASR 模型

把模型 checkpoint 放到以下路徑（容器會掛載這個目錄為 `/model`）：

```
models/
└── qwen3-asr/
    └── checkpoint-20340/
        ├── config.json
        ├── model.safetensors   （或分片的 model-00001-of-xxxxx.safetensors）
        ├── tokenizer.json
        ├── tokenizer_config.json
        └── ...
```

如果目錄不存在，先建立：

```bash
mkdir -p models/qwen3-asr
```

> 模型來源：從 HuggingFace 下載 QwenLM/Qwen3-ASR，或使用本地已有的 checkpoint。

### 5.2 Piper TTS 聲音模型

`piper-tts-http-server/` 是 git submodule，clone 時已一起拉下來，包含 HTTP server 程式碼。
但聲音模型檔案（`.onnx`）太大，不放在 repo 裡，需要手動放進去：

```
piper-tts-http-server/
└── data/
    ├── taigi_epoch1339.onnx
    └── taigi_epoch1339.onnx.json
```

如果 `data/` 目錄不存在，先建立：

```bash
mkdir -p piper-tts-http-server/data
```

`.env.local` 的 `PIPER_VOICE` 必須和 `.onnx` 的檔名（不含副檔名）相同。

---

## 6. 啟動基礎服務

啟動 LiveKit、Ollama、Qwen3-ASR、Piper TTS 四個核心服務：

```bash
docker compose up -d livekit-server ollama qwen-asr piper-tts
```

### 確認各服務狀態

```bash
docker compose ps
```

所有服務應顯示 `running`。接著逐一確認：

**LiveKit Server**（立即就緒）：
```bash
curl http://localhost:7880/
# 應回傳 404 或 LiveKit 相關訊息（代表 server 有在）
```

**Ollama**（立即就緒）：
```bash
curl http://localhost:11434/api/tags
# 應回傳 {"models": [...]}
```

**Qwen3-ASR**（首次啟動需要 1～3 分鐘載入模型）：
```bash
# 查看載入進度
docker compose logs -f qwen-asr

# 等看到 "Model loaded" 再繼續
# 確認健康狀態
curl http://localhost:8001/health
# 應回傳 {"status": "ok", "model": "...", "device": "cuda", ...}
```

**Piper TTS**：
```bash
curl http://localhost:5000/health
# 或直接測試合成（如果 server 有 /health 端點）
```

---

## 7. 下載 LLM 模型

Ollama 啟動後，執行腳本下載 LLM 模型：

```bash
./scripts/setup_ollama.sh
```

這等同於手動執行：

```bash
docker compose exec ollama ollama pull frob/qwen3.5-instruct:4b
```

下載大小約 2.5GB，視網路速度需要幾分鐘。完成後確認：

```bash
docker compose exec ollama ollama list
# 應該看到 frob/qwen3.5-instruct:4b
```

> **為什麼用這個模型？** `frob/qwen3.5-instruct:4b` 是 Ollama Hub 上明確標為 non-thinking 的 Qwen3.5 4B 版本，比 thinking 模式少很多不必要的推論 token，VRAM 佔用更低，適合同時跑 GPU ASR 的環境。

---

## 8. 啟動 Agent Worker

所有服務就緒後，在本機啟動 Agent Worker：

```bash
uv run taigi-flow dev
```

> 用 `uv run` 的好處是不需要先 activate 虛擬環境，uv 會自動選到正確的 `.venv`。

如果已經 `source .venv/bin/activate`，也可以直接：

```bash
taigi-flow dev
# 或
python -m taigi_flow dev
```

正常啟動後應看到類似以下的 log：

```
INFO     livekit.agents - starting agent
INFO     livekit.agents - connected to LiveKit server  url=ws://localhost:7880
INFO     taigi_flow.main - Worker ready, waiting for connections...
```

Worker 現在會持續等待 LiveKit room 有人連入。

---

## 9. 產生 Room Token 並連線測試

### 9.1 產生 Token

開另一個 terminal，執行：

```bash
uv run taigi-room-token
```

輸出範例：

```
LIVEKIT_URL=ws://localhost:7880
ROOM=test-room-20260406-164500-a1b2c3
IDENTITY=user1
NAME=user1
TTL_MINUTES=60
TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

也可以自訂參數：

```bash
# 指定 room 名稱
uv run taigi-room-token --room my-room

# 指定身份
uv run taigi-room-token --identity alice --name "Alice"

# 輸出 JSON 格式（方便給程式讀取）
uv run taigi-room-token --json
```

### 9.2 使用 LiveKit Meet 連線

最快的測試方式是用 LiveKit 官方的 [Meet 範例](https://meet.livekit.io)：

1. 開啟 `https://meet.livekit.io`
2. 點選右上角設定，輸入：
   - **LiveKit URL**：`ws://localhost:7880`（注意：本機需使用 ws://，非 wss://）
   - **Token**：貼上上一步產生的 TOKEN
3. 點 Join，授權麥克風
4. 對著麥克風說話，Agent 應開始回應台語語音

> **注意**：瀏覽器存取 `ws://`（非加密）可能被安全政策擋住。如果遇到連線問題，改用 LiveKit 的 [CLI 工具](https://github.com/livekit/livekit-cli) 或自行架設前端。

### 9.3 確認 Agent Worker 有收到連線

回到 Agent Worker 的 terminal，應看到：

```
INFO     taigi_flow.main - New session: room=test-room-..., stt=qwen_asr, llm=ollama, ...
```

---

## 10. 啟動監控後台

啟動 Prometheus + Tempo + Grafana：

```bash
docker compose up -d prometheus tempo grafana
```

Grafana 第一次啟動約需 15 秒初始化，完成後開啟 `http://localhost:3000`：

- 帳號：`admin`
- 密碼：`admin`（建議登入後立刻修改）

> **Prometheus metrics 的前提**：Agent Worker 必須正在執行（`uv run taigi-flow dev`），Prometheus 才抓得到 `:8090/metrics` 的資料。Grafana 顯示的是 Prometheus 已收集到的歷史資料，新啟動的 Grafana 需要等 Prometheus 至少抓過一次才會有圖表。

> **Tempo traces 的前提**：Tempo 必須在 Agent Worker 啟動前就已執行，Agent 才能成功送出 trace。如果 Agent 先跑、Tempo 後啟動，可以重啟 Agent Worker 讓它重新連線。

### Grafana 可以看到什麼

**Dashboards → Taigi-Flow**（Prometheus 指標）：

| 面板 | 說明 |
|------|------|
| Active Sessions | 目前幾個對話 session 在線 |
| Turns / min | 每分鐘對話輪次數 |
| Conversion Latency | HanloFlow 繁中→Taibun 每句耗時（p50 / p95） |
| TTS Latency | Piper 合成每句耗時（p50 / p95） |
| Total Turns | 對話輪次趨勢 |

**Explore → 選 Tempo datasource**（OpenTelemetry traces）：

1. 點左側選單 **Explore**
2. 左上角 datasource 改選 **Tempo**
3. Query type 選 **Search**，Service name 選 **taigi-flow**
4. 可以看到每個句子的 `converter.convert` 和 `tts.synthesize` span，以及各自的耗時

---

## 11. 沒有 NVIDIA GPU？

如果機器沒有 NVIDIA GPU，改用 CPU fallback 啟動 Qwen3-ASR：

```bash
# 不啟動 qwen-asr（GPU），改啟動 qwen-asr-cpu
docker compose up -d livekit-server ollama piper-tts
docker compose --profile cpu-fallback up -d qwen-asr-cpu
```

> CPU 推論速度會慢很多（每段語音可能需要數秒才能辨識完成），僅建議用於功能測試，不適合正常對話使用。

Ollama 本身在沒有 GPU 的環境下會自動 fallback 到 CPU，不需要額外設定，但速度一樣會慢。

---

## 12. 常見問題

### Qwen3-ASR 容器一直 restarting

**原因**：通常是記憶體不足（OOM）。

**解法**：
1. Docker Desktop → Settings → Resources → Memory → 調高至 8GB+
2. 確認 `models/qwen3-asr/checkpoint-20340/` 目錄有正確的模型檔案
3. 查看詳細錯誤：`docker compose logs qwen-asr`

---

### Agent 第一次回應很慢（甚至 timeout）

**原因**：Ollama 冷啟動需要把模型載進 VRAM，通常第一次需要 10～30 秒。

**解法**：
- 先對 Ollama 送一個暖機請求：
  ```bash
  curl http://localhost:11434/api/generate -d '{"model":"frob/qwen3.5-instruct:4b","prompt":"hi"}'
  ```
- 或在 `.env.local` 調大 `LLM_TIMEOUT_SECONDS`（預設 120 秒）

---

### Agent Worker 出現「no permissions to access the room」

**原因**：LiveKit 的 job token 權限不足（通常發生在自訂 LiveKit Server 設定時）。

**影響**：Agent 會自動 fallback，用本地簽出的 room token 重試連線，正常情況下不影響功能。這個 warning 可以忽略。

---

### `taigi-room-token` 輸出的 TOKEN 連線失敗

**確認事項**：
1. LiveKit Server 有在跑：`docker compose ps livekit-server`
2. Token 還沒過期（預設 60 分鐘）
3. `.env.local` 的 `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` 和 `docker-compose.yml` 的 `LIVEKIT_KEYS` 對得上：
   - docker-compose 預設：`devkey: devsecret`（注意冒號後有空格）
   - .env.local 預設：`LIVEKIT_API_KEY=devkey` / `LIVEKIT_API_SECRET=devsecret`

---

### HanloFlow 初始化很慢

第一次呼叫 `stream_convert()` 時，HanloFlow 會載入辭典資料（`hanloflow/data/`）。這是一次性的初始化，之後的轉換就很快。

---

### 想換 Prompt

預設 prompt 在 `src/taigi_flow/prompts/`，可直接編輯，或在 `.env.local` 設定外部路徑：

```bash
AGENT_INSTRUCTIONS_PATH=/path/to/my_instructions.md
AGENT_GREETING_INSTRUCTIONS_PATH=/path/to/my_greeting.md
```
