# 台語即時語音 Agent 系統

> 大學專題：以台語為互動語言的即時語音 AI Agent，整合 LiveKit、自訓 Piper TTS 與台語 ASR 模型。

## 核心特性

- **原生台語互動**：使用 Qwen3-ASR / Breeze-ASR-26 + 自訓 Piper TTS
- **低延遲串流**：目標首次音訊延遲 < 1.2s
- **擬真打斷機制**：完整 Barge-in + VAD 抑制實作
- **多人格管理**：透過管理後台熱更新 Agent 人格與發音字典
- **可觀測**：每通對話的完整文字轉換鏈可追溯、可修正

## 架構總覽

```
Browser (Next.js) ←WebRTC→ LiveKit Server ←→ Agent Worker (Python)
                                                    ↓
                                       ASR → LLM → Splitter →
                                       HanloFlow → Taibun → Piper TTS
                                                    ↓
                                          PostgreSQL + pgvector
                                                    ↑
                                         Admin Panel (Next.js :3001)
```

詳細架構見 [`docs/plan.md`](docs/plan.md#1-系統架構總覽)。

## 技術棧

- **語音**：LiveKit (WebRTC)、Silero VAD、Qwen3-ASR、Piper TTS
- **文字處理**：[HanloFlow](https://github.com/Yizhe0407/HanloFlow)、[Taibun](https://github.com/andreihar/taibun)
- **後端**：Python 3.12、`uv`
- **前端**：Next.js 14 (Monorepo)、pnpm、Tailwind CSS、lucide-react
- **資料**：PostgreSQL + pgvector、Prisma ORM、zod
- **部署**：Docker Compose

## 快速開始

### 前置需求

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [pnpm](https://pnpm.io/installation) v10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 套件管理)
- [tmux](https://github.com/tmux/tmux) — `brew install tmux`
- Node.js 20+
- Python 3.12+

### 首次設定

```bash
# 1. Clone 專案
git clone <repo-url>
cd taigi-flow

# 2. 複製並填入環境變數
cp .env.example .env
# 填入：POSTGRES_PASSWORD、LIVEKIT_API_KEY、LIVEKIT_API_SECRET

# 3. 安裝前端依賴
cd web && pnpm install && cd ..

# 4. 安裝 Worker 依賴（含 HanloFlow）
cd worker && uv sync --dev && cd ..

# 5. 初始化資料庫（首次執行）
cd web/packages/db
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  pnpm exec prisma migrate deploy
DATABASE_URL="postgresql://admin:<POSTGRES_PASSWORD>@localhost:5432/agent_system" \
  pnpm exec prisma db seed
cd ../../..
```

### 一鍵啟動

| 腳本 | 用途 | 環境變數 | Next.js | Worker |
|------|------|---------|---------|--------|
| `./dev.sh` | 本機開發 | `.env` | `next dev`（hot-reload）| `worker dev`（自動重載）|
| `./prod.sh` | 正式展示 | `.env.prod` → `.env` | `next build` + `next start` | `worker start` |

```bash
./dev.sh                    # 開發模式
./prod.sh                   # 正式模式（先 build，再啟動）
./prod.sh --skip-build      # 正式模式（略過 build，已建置過）
./dev.sh --no-worker        # 只起前端，不啟動 Python Worker
```

兩支腳本都會自動：
1. 啟動 Docker 基礎設施（postgres / redis / livekit）
2. 等待 PostgreSQL 就緒
3. 套用 pending DB migrations
4. 開啟 tmux session，三個 pane 同時跑 Playground / Admin / Worker

```
┌──────────────────────┬───────────────────────┐
│  Playground :3000    │  Admin :3001           │
├──────────────────────┴───────────────────────┤
│  Worker (Python)                             │
└──────────────────────────────────────────────┘
```

**tmux 第一次用？**

```bash
brew install tmux   # 安裝（一次性）
```

啟動後畫面會分割成三個區塊，滑鼠點擊可切換（需 tmux ≥ 2.1）。

| 按鍵 | 動作 |
|------|------|
| `Ctrl+B` 再按方向鍵 | 切換到另一個 pane |
| `Ctrl+B` 再按 `z` | 目前 pane 放大/還原 |
| `Ctrl+B` 再按 `d` | 離開畫面（程序繼續跑） |
| `Ctrl+B` 再按 `[` | 進入捲動模式（`q` 退出）|
| `q` | 退出捲動模式 |

**重新回到畫面**（detach 後）：
```bash
tmux attach -t taigi-flow-dev    # 開發模式
tmux attach -t taigi-flow-prod   # 正式模式
```

**完全停止所有服務**：
```bash
tmux kill-session -t taigi-flow-dev
```

### 服務一覽

| 服務 | URL | 說明 |
|------|-----|------|
| Playground | http://localhost:3000 | 使用者語音對話介面 |
| Admin | http://localhost:3001 | 管理後台 |
| LiveKit | ws://localhost:7880 | WebRTC 媒體伺服器 |
| PostgreSQL | localhost:5432 / DB: `agent_system` | 主資料庫 |
| Redis | localhost:6379 | LiveKit 佇列 |
| Piper TTS | http://localhost:5000 | 台語 TTS（CPU，Docker build）|
| Cloudbeaver（DB UI）| http://localhost:8978 | 資料庫瀏覽器 |

### 管理後台（Admin :3001）

後台提供四個頁面：

| 路徑 | 功能 |
|------|------|
| `/agents` | Agent 人格列表、新增、編輯、啟用/停用 |
| `/sessions` | 對話 session 列表（最近 100） |
| `/sessions/:id` | 逐 turn 四欄對照（ASR / LLM / HanLo / Taibun）+ 篩選 + 一鍵加入字典 |
| `/dictionary` | 全域 / Agent 專屬發音字典，支援搜尋、inline 編輯、CSV 匯入/匯出 |
| `/monitor` | 即時監控（active sessions、首音延遲、錯誤率，每 10s 輪詢） |

### Playground 測試方式（重要）

**建議先用 localhost 測試，不要先用 ngrok。**

1. 以本機方式啟動：
   - Playground: `http://localhost:3000`
   - Worker: `uv run python -m worker.main dev`（等待 LiveKit dispatch job）
2. 若看不到麥克風權限提示：
   - 到瀏覽器 `localhost:3000` 的 Site settings，把 Microphone 權限 reset 後重開頁面
3. 成功條件：
   - 診斷區顯示 `LiveKit connected: yes`
   - `Local microphone enabled: yes`
   - `Your voice` 波形會動

#### ngrok 為什麼常常 Disconnected？

若頁面走 `https://...ngrok...`，LiveKit 必須同時提供可從外網連線的 **`wss://`** 位址。  
只 tunnel `:3000` 但仍讓前端連 `ws://localhost:7880`，一定會失敗。

要用 ngrok，至少要滿足：

1. `NEXT_PUBLIC_LIVEKIT_URL` 設成可公開的 `wss://...`
2. 該 `wss` 位址可從瀏覽器所在網路實際連到 LiveKit

**Cloudbeaver 初次設定**：進入 http://localhost:8978 後連線設定填：
- Host: `postgres`、Port: `5432`、DB: `agent_system`
- User: `admin`、Password: 你的 `POSTGRES_PASSWORD`

## 文字對話 CLI（Phase 1）

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

## 更新 HanloFlow

HanloFlow 有新 commit push 後，在 worker 目錄執行：

```bash
cd worker
uv sync --upgrade-package taigi-converter
```

## LLM 設定

Worker 預設使用 Ollama（OpenAI-compatible API）：

| 環境變數 | 預設值 |
|---------|--------|
| `LLM_BASE_URL` | `http://100.107.45.116:11434/v1` |
| `LLM_MODEL` | `frob/qwen3.5-instruct:9b` |
| `LLM_API_KEY` | `ollama` |

> `worker.main` 會優先讀 `LLM_BASE_URL` / `LLM_API_KEY`，
> 若未設定則 fallback 到 `OPENAI_BASE_URL` / `OPENAI_API_KEY`。

可在 `.env` 中覆寫，或在執行指令前設定：

```bash
LLM_BASE_URL="http://localhost:11434/v1" \
LLM_MODEL="llama3.2" \
  uv run python -m worker.cli --profile "公車站長"
```

## 專案結構

```
.
├── docker-compose.yml         # postgres / redis / livekit / cloudbeaver
├── .env.example               # 環境變數範本
├── CLAUDE.md                  # AI 開發助手工作規則
├── docs/
│   ├── plan.md               # 完整設計文件
│   ├── adr/                  # 架構決策紀錄（001-004）
│   └── phase-1-report.md     # Phase 1 完成報告
├── tasks/                     # 分階段任務清單（含完成記錄）
├── web/                       # Next.js Monorepo (pnpm)
│   ├── apps/playground/      # 使用者對話介面 :3000
│   ├── apps/admin/           # 管理後台 :3001（Tailwind + lucide-react）
│   └── packages/
│       ├── db/               # Prisma schema + migrations + 單例 client
│       ├── types/            # 共用 zod schema（API 輸入驗證）
│       ├── ui/               # 共用元件（待用）
│       └── api-client/       # 後端 API 封裝（待用）
└── worker/                    # Agent Worker (Python + uv)
    ├── worker/
    │   ├── session/          # 對話協調層（AgentComponents + PipelineRunner）
    │   ├── audio/            # 音訊 I/O 層（VAD + AudioProcessor + Barge-in FSM）
    │   ├── pipeline/         # 純計算元件（ASR / LLM / TTS / memory / splitter）
    │   ├── db/               # SQLAlchemy models + repositories
    │   ├── tools/            # Function calling tools（Phase 6）
    │   └── observability/    # 延遲計時器
    ├── tests/
    └── cli.py                # 文字對話測試工具
```

## 開發路線

| Phase | 主題 | 狀態 |
|-------|------|------|
| 0 | 基礎設施 | ✅ 完成 |
| 1 | 純文字對話鏈（CLI）| ✅ 完成 |
| 2 | 語音層接入 + ASR A/B 評估 | ✅ 完成 |
| 3 | 完整迴圈整合 | ✅ 完成 |
| 4 | Barge-in + VAD 抑制 | ✅ 完成 |
| 5 | 管理後台 | ✅ 完成 |
| 6 | RAG + Tools | 🔲 |
| 7 | 打磨與文件 | 🔲 |

完整細節見 [`docs/plan.md §9`](docs/plan.md#9-分階段實作路線) 與 [`tasks/`](tasks/)。

## 授權

[待定]
