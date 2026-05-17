# Phase 6.5：地圖整合（Week 7.5）

> **前置**：Phase 6.4 完成（function calling + bus tools 已成立）
>
> **交付物**：對話提到「從 A 到 B」或「附近有什麼」時，前端即時顯示路線 / POI / 公車站序列；admin 可手動設定目前所在地
>
> **對應 plan.md**：新 schema 欄位 `Session.currentLocation`

---

## 技術選型結論（已查證）

| 元件 | 選擇 | 備註 |
|------|------|------|
| 前端地圖 lib | **mapcn**（github.com/AnmolSaini16/mapcn, 9.2k★）| React + MapLibre GL + Tailwind + shadcn/ui，與既有棧完美對齊 |
| 地圖 tile | MapLibre 免費 tiles（mapcn 預設） | 零 API key |
| Geocoding | **Nominatim 公開 API** | 1 req/s 限速，專題規模夠用 |
| Routing | **OSRM 公開 server**（router.project-osrm.org） | FOSSGIS 維運，免費、無 key |
| POI 搜尋 | Nominatim search + Overpass API | Overpass 用於「附近 X」查詢 |
| Worker → Frontend 通訊 | **LiveKit data channel** | 既有連線，零新基建 |

**已排除**：Mapbox（需 key + 付費）、GraphHopper 公開 API（需註冊）、自建 OSRM / Nominatim（專題規模不需）

---

## 現況盤點

**已存在**
- Phase 6.4 完成 → function calling stream（P6.4-02）+ Tool Registry（P6.4-01）已上
- Phase 6.4 完成 → `worker/tools/bus.py` 可查雲林客運靜態資料，並會推 `bus.route_stops` 到 data channel
- `AgentProfile.tools` Json 欄位、`Session` 表
- LiveKit room 已通

**缺**
- mapcn 元件未引入 playground / admin
- worker `tools/geo.py`（geocoding / routing / poi）
- worker → frontend data channel 推送通道
- admin 位置設定 UI
- `Session.currentLocation` schema 欄位

---

## Schema 異動

```prisma
// 新增到 Session
model Session {
  // ... 既有欄位
  currentLocation Json?  // { lat: number, lng: number, label: string }
}
```

**為何綁 Session 不綁 Profile**：
- 不同對話可能在不同地點（出門前問家附近、出門後問目的地附近）
- Profile 是「人格」，位置是「對話狀態」
- 若 Session 啟動時 location 為空，fallback 用 Profile 預設值

進階：`AgentProfile.defaultLocation Json?` 當 fallback（選做）

---

## 任務清單

### P6.5-01：mapcn 整合 spike

- [ ] **目標**：驗證 mapcn 在 Next.js 16 App Router 不爆
- [ ] **步驟**：
  1. 在 `web/apps/playground` 跑 `pnpm dlx mapcn@latest init`
  2. ⚠️ 確認 **不會覆蓋既有 `globals.css`**（shadcn 已知 gotcha，見 CLAUDE.md）。若會 → 手動 merge
  3. `pnpm dlx mapcn@latest add basic-map`
  4. 包 `'use client'`，確認 SSR 不爆
  5. 試畫 marker + route polyline
- [ ] **驗收**：playground 開出靜態地圖、台北 → 高雄畫一條線
- [ ] **若失敗**：fallback 直接用 MapLibre GL JS 原生 + 自寫 React wrapper
- [ ] **Commit**：`feat(playground): integrate mapcn map component`

---

### P6.5-02：Session.currentLocation schema

- [ ] **檔**：`web/packages/db/prisma/schema.prisma`
- [ ] **加欄位**：`Session.currentLocation Json?`
- [ ] **Migration**：`pnpm exec prisma migrate dev --name add_session_location`
- [ ] **Worker 同步**：`worker/worker/db/models.py` 對應 `currentLocation` Mapped 欄位
- [ ] **Commit**：`feat(db): add session current location field`

---

### P6.5-03：Admin 位置設定 UI

