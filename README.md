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

```bash
# 1. 複製環境變數範本
cp .env.example .env
# 編輯 .env 填入 OPENAI_API_KEY 等

# 2. 啟動全部服務
docker compose up -d

# 3. 執行 DB migration
pnpm --filter @app/web prisma migrate dev

# 4. 訪問
# Playground: http://localhost:3000
# Admin:      http://localhost:3000/admin
```

詳細部署步驟見 [`docs/plan.md §8`](docs/plan.md#8-容器化部署-docker-compose)。

## 📁 專案結構

```
.
├── README.md               # 本檔
├── CLAUDE.md              # AI 開發助手工作規則
├── docs/
│   ├── plan.md           # 完整設計文件
│   ├── architecture.md   # 純架構圖彙整
│   ├── asr_evaluation.md # Phase 2 ASR 評估報告
│   └── adr/              # 架構決策紀錄
├── tasks/                 # 分階段任務清單
│   ├── phase-0-infrastructure.md
│   ├── phase-1-text-pipeline.md
│   └── ...
├── web/                   # Next.js Monorepo
└── worker/                # Agent Worker
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