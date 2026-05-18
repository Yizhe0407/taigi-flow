# Phase 6.4：Function Calling 基礎 + 雲林客運資料底層（Week 7.4）

> **前置**：Phase 6（RAG）完成
>
> **交付物**：
> - LLM 可呼叫工具（function calling 完整迴圈）
> - 雲林客運靜態資料進 DB，可查路線 / 站點 / 班表
> - TDX 即時到站 tool
>
> **後續依賴**：Phase 6.5 地圖整合會用本 Phase 的 bus tools 與 function calling 基礎
>
> **對應 plan.md**：`AgentProfile.tools`、tool 設計章節

---

## 現況盤點

**已存在**
- `worker/pipeline/llm.py:45` `stream()` 已接 `tools` 參數
- `worker/tools/__init__.py` 空殼
- 使用者本機 `~/Documents/NYUST/專題/TDX/` 已有資料：
  - `route.json`（12 路線）
  - `stop.json`（338 站）
  - `stop_of_route.json`（32 筆）
  - `schedule.json`（22 筆班表）
  - `雲林客運.zip`（完整版，含 165MB schedule、realtime.json）

**缺**
- `worker/tools/base.py`, `worker/tools/__init__.py` registry
- Function calling 完整迴圈（LLM 回 `tool_calls` chunk 目前當文字流出 → 壞）
- `BusRoute / BusStop / RouteStop / BusSchedule` schema
- Importer：JSON → DB
- `worker/tools/bus.py`（靜態查詢）
- `worker/tools/tdx_realtime.py`（即時到站）

---

## 資料來源策略

**先小後大**：
1. **第一階段**：用根目錄那 4 個小 JSON（12 路線 / 338 站）跑通 importer + tools
2. **第二階段**：解壓 `雲林客運.zip` → 換完整資料（route 應 > 100、stop > 數千）
3. **realtime.json 不用**：歷史快照，無意義。即時資料一律走 TDX API

理由：小檔案 demo 順暢、importer 邏輯先驗證；完整資料量大、idempotent importer 後再灌。

---

## Schema 設計

```prisma
// ============ 公車路線 ============
model BusOperator {
  id           String   @id            // OperatorID e.g. "21"
  code         String                  // OperatorCode e.g. "TaisiBus"
  nameZh       String
  nameEn       String

  routes       BusRoute[]
}

model BusRoute {
  uid          String   @id            // RouteUID e.g. "YUN0030"
  routeId      String                  // RouteID e.g. "0030"
  nameZh       String                  // SubRouteName.Zh_tw e.g. "Y02"
  nameEn       String
  headsign     String?                 // e.g. "北港虎尾線"
  direction    Int                     // 0 去程 / 1 返程
  city         String                  // "YunlinCounty"
  operatorId   String
  operator     BusOperator @relation(fields: [operatorId], references: [id])

  stops        RouteStop[]
  schedules    BusSchedule[]

  @@index([city])
  @@index([nameZh])
}

model BusStop {
  uid          String   @id            // StopUID e.g. "YUN298779"
  stopId       String
  nameZh       String
  nameEn       String
  lat          Float
  lng          Float
  address      String?
  city         String

  routeStops   RouteStop[]

  @@index([city])
  @@index([nameZh])
  // PostGIS index 選做（pgvector 已裝，POSTGIS extension 另裝）
}

model RouteStop {
  routeUid     String
  stopUid      String
  sequence     Int      // StopSequence
  boarding     Boolean  @default(true)

  route        BusRoute @relation(fields: [routeUid], references: [uid])
  stop         BusStop  @relation(fields: [stopUid], references: [uid])

  @@id([routeUid, stopUid, sequence])
  @@index([routeUid, sequence])
  @@index([stopUid])
}

model BusSchedule {
  id           String   @id @default(uuid())
  routeUid     String
  tripId       String
  serviceDays  Int      // bitmask: Sun=1, Mon=2, Tue=4 ... Sat=64
  isLowFloor   Boolean  @default(false)
  stopTimes    Json     // [{ stopUid, sequence, arrivalTime: "HH:MM" }, ...]

  route        BusRoute @relation(fields: [routeUid], references: [uid])

  @@index([routeUid, serviceDays])
}
```

