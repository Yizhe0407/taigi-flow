# Phase 6.5：地圖整合（Week 7.5）

> **前置**：Phase 6.4 完成（function calling + bus tools 已成立）
>
> **交付物**：對話提到「從 A 到 B」或「附近有什麼」時，前端即時顯示路線 / POI / 公車站序列；瀏覽器 GPS 自動送給 worker
>
> **對應 plan.md**：新 schema 欄位 `Session.currentLocation`

---

## 技術選型結論（已查證）

| 元件 | 選擇 | 備註 |
|------|------|------|
| 前端地圖 lib | **MapLibre GL JS** + 自寫 React wrapper | mapcn npm 套件名被 squatted，直接用原生 |
| 地圖 tile | **Carto Dark Matter**（`basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`） | 零 API key，vector tiles，中文地名 |
| Geocoding | **Nominatim 公開 API** | 1 req/s 限速，專題規模夠用 |
| Routing | **OSRM 公開 server**（router.project-osrm.org） | FOSSGIS 維運，免費、無 key |
| POI 搜尋 | Overpass API | 用於「附近 X」查詢 |
| Worker → Frontend 通訊 | **LiveKit data channel** | 既有連線，零新基建 |
| GPS 取得 | **瀏覽器 Geolocation API** → data channel → worker | 不走 DB，連線後自動推送 |

**已排除**：mapcn（npm squatted）、Mapbox（需 key + 付費）、Admin location picker（改用 GPS data channel）

---

## 任務清單

### P6.5-01：MapLibre GL JS 整合

- [x] **安裝**：`pnpm --filter playground add maplibre-gl`
- [x] **檔**：`web/apps/playground/src/components/map-view.tsx`
  - `forwardRef<MapHandle>` with `focusOn / drawRoute / showStops / clearOverlays`
  - Carto Dark Matter style（向量圖磚，中文地名）
  - `map.on("load")` → 對所有 symbol layer 套 `name:zh-Hant → name:zh → name` fallback
- [x] **動態 import + `ssr: false`**（MapLibre 不支援 SSR）
- [x] **Commit**：`feat(playground): add MapLibre GL map component with Carto Dark Matter tiles`

---

### P6.5-02：Session.currentLocation schema

- [x] **檔**：`web/packages/db/prisma/schema.prisma`
- [x] **加欄位**：`Session.currentLocation Json?`
- [x] **Migration**：`20260518125336_add_session_location`
- [x] **Worker 同步**：`worker/worker/db/models.py` 對應 `currentLocation` Mapped 欄位
- [x] **Commit**：`feat(db): add session current location field`

---

### P6.5-03：GPS 位置取得（改版）

> 原設計為 Admin location picker；實際改為瀏覽器 GPS → data channel → worker

- [x] **Playground**：`navigator.geolocation.getCurrentPosition({ enableHighAccuracy: true })`
  - 連線後自動推 `{ type: "client.location", lat, lng }` via data channel（topic: "map"）
- [x] **Worker**：`main.py` 的 `@ctx.room.on("data_received")` 解析後呼叫 `set_client_location()`
- [x] **`data_channel.py`**：`get_client_location()` / `set_client_location()` module-level store
- [x] **`geo.poi_nearby`**：location 未提供時 fallback 到 `get_client_location()`

---

### P6.5-04：Worker geo tools

- [x] **檔**：`worker/worker/tools/geo.py`
- [x] **四支 tool**：

  | name | 說明 |
  |------|------|
  | `geo.get_location` | 讀 GPS + Nominatim reverse geocode，回傳地名 |
  | `geo.geocode` | 地名 → 座標，in-memory cache |
  | `geo.route` | OSRM 路線查詢，含 GeoJSON geometry |
  | `geo.poi_nearby` | Overpass POI 查詢，fallback 用 GPS |

- [x] User-Agent / 8s timeout / 失敗回「地圖資料這馬提無著」
- [x] `geo.route` / `geo.poi_nearby` 執行後推 map data channel
- [x] **Commit**：`feat(worker): implement geo tools (get_location, geocode, route, poi_nearby)`

