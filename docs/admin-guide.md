# Admin 使用手冊

這份文件說明 Taigi Flow 管理後台的日常使用方式。Admin 主要用來管理 Role、RAG 知識庫、發音字典、對話日誌與即時監控。

## 進入後台

本機啟動後進入：

```bash
http://localhost:3001
```

建議用專案腳本啟動完整環境：

```bash
./dev.sh
```

正式展示模式：

```bash
./prod.sh
```

Admin 依賴 PostgreSQL。RAG 的檢索測試還需要 RAG retrieval service，預設位址是：

```bash
RAG_RETRIEVAL_URL=http://127.0.0.1:8765
```

目前 Admin 沒有內建登入與權限控管；正式部署時應放在可信任網路、VPN 或反向代理的認證後面。

## 側邊欄功能

| 頁面 | 路徑 | 用途 |
|---|---|---|
| Role | `/agents` | 建立、編輯、啟用 Agent 人格 |
| RAG | `/knowledge` | 管理每個 Role 的知識庫 |
| 發音字典 | `/dictionary` | 維護全域與 Role 專屬的發音替換 |
| 對話日誌 | `/sessions` | 查詢歷史 session 與逐輪文字轉換 |
| 即時監控 | `/monitor` | 觀察目前對話、延遲與錯誤率 |

## 建議操作流程

1. 到 `Role` 建立或選擇要使用的 Agent。
2. 編輯 Role 的系統提示詞、語音設定、工具清單與 RAG 設定。
3. 如果該 Role 需要文件知識，到 `RAG` 上傳文件並等待 ingest 完成。
4. 到 Playground 進行對話測試。
5. 到 `對話日誌` 檢查 ASR、LLM、HanLo、Taibun 的逐輪結果。
6. 發現發音錯誤時，從對話日誌加入發音字典，或直接到 `發音字典` 編輯。
7. 展示或壓測時，到 `即時監控` 看 active session、延遲與錯誤。

## Role

Role 是 Agent 的人格設定。系統同一時間只會啟用一個 Role，新連線會套用目前啟用中的 Role。

### Role 列表

在 `/agents` 可以：

- 查看所有 Role。
- 點擊 Role 進入編輯頁。
- 點擊圓形啟用按鈕切換目前使用中的 Role。
- 點擊書本圖示進入該 Role 的 RAG 知識庫。
- 刪除不再使用的 Role。

### 新增或編輯 Role

Role 表單包含：

| 欄位 | 說明 |
|---|---|
| 名稱 | Role 顯示名稱，必填 |
| 說明 | 簡短用途描述 |
| 系統提示詞 | LLM 的主要行為設定，必填 |
| Piper 模型 | TTS 使用的語音模型名稱 |
| 速度 | TTS 語速，常用值約 `0.5` 到 `2` |
| 音調 | TTS pitch，常用值約 `-10` 到 `10` |
| RAG 啟用 | 是否讓對話自動檢索此 Role 的知識庫 |
| Top-K | 每次檢索最多取回幾個 chunk |
| 相似度門檻 | 低於此分數的 chunk 不會被採用 |
| 工具 | 逗號分隔的工具名稱 |
| 啟用此人格 | 儲存後是否作為目前使用中的 Role |

RAG 的 collection ID 會使用 Role ID。建立新 Role 時還沒有 ID，所以 RAG 文件上傳要在 Role 建立後進行。

## RAG

每個 Role 對應一個 RAG 知識庫，collection ID 等於 Role ID。

### RAG 列表

在 `/knowledge` 可以看到所有 Role 的 RAG 狀態：

- chunk 數量。
- RAG 是否啟用。
- 點擊列進入該 Role 的知識庫。
- 點擊清空按鈕刪除該 Role 的所有 RAG 內容。

### RAG 設定

進入 `/knowledge/:collectionId` 後，頁面上方會顯示：

- 文件數。
- chunk 數。
- ingest 失敗文件數。
- Top-K 與 threshold。
- RAG 是否啟用。
- collection ID 是否與 Role 設定一致。

如果 RAG 停用，即使已上傳文件，正式對話也不會使用這些內容。要啟用請回到該 Role 的編輯頁。

### 上傳文件

支援格式：

| 格式 | 說明 |
|---|---|
| PDF | 適合一般文件 |
| Markdown | 適合結構化文字文件 |
| TXT | 適合純文字 |
| DOCX | 適合 Word 文件 |

限制：

- 單檔最大 `20 MB`。
- 上傳後會建立 ingest job。
- Worker 會處理切 chunk、embedding 與寫入 pgvector。
- 處理中頁面會自動刷新狀態。

RAG 適合放自然語言知識，例如服務說明、FAQ、政策、腳本、長篇背景資料。不適合放需要精確查詢或高時效性的資料，例如即時公車到站、庫存、價格、班表。

### 文件與 chunk 管理

在文件庫可以：

- 查看每份文件的 ingest 狀態。
- 展開已完成的文件查看 chunks。
- 刪除整份文件，會一併刪除該文件的 chunks 與上傳檔案。
- 刪除單一 chunk，頁面會自動刷新。
- 如果某份文件只剩最後一個 chunk，刪掉該 chunk 時文件紀錄與上傳檔案也會一併移除。

一般操作應以「文件」為單位。單一 chunk 刪除主要用於清理錯誤切塊或測試資料。