**設計決策**：
- ID 用 TDX 的 UID（穩定 + 對外可追溯），不自產 UUID
- `BusSchedule.stopTimes` 用 Json，省 N×M 表（單班次停靠序列查詢無強烈關聯需求）
- `serviceDays` 用 bitmask，**省**七個布林欄位（取「今天有沒有發車」用 `serviceDays & (1 << weekday)`）
- 不存即時資料

---

## 任務清單

### P6.4-01：Tool Base Class + Registry

- [x] **檔**：`worker/worker/tools/base.py`

  ```python
  class BaseTool(ABC):
      name: str
      description: str
      parameters: dict          # JSON Schema

      @abstractmethod
      async def execute(self, **kwargs) -> str: ...

      def to_openai_schema(self) -> dict:
          return {"type": "function", "function": {
              "name": self.name,
              "description": self.description,
              "parameters": self.parameters,
          }}
  ```

- [x] **檔**：`worker/worker/tools/__init__.py`

  ```python
  TOOL_REGISTRY: dict[str, BaseTool] = {}

  def register(tool: BaseTool) -> None:
      TOOL_REGISTRY[tool.name] = tool

  def get_tools(names: list[str]) -> list[BaseTool]:
      return [TOOL_REGISTRY[n] for n in names if n in TOOL_REGISTRY]
  ```

- [x] **AgentProfile.tools 載入**：`session/components.py` 啟動 session 時讀 `profile.tools: list[str]` → 取對應 tool 餵 LLM
- [x] **單元測試**：註冊 dummy tool、`to_openai_schema()` shape 正確
- [x] **Commit**：`feat(worker): add tool base class and registry`

---

### P6.4-02：Function Calling 完整迴圈

- [x] **檔**：`worker/worker/pipeline/llm.py`（擴 `stream_with_tools`）+ `session/components.py`（接線）
- [x] **現況問題**：`stream()` 把 `tools` 傳給 OpenAI，但若 LLM 回 `tool_calls` chunk，目前直接當文字流出
- [x] **解法**：

  ```python
  async def stream_with_tools(messages, tools_objs, max_rounds=3):
      for _round in range(max_rounds):
          # round N: 收 chunk
          tool_calls_buffer = {}    # index → {name, arguments_delta}
          text_buffer = []
          async for chunk in self._client.chat.completions.create(...):
              delta = chunk.choices[0].delta
              if delta.tool_calls:
                  # 累積 arguments delta（OpenAI 串流 delta 形式）
                  for tc in delta.tool_calls:
                      buf = tool_calls_buffer.setdefault(tc.index, {"name": "", "args": ""})
                      if tc.function.name: buf["name"] = tc.function.name
                      if tc.function.arguments: buf["args"] += tc.function.arguments
              elif delta.content:
                  yield delta.content
                  text_buffer.append(delta.content)

          if not tool_calls_buffer:
              return  # 純文字回應，結束

          # 執行所有 tool calls
          messages.append({"role": "assistant", "tool_calls": [...]})
          for idx, buf in tool_calls_buffer.items():
              tool = TOOL_REGISTRY[buf["name"]]
              args = json.loads(buf["args"])
              result = await tool.execute(**args)
              messages.append({
                  "role": "tool",
                  "tool_call_id": ...,
                  "content": result,
              })
          # 進下一輪
  ```

- [x] **Pipeline 整合**：tool 執行期間 **TTS 不啟動**（不能讓使用者聽到半句被中斷）
  - splitter 偵測到 round 是 tool call → buffer 不送 TTS
  - 進入文字 round 才開始送 TTS
- [x] **Log**：`tool_call_started`, `tool_call_completed`, `tool_name`, `latency_tool_ms`
- [x] **錯誤處理**：tool raise → 不中斷迴圈，把 error message 當 result 給 LLM continue
- [x] **Commit**：`feat(worker): add function calling loop with tool execution`

---

### P6.4-03：Bus Schema + Migration