---

### P6.5-05：Worker → Frontend 即時推送

- [x] **檔**：`worker/worker/session/data_channel.py`
  - `set_participant()` / `publish_map_event()` / `publish_conv_event()`
  - `set_client_location()` / `get_client_location()`
- [x] **main.py**：`set_participant(ctx.room.local_participant)` + `on_data_received` handler
- [x] **Map payloads**（topic: "map"）：`bus.route_stops` / `map.route` / `map.poi` / `map.focus`
- [x] **Conv payloads**（topic: "conv"）：`conv.user` / `conv.agent_chunk` / `conv.agent_done`
  - runner.py：ASR done → `conv.user`；`_launch()` → `conv.agent_chunk`；turn_done → `conv.agent_done`
- [x] **Frontend**：`MapPanel` 處理 map topic；`SplitLayout` 處理 conv topic（含打字機效果）
- [x] **Commit**：`feat(worker,playground): bridge tool results to map/conv via livekit data channel`

---

### P6.5-06：LLM intent 觸發

- [x] **檔**：`worker/worker/session/components.py`
- [x] **加 geo system prompt 片段**（`_GEO_SYSTEM_PROMPT_FRAGMENT`）：
  - `geo.get_location`：「你知道我在哪」/ 「我佇佗位」
  - `geo.geocode`：「X 在哪裡」
  - `geo.route`：「從 X 到 Y 多遠 / 怎麼開車去」
  - `geo.poi_nearby`：「附近的 X」/ GPS 已知不用問位置
- [x] **Commit**：`feat(worker): add geo tools to system prompt`

---

## 已知 Gotcha

- **mapcn npm squatted**：`mapcn@0.0.1` 是佔名包，直接用 MapLibre GL JS 原生
- **MapLibre SSR 爆**：`dynamic(() => import(...), { ssr: false })` 必加
- **Carto style 中文地名**：需在 `map.on("load")` 後對 symbol layers 套 `name:zh-Hant → name:zh → name` coalesce
- **Nominatim User-Agent 強制**：缺 UA 直接被擋 403
- **OSRM geometry**：需 `geometries=geojson&overview=simplified`，回傳 `coordinates: [lng, lat][]`（注意 lng/lat 順序）
- **Overpass timeout**：加 `[timeout:5]` 強制 5s 內回應
- **useVoiceAssistant().state 永遠 "connecting"**：worker 用 raw rtc SDK，不符合 livekit-agents state machine，改從 data channel events 派生 UI state
- **GPS data channel timing**：`useConnectionState()` 而非 `room.state` 做 reactive dependency

---

## Phase 6.5 完成標準

**核心**
- [x] Playground 對話：「我想從斗六火車站到北港」→ 地圖即時畫出路線，LLM 用台語講距離 / 時間
- [x] 對話：「Y02 經過哪些站」→ 觸發 `bus.list_stops`，地圖標記全部停靠站
- [x] 對話：「附近有什麼小吃」→ 用 GPS 查 POI，地圖標記，LLM 念前 3 名
- [x] 對話：「你知影我佇佗位」→ `geo.get_location` 回傳地名
- [x] Tool 失敗 → 不 crash，LLM 講「地圖提無著」
- [ ] Admin 可在 session 詳情頁點地圖更新 `currentLocation`（改為 GPS 方案，此項跳過）

**延伸（選做）**
- [ ] AgentProfile.defaultLocation fallback
- [ ] 路線顯示交通方式切換（駕車 / 步行 / 騎車）
- [ ] POI 點擊 → 自動帶入下一輪對話
- [ ] 公車路線多色 polyline（不同路線不同顏色）

---

## Phase 編號全景

```
Phase 6   : RAG（純文字 / 知識庫）
Phase 6.4 : Function calling + 雲林客運資料底層  ✅
Phase 6.5 : 地圖整合（本檔）                    ✅
Phase 7   : 打磨與文件
Phase 8   : OTP + GTFS 路線查詢引擎
```
