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
- **文字處理**：HanloFlow、Taibun
- **後端**：Python 3.11、FastAPI、`uv`
- **前端**：Next.js (Monorepo)、pnpm、shadcn/ui
- **資料**：PostgreSQL + pgvector、Prisma ORM
- **部署**：Docker Compose、Caddy

## 🚀 快速開始

### 前置需求

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [pnpm](https://pnpm.io/installation) v10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 套件管理)
- Node.js 20+

### 步驟（約 30 分鐘）

```bash
# 1. Clone 專案
git clone <repo-url>
cd taigi-flow

# 2. 複製並編輯環境變數
cp .env.example .env
# 至少填入：POSTGRES_PASSWORD、LIVEKIT_API_KEY、LIVEKIT_API_SECRET
# OPENAI_API_KEY 在 Phase 1 前不需要

# 3. 啟動基礎設施（postgres / redis / livekit）
docker compose up -d

# 確認全部 healthy
docker compose ps

# 4. 安裝前端依賴
cd web && pnpm install && cd ..

# 5. 執行 DB migration + seed
cd web/packages/db
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  pnpm exec prisma migrate deploy
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  pnpm exec prisma db seed
cd ../../..

# 6. 安裝 Worker 依賴
cd worker && uv sync --extra dev && cd ..

# 7. 驗證 Worker 能連上 DB
cd worker
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  uv run pytest tests/test_db_smoke.py -v
cd ..
```

### 開發伺服器

```bash
# 前端
cd web
pnpm --filter playground dev   # http://localhost:3000
pnpm --filter admin dev        # http://localhost:3001

# Worker（目前只印 "Worker ready"，Phase 1 後有實際邏輯）
cd worker
uv run python -m worker.main
```

### 服務一覽

| 服務 | URL / 連線 |
|------|-----------|
| Playground | http://localhost:3000 |
| Admin | http://localhost:3001 |
| LiveKit | ws://localhost:7880 |
| PostgreSQL | localhost:5432 / DB: `agent_system` |
| Redis | localhost:6379 |

詳細架構與設計決策見 [`docs/plan.md`](docs/plan.md)。

## 📁 專案結構

```
.
├── .github/workflows/ci.yml   # GitHub Actions CI
├── docker-compose.yml         # postgres / redis / livekit
├── infra/livekit.yaml         # LiveKit dev 設定
├── .env.example               # 環境變數範本
├── CLAUDE.md                  # AI 開發助手工作規則
├── docs/
│   ├── plan.md               # 完整設計文件
│   └── adr/                  # 架構決策紀錄
├── tasks/                     # 分階段任務清單
├── web/                       # Next.js Monorepo (pnpm + Turbo)
│   ├── apps/playground/      # 使用者對話介面 :3000
│   ├── apps/admin/           # 管理後台 :3001
│   └── packages/
│       ├── db/               # Prisma schema + migrations
│       ├── types/            # 共用 zod schema
│       ├── ui/               # 共用元件
│       └── api-client/       # 後端 API 封裝
└── worker/                    # Agent Worker (Python + uv)
    ├── worker/
    │   ├── controller/       # VAD + Barge-in FSM
    │   ├── pipeline/         # ASR / LLM / Splitter / TTS
    │   ├── db/               # SQLAlchemy models + repositories
    │   ├── tools/            # Function calling tools
    │   └── observability/    # 延遲計時器
    └── tests/
```

## 🗺️ 開發路線

| Phase | 主題 | 週 |
|-------|------|----|
| 0 | 基礎設施 | W1 |
| 1 | 純文字對話鏈 | W2 |
| 2 | 語音層接入 + ASR A/B 評估 | W3 |
| 3 | 完整迴圈整合 | W4 |
| 4 | Barge-in + AEC | W5 |
| 5 | 管理後台 | W6 |
| 6 | RAG + Tools | W7 |
| 7 | 打磨與文件 | W8 |

完整細節見 [`docs/plan.md §9`](docs/plan.md#9-分階段實作路線) 與 [`tasks/`](tasks/)。

## 📜 授權

[待定]

## 👥 團隊

[待填]