- [x] **檔**：`web/packages/db/prisma/schema.prisma`（加 4 個 model）
- [x] **Migration**：`pnpm exec prisma migrate dev --name add_bus_models`
- [x] **SQLAlchemy 對應**：`worker/worker/db/models.py` 加 `BusRoute`, `BusStop`, `RouteStop`, `BusSchedule`, `BusOperator`
- [x] **Commit**：`feat(db): add bus route / stop / schedule models`

---

### P6.4-04：Importer（JSON → DB）

- [x] **檔**：`worker/worker/scripts/import_bus.py`
- [x] **CLI**：`uv run python -m worker.scripts.import_bus --dir <path> [--clean]`
  - `--clean`：先 truncate 4 張表再灌（idempotent demo）
  - 預設 upsert（更新就好）
- [x] **流程**：
  1. 讀 `route.json` → upsert BusOperator + BusRoute（注意 SubRoute 結構，一筆 RouteUID 內可能多 SubRoutes，要展開）
  2. 讀 `stop.json` → upsert BusStop
  3. 讀 `stop_of_route.json` → 對 RouteStop 做 truncate-and-insert（避免序列錯亂）
  4. 讀 `schedule.json` → upsert BusSchedule
     - `ServiceDay {Sunday:1, Monday:1,...}` → bitmask
     - `StopTimes` 整段塞 Json
- [x] **驗證**：
  - 灌完後 `SELECT COUNT(*) FROM "BusRoute"` 應 = 12（小檔）
  - JOIN 查詢 Y02 完整停靠序列 → 對得起來
- [x] **大檔切換**：寫成 idempotent，未來解 zip 後重跑即可
- [x] **測試**：用 fixture（精簡 sample JSON）跑 e2e
- [x] **Commit**：`feat(worker): add bus data importer from tdx json`

---

### P6.4-05：Bus Static Tools

- [x] **檔**：`worker/worker/tools/bus.py`
- [x] **三支 tool**：

  | name | params | 回傳描述 |
  |------|--------|---------|
  | `bus.search_stops` | `query: str, city?: str, limit: int = 5` | 站名模糊搜尋（ILIKE），回 `[{uid, name, lat, lng, city}]` |
  | `bus.find_routes` | `from_stop: str, to_stop: str` | 找直達路線（單跳，不做轉乘）。回路線列表 + 兩站序列位置 |
  | `bus.list_stops` | `route: str, direction: int = 0` | 路線完整停靠序列 |
  | `bus.next_departures` | `stop: str, route?: str, weekday?: int, limit: int = 3` | 班表查詢：今天從某站、某路線、接下來 N 班 |

- [x] **實作要點**：
  - 站名輸入容錯：用 `pg_trgm` 模糊匹配（先 ILIKE 直接比對，若 0 筆 fallback trigram similarity）
  - `next_departures` 用 `serviceDays & (1 << today_weekday)` 過濾
  - 時間用 `Asia/Taipei` 時區（已有 `worker/db/time.py`）
- [x] **回傳格式**：給 LLM 的字串描述要**簡潔**，不要塞經緯度（除非地圖工具用）

  ```
  # bus.next_departures 範例
  Y02（北港虎尾線）從斗六火車站今日下午接下來 3 班：14:20、15:10、16:00
  ```

- [ ] **副通道**：執行完後**同時**推 LiveKit data channel（給 Phase 6.5 地圖畫）
  - payload: `{ type: "bus.route_stops", stops: [{name, lat, lng}, ...] }`
  - 若 Phase 6.5 還沒做，data channel 推送先寫但 frontend 無 listener 也無妨
- [x] **單元測試**：mock DB session，每支 tool 驗 SQL / 結果格式
- [x] **Commit**：`feat(worker): add bus static query tools`

---

### P6.4-06：TDX 即時到站 Tool

- [x] **檔**：`worker/worker/tools/tdx_realtime.py`
- [x] **TDX API**：
  - OAuth2：`https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token`
  - Endpoint：`/api/basic/v2/Bus/EstimatedTimeOfArrival/City/{City}/{RouteName}`
