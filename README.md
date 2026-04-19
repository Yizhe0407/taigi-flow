# 台語即時語音 Agent 系統

> 大學專題：以台語為互動語言的即時語音 AI Agent，整合 LiveKit、自訓 Piper TTS 與台語 ASR 模型。

## ✨ 核心特性

- 🎙️ **原生台語互動**：使用 Qwen3-ASR / Breeze-ASR-26 + 自訓 Piper TTS
- ⚡ **低延遲串流**：目標首次音訊延遲 < 1.2s
- 🛑 **擬真打斷機制**：完整 Barge-in + AEC 實作
- 🎭 **多人格管理**：透過後台熱更新 Agent 人格與發音字典
- 📊 **可觀測**：每通對話的完整文字轉換鏈可追溯、可修正

## 🏗️ 架構總覽

```
Browser (Next.js) ←WebRTC→ LiveKit Server ←→ Agent Worker (Python)
                                                    ↓
                                       ASR → LLM → Splitter →
                                       HanloFlow → Taibun → Piper TTS
                                                    ↓
                                          PostgreSQL + pgvector
```

詳細架構見 [`docs/plan.md`](docs/plan.md#1-系統架構總覽)。

## 📦 技術棧

- **語音**：LiveKit (WebRTC)、Silero VAD、Qwen3-ASR、Piper TTS
- **文字處理**：[HanloFlow](https://github.com/Yizhe0407/HanloFlow)、[Taibun](https://github.com/andreihar/taibun)
- **後端**：Python 3.12、`uv`
- **前端**：Next.js (Monorepo)、pnpm、shadcn/ui
- **資料**：PostgreSQL + pgvector、Prisma ORM
- **部署**：Docker Compose

## 🚀 快速開始

### 前置需求

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [pnpm](https://pnpm.io/installation) v10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 套件管理)
- Node.js 20+
- Python 3.12+

### 步驟

```bash
# 1. Clone 專案
git clone <repo-url>
cd taigi-flow

# 2. 複製並編輯環境變數
cp .env.example .env
# 填入：POSTGRES_PASSWORD、LIVEKIT_API_KEY、LIVEKIT_API_SECRET

# 3. 啟動基礎設施（postgres / redis / livekit / cloudbeaver）
docker compose up -d
docker compose ps   # 確認全部 healthy

# 4. 安裝前端依賴
cd web && pnpm install && cd ..

# 5. 執行 DB migration + seed
cd web/packages/db
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  pnpm exec prisma migrate deploy
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  pnpm exec prisma db seed
cd ../../..

# 6. 安裝 Worker 依賴（含 HanloFlow）
cd worker
uv sync --dev
cd ..

# 7. 驗證 Worker 能連上 DB
cd worker
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  uv run pytest tests/ -v
cd ..
```

### 服務一覽

| 服務 | URL |
|------|-----|
| Playground | http://localhost:3000 |
| Admin | http://localhost:3001 |
| LiveKit | ws://localhost:7880 |
| PostgreSQL | localhost:5432 / DB: `agent_system` |
| Redis | localhost:6379 |
| Cloudbeaver（DB UI）| http://localhost:8978 |

**Cloudbeaver 初次設定**：進入 http://localhost:8978 後連線設定填：
- Host: `postgres`、Port: `5432`、DB: `agent_system`
- User: `admin`、Password: 你的 `POSTGRES_PASSWORD`

## 💬 文字對話 CLI（Phase 1）

不需語音，直接用文字跟 Agent 對話，驗證文字轉換鏈：

```bash
cd worker
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  uv run python -m worker.cli --profile "公車站長"
```

輸出格式：

```
You > 請問 307 公車到站時間？
Assistant >
  [原文]   根據最新資料，307 公車大約 5 分鐘後到站。
  [漢羅]   根據最新資料，307 公車大約 5 分鐘後到站矣。
  [台羅]   King-ku tsue3-sin tsu1-liau7, sam1-khong3-tshit4 kong1-tshia1 tua7-ioh4 go7 hun1-tsing1 au7 kau3-tsam7--ah0.

[Latency] ASR end N/A | LLM first tok 342ms | Total 1203ms
```

- `Ctrl+C` 優雅退出
- 每輪對話自動寫入 DB，可在 Cloudbeaver 查看

## 🔄 更新 HanloFlow

taigi-flow 的 worker 透過 local path 引用 HanloFlow（`../../HanloFlow`）。

**本機開發（editable）**：HanloFlow 改完 `.py` 直接生效，不需任何指令。若尚未設定 editable：

```bash
cd worker
uv add --editable "../../HanloFlow"
```

**切換為 GitHub git URL**（HanloFlow push 後）：

```bash
cd worker
uv add "taigi-converter @ git+https://github.com/Yizhe0407/HanloFlow.git"
```

之後每次 HanloFlow 有新 commit：

```bash
cd worker
uv sync --upgrade-package taigi-converter
```

## 🔧 LLM 設定

Worker 預設使用 Ollama（OpenAI-compatible API）：

| 環境變數 | 預設值 |
|---------|--------|
| `LLM_BASE_URL` | `http://100.107.45.116:11434/v1` |
| `LLM_MODEL` | `frob/qwen3.5-instruct:4b` |
| `LLM_API_KEY` | `ollama` |

可在 `.env` 中覆寫，或在執行指令前設定：

```bash
LLM_BASE_URL="http://localhost:11434/v1" \
LLM_MODEL="llama3.2" \
  uv run python -m worker.cli --profile "公車站長"
```

## 📁 專案結構

```
.
├── docker-compose.yml         # postgres / redis / livekit / cloudbeaver
├── .env.example               # 環境變數範本
├── CLAUDE.md                  # AI 開發助手工作規則
├── docs/
│   ├── plan.md               # 完整設計文件
│   ├── adr/                  # 架構決策紀錄
│   └── phase-1-report.md     # Phase 1 完成報告
├── tasks/                     # 分階段任務清單
├── web/                       # Next.js Monorepo (pnpm)
│   ├── apps/playground/      # 使用者對話介面 :3000
│   ├── apps/admin/           # 管理後台 :3001
│   └── packages/
│       ├── db/               # Prisma schema + migrations
│       ├── types/            # 共用 zod schema
│       ├── ui/               # 共用元件
│       └── api-client/       # 後端 API 封裝
└── worker/                    # Agent Worker (Python + uv)
    ├── worker/
    │   ├── pipeline/         # memory / splitter / llm / text_processor
    │   ├── db/               # SQLAlchemy models + repositories
    │   ├── controller/       # VAD + Barge-in FSM（Phase 4）
    │   ├── tools/            # Function calling tools（Phase 6）
    │   └── observability/    # 延遲計時器
    ├── tests/
    └── cli.py                # 文字對話測試工具
```

## 🗺️ 開發路線

| Phase | 主題 | 狀態 |
|-------|------|------|
| 0 | 基礎設施 | ✅ 完成 |
| 1 | 純文字對話鏈（CLI）| ✅ 完成 |
| 2 | 語音層接入 + ASR A/B 評估 | 🔲 |
| 3 | 完整迴圈整合 | 🔲 |
| 4 | Barge-in + AEC | 🔲 |
| 5 | 管理後台 | 🔲 |
| 6 | RAG + Tools | 🔲 |
| 7 | 打磨與文件 | 🔲 |

完整細節見 [`docs/plan.md §9`](docs/plan.md#9-分階段實作路線) 與 [`tasks/`](tasks/)。

## 📜 授權

[待定]
