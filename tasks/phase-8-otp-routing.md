# Phase 8：OTP + GTFS 路線查詢引擎遷移

> **前置**：Phase 6.4（bus tools）完成、TDX 帳號取得（或 GTFS 靜態 zip 已下載）
>
> **交付物**：
> - OpenTripPlanner 以 Docker 在本機跑通
> - `bus.find_routes` 改走 OTP API（時刻表相依轉乘）
> - `bus.list_stops` / `bus.next_departures` 改走 OTP stoptimes
> - `bus.search_stops` / `tdx.bus_arrival` 保留不動
>
> **動機**：現有自刻 SQL transfer 演算法只看站序，不判斷能否趕上連接班次；
> OTP 做時刻表相依最短路徑，支援多次轉乘、走路換乘、行程排序。

---

## 現況盤點

**已存在（可保留）**
- `worker/tools/bus.py`：`SearchStopsTool`（ILIKE 中文搜尋保留）、`tdx_realtime.py`（即時到站保留）
- PostgreSQL：`BusStop`、`BusRoute` 表（站名搜尋繼續用）
- `worker/scripts/import_bus.py`：改成只匯入 BusStop / BusRoute，BusSchedule / RouteStop 可廢棄
- Docker 已安裝

**要換掉**
- `_find_routes` + `_find_transfer_routes`（自刻 SQL transfer）→ OTP plan API
- `_list_stops`（自刻 JOIN 查詢）→ OTP stoptimes API
- `_next_departures`（bitmask 班表查詢）→ OTP stoptimes API
- `BusSchedule` / `RouteStop` Prisma model（可移除或廢棄）

**前置條件確認**
- [ ] TDX 帳號取得，或雲林縣 GTFS zip 已手動下載
- [ ] 機器 RAM ≥ 2GB 可給 OTP（全台灣 GTFS + OSM 約需 1.5-2GB；只用雲林 ~512MB）
- [ ] Docker Desktop 正在執行

---

## GTFS 資料說明

TDX GTFS endpoint（需 Bearer token）：
```
https://tdx.transportdata.tw/api/advanced/v2/Bus/GTFS/City/YunlinCounty
```

手動下載替代方案：TDX 官網 → 進階資料 → 公車 GTFS → 雲林縣 → 下載 zip

GTFS zip 內含標準檔案：`routes.txt`、`stops.txt`、`trips.txt`、`stop_times.txt`、`calendar.txt`

---

## 架構說明

```
before:  TDX JSON → import_bus.py → PostgreSQL → 自刻 SQL → 工具回傳
after:   GTFS zip + OSM pbf → OTP build graph → OTP REST API → 工具回傳
                                                              ↑
                               BusStop / BusRoute（PostgreSQL 保留，做站名搜尋）
```

OTP Plan API 回傳範例（格式化後給 LLM）：
```
路線 1（1 次轉乘，80 分鐘）：
  搭 7124，09:10 斗六火車站 → 09:40 虎尾
  轉 7701，09:55 虎尾 → 10:30 麥寮
```

---

## 任務清單

### P8-01：OTP 環境建立

- [ ] **取得 OSM 資料**
  - 下載雲林縣範圍：`https://download.geofabrik.de/asia/taiwan-latest.osm.pbf`（全台 ~230MB）
  - 或用 osmium 裁切雲林縣範圍（約 10MB，build 更快）：
    ```bash
    osmium extract -b 120.0,23.3,120.7,23.9 taiwan-latest.osm.pbf -o yunlin.osm.pbf
    ```
  - 放入 `otp-data/` 目錄

- [ ] **取得 GTFS 資料**
  - 下載雲林縣 GTFS zip（TDX API 或手動）
  - 放入 `otp-data/` 目錄，重命名為 `yunlin-gtfs.zip`

- [ ] **建立 `otp-data/otp-config.json`**（可空 `{}`，控制快取等選項）

- [ ] **docker-compose.yml 加入 OTP service**
  ```yaml
  otp:
    image: docker.io/opentripplanner/opentripplanner:2.5.0
    volumes:
      - ./otp-data:/var/opentripplanner
    ports:
      - "8080:8080"
    command: ["--load", "--serve"]
    restart: unless-stopped
    mem_limit: 2g
  ```

