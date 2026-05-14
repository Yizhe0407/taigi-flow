# CLAUDE.md

本文件是給 AI 程式開發助手（Claude Code 或類似工具）的工作規則。**人類讀者可跳過此檔**，請改看 `README.md`。

---

## 專案簡介

台語即時語音 Agent 系統。使用者用台語語音互動，系統以 LiveKit (WebRTC) 傳輸音訊，Agent Worker 串接 ASR → LLM → 文字處理 → TTS 處理鏈，支援 Barge-in 打斷機制。這是一個大學專題。

---

## 📚 文件導覽（Read This First）

這個專案有**三種**文件，用途不同，讀取時機不同：

| 文件 | 何時讀 | 用途 |
|------|-------|------|
| `CLAUDE.md`（本檔） | **每次對話開始** | 工作規則與文件導覽 |
| `tasks/phase-N-*.md` | **當前 Phase 執行時** | 具體任務清單與驗收條件 |
| `docs/plan.md` | **只在需要查設計理由時** | 完整設計文件（長，勿全讀）|
| `docs/adr/*.md` | **遇到「為何不用 X」時** | 已定案的架構決策紀錄 |

### ⚠️ 重要：讀取策略

1. **不要一開始就把 `docs/plan.md` 整份讀進 context**。它有 1000+ 行，會稀釋你對當前任務的注意力。
2. **只在 task 檔明確引用時才查閱 plan**，且只讀被引用的章節。
3. **優先級**：當 task 檔與 plan 內容衝突時，**以 task 檔為準**。Plan 是設計依據，task 才是執行指令。

---

## 🚫 決策已定案（不可推翻）

以下項目在專案開工前已經過討論定案。**無論你覺得多有更好的方案，都不要在實作過程中自行替換**。如果你真的認為某個決策有嚴重問題，請**停下來詢問人類**，不要動手改。

### 技術選型（不可換）

- **記憶管理**：滑動視窗（`SlidingWindowMemory`），**不做摘要壓縮**。理由見 `docs/adr/001-sliding-window-memory.md`。
- **資料庫**：PostgreSQL + pgvector（同一 DB 裝關聯資料與向量）。**不引入** Qdrant / Weaviate / Chroma / Milvus。
- **ORM**：Prisma（Node 端）+ SQLAlchemy（Python 端）。兩邊共用同一份 Prisma schema 為 source of truth。
- **TTS**：自訓 Piper 台語模型已存在且品質確認。**不評估替代 TTS 方案**（不要提 Coqui、VITS、XTTS 等）。
- **ASR**：Qwen3-ASR 與 Breeze-ASR-26 雙 backend 抽象介面。Phase 2 以實測數據決定預設，**在此之前兩者都要實作**。
- **套件管理**：Python 端一律用 `uv`，**不用 pip / poetry / conda**。Node 端用 pnpm。
- **傳輸**：LiveKit（WebRTC）。**不自幹 WebSocket 音訊協定**。
- **前端 UI 元件**：一律使用 **shadcn/ui**（`pnpm dlx shadcn@latest add <component>` 下載，**不手寫元件代碼**）。Icons 一律使用 **lucide-react**，**不用其他 icon library**。兩個前端 app（admin、playground）均適用。

### 架構決策（不可改）

- **業務設定進 DB，基礎設施留 env**：Agent 人格、系統提示、字典、工具開關在 DB；`DATABASE_URL`、`LIVEKIT_API_KEY`、`OPENAI_API_KEY` 在 `.env`。
- **單 session，無跨 session 記憶**：對話結束即遺忘，不實作長期記憶功能。
- **單使用者併發**：不處理多使用者同時連線，不寫 Worker Pool / 任務佇列。

### 範圍排除（不可擴張）

這些**不做**：多使用者併發、跨 session 記憶、聲紋辨識、情緒偵測、使用者帳號系統（後台用單一 admin 帳密即可）、水平擴展、負載均衡、對話摘要、Kubernetes 部署。

---

## 🏗️ 工程約束

### 程式碼風格

**Python**
- Python 3.11+
- 強制 type hint（使用 `ruff check --select E,F,I,UP,B,SIM,TCH` + `pyright` strict mode）
- 格式化：`ruff format`
- 禁止 `from x import *`
- Async 優先：I/O 操作都用 `async def`，除非有具體理由
- 錯誤處理：**不吞例外**（`except: pass` 絕對禁止）。捕獲後至少要 `logger.error(...)` 再 re-raise 或處理

**TypeScript**
- 嚴格模式：`strict: true` 全開
- 禁止 `any`（用 `unknown` + type guard 替代）
- 格式化：Prettier + ESLint
- 共用型別放 `packages/types/`，用 `zod` schema 當 source of truth

### 測試要求

| 模組類型 | 測試要求 |
|---------|---------|
| 純邏輯（splitter、memory、text processor）| **必須**有 unit test，覆蓋常見與邊界案例 |
| IO 包裝（ASR、TTS、LLM 客戶端）| 用 mock/fixture 測介面契約，不跑真實模型 |
| 端到端流程 | Phase 3 之後再加 integration test |
| 前端元件 | 不強制，核心 hook 建議測 |

**測試框架**：Python 用 `pytest`，TS 用 `vitest`。

### Git 與 commit

- 分支策略：`main` = 穩定、`dev` = 整合、`feat/xxx` = 功能分支
- Commit 訊息：**Conventional Commits** 格式
  - `feat(worker): add sliding window memory`
  - `fix(splitter): handle trailing punctuation edge case`
  - `docs(adr): add ASR selection decision record`
  - `test(memory): cover overflow scenario`
