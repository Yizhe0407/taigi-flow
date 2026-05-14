# CLAUDE.md

台語即時語音 Agent 系統（大學專題）。LiveKit WebRTC → Worker (ASR → LLM → TTS) → Admin 後台。

## 常用指令

```bash
# Web
cd web && pnpm install          # 安裝依賴（自動執行 prisma generate）
pnpm typecheck                   # 全套型別檢查
pnpm build                       # 生產建置
pnpm --filter admin dev          # Admin 開發伺服器（port 3001）
pnpm --filter playground dev     # Playground 開發伺服器（port 3000）

# Worker
cd worker
uv sync --extra dev              # 安裝依賴
uv run ruff check .              # Lint
uv run pyright                   # 型別檢查
uv run pytest                    # 跑測試

# DB
cd web/packages/db
pnpm exec prisma generate        # 重新產生 Prisma client（pnpm install 後自動執行）
pnpm exec prisma migrate dev     # 套用 migration
```

## 技術約束（不可更換）

- **Python 套件管理**：`uv`，禁用 pip / poetry / conda
- **Node 套件管理**：`pnpm`
- **前端 UI**：shadcn/ui（`pnpm dlx shadcn@latest add <component>`，**不手寫元件代碼**）
- **Icons**：lucide-react，不用其他 icon library
- **記憶體管理**：`SlidingWindowMemory` 滑動視窗，不做摘要壓縮（見 `docs/adr/001`）
- **資料庫**：PostgreSQL + pgvector，不引入獨立向量 DB
- **ORM**：Prisma（Node）+ SQLAlchemy（Python），Prisma schema 為 source of truth
- **TTS**：自訓 Piper 台語模型，不評估替代方案
- **傳輸**：LiveKit WebRTC，不自幹 WebSocket
- **`docs/plan.md`**：由人類維護，**AI 不改**

## 不做的功能

多使用者併發、跨 session 記憶、聲紋辨識、情緒偵測、使用者帳號系統、水平擴展、Kubernetes。

## 目錄結構

```
worker/worker/
├── session/      # AgentComponents、PipelineRunner
├── audio/        # VAD、AudioProcessor、Barge-in FSM
├── pipeline/     # ASR / LLM / TTS / memory / splitter（stateless）
├── db/           # models、repositories
├── tools/        # Function calling tools
└── observability/

web/apps/admin/src/
├── app/api/      # 薄 Controller（parse → service → response）
├── app/(pages)/  # RSC 頁面
└── lib/
    ├── services/ # 跨模型 transaction 或可複用業務邏輯才放這裡
    ├── api.ts    # ok / error / handleError / parseJson
    └── utils.ts  # cn()
```

## 程式碼規範

**Python**：type hint 全開，`ruff check`（E,F,I,UP,B,SIM,TCH）+ pyright strict，禁止 `except: pass`，I/O 一律 `async def`。

**TypeScript**：`strict: true`，禁止 `any`，共用型別放 `packages/types/`，Zod schema 為 source of truth。

**Commit**：Conventional Commits（`feat(worker): ...`、`fix(admin): ...`）。

## 文件

- 設計文件：`docs/plan.md`（需要設計理由時才讀，勿全讀）
- 架構決策：`docs/adr/`（遇到「為何不用 X」時查）
- 任務清單：`tasks/phase-N-*.md`（開工前先讀當前 phase）

**修改完成後評估**：目錄結構異動 → 更新 CLAUDE.md；架構取捨 → 補 ADR；安裝/啟動有變 → 更新 README.md。
