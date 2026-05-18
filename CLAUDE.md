# CLAUDE.md

台語即時語音 Agent（大學專題）。LiveKit WebRTC → Worker (ASR→LLM→TTS) → Admin 後台。

## 指令

```bash
# Web
cd web
pnpm install                              # 安裝依賴（自動執行 prisma generate）
pnpm typecheck                            # 全套型別檢查
pnpm build                                # 生產建置
pnpm --filter admin dev                   # Admin 開發伺服器 port 3001
pnpm --filter playground dev             # Playground 開發伺服器 port 3000

# Worker
cd worker
uv sync --extra dev                       # 安裝依賴
uv run ruff check .                       # Lint
uv run pyright                            # 型別檢查
uv run pytest                             # 跑測試

# DB（在 web/packages/db 執行）
pnpm exec prisma generate                 # 重新產生 Prisma client
pnpm exec prisma migrate dev             # 套用 migration
```

## 固定約束

- **Python 套件**：`uv`，禁用 pip / poetry / conda；**Node**：`pnpm`
- **前端 UI**：shadcn/ui（`pnpm dlx shadcn@latest add <component>`，不手寫元件代碼）；Icon：lucide-react
- **記憶體管理**：SlidingWindowMemory，不做摘要壓縮（見 `docs/adr/001`）
- **資料庫**：PostgreSQL + pgvector，不引入獨立向量 DB
- **TTS**：Piper 台語模型，不評估替代方案
- **`docs/plan.md`**：由人類維護，AI 不改

不做：多使用者併發、跨 session 記憶、帳號系統、水平擴展、Kubernetes。

## 目錄結構

```
worker/worker/
├── session/      # AgentComponents、PipelineRunner、data_channel.py（LiveKit data channel）
├── audio/        # VAD、AudioProcessor、Barge-in FSM
├── pipeline/     # ASR / LLM / TTS / memory / splitter（stateless）
├── db/           # models、repositories
├── tools/        # Function calling tools（bus.py / geo.py / tdx_realtime.py）
└── observability/

web/apps/admin/src/
├── app/api/          # 薄 Controller（parse → service → response）
├── app/agents/       # 人格管理（列表、新增、編輯 — Tab UI：基本/工具/知識庫）
├── app/sessions/     # 對話日誌
├── app/dictionary/   # 發音字典
├── app/monitor/      # 即時監控
└── lib/
    ├── services/     # 跨模型 transaction 或可複用業務邏輯
    ├── api.ts        # ok / error / handleError / parseJson
    └── utils.ts      # cn()

web/apps/playground/src/
├── app/page.tsx      # 主頁（連線前置中，連線後 SplitLayout）
└── components/
    └── map-view.tsx  # MapLibre GL React wrapper（forwardRef MapHandle）
```

## 已知 Gotcha

- **Next.js 16 `params`**：動態路由的 `params` 是 `Promise`，必須 `const { id } = await params`
- **shadcn 新增元件**：用 `add`，不要重跑 `init`（會覆蓋 globals.css）
- **base-ui 無 `asChild`**：base-ui 元件（CollapsibleTrigger 等）不接受 `asChild` prop
- **git add 含 `[id]` 路徑**：需加引號，`git add "path/[id]/route.ts"`，否則 shell glob 展開失敗
- **mapcn npm squatted**：`mapcn@0.0.1` 是佔名包，地圖請用 `maplibre-gl` 原生
- **MapLibre SSR**：一定要 `dynamic(() => import(...), { ssr: false })`
- **useVoiceAssistant().state**：worker 用 raw rtc SDK，`state` 永遠是 `"connecting"`；UI state 應從 data channel events 自行派生
- **LiveKit data channel topic**：playground MapPanel 監聽 topic `"map"`，conv 事件 topic `"conv"`；worker 在 `data_channel.py` 管理

## Commit 與文件

- Conventional Commits：`feat(worker):` / `fix(admin):` / `docs(adr):`
- 改完後評估：目錄結構異動 → 更新 CLAUDE.md；架構取捨 → 補 ADR；安裝步驟有變 → 更新 README
- 設計文件：`docs/plan.md`（需要設計理由時才讀，勿全讀）
- 架構決策：`docs/adr/`
- 任務清單：`tasks/phase-N-*.md`（開工前先讀當前 phase）