### 檢索測試

`檢索測試` 分頁可以直接測查詢結果：

1. 輸入使用者可能會問的問題。
2. 設定 Top-K 與 threshold。
3. 執行檢索。
4. 檢查 hit count、top similarity、latency、命中文本與來源。

低於 threshold 的結果會標示為未採用。若查詢失敗，先確認 RAG retrieval service 是否啟動，以及 `RAG_RETRIEVAL_URL` 是否正確。

### 診斷

`診斷` 分頁用來看需要人工處理的資料：

- ingest 中的文件。
- ingest 失敗與錯誤訊息。
- 找不到文件紀錄的孤兒 chunks。
- collection 基本資訊。

如果有孤兒 chunks，可以在診斷分頁依來源展開並清理。

## 發音字典

發音字典用來修正 TTS 前的文字替換。字典分成：

| 類型 | 說明 |
|---|---|
| 全域 | 所有 Role 都會套用 |
| Role 專屬 | 只套用在指定 Role |

在 `/dictionary` 可以：

- 切換全域或特定 Role。
- 搜尋詞彙或替換內容。
- 新增、編輯、刪除條目。
- 匯出 CSV。
- 批次匯入 CSV。

欄位格式：

| 欄位 | 說明 |
|---|---|
| 詞彙 | 要被替換的原始文字 |
| 替換 | 替換後的發音文字或台羅拼音 |
| 優先 | 數字越高越優先 |
| 備註 | 管理用途，不影響輸出 |

CSV 欄位順序：

```csv
term,replacement,priority,note
```

## 對話日誌

對話日誌用來追蹤每次對話的實際處理結果。

### Session 列表

在 `/sessions` 可以：

- 依狀態篩選：所有、進行中、已結束、未正常結束。
- 依 Role 篩選。
- 依時間或輪次排序。
- 點擊 session 進入詳情。
- 勾選多筆後批次刪除。
- 刪除單筆 session。

`未正常結束` 通常代表 Worker 沒有正常寫入結束時間，可能是程序中斷或連線異常。

### Session 詳情

在 `/sessions/:id` 可以看到每輪對話：

| 欄位 | 說明 |
|---|---|
| ASR 辨識 | 使用者語音轉文字結果 |
| LLM 回應 | 模型原始回應 |
| HanLo 文字 | 台語漢羅處理後文字 |
| Taibun 注音 | 台羅拼音或注音輸出 |
| 首音 | first audio latency |
| 總計 | 該輪總延遲 |
| 標記 | 打斷、錯誤等狀態 |

可用篩選：

- 只看被打斷的輪次。
- 只看有錯誤的輪次。
- 只看總延遲大於指定毫秒數的輪次。

如果某輪發音需要修正，可以點擊加入字典按鈕，系統會依該 session 的 Role 建立對應字典條目。

## 即時監控

`/monitor` 使用 server-sent events 顯示即時狀態。

主要指標：

| 指標 | 說明 |
|---|---|
| 進行中 Session | 目前尚未結束的 session 數 |
| 首音延遲均值 | 近期 first audio latency 平均值 |
| LLM 首字均值 | 近期 LLM first token 平均值 |
| ASR 均值 | 近期 ASR latency 平均值 |
| 錯誤率 | 最近 100 輪的錯誤比例 |

下方對話串流會顯示即時 ASR、Agent 回應、延遲、打斷與錯誤。可展開查看台羅拼音。

## 常見狀況

### Admin 打不開

檢查：

- `./dev.sh` 或 `./prod.sh` 是否正在跑。
- Admin 是否在 `http://localhost:3001`。
- PostgreSQL 是否已啟動。
- migrations 是否已套用。

### Role 儲存失敗

檢查：

- 名稱是否與既有 Role 重複。
- 系統提示詞是否為空。
- RAG threshold 是否在 `0` 到 `1` 之間。
- Top-K 是否為合理整數。

### RAG 上傳後一直處理中

檢查：

- Worker 是否啟動。
- PostgreSQL 是否可連線。
- embedding model 是否可用。
- ingest job 是否有錯誤訊息。

### 檢索測試失敗

檢查：

- RAG retrieval service 是否啟動。
- `RAG_RETRIEVAL_URL` 是否指向正確位置。
- 該 Role 是否已有完成 ingest 的 chunks。
- query、Top-K、threshold 是否符合限制。

### 對話沒有吃到 RAG

檢查：

- Role 編輯頁是否已啟用 RAG。
- RAG 頁面 collection ID 是否與 Role ID 一致。
- 文件是否已 ingest 完成。
- 檢索測試是否能命中內容。
- threshold 是否設太高。

### 發音字典沒有生效

檢查：

- 條目是否放在正確分頁，全域或指定 Role。
- 詞彙是否與實際 HanLo/輸出前文字一致。
- 優先權是否被其他條目覆蓋。
- 是否已開始新的對話輪次。

## 日常檢查清單

展示或測試前建議確認：

- `Role` 頁面只有預期的 Role 處於啟用狀態。
- 該 Role 的 system prompt、TTS 速度與 pitch 正確。
- 若需要 RAG，該 Role 的 RAG 已啟用且文件 ingest 完成。
- `檢索測試` 能查到預期內容。
- `發音字典` 已包含常見專有名詞。
- `即時監控` 顯示串流連線中。
- Playground 能正常連線並收到語音回應。
