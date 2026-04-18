# Phase 0：基礎設施（Week 1）

> **目標**：讓整個專案骨架跑起來，所有服務能互相連通，但還沒有業務邏輯。
>
> **前置**：無
>
> **交付物**：一個 `docker compose up` 就能啟動全部服務的專案
>
> **對應 plan.md**：[§8 容器化部署](../docs/plan.md#8-容器化部署-docker-compose)、[§2 資料庫設計](../docs/plan.md#2-資料庫設計postgresql--pgvector)

---

## 任務清單

### P0-01：初始化 Monorepo 與 Git

- [x] **依賴**：無
- [x] **輸入**：無
- [x] **動作**：
  - 建立 Git repo，首次 commit 含 `.gitignore`、`README.md`、`CLAUDE.md`、`docs/`、`tasks/`
  - 建立 pnpm workspace（`pnpm-workspace.yaml`）
  - 建立 `.env.example` 含所有必要的環境變數 key（不填值，只有 key）
- [x] **驗收**：
  - `git log` 有首次 commit
  - `pnpm -v` 可執行
  - `.gitignore` 至少排除 `node_modules/`, `.env`, `__pycache__/`, `.venv/`, `dist/`, `.turbo/`
- [x] **Commit 訊息**：`chore: initial project scaffolding`

---

### P0-02：建立 Docker Compose 骨架

- [x] **依賴**：P0-01
- [x] **輸入**：`docs/plan.md §8.1` 的 compose 範例
- [x] **動作**：
  - 建立 `docker-compose.yml`，服務含：`postgres`、`redis`、`livekit`
  - 建立 `infra/livekit.yaml`（最小 dev 設定）
  - **暫時不含** `web`、`agent-worker`、`caddy`（這些 Phase 後面才加）
- [x] **驗收**：
  - `docker compose up -d` 三個服務啟動成功
  - `docker compose ps` 全部 healthy
  - `psql -h localhost -U admin -d agent_system -c '\l'` 能連上
  - `redis-cli -h localhost ping` 回 PONG
  - LiveKit admin panel 可在 `http://localhost:7880` 回應
- [x] **Commit 訊息**：`feat(infra): add docker compose with postgres/redis/livekit`

---

### P0-03：建立 Web 專案骨架

- [x] **依賴**：P0-01
- [x] **輸入**：`docs/plan.md §7.1` 的 Monorepo 結構
- [x] **動作**：
  - 建立 `web/apps/playground`（Next.js 14+，App Router）
  - 建立 `web/apps/admin`（Next.js 14+）
  - 建立 `web/packages/ui`、`web/packages/types`、`web/packages/api-client`（暫時為空殼）
  - 設定 Turbo（`turbo.json`）
  - 兩個 app 各寫一個 hello world 頁面
- [x] **驗收**：
  - `pnpm install` 不出錯
  - `pnpm --filter playground dev` 啟動在 :3000
  - `pnpm --filter admin dev` 啟動在 :3001
  - 兩頁各自顯示 hello world
  - `pnpm build` 全部編譯通過
- [x] **Commit 訊息**：`feat(web): scaffold monorepo with playground and admin apps`

---

### P0-04：建立 Prisma Schema 與首次 migration

- [x] **依賴**：P0-02、P0-03
- [x] **輸入**：`docs/plan.md §2.2` 的完整 Prisma schema
- [x] **動作**：
  - 在 `web/packages/db/` 建立 Prisma 專案
  - 寫入 `schema.prisma`（完整 schema 含所有 model）
  - 執行首次 migration：`prisma migrate dev --name init`
  - 啟用 pgvector extension（migration 內用 raw SQL）
  - 寫 seed script（`prisma/seed.ts`）插入一個預設 AgentProfile（名為「公車站長」）
- [x] **驗收**：
  - `prisma migrate dev` 成功
  - `prisma studio` 可開，看到所有 table
  - `pnpm prisma db seed` 後，資料表有一筆 AgentProfile
  - `SELECT * FROM "AgentProfile";` 能查到資料
  - `CREATE EXTENSION IF NOT EXISTS vector;` 已執行（`SELECT * FROM pg_extension;` 可見）
- [x] **Commit 訊息**：`feat(db): add prisma schema with pgvector extension`

---

### P0-05：建立 Worker 專案骨架

- [x] **依賴**：P0-01
- [x] **輸入**：`docs/plan.md §3.1` 的目錄結構
- [x] **動作**：
  - 建立 `worker/` 目錄
  - `uv init` 建立 Python 專案（Python 3.11+）
  - 建立完整目錄結構（`controller/`, `pipeline/`, `pipeline/asr/`, `tools/`, `db/`, `observability/`）
  - 每個子目錄放一個 `__init__.py`
  - 建立 `worker/main.py` 印 "Worker ready"
  - 設定 `pyproject.toml` 含基本依賴（`livekit-agents`, `sqlalchemy`, `pydantic`, `ruff`, `pytest`, `pyright`）
  - 設定 `.python-version` 鎖定 3.11
  - 設定 ruff 與 pyright config
- [x] **驗收**：
  - `uv sync` 成功
  - `uv run python -m worker.main` 印 "Worker ready"
  - `uv run ruff check .` 通過
  - `uv run pyright` 通過
  - `uv run pytest` 通過（即使沒有測試）
- [x] **Commit 訊息**：`feat(worker): scaffold python project with uv`

---

### P0-06：建立 SQLAlchemy Models 對應 Prisma Schema

- [x] **依賴**：P0-04、P0-05
- [x] **輸入**：已建立的 Prisma schema
- [x] **動作**：
  - 在 `worker/db/models.py` 用 SQLAlchemy 2.0 語法對應 Prisma 的所有 model
  - 在 `worker/db/session.py` 建立 async engine（`asyncpg` driver）與 session factory
  - 在 `worker/db/repositories.py` 寫 `AgentProfileRepository` 有 `get_active_by_id()` 方法
  - 寫一個 smoke test：能連 DB、能讀到 seed 的 AgentProfile
- [x] **驗收**：
  - `uv run pytest worker/tests/test_db_smoke.py -v` 通過
  - Pyright 通過（所有 model 有完整 type）
- [x] **Commit 訊息**：`feat(worker): add sqlalchemy models and repositories`

---

### P0-07：設定 CI（GitHub Actions）

- [x] **依賴**：P0-03、P0-05
- [x] **輸入**：已建立的 web 與 worker 專案
- [x] **動作**：
  - 建立 `.github/workflows/ci.yml`
  - Job 1：Web — 跑 `pnpm install`、`pnpm typecheck`、`pnpm lint`、`pnpm build`
  - Job 2：Worker — 跑 `uv sync`、`uv run ruff check`、`uv run pyright`、`uv run pytest`
  - Job 3：Prisma schema 檢查 — 跑 `prisma format --check` 確保 schema 格式正確
- [x] **驗收**：
  - Push 到 GitHub 後 CI 全綠
  - 三個 job 都有執行
- [x] **Commit 訊息**：`ci: add github actions for web, worker, and prisma checks`

---

### P0-08：撰寫 Phase 0 驗收文件

- [x] **依賴**：P0-01 ~ P0-07 全部完成
- [x] **動作**：
  - 更新 `README.md` 的「快速開始」章節，確保按步驟真的能跑
  - 請團隊成員（或自己重新 clone）跑一次，驗證流程無缺漏
  - 若流程有問題，補齊 README
- [x] **驗收**：
  - 新環境從零 clone 專案，照 README 能在 30 分鐘內跑起全部 Phase 0 服務
- [x] **Commit 訊息**：`docs: update readme with verified setup steps`

---

## Phase 0 完成標準

所有任務 checkbox 打勾 + 以下條件成立：

- [x] `docker compose up -d` 全綠
- [x] 兩個前端 app 能啟動
- [x] Worker 能連 DB 讀到 seed 資料
- [ ] CI 在 main branch 全綠（push 到 GitHub 後驗證）
- [x] 同團隊新成員能在 1 小時內跑起開發環境

## 常見問題

**Q：pgvector extension 裝不起來？**
A：確認用的是 `ankane/pgvector:latest` 而非標準 postgres image。

**Q：Prisma migration 報 enum 錯誤？**
A：pgvector 的 `vector` 類型在 Prisma 是 `Unsupported("vector(1536)")`，不是 enum。

**Q：uv 執行 Python 提示找不到模組？**
A：確認在 `worker/` 根目錄執行，且 `pyproject.toml` 有 `[tool.setuptools.packages.find]` 或 `[project] packages = [...]` 設定。