- [ ] **檔**：`web/apps/admin/src/app/sessions/[id]/_components/location-picker.tsx`
- [ ] **功能**：
  - session 詳情頁加「目前位置」區塊
  - 嵌 mapcn 小地圖 + 搜尋框（呼叫 admin 側 geocoding proxy）
  - 點地圖任意點 → 更新 `Session.currentLocation`
  - 顯示目前綁定位置（lat / lng / label）
- [ ] **API**：`web/apps/admin/src/app/api/sessions/[id]/location/route.ts`
  - `PATCH` { lat, lng, label }
- [ ] **Geocoding proxy**：`web/apps/admin/src/app/api/geocode/route.ts`
  - 代理 Nominatim 搜尋（避免 client 直接打 OSM、可加快取）
  - 強制 User-Agent header
- [ ] **Commit**：`feat(admin): add session location picker`

---

### P6.5-04：Worker geo tools

- [ ] **檔**：`worker/worker/tools/geo.py`
- [ ] **三支 tool**（用 Phase 6.4 P6.4-01 BaseTool 介面）：

  | name | params | 回傳 |
  |------|--------|------|
  | `geo.geocode` | `address: str` | `{lat, lng, display_name}` |
  | `geo.route` | `from: str\|coord, to: str\|coord, mode: "driving"\|"walking"\|"cycling"` | `{polyline, distance_m, duration_s, steps}` |
  | `geo.poi_nearby` | `location?: coord, query: str, radius_m: int = 1000` | `[{name, lat, lng, type, distance}]` |

- [ ] **服務端點**：
  - Nominatim: `https://nominatim.openstreetmap.org/search`、`/reverse`
  - OSRM: `https://router.project-osrm.org/route/v1/{mode}/{lng1},{lat1};{lng2},{lat2}`
  - Overpass (POI): `https://overpass-api.de/api/interpreter`
- [ ] **強制要求**：
  - User-Agent：`taigi-flow/0.1 (學校專題 - <聯絡 email>)`
  - 8s timeout（對齊 plan.md 5.2）
  - 失敗 → 回字串「地圖資料這馬提無著」給 LLM
  - 結果除回給 LLM 文字描述外，**側通道**推結構化 payload 給 frontend（P6.5-05）
- [ ] **位置上下文**：tool 執行時讀 `Session.currentLocation` 當 `from` / `location` 預設值
  - LLM 講「附近有什麼小吃」→ 不用問位置，直接帶 session location
- [ ] **快取**：geocode 結果以 query 為 key 進 in-memory dict（同 session 重複問同地點不重打）
- [ ] **測試**：`respx` mock 三個外部服務
- [ ] **Commit**：`feat(worker): implement geo tools (geocode, route, poi)`

---

### P6.5-05：Worker → Frontend 即時推送

- [ ] **通道**：LiveKit data channel（已有連線）
- [ ] **Worker 側**：`worker/worker/session/components.py` 加 `publish_data(payload: dict)` helper
  - 包成 JSON → `room.local_participant.publish_data(bytes)`
  - reliable mode（順序、可靠）
- [ ] **Tool 觸發**：`geo.route` / `geo.poi_nearby` 執行完 → 兩條推送：
  1. 結構化結果給 frontend（畫地圖）
  2. 自然語言描述給 LLM continue（LLM 拿來講台語）
- [ ] **Payload schema**：

  ```ts
  type MapPayload =
    | { type: "map.route"; from: Coord; to: Coord; polyline: string; distance_m: number; duration_s: number }
    | { type: "map.poi"; center: Coord; items: { name: string; lat: number; lng: number }[] }
    | { type: "map.focus"; lat: number; lng: number; zoom?: number }
    // Phase 6.4 bus tools 推送
    | { type: "bus.route_stops"; route: string; stops: { name: string; lat: number; lng: number; sequence: number }[] };
  ```

- [ ] **Frontend 訂閱**：`web/apps/playground/src/components/map-listener.tsx`
  - `room.on('dataReceived', (payload) => ...)`
  - 依 `type` 更新 mapcn state（畫線、放標記、置中）
- [ ] **Commit**：`feat(worker,playground): bridge tool results to map via livekit data channel`

---

### P6.5-06：LLM intent 觸發