- [x] **Tool**：`tdx.bus_arrival(city: str, route: str, stop?: str)`
  - 回：某路線各站到站時間（或單站若提供 `stop`）
  - 給 LLM：`Y02 在斗六火車站約 5 分鐘到站、北港朝天宮 35 分鐘到站`
- [x] **Token 快取**：module-level，到期前 5min refresh，不打 Redis
- [x] **錯誤**：8s timeout、403/429 → 「即時資料這馬提無著」字串給 LLM
- [x] **Env**：`TDX_CLIENT_ID`, `TDX_CLIENT_SECRET`（plan.md L944 已預留）
- [x] **註冊申請**：https://tdx.transportdata.tw/ → 個人帳號 → 取 client_id/secret（免費）
- [x] **測試**：`respx` mock token + arrival endpoints
- [x] **Commit**：`feat(worker): implement tdx realtime bus arrival tool`

---

### P6.4-07：System Prompt 接線

- [x] **檔**：`worker/worker/session/components.py`（system prompt 拼接）
- [x] **加 prompt 片段**（依 AgentProfile.tools 動態判斷是否加入）：

  ```
  你有公車工具。若使用者問：
  - 「Y02 經過哪些站」 → bus.list_stops
  - 「從 X 到 Y 怎麼搭」 → bus.find_routes（直達），若無 → 用 RAG 看異動公告
  - 「Y02 接下來幾點」 → bus.next_departures（用班表）
  - 「Y02 現在到哪」/「還多久到」 → tdx.bus_arrival（即時）

  講站名與時間，不要念經緯度。
  ```

- [x] **Commit**：`feat(worker): add bus tools to system prompt`

---

## 已知 Gotcha

- **SubRoute 展開**：TDX 一筆 `Route` 內有多個 `SubRoutes`（去程 / 返程 / 區間），匯入時要拆成多筆 BusRoute（用 SubRouteUID）
- **OpenAI tool_calls stream**：`arguments` 是 delta，要 concat 才 `json.parse`；不同 index 是不同 call
- **serviceDays bitmask 順序**：Python `datetime.weekday()` 是 Mon=0、Sun=6，TDX 是 Sun-first。對齊時轉一下
- **時區**：班表 `StopTimes` 用本地時間（沒時區標記），查詢時用 `Asia/Taipei` 才不會錯一天
- **空字串 vs None**：TDX JSON 內 `Headsign` 可能空字串，prisma optional 欄位寫 null 別寫 ""
- **大檔解壓**：`雲林客運.zip` 內 schedule.json 121MB，importer 要用 streaming 解析（`ijson` 或分批讀），別一次 `json.load`

---

## Phase 6.4 完成標準

**核心**
- [x] 4 個 JSON 灌進 DB，count 對得起來
- [x] LLM 問「Y02 經過哪些站」→ tool 回站序列、台語念站名
- [x] LLM 問「從斗六火車站到北港怎麼搭」→ tool 回直達路線、台語回答
- [x] LLM 問「Y02 現在到哪」→ TDX 即時 call、台語播報
- [x] Tool raise → LLM 接 error string，不 crash
- [x] Function calling 多輪：LLM 連續呼叫 2 個 tool 也正常

**延伸（選做）**
- [x] `雲林客運.zip` 完整資料灌入（route > 100、schedule 完整）
- [x] 轉乘搜尋（`bus.find_routes` 支援 1 次轉乘）
- [ ] PostGIS 「最近的站」（地圖整合可用）

---

## 時程壓力時的取捨

- **最低限**：P6.4-01 + P6.4-02 + P6.4-03 + P6.4-04 + 單支 `bus.search_stops` + `bus.list_stops` → 可 demo 雲林客運查詢
- **加碼**：完整 4 支 bus tool + TDX 即時
- **全砍**：function calling 基礎仍需做（Phase 6.5 地圖也要），bus 部分整段跳過

---

## Phase 編號全景

```
Phase 6   : RAG（純文字 / 知識庫）
Phase 6.4 : Function calling + 雲林客運資料底層（本檔）
Phase 6.5 : 地圖整合（依賴 6.4 function calling + bus tools）
Phase 7   : 打磨與文件
```