- [ ] **Build OTP graph（一次性）**
  ```bash
  docker run --rm -v ./otp-data:/var/opentripplanner \
    opentripplanner/opentripplanner:2.5.0 --build --save
  # 預期 2-5 分鐘，產出 graph.obj
  ```

- [ ] **驗收**：
  - `docker compose up otp`
  - `curl "http://localhost:8080/otp/routers/default"` → 200 OK
  - 瀏覽器開 `http://localhost:8080` → OTP debug UI 出現地圖

- [ ] **加入 `.env`**：`OTP_URL=http://localhost:8080`

- [ ] **Commit**：`feat(infra): add OpenTripPlanner docker service`

---

### P8-02：OTP Python Client

- [ ] **檔**：`worker/worker/tools/otp_client.py`
- [ ] **功能**：
  ```python
  async def plan(
      from_lat: float, from_lng: float,
      to_lat: float, to_lng: float,
      depart_at: datetime | None = None,   # None = now
      num_itineraries: int = 3,
      max_walk_distance: int = 500,        # 公尺
  ) -> list[dict]:
      """
      呼叫 OTP /otp/routers/default/plan
      回傳 list of itinerary dict（已解析，非原始 JSON）
      """

  async def stoptimes(
      stop_gtfs_id: str,
      num_departures: int = 5,
  ) -> list[dict]:
      """
      呼叫 OTP /otp/routers/default/index/stops/{id}/stoptimes
      回傳接下來幾班的 {route, headsign, departure_time}
      """
  ```
- [ ] **錯誤處理**：OTP 8s timeout、連線失敗 → raise 讓呼叫端統一處理
- [ ] **測試**：`respx` mock OTP 端點，測 itinerary 解析格式
- [ ] **Commit**：`feat(worker): add OTP REST client`

---

### P8-03：stop_id 對照表

OTP 使用 GTFS `stop_id` 識別站點，DB 存的是 TDX `StopUID`（`YUN298841` 形式）。
TDX GTFS 的 `stops.txt` 內 `stop_id` 欄位即為 `StopUID`，兩者一致，**不需要額外對照表**。

- [ ] **確認**：解壓 GTFS zip，檢查 `stops.txt` 的 `stop_id` 是否與 `BusStop.uid` 相符
  ```bash
  head -3 yunlin-gtfs/stops.txt
  # stop_id 應為 YUN298841 形式
  ```
- [ ] 若格式不同 → 在 `BusStop` 加 `gtfsStopId` 欄位 + migration（選做）
- [ ] **Commit**（若需要 migration）：`feat(db): add gtfsStopId to BusStop`

---

### P8-04：改寫 `bus.find_routes`

- [ ] **檔**：`worker/worker/tools/bus.py`
- [ ] **新流程**：
  1. `_search_stops()` 取 from / to 的 `lat`、`lng`（已有）
  2. 呼叫 `otp_client.plan(from_lat, from_lng, to_lat, to_lng)`
  3. 格式化 itineraries 為自然語言：
     ```
     路線 1（直達，45 分鐘）：
       搭 7124，09:10 斗六火車站 → 09:55 虎尾分局
     
     路線 2（1 次轉乘，80 分鐘）：
       搭 7124，09:10 斗六火車站 → 09:40 虎尾
       轉 7701，09:55 虎尾 → 10:30 麥寮
     ```
  4. 工具失敗 → 回「路線資料這馬提無著」
- [ ] **移除**：`max_transfers` 參數（OTP 自動處理）、`_find_routes`、`_find_transfer_routes`
- [ ] **Commit**：`feat(worker): route bus.find_routes through OTP plan API`

---

### P8-05：改寫 `bus.list_stops`

- [ ] **新流程**：
  1. 從 DB 搜路線名稱 → 取得 GTFS route_id（即 BusRoute.uid）
  2. 呼叫 OTP `/otp/routers/default/index/routes/{route_id}/stops`
  3. 依 sequence 排序回傳
- [ ] **Commit**：`feat(worker): route bus.list_stops through OTP stops API`

---

### P8-06：改寫 `bus.next_departures`