- 每個 Phase 的 checkbox 完成後才 commit，**不要一次 commit 一堆不相關檔案**

### 檔案組織

遵守以下目錄結構（與 `docs/plan.md §3.1` 同步）。**新增檔案前先檢查該目錄是否已有適合的位置**，不要隨便開新目錄。

```
worker/worker/
├── session/        # 單次對話的狀態與協調（AgentComponents、PipelineRunner）
├── audio/          # 音訊 I/O 層（VAD、AudioProcessor、Barge-in FSM）
├── pipeline/       # 純計算元件，stateless（ASR / LLM / TTS / memory / splitter）
├── db/             # 資料存取層（models、repositories、session、time）
├── tools/          # Function calling tools
└── observability/  # 延遲計時器

web/apps/admin/src/
├── app/
│   ├── api/        # 薄 Controller（請求解析、呼叫 service、回傳 JSON）
│   └── (pages)/    # RSC 頁面，直接查 DB 或呼叫 service
└── lib/
    ├── services/   # 業務邏輯層（跨多模型的 transaction、複雜 upsert 等）
    ├── api.ts      # HTTP 回應工具（ok / error / handleError / parseJson）
    ├── redis.ts    # Redis 連線
    └── utils.ts    # cn() 等共用工具
```

**原則**：簡單 CRUD 直接在 page / API route 查 DB；有跨模型 transaction 或可複用的業務邏輯才抽進 `lib/services/`。

---

## 🤝 協作規則

### 遇到不確定時該怎麼辦

**自己決定的情境**（不必問）：
- 純實作細節：變數命名、程式碼組織、測試案例補充
- 明確的 bug fix
- 已在 plan/task 中寫清楚的事項
- 符合「已定案決策」範圍內的技術選擇

**必須停下來問人類的情境**：
- 任何「看起來 plan 寫錯了」的情況
- 需要引入新的套件或服務（特別是 DB、message queue、AI 模型）
- 需要修改資料庫 schema
- 任務描述模糊到有多種合理解讀
- 遇到「已定案決策」的衝突
- 發現 Phase 之間的依賴順序有問題

**問問題的格式**：
```
🤔 需要確認：[一句話問題摘要]

情境：我在做 [task 名稱]，做到 [具體步驟] 時發現 [觀察]。

選項：
A. [做法]，優點是 X，缺點是 Y
B. [做法]，優點是 X，缺點是 Y

建議：我傾向 A，因為 [理由]，但這會影響 [其他模組]，所以先問一下。
```

### 不允許的行為

- ❌ **靜默擴張範圍**：任務要求做 A，不要順手加 B（即使你覺得 B 很棒）
- ❌ **自行升級依賴**：不要在 feature 分支裡順便升級套件主版本
- ❌ **跳著做**：不要因為「Phase 4 比較有趣」就跳過 Phase 2
- ❌ **忽略測試**：不要寫了程式碼就說完成，至少要把可測的部分測了
- ❌ **輸出不完整的程式碼**：不要留 `# TODO: implement this` 或 `pass` 當作完成
- ❌ **修改 `docs/plan.md`**：這是設計依據文件，由人類維護。發現錯誤請回報，不要直接改

---

## 🎯 當前 Phase 識別

工作前先確認當前 Phase。執行順序：

1. 檢查 `tasks/` 目錄中哪些 Phase 檔有未完成的 checkbox
2. 從編號最小且未完成的 Phase 開始
3. 同一 Phase 內**嚴格按 checkbox 順序執行**（它們之間通常有依賴）

如果你不確定當前在哪個 Phase，**先問人類**。

---

## 📝 工作流程

執行一個 task 時的標準流程：

```
1. 讀取當前 Phase 的 task 檔
2. 找到第一個未勾選的任務
3. 讀該任務的「依賴」「輸入」「驗收」三個欄位
4. 若依賴的 task 未完成 → 停下來問
5. 實作
6. 寫/跑測試
7. 確認驗收條件全部滿足
8. 評估文件是否需要更新（見下方「文件更新評估」）
9. Commit（使用 Conventional Commits 格式）
10. 將 checkbox 改為 [x]，並在旁邊寫 commit SHA
11. 回報人類本 task 已完成，問下一步
```

**重要**：完成一個 task 後**停下來等人類確認**，不要自動往下做。人類可能想看 diff、可能想調整下一步方向。

### 📄 文件更新評估

每次修改完成後，**必須評估**以下文件是否需要同步更新：

| 文件 | 何時需要更新 |
|------|------------|
| `tasks/phase-N-*.md` | 任務狀態變更（勾選 checkbox、補充備註）|
| `CLAUDE.md` | 新增工作規則、技術選型變更、目錄結構異動 |
| `docs/adr/*.md` | 做了架構決策（選 A 不選 B，且理由值得記錄）|
| `README.md` | 安裝步驟、啟動方式、環境需求有變 |

**不需要更新**：`docs/plan.md`（由人類維護，AI 不改）。

評估原則：
- 改了 API 介面 → 查是否有對應文件描述該介面
- 改了目錄結構或引入新套件 → 看 `CLAUDE.md` 的目錄說明是否過時
- 做了非顯而易見的架構取捨 → 考慮補 ADR
- 純 bug fix / 內部重構 → 通常不需要更新文件

---

## 🔗 常用連結

- 設計文件：`docs/plan.md`
- 架構決策紀錄：`docs/adr/`
- Phase 任務清單：`tasks/`
- 人類用 README：`README.md`

---

**最後提醒**：這是大學專題，目標是做出一個能 demo、書面報告能交代清楚的系統，**不是**商用產品。過度工程（over-engineering）會拖垮進度，請保持務實。