- [ ] **檔**：`worker/worker/session/components.py`（system prompt 拼接處）
- [ ] **加 system prompt 片段**：

  ```
  你有地圖與公車工具：

  通用地理：
  - 「從 X 到 Y」/「怎麼去」/「路線」 → geo.route
  - 「附近的 X」/「周邊」 → geo.poi_nearby（不用問位置，已知）
  - 「X 在哪裡」/「定位 X」 → geo.geocode

  雲林客運（優先於 geo.route，若是公車相關問題）：
  - 「Y02 經過哪些站」 → bus.list_stops
  - 「從 A 站到 B 站怎麼搭」 → bus.find_routes
  - 「Y02 現在到哪 / 還多久到」 → tdx.bus_arrival

  呼叫工具前先用台語講「我看一下地圖」遮蔽延遲。
  講路線時不要念經緯度，講地名與時間 / 距離即可。
  ```

- [ ] **限制**：避免每次都呼叫地圖工具（讓 LLM 自行判斷必要性）
- [ ] **Commit**：`feat(worker): add map tools to system prompt`

---

## 延遲預算（會破 first_audio）

| 階段 | 時間 |
|------|------|
| VAD silence | 500ms |
| ASR | 300ms |
| LLM first token | 400ms |
| **Tool call**（OSRM ~800ms / Nominatim ~600ms） | 600-800ms |
| LLM second round 首字 | 300ms |
| TTS first audio | 300ms |
| **合計** | **~2.5-2.8s** |

**緩解**：LLM **先講「我看一下地圖」遮蔽 tool latency**（system prompt 已要求），實際感知延遲降回 ~1.5s。

---

## 已知 Gotcha

- **mapcn `add` 不覆蓋 globals.css**：shadcn 系列工具的已知雷區，先備份再執行
- **MapLibre SSR 爆**：mapcn 元件一定要 `'use client'` 包，動態 import + `ssr: false` 更穩
- **Nominatim User-Agent 強制**：缺 UA 直接被擋 403
- **OSRM polyline 編碼**：回傳 `polyline6`（precision 6），前端需用 `@mapbox/polyline` 或 mapcn 內建解碼
- **LiveKit data channel 大小限制**：單封包 ≤ 15KB，POI 大量結果需分批或精簡
- **Overpass timeout**：免費實例常 30s 才回，加上限 `[timeout:5]` 強制 5s 內回應
- **Next.js 16 params**：admin 動態路由 `await params`（CLAUDE.md 已記）

---

## Phase 6.5 完成標準

**核心**
- [ ] Playground 對話：「我想從斗六火車站到北港」→ 地圖即時畫出路線，LLM 用台語講距離 / 時間
- [ ] 對話：「Y02 經過哪些站」→ 觸發 Phase 6.4 `bus.list_stops`，地圖標記全部停靠站，LLM 念前幾站
- [ ] 對話：「附近有什麼小吃」→ 用 Session.currentLocation 查 POI，地圖標記，LLM 念前 3 名
- [ ] Admin 可在 session 詳情頁點地圖更新 `currentLocation`
- [ ] Tool 失敗 → 不 crash，LLM 講「地圖提無著」

**延伸（選做）**
- [ ] AgentProfile.defaultLocation fallback
- [ ] 路線顯示交通方式切換（駕車 / 步行 / 騎車）
- [ ] POI 點擊 → 自動帶入下一輪對話
- [ ] 公車路線多色 polyline（不同路線不同顏色）

---

## 時程壓力時的取捨

- **最低限**：P6.5-01 + P6.5-04（單支 `geo.route`） + P6.5-05 + P6.5-06 = demo 可用路線功能
  - 砍 admin 位置 UI（用 seed 寫死台北車站）、砍 POI tool
- **加碼**：完整三支 tool + admin UI + POI 點擊互動
- **全砍**：整個 Phase 6.5 跳過，回去做 Phase 7 polish

---

## Phase 編號異動

```
Phase 6   : RAG（已規劃）
Phase 6.4 : Function calling + 雲林客運資料底層
Phase 6.5 : 地圖整合（本檔）
Phase 7   : 打磨與文件（順延一週）
```

需同步更新 `tasks/README.md` 與 `docs/plan.md` 的 Phase 表。