- [ ] **新流程**：
  1. `_search_stops()` 取 stop uid（即 GTFS stop_id）
  2. 呼叫 `otp_client.stoptimes(stop_uid, num_departures=limit)`
  3. 若有指定路線 → 過濾結果
  4. 格式化：`Y02 09:10、Y02 10:30、Y02 13:00`
- [ ] **Commit**：`feat(worker): route bus.next_departures through OTP stoptimes API`

---

### P8-07：清理舊程式碼

- [ ] **移除**：
  - `_find_routes`、`_find_transfer_routes`、`_list_stops`、`_next_departures`（DB 版）
  - `BusSchedule`、`RouteStop` Prisma model（可先加 `// deprecated` 留著不刪，或直接刪 + migration）
  - `import_bus.py` 移除 schedule / stop_of_route 匯入邏輯（保留 operator / route / stop）
- [ ] **選做**：`BusSchedule`、`RouteStop` 表 drop migration
- [ ] **Commit**：`chore(worker): remove legacy SQL bus routing logic`

---

### P8-08：資料更新流程

- [ ] **文件**：在 `docs/ops/update-gtfs.md` 記錄更新步驟：
  ```bash
  # 1. 下載新 GTFS
  curl -H "Authorization: Bearer $TDX_TOKEN" \
    https://tdx.transportdata.tw/.../GTFS/City/YunlinCounty \
    -o otp-data/yunlin-gtfs.zip

  # 2. Rebuild graph
  docker compose stop otp
  docker run --rm -v ./otp-data:/var/opentripplanner \
    opentripplanner/opentripplanner:2.5.0 --build --save
  docker compose start otp
  ```
- [ ] **選做**：加 cron script 自動化（TDX GTFS 約每週更新）
- [ ] **Commit**：`docs(ops): add GTFS update runbook`

---

## 已知 Gotcha

- **OTP 2.x API 路徑**：v2 改用 GraphQL（`/otp/gtfs/v1`），REST plan API 仍在 v2 支援但路徑不同，確認版本再寫 URL
- **OSM + GTFS 版本對齊**：OSM 資料日期與 GTFS 差太多可能造成步行路段錯誤（demo 規模影響不大）
- **OTP graph build 記憶體**：預設 1GB，全台 GTFS 需要 `-Xmx2g`，docker-compose `mem_limit: 2g`
- **GTFS stop_id 格式**：確認 TDX GTFS 的 `stop_id` 是否含 prefix（如 `TW:YUN298841`），要對齊 DB uid
- **出發時間**：OTP plan 需要出發時間（`time` + `date`），預設用「現在」；`bus.next_departures` 要傳正確台灣本地時間
- **OTP warmup**：graph load 後前幾秒可能 503，client 要有 retry

---

## Phase 8 完成標準

**核心**
- [ ] `docker compose up` → OTP 正常啟動，debug UI 可見雲林地圖
- [ ] 問「從斗六火車站到虎尾分局怎麼搭」→ OTP 回有時刻的班次，含換乘時間
- [ ] 問「7124 幾點到斗六火車站」→ OTP stoptimes 回正確時刻
- [ ] 問「7124 經過哪些站」→ OTP routes/stops 回正確序列
- [ ] OTP 掛掉 → tool 回錯誤字串，不 crash worker

**延伸（選做）**
- [ ] GTFS-RT（即時更新）接入 OTP → `tdx.bus_arrival` 升級成 OTP 即時查詢
- [ ] `BusSchedule` / `RouteStop` 表 drop migration（清理 DB）
- [ ] cron 自動更新 GTFS

---

## 時程壓力時的取捨

- **最低限**：P8-01 + P8-02 + P8-04（只換 `find_routes`）→ 轉乘品質提升，其他工具暫時保留 DB 版
- **加碼**：P8-05 + P8-06（全部換掉）
- **全砍**：保留現有 DB 版，將「轉乘不考慮時刻」標記為已知限制

---

## Phase 編號全景

```
Phase 6   : RAG
Phase 6.4 : Function calling + 雲林客運資料底層  ✅
Phase 6.5 : 地圖整合（未開始）
Phase 7   : 打磨與文件
Phase 8   : OTP + GTFS 路線查詢引擎（本檔）
```
