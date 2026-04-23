<!--
本文件是完整系統設計文件，長度較長（~1100 行）。

⚠️  對 AI 助手的提醒：
- 不要一開始就把整份讀進 context
- 只在當前 task 明確引用時查閱對應章節
- 若內容與 tasks/ 衝突，以 tasks/ 為準
- 本文件由人類維護，請勿自行修改

對人類讀者：這是設計理由與技術細節的完整記錄，作為書面報告與 review 依據。
-->

# 系統實作計畫：基於 LiveKit 與台語語音處理鏈之即時 Agent 系統

> **文件目的**：本文件作為專題的書面規劃、技術藍圖與團隊協作依據，涵蓋系統架構、資料設計、核心演算法、部署策略與分階段實作路線。

---

## 0. 專案概觀

### 0.1 系統目標

打造一個以台語（台灣閩南語）為互動語言的即時語音 Agent 系統，具備擬真人對話的打斷能力（Barge-in）、極低的首次音訊延遲（FTTA, First-Time-To-Audio），以及可熱更新的人格與發音字典管理。

### 0.2 設計原則

1. **低延遲優先**：所有決策以降低感知延遲為最高優先，採用 Chunk-based 串流處理。
2. **職責分離與可抽換**：ASR / LLM / Text Normalization / TTS / Transport 各自獨立，透過抽象介面隔離，便於替換、測試與 A/B 比較。
3. **可觀測性**：每次對話可追溯文字轉換鏈，支援「羅馬字拼錯」的事後修正。
4. **專題導向的務實取捨**：不處理多租戶、跨 session 記憶、水平擴展等生產級議題；但保留未來擴充的介面。

### 0.3 技術選型總覽

| 層級 | 技術 | 理由 |
|------|------|------|
| 即時通訊 | LiveKit (WebRTC) | 成熟的開源方案，支援原生 AEC、VAD、Opus 編解碼 |
| Agent 框架 | Python 3.11 + `livekit-agents` | 官方 SDK，原生支援串流管線與 Worker 模式 |
| 套件管理 | `uv` | 比 pip/poetry 快數十倍，部署時間顯著下降 |
| 資料庫 | PostgreSQL + pgvector | 關聯資料與向量檢索共用單一資料庫 |
| ORM | Prisma (Node) + SQLAlchemy (Python) | 前後端分別用各自生態最成熟的方案 |
| VAD | Silero VAD | 輕量、準確、業界通用 |
| ASR | Qwen3-ASR / Breeze-ASR-26 (可抽換) | 兩者皆原生支援台語；架構設計上允許 A/B 比較後再鎖定 |
| LLM | OpenAI 相容介面 | 統一介面，方便未來替換本地/商用模型 |
| TTS | 自訓 Piper 台語模型 | 已完成微調，品質與延遲符合需求 |
| 文字處理 | HanloFlow + Taibun | 繁中→漢羅→台羅的標準轉換鏈 |
| 前端 | Next.js (Monorepo) | 符合現有技術棧 |

---

## 1. 系統架構總覽

### 1.1 高階架構

```
┌────────────────┐      WebRTC       ┌──────────────────────────────┐
│  Browser       │◄─────────────────►│  LiveKit Server              │
│  (Next.js)     │   Audio + Data    │  (Room + Signaling + AEC)    │
└────────────────┘                   └──────────────┬───────────────┘
                                                    │
                                                    │ Audio Stream
                                                    ▼
                                     ┌──────────────────────────────┐
                                     │  Agent Worker (Python)       │
                                     │                              │
                                     │  ┌────────────────────────┐  │
                                     │  │ Voice Controller       │  │
                                     │  │ (VAD + Barge-in FSM)   │  │
                                     │  └────┬─────────────┬─────┘  │
                                     │       │             │        │
                                     │       ▼             ▲        │
                                     │  ┌─────────┐   ┌────────┐    │
                                     │  │ ASR     │   │ Piper  │    │
                                     │  │ Whisper │   │ TTS    │    │
                                     │  └────┬────┘   └───▲────┘    │
                                     │       │            │         │
                                     │       ▼            │         │
                                     │  ┌─────────────────────────┐ │
                                     │  │ LLM + Memory Manager    │ │
                                     │  │ (Sliding Window)        │ │
                                     │  └────┬────────────────────┘ │
                                     │       │                      │
                                     │       ▼                      │
                                     │  ┌─────────────────────────┐ │
                                     │  │ Smart Splitter          │ │
                                     │  │ → HanloFlow → Taibun    │ │
                                     │  └─────────────────────────┘ │
                                     └──────────────┬───────────────┘
                                                    │
                       ┌────────────────┬───────────┴────────────┐
                       ▼                ▼                        ▼
              ┌────────────────┐ ┌──────────────┐     ┌─────────────────┐
              │ PostgreSQL     │ │  Redis       │     │ External Tools  │
              │ + pgvector     │ │  (狀態/佇列) │     │ (TDX, 等)       │
              └────────────────┘ └──────────────┘     └─────────────────┘
```

### 1.2 資料流轉（單一對話回合）

```
[使用者說話]
   │
   ├─► LiveKit client AEC (抑制本機回音)
   ├─► WebRTC 上行
   ├─► LiveKit server 轉發
   ├─► Agent Worker 接收 PCM frames
   │
   ├─► Silero VAD 偵測語音起點 → 觸發 ASR
   ├─► Whisper-style ASR 串流辨識 → 輸出 partial text
   ├─► VAD 偵測語音終點 → 送出 final text
   │
   ├─► Memory Manager 組裝上下文（系統提示 + 滑動視窗）
   ├─► LLM 串流生成 → 逐 token 吐出
   │
   ├─► Smart Splitter 累積成合理短句
   ├─► HanloFlow 正規化 → Taibun 轉羅馬字
   ├─► Piper 生成音訊 chunk
   │
   ├─► WebRTC 下行 → LiveKit server → client
   └─► [使用者聽到]
```

---

## 2. 資料庫設計（PostgreSQL + pgvector）

### 2.1 設計哲學

* **業務設定進 DB，基礎設施留 env**
  * DB 中存放：Agent 人格、系統提示、工具開關、自訂字典、對話日誌
  * env 中保留：`DATABASE_URL`、`LIVEKIT_API_KEY`、LLM API Key、外部 API 金鑰
* **單一資料庫解決關聯與向量需求**：pgvector 足以應付專題規模的 RAG，不引入額外的 Qdrant/Weaviate。

### 2.2 核心 Schema (Prisma)

```prisma
// ============ Agent 人格管理 ============
model AgentProfile {
  id           String   @id @default(uuid())
  name         String   @unique          // "公車站長"
  description  String?                    // 前台顯示用描述
  systemPrompt String   @db.Text          // 系統提示詞
  voiceConfig  Json                       // { piperModel, speed, pitch }
  ragConfig    Json?                      // { enabled, topK, threshold, collectionId }
  tools        Json                       // ["tdx.bus_arrival", "tdx.bus_route"]
  isActive     Boolean  @default(true)
  createdAt    DateTime @default(now())
  updatedAt    DateTime @updatedAt

  sessions     Session[]
}

// ============ 單一對話 Session ============
model Session {
  id             String   @id @default(uuid())
  agentProfileId String
  agentProfile   AgentProfile @relation(fields: [agentProfileId], references: [id])
  livekitRoom    String   // LiveKit Room 名稱
  startedAt      DateTime @default(now())
  endedAt        DateTime?

  logs           InteractionLog[]

  @@index([livekitRoom])
}

// ============ 對話日誌 (除錯與字典修正核心) ============
model InteractionLog {
  id             String   @id @default(uuid())
  sessionId      String
  session        Session  @relation(fields: [sessionId], references: [id])
  turnIndex      Int      // 本次 session 中的第幾輪

  userAsrText    String   @db.Text         // ASR 辨識結果
  llmRawText     String   @db.Text         // LLM 輸出原文 (繁中)
  hanloText      String?  @db.Text         // HanloFlow 輸出 (漢羅)
  taibunText     String   @db.Text         // Taibun 輸出 (羅馬字) ★除錯關鍵

  // 延遲觀測 (ms)
  latencyAsrEnd      Int?  // 使用者說完到 ASR final
  latencyLlmFirstTok Int?  // ASR final 到 LLM 首 token
  latencyFirstAudio  Int?  // LLM 首 token 到首段 TTS 音訊
  latencyTotal       Int?  // 使用者說完到首段音訊

  wasBargedIn    Boolean  @default(false)  // 本次回應是否被打斷
  errorFlag      String?  // "asr_timeout" / "llm_error" / "tts_fail"

  createdAt      DateTime @default(now())

  @@index([sessionId, turnIndex])
}

// ============ 發音字典 (熱更新) ============
model PronunciationEntry {
  id          String   @id @default(uuid())
  profileId   String?  // null = 全域字典；填入 = 該 Agent 專屬
  term        String   // 繁中詞彙，如 "307"
  replacement String   // 強制替換的羅馬字，如 "saⁿ-khòng-tshit"
  priority    Int      @default(0)  // 優先級，數字大者先匹配
  note        String?  // 備註：為何要改

  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  @@unique([profileId, term])
  @@index([term])
}

// ============ RAG 向量儲存 ============
model KnowledgeChunk {
  id            String                      @id @default(uuid())
  collectionId  String                      // 對應 AgentProfile.ragConfig.collectionId
  content       String                      @db.Text
  metadata      Json                        // { source, page, ... }
  embedding     Unsupported("vector(1536)")? // pgvector

  createdAt     DateTime @default(now())

  @@index([collectionId])
}
```

### 2.3 字典優先級策略

查詢順序（由高到低）：**Agent 專屬字典 → 全域字典 → Taibun 預設轉換**。同一詞條在同層級內以 `priority` 排序。這讓「公車站長」可以把「行」固定轉成 `kiâⁿ`（走），而「唐詩導讀」可以另外定義為 `hîng`（行列）。

---

## 3. Agent Worker 核心架構

### 3.1 模組切分

```
worker/
├── main.py                    # LiveKit Agent 入口（薄層，只做接線）
├── session/
│   ├── components.py          # AgentComponents dataclass + 元件 factory
│   └── runner.py              # PipelineRunner（ASR→LLM→TTS 協調）
├── audio/
│   ├── vad.py                 # SileroVAD 包裝
│   ├── processor.py           # AudioProcessor（VAD 事件消費 + fallback RMS）
│   └── voice_controller.py    # Barge-in 狀態機（Phase 4 實作）
├── pipeline/
│   ├── asr/
│   │   ├── base.py            # BaseASR 抽象介面
│   │   ├── qwen3.py           # Qwen3-ASR 實作
│   │   └── breeze.py          # Breeze-ASR-26 實作
│   ├── llm.py                 # OpenAI 相容客戶端
│   ├── memory.py              # 滑動視窗記憶
│   ├── splitter.py            # Smart Sentence Splitter
│   ├── text_processor.py      # HanloFlow + Taibun + 字典
│   └── tts.py                 # Piper 包裝
├── tools/
│   ├── base.py                # Function Calling 基礎類別
│   └── tdx.py                 # 交通部 TDX
├── db/
│   ├── models.py              # SQLAlchemy 對應 Prisma schema
│   ├── repositories.py        # DB 操作封裝
│   ├── session.py             # AsyncSession factory
│   └── time.py                # UTC 時區工具
└── observability/
    └── metrics.py             # 延遲計時器
```

**分層原則：**
- `session/`：單次對話的狀態與協調（有 state 的物件）
- `audio/`：音訊 I/O 層（VAD、音訊串流處理、Barge-in FSM）
- `pipeline/`：純計算元件，stateless，可獨立測試

### 3.2 Barge-in 狀態機（完整實作）

這是本系統最需要被嚴謹處理的部分。採用顯式的 FSM：

```
                  ┌──────────────┐
                  │  IDLE        │◄─────────────────────────┐
                  └──────┬───────┘                          │
                VAD 起點  │                                  │ 回合結束
                         ▼                                  │
                  ┌──────────────┐                          │
                  │  LISTENING   │                          │
                  │  (ASR 串流)  │                          │
                  └──────┬───────┘                          │
                VAD 終點  │                                  │
                         ▼                                  │
                  ┌──────────────┐                          │
                  │  THINKING    │                          │
                  │  (LLM 生成)  │                          │
                  └──────┬───────┘                          │
                LLM 首句  │                                  │
                         ▼                                  │
                  ┌──────────────┐    VAD 觸發打斷          │
                  │  SPEAKING    ├──────┐                   │
                  │  (TTS 播放)  │      │                   │
                  └──────┬───────┘      ▼                   │
                播放完畢  │        ┌──────────────┐         │
                         │        │ BARGED_IN    │         │
                         │        │ (取消中)     │         │
                         │        └──────┬───────┘         │
                         │        取消完成 │                 │
                         └───────────────┴──────────────────┘
```

**狀態轉換規則**：

| 當前狀態 | 事件 | 動作 | 新狀態 |
|---------|------|------|--------|
| IDLE | VAD 偵測語音（持續 > 300ms） | 啟動 ASR | LISTENING |
| LISTENING | VAD 偵測靜音（持續 > 700ms） | 取得 ASR final，送 LLM | THINKING |
| LISTENING | VAD 再次偵測語音 | 延長 ASR | LISTENING |
| THINKING | LLM 首句完成 | 送入 TTS pipeline | SPEAKING |
| SPEAKING | TTS 播放完畢 | 等待新輸入 | IDLE |
| SPEAKING | **VAD 偵測語音（持續 > 300ms）** | **觸發打斷流程** | BARGED_IN |
| BARGED_IN | 清理完成 | 開始新 ASR | LISTENING |

**打斷時的清理順序（非常重要，順序錯會有殘音）**：

```python
async def on_barge_in(self):
    # 1. 立刻停止向 LiveKit 推送音訊 (最優先，避免殘音)
    self.audio_publisher.pause()

    # 2. 清空 TTS 合成佇列
    self.tts.clear_queue()

    # 3. 取消 LLM 串流請求 (透過 asyncio CancellationToken)
    if self.current_llm_task and not self.current_llm_task.done():
        self.current_llm_task.cancel()

    # 4. 清空 Smart Splitter 累積的半成品文字
    self.splitter.flush()

    # 5. 將本次未完成的 turn 標記為 wasBargedIn=True 寫入 log
    await self.log_turn(barged_in=True)

    # 6. 重置音訊管線緩衝
    self.audio_publisher.reset_buffer()
    self.audio_publisher.resume()
```

### 3.3 AEC（Acoustic Echo Cancellation）策略

分兩道防線，盡可能不讓 Agent 的 TTS 回灌觸發自己的 VAD：

**第一道：Client 端（LiveKit 原生）**

LiveKit Web SDK 預設啟用 WebRTC 的 AEC3。在前端建立本地音軌時明確開啟：

```typescript
const audioTrack = await createLocalAudioTrack({
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
});
```

這能處理「使用者本機喇叭 → 麥克風」的物理回音路徑，絕大多數場景由此層解決。

**第二道：Worker 端的「自說話抑制」**

即使 client AEC 完美，仍可能有殘餘迴響或使用者戴耳機時的藍牙延遲問題。在 Worker 內加入軟性規則：

```python
# 當 state == SPEAKING 且自己剛送出音訊 < 200ms 內
# 對 VAD 的觸發門檻提高（例如從 0.5 → 0.75）
# 或要求連續觸發時間從 300ms → 500ms
def vad_threshold_dynamic(self):
    if self.state == State.SPEAKING:
        time_since_tts = now() - self.last_tts_output_ts
        if time_since_tts < 200:  # ms
            return {"prob": 0.75, "min_duration": 500}
    return {"prob": 0.5, "min_duration": 300}
```

這不是真正的聲學 AEC（需要參考訊號減法），但對專題等級已足夠避免誤觸發。若未來有需要做真正的頻域 AEC，可以引入 `speexdsp` 或 `webrtc-audio-processing` 的 Python binding。

### 3.4 滑動視窗記憶管理

**設計理由**：本系統為單 session、一次對話通常 5–15 分鐘、每輪約 50–150 tokens。以保留 12 輪對話計算，最大上下文約 3000 tokens，遠低於任何現代 LLM 的上下文窗口。**不需要摘要壓縮，記憶體絕對不會爆**。

```python
class SlidingWindowMemory:
    def __init__(self, max_turns: int = 12, system_prompt: str = ""):
        self.max_turns = max_turns
        self.system_prompt = system_prompt
        self.history: list[dict] = []  # [{"role": ..., "content": ...}]

    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        # 保留最近 max_turns * 2 則訊息 (user + assistant 配對)
        if len(self.history) > self.max_turns * 2:
            # 成對丟棄，確保不會出現孤兒 assistant 訊息
            self.history = self.history[-(self.max_turns * 2):]

    def to_messages(self) -> list[dict]:
        return [{"role": "system", "content": self.system_prompt}] + self.history

    def clear(self):
        self.history.clear()
```

**記憶體上限推算**：

* 12 輪對話 × 2 訊息 × 150 tokens × 4 bytes/token（Python 字串近似）= **約 14 KB**
* 即使拉到 50 輪：**約 60 KB**
* 對單一 session 完全不是問題，GC 也能正常回收

**關於「一通對話從頭到尾不爆記憶體」的保證**：

滑動視窗的本質是 **O(1) 空間複雜度**——無論對話進行多久，記憶體使用量永遠不會超過 `max_turns * avg_tokens_per_turn` 的上界。這跟「對話持續時間」完全解耦，是可以數學上保證的上界。

相較之下，摘要壓縮雖然也能控制上界，但每次壓縮都要多呼叫一次 LLM，對專題場景來說是不必要的延遲與成本。**本專案明確採用滑動視窗，不使用摘要**。

---

## 4. 台語語音串流處理鏈

### 4.1 Chunk-based 串流原則

FTTA（First-Time-To-Audio）是決定「擬真感」的關鍵指標。目標：**從使用者說完到 Agent 開口 < 1.2 秒**。達成此目標的核心是「絕不等待完整生成」。

### 4.2 ASR 選型與抽象介面設計

#### 4.2.1 為何保留雙模型選項

本專題評估的兩個台語 ASR 模型特性差異明顯，各有優勢，因此採用「抽象介面 + 可抽換實作」的設計策略，在 Phase 2 整合完成後以實測數據決定正式版本。

| 項目 | Qwen3-ASR (0.6B / 1.7B) | Breeze-ASR-26 |
|------|-------------------------|---------------|
| 基礎架構 | Qwen3-Omni | Whisper-large-v2 微調 |
| 台語支援 | 多語言模型，閩南語為 22 種中文方言之一 | 專攻台語（約 10,000 小時合成語料微調）|
| 輸出形式 | 中文漢字 | 中文漢字（國語映射）|
| 串流推論 | 原生支援（vLLM backend，TTFT 約 92ms） | 需自行實作 chunk 切片 |
| 模型大小 | 0.6B / 1.7B | ~1.5B (Whisper-large-v2) |
| 推論部署 | vLLM / 官方 Docker / transformers | HuggingFace transformers |
| 長音訊處理 | 單次最長 20 分鐘 | 任意長度（pipeline 切片）|
| 適用情境 | 多語言、語言自動偵測、低延遲串流 | 純台語場景、標記準確度高 |

**取捨**：Qwen3-ASR 在「延遲」與「工程成熟度」上佔優（串流是原生能力、TTFT 極低、官方 vLLM 支援），Breeze-ASR-26 在「台語專精度」上佔優（訓練資料幾乎 100% 為台語）。對本系統的即時語音互動場景，**串流能力的價值高於絕對辨識率**，因此預設採用 Qwen3-ASR，Breeze-26 作為 A/B 比較基準。

#### 4.2.2 抽象介面設計

```python
# worker/pipeline/asr/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class ASRPartial:
    """ASR 串流過程中的中間結果"""
    text: str
    is_final: bool
    confidence: float | None = None

class BaseASR(ABC):
    """所有 ASR 實作必須遵循此介面"""

    @abstractmethod
    async def stream(
        self,
        audio_chunks: AsyncIterator[bytes],
    ) -> AsyncIterator[ASRPartial]:
        """接收 PCM 音訊 chunk，產出串流辨識結果。

        Args:
            audio_chunks: 16kHz mono PCM 音訊片段

        Yields:
            ASRPartial: partial 結果持續更新，最後會有一個 is_final=True
        """
        ...

    @abstractmethod
    async def warmup(self) -> None:
        """啟動時預熱模型，避免首次推論延遲"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
```

#### 4.2.3 Qwen3-ASR 實作要點

```python
# worker/pipeline/asr/qwen3.py
from vllm import AsyncLLMEngine, AsyncEngineArgs

class Qwen3ASR(BaseASR):
    def __init__(self, model_path: str = "Qwen/Qwen3-ASR-0.6B"):
        self.engine_args = AsyncEngineArgs(
            model=model_path,
            dtype="bfloat16",
            enforce_eager=False,  # 啟用 CUDA Graph 降低 TTFT
        )
        self.engine = None

    async def warmup(self):
        self.engine = AsyncLLMEngine.from_engine_args(self.engine_args)
        # 跑一次 dummy audio 觸發 kernel 編譯
        await self._dummy_inference()

    async def stream(self, audio_chunks):
        # Qwen3-ASR 原生串流：累積 chunk 到 min_chunk_ms 後送入
        async for partial in self.engine.transcribe_stream(audio_chunks):
            yield ASRPartial(
                text=partial.text,
                is_final=partial.is_final,
                confidence=partial.logprob,
            )

    @property
    def name(self) -> str:
        return "qwen3-asr-0.6b"
```

**設定建議**：
- **0.6B 版本優先**：TTFT 可達 92ms，對即時對話最友善；1.7B 版本準確率略高但延遲倍增，視實測決定是否升級
- **啟用 context biasing**：Qwen3-ASR 支援輸入文字上下文來偏向特定詞彙（例如公車路線名「307」「紅 2」），這對專題場景極有用
  ```python
  await engine.transcribe(audio, context="公車路線: 307, 紅2, 市區公車")
  ```

#### 4.2.4 Breeze-ASR-26 實作要點

```python
# worker/pipeline/asr/breeze.py
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import torch

class BreezeASR26(BaseASR):
    def __init__(self, model_path: str = "MediaTek-Research/Breeze-ASR-26"):
        self.processor = None
        self.model = None
        self.model_path = model_path

    async def warmup(self):
        self.processor = WhisperProcessor.from_pretrained(self.model_path)
        self.model = WhisperForConditionalGeneration.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16,
        ).to("cuda").eval()

    async def stream(self, audio_chunks):
        # Breeze-26 無原生串流，需自行以 VAD endpoint 驅動：
        # 1. 累積音訊直到 VAD 偵測到靜音
        # 2. 整段送入 Whisper pipeline
        # 3. 僅回傳 is_final=True 的結果（沒有 partial）
        buffer = b""
        async for chunk in audio_chunks:
            buffer += chunk
            # VAD 在外層控制；這裡收到 chunk 就累積

        # 實務上由 Voice Controller 呼叫 .transcribe_final(buffer)
        text = await self._transcribe_full(buffer)
        yield ASRPartial(text=text, is_final=True)

    @property
    def name(self) -> str:
        return "breeze-asr-26"
```

**關鍵限制**：Breeze-26 沒有原生串流推論能力，走「等待完整句子再辨識」的模式。這會讓使用者感知延遲比 Qwen3-ASR 高 300–800ms（一整句話講完才開始辨識，而非邊講邊辨識）。這是選型時最大的技術債。

#### 4.2.5 A/B 比較評估計畫

Phase 2 結束時，於 `docs/asr_evaluation.md` 記錄以下比較數據：

| 指標 | 量測方式 |
|------|---------|
| 辨識準確率 (CER) | 錄製 30 段台語測試語音（含常見句、公車路線詢問、數字念法），人工轉譯後比對 |
| 平均 TTFT | 從音訊最後一個 chunk 送出到首個 partial/final 返回 |
| 平均 end-to-end 延遲 | 使用者說完到 ASR final 產出 |
| GPU 記憶體佔用 | nvidia-smi 監測峰值 |
| 誤辨類型分佈 | 同音字 / 數字 / 路線名 / 人名地名 各類型錯誤比例 |

**決策準則**：若兩者 CER 差距 < 5%，選擇 TTFT 較低的（預期為 Qwen3-ASR 0.6B）；若差距 > 10%，選擇 CER 較低者並接受延遲代價。這個評估本身也是專題書面報告的一個有力章節。

#### 4.2.6 設定切換

透過環境變數或 DB `AgentProfile.voiceConfig` 即可切換：

```python
# worker/main.py
asr_name = os.getenv("ASR_BACKEND", "qwen3")
asr: BaseASR = {
    "qwen3": Qwen3ASR,
    "breeze26": BreezeASR26,
}[asr_name]()
await asr.warmup()
```

---

### 4.3 Smart Sentence Splitter

**設計動機**：若 LLM 每吐一個字就送 TTS，語氣支離破碎；若等整句完成才送，首字延遲爆炸。折衷方案是「累積到合理切點再送」。

**切點優先級**：

```python
# 由高到低
STRONG_BREAKS = {"。", "！", "？", "\n"}   # 遇到立刻切
MEDIUM_BREAKS = {"，", "；", "："}         # 累積 >= 6 字才切
WEAK_BREAKS   = {" ", "、"}                # 僅在累積 >= 15 字時切
```

**演算法**：

```python
class SmartSplitter:
    MIN_CHARS_FOR_MEDIUM = 6
    MAX_BUFFER_CHARS = 40  # 超過強制切，避免 LLM 不愛用句號時爆長

    def __init__(self):
        self.buffer = ""

    def feed(self, token: str) -> list[str]:
        """餵入一個 LLM token，回傳可立即合成的完整句子列表。"""
        self.buffer += token
        sentences = []

        while True:
            cut_idx = self._find_cut_point()
            if cut_idx is None:
                break
            sentences.append(self.buffer[:cut_idx + 1])
            self.buffer = self.buffer[cut_idx + 1:]

        return sentences

    def _find_cut_point(self) -> int | None:
        # 1. 強斷點：任何位置
        for i, ch in enumerate(self.buffer):
            if ch in STRONG_BREAKS:
                return i
        # 2. 中斷點：長度 >= 6 才考慮
        if len(self.buffer) >= self.MIN_CHARS_FOR_MEDIUM:
            for i, ch in enumerate(self.buffer):
                if ch in MEDIUM_BREAKS and i >= self.MIN_CHARS_FOR_MEDIUM - 1:
                    return i
        # 3. 強制切：超過最大緩衝
        if len(self.buffer) >= self.MAX_BUFFER_CHARS:
            return self.MAX_BUFFER_CHARS - 1
        return None

    def flush(self) -> str:
        """串流結束或 barge-in 時呼叫，取出剩餘內容。"""
        rest = self.buffer
        self.buffer = ""
        return rest
```

**為何不只用字數門檻**：如前一版回饋所述，台語口語有大量短尾語氣詞（「啊」「喔」「hoⁿ」），純字數門檻會把「好喔。」硬接到下一句。以標點為主、字數為輔的策略能避開這個問題。

### 4.4 文字處理鏈（HanloFlow → 字典替換 → Taibun）

```python
class TextProcessor:
    def __init__(self, profile_id: str, db):
        self.hanlo = HanloFlow()
        self.taibun = Taibun()
        # 啟動時載入字典，避免每次 DB 查詢
        self.dictionary = db.load_dictionary(profile_id)
        # 按 priority 降序 + term 長度降序（長詞優先匹配）
        self.dictionary.sort(key=lambda e: (-e.priority, -len(e.term)))

    def process(self, zh_text: str) -> tuple[str, str]:
        """回傳 (漢羅, 台羅)。"""
        # 1. 字典強制替換（在 Hanlo 之前做，確保優先級）
        protected = self._apply_dictionary(zh_text)
        # 2. HanloFlow 繁中 → 漢羅
        hanlo = self.hanlo.convert(protected)
        # 3. Taibun 漢羅 → 台羅
        taibun_text = self.taibun.to_poj(hanlo)
        return hanlo, taibun_text

    def _apply_dictionary(self, text: str) -> str:
        # 使用特殊標記保護字典命中結果，避免被後續模型改寫
        for entry in self.dictionary:
            text = text.replace(entry.term, f"⟨{entry.replacement}⟩")
        return text
```

### 4.5 資源調度（GPU/CPU 分離）

| 階段 | 裝置 | 原因 |
|------|------|------|
| ASR (Qwen3-ASR / Breeze-26) | GPU | 矩陣運算密集，CPU 會成為瓶頸 |
| LLM | GPU (若本地) / 遠端 API | 同上 |
| Silero VAD | CPU | 模型極小 (~1.5MB)，GPU 轉移成本反而更高 |
| HanloFlow | CPU | 純文字處理，無需 GPU |
| Taibun | CPU | 同上 |
| Piper TTS | CPU | Piper 設計目標即 CPU 推論，品質已驗證 |

GPU 只做 ASR + LLM，CPU 處理 VAD + 文字鏈 + TTS，兩者可管線化並行。

---

## 5. 錯誤處理與降級策略

每個環節都要有「當這一步壞掉時，使用者會聽到什麼」的明確答案。

### 5.1 預錄 Fallback 音訊

在專案啟動時預先生成以下音訊，載入記憶體備用：

```python
FALLBACK_AUDIOS = {
    "asr_timeout": "歹勢，我這馬聽無清楚，你閣講一遍好無？",
    "llm_error":   "袂好勢，我拄才頭殼當機，請你閣問一擺。",
    "tts_fail":    "拄才有小可問題，你閣講一擺。",
    "tool_error":  "抱歉，外部資料這馬提無著，等一下才閣試看覓。",
    "general":     "歹勢，出了一个小問題。",
}
```

### 5.2 各層級超時門檻

| 階段 | 超時 | 超時動作 |
|------|------|---------|
| ASR partial 更新 | 3s 無更新 | 視為 final，送 LLM |
| LLM 首 token | 5s | 中止，播放 `llm_error` |
| LLM 整體生成 | 15s | 中止，以已生成內容結尾 |
| TTS 單一 chunk | 2s | 中止本 chunk，跳下一句 |
| Tool call | 8s | 中止，告訴 LLM「資料取不到」 |

### 5.3 關鍵失敗模式與處理

```python
try:
    async for token in llm.stream(messages):
        ...
except asyncio.TimeoutError:
    await self.play_fallback("llm_error")
    await self.log_turn(error_flag="llm_timeout")
except LLMAPIError as e:
    logger.error(f"LLM error: {e}")
    await self.play_fallback("llm_error")
    await self.log_turn(error_flag="llm_api_error")
except asyncio.CancelledError:
    # barge-in 取消，不需要 fallback，交由 barge-in 流程處理
    raise
```

---

## 6. 觀測性 (Observability)

### 6.1 核心指標

每一輪對話至少記錄四個時間點，寫入 `InteractionLog`：

```
T0: 使用者 VAD 終點            (ASR 開始處理)
T1: ASR final 產出             → latency_asr_end    = T1 - T0
T2: LLM 首 token                → latency_llm_first  = T2 - T1
T3: 首個 TTS audio chunk 送出   → latency_first_audio = T3 - T2
                                → latency_total      = T3 - T0  ★ 關鍵 KPI
```

### 6.2 即時觀察工具

專題階段不必上 Prometheus / Grafana，用 structured logging + 後台頁面即可：

```python
logger.info("turn_completed", extra={
    "session_id": session_id,
    "turn_index": turn_idx,
    "latency_total_ms": total_ms,
    "barged_in": was_barged_in,
})
```

後台提供一個頁面顯示最近 50 筆 `InteractionLog` 的延遲時間，即可快速找出瓶頸。

### 6.3 目標延遲

| 指標 | 目標 | 可接受上限 |
|------|------|-----------|
| `latency_total` | < 1200ms | 2000ms |
| `latency_asr_end` | < 300ms | 600ms |
| `latency_llm_first` | < 500ms | 1000ms |
| `latency_first_audio` | < 400ms | 800ms |

---

## 7. 前端設計 (Next.js Monorepo)

### 7.1 Monorepo 結構

```
web/
├── apps/
│   ├── playground/         # 使用者對話介面
│   └── admin/              # 管理後台
├── packages/
│   ├── ui/                 # 共用元件 (shadcn/ui)
│   ├── api-client/         # 後端 API 封裝
│   ├── types/              # 與 worker 共用的 TS 型別 (zod schema)
│   └── livekit-hooks/      # LiveKit React hook 封裝
└── turbo.json
```

### 7.2 Playground (使用者端)

核心功能：

1. **免設定進入**：訪問頁面 → 後端自動建立 Room + 發 Token → LiveKit 連線建立
2. **雙軌輸入**：麥克風（預設）+ 文字輸入框（備援 / 無法開麥時使用）
3. **視覺回饋**：
   * Audio Visualizer 顯示使用者與 Agent 的音量波形
   * 狀態燈號：傾聽中 / 思考中 / 說話中 / 被打斷
   * 即時顯示 ASR partial（讓使用者知道系統有在聽）
4. **對話記錄面板**：左側顯示繁中對話（參考用，正式互動還是靠聽）

### 7.3 Admin Panel (管理端)

核心頁面：

1. **Agent Profile 管理**
   * CRUD：建立/編輯/停用人格
   * Prompt 編輯器（含即時字數統計）
   * 工具勾選（從 `tools/` 註冊的清單中選）
   * RAG 設定（啟用開關、topK、知識庫 collection）
2. **對話日誌檢視**
   * 依 session 展開 turn 列表
   * 每個 turn 顯示：ASR / LLM / Hanlo / Taibun 四欄對照
   * 可篩選：被打斷的 / 有錯誤的 / 延遲 > 2s 的
3. **發音字典管理** ★ 本系統最核心的營運介面
   * 從對話日誌「一鍵加入字典」：在 Taibun 欄位標示錯誤詞彙 → 跳出新增字典視窗 → 存檔後下次對話生效
   * 全域 / Agent 專屬字典分頁管理
   * 批次匯入/匯出 CSV
4. **知識庫管理**
   * Collection CRUD
   * 文件上傳 → 自動切塊 + embedding → 寫入 `KnowledgeChunk`
5. **即時監控儀表板**
   * 當前 active session 數
   * 最近 100 輪平均延遲
   * 錯誤率（errorFlag 非 null 的比例）

### 7.4 共用 Type 策略

使用 `zod` 定義 schema，前後端共用：

```typescript
// packages/types/src/agent.ts
export const AgentProfileSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1).max(50),
  systemPrompt: z.string().max(10000),
  voiceConfig: z.object({
    piperModel: z.string(),
    speed: z.number().min(0.5).max(2.0),
    pitch: z.number().min(-12).max(12),
  }),
  // ...
});

export type AgentProfile = z.infer<typeof AgentProfileSchema>;
```

Worker 端用 `datamodel-code-generator` 從同一份 JSON Schema 生 Python Pydantic model，確保跨語言一致。

---

## 8. 容器化部署 (Docker Compose)

### 8.1 完整 compose

```yaml
version: '3.8'

services:
  # ========== 資料層 ==========
  postgres:
    image: ankane/pgvector:latest
    restart: unless-stopped
    environment:
      POSTGRES_DB: agent_system
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin -d agent_system"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    # 用途：LiveKit 節點狀態、Worker 待辦 session 佇列

  # ========== 通訊層 ==========
  livekit:
    image: livekit/livekit-server:latest
    restart: unless-stopped
    command: --config /etc/livekit.yaml
    volumes:
      - ./infra/livekit.yaml:/etc/livekit.yaml:ro
    ports:
      - "7880:7880"     # WebSocket (signaling)
      - "7881:7881"     # WebRTC TCP
      - "7882:7882/udp" # WebRTC UDP
    depends_on:
      - redis

  # ========== 應用層 ==========
  web:
    build:
      context: ./web
      target: production
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://admin:${POSTGRES_PASSWORD}@postgres:5432/agent_system
      LIVEKIT_URL: ws://livekit:7880
      LIVEKIT_API_KEY: ${LIVEKIT_API_KEY}
      LIVEKIT_API_SECRET: ${LIVEKIT_API_SECRET}
    ports:
      - "3000:3000"
    depends_on:
      postgres:
        condition: service_healthy

  agent-worker:
    build:
      context: ./worker
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      LIVEKIT_URL: ws://livekit:7880
      LIVEKIT_API_KEY: ${LIVEKIT_API_KEY}
      LIVEKIT_API_SECRET: ${LIVEKIT_API_SECRET}
      DATABASE_URL: postgresql://admin:${POSTGRES_PASSWORD}@postgres:5432/agent_system
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      TDX_CLIENT_ID: ${TDX_CLIENT_ID}
      TDX_CLIENT_SECRET: ${TDX_CLIENT_SECRET}
    depends_on:
      postgres:
        condition: service_healthy
      livekit:
        condition: service_started

  # ========== 反向代理 (開發時可用 ngrok 取代) ==========
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./infra/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data

volumes:
  pgdata:
  caddy_data:
```

### 8.2 開發 vs 生產環境差異

| 項目 | 開發 | 生產 |
|------|------|------|
| HTTPS | ngrok / Cloudflare Tunnel | Caddy 自動簽 Let's Encrypt |
| TURN | 無（限同網段） | 獨立 coturn 容器 |
| DB | compose 內建 | 建議 managed service |
| Log | stdout | Loki / 雲端日誌 |

### 8.3 WebRTC / HTTPS 注意事項

瀏覽器要求必須在 HTTPS 下才能存取麥克風。三種可用方案：

1. **本機開發**：`localhost` 被瀏覽器視為安全來源，可直接用
2. **手機測試 / 遠端 Demo**：`ngrok http 3000` 或 `cloudflared tunnel`
3. **正式部署**：Caddy / Traefik 自動簽證

---

## 9. 分階段實作路線

**核心理念：語音層最後接，前期用純文字迴圈把所有邏輯磨利**。很多團隊一開始就卡在 WebRTC 連不上，反而延誤核心邏輯。

### Phase 0：基礎設施（Week 1）

- [ ] Monorepo 初始化（Turbo / pnpm workspace）
- [ ] Docker Compose 跑起 postgres + redis + livekit
- [ ] Prisma schema 建立 + migration
- [ ] 一支 seed 腳本塞入預設 Agent Profile
- [ ] Worker 專案骨架（`uv init`，跑起來會印 hello）
- [ ] CI：lint + type check + unit test（GitHub Actions）

**驗收**：`docker compose up` 全部 service 健康，可連到 DB 看到 seed 資料。

### Phase 1：純文字對話鏈（Week 2）

- [ ] `SlidingWindowMemory` 實作 + 單元測試
- [ ] `LLM` 串流客戶端
- [ ] `SmartSplitter` 實作 + 單元測試（涵蓋 20+ 邊界案例）
- [ ] `TextProcessor` (HanloFlow + Taibun + 字典) + 單元測試
- [ ] `InteractionLog` 寫入
- [ ] CLI demo：`python -m worker.cli "請問 307 公車到站時間？"` 在 terminal 看到：
  * LLM 串流文字
  * 被 Splitter 切出的句子
  * 每句的漢羅、台羅

**驗收**：`uv run pytest` 全綠，CLI 能完整對話 10 輪以上，不會出現記憶遺漏或轉換錯誤。

### Phase 2：語音層接入（Week 3）

- [ ] Piper TTS 包裝（輸入台羅 → 輸出 PCM）
- [ ] ASR 抽象介面 + Qwen3-ASR 接入（首選，因原生支援串流）
- [ ] Breeze-ASR-26 接入（作為比較基準）
- [ ] Silero VAD 整合
- [ ] LiveKit Agent 入口（連線、訂閱音軌、發佈音軌）
- [ ] **Dummy Loop**：麥克風 → VAD → 寫死「你好」→ TTS → 喇叭。**不接 LLM**。
- [ ] 前端 Playground 最小版本：進頁面能連線、能聽到回應
- [ ] ASR A/B 評估：錄製 30 段測試語音，跑過兩個模型比對 CER 與延遲，寫入 `docs/asr_evaluation.md`，決定正式採用的 backend

**驗收**：麥克風說話會觸發 Dummy Loop，聽到固定台語回應。延遲 < 1.5s。ASR 評估報告完成並選定預設 backend。

### Phase 3：完整迴圈整合（Week 4）

- [ ] Dummy Loop 替換為真實 LLM
- [ ] 延遲量測埋點寫入 `InteractionLog`
- [ ] Fallback 音訊預生成機制
- [ ] 各層超時 + 錯誤處理

**驗收**：能進行 10 分鐘無中斷的自然對話，平均 `latency_total` < 1.5s。

### Phase 4：Barge-in + AEC（Week 5）

- [ ] Voice Controller FSM 實作
- [ ] 動態 VAD 門檻（SPEAKING 狀態下提高）
- [ ] Client 端 AEC 參數確認
- [ ] 完整清理序列實作（停音訊 → 清 TTS → 取消 LLM → flush splitter → 寫 log）
- [ ] 測試案例：
  * 使用者在 Agent 說話中途打斷 → Agent 立即停
  * Agent 自己的 TTS 不會觸發 barge-in
  * 快速連續打斷不會導致狀態錯亂

**驗收**：在自然對話中至少成功打斷 5 次，無殘音、無狀態卡死。

### Phase 5：管理後台（Week 6）

- [ ] Agent Profile CRUD 頁面
- [ ] 對話日誌檢視頁面（含 Hanlo/Taibun 四欄對照）
- [ ] 發音字典管理頁面
- [ ] 「從 log 一鍵加入字典」功能
- [ ] 即時監控儀表板

**驗收**：指導老師或非技術同學能獨立透過後台新增一個 Agent 並修正發音。

### Phase 6：RAG + Tools（Week 7）

- [ ] 知識庫上傳流程（PDF / MD → 切塊 → embedding → pgvector）
- [ ] RAG 檢索整合進 LLM 呼叫
- [ ] TDX Tool 實作 + 整合 function calling

**驗收**：問「307 公車現在到哪了？」能正確呼叫 TDX 並用台語回答。

### Phase 7：打磨與文件（Week 8）

- [ ] 延遲優化（找出最慢的 10% turn，逐一分析）
- [ ] Demo 腳本撰寫
- [ ] 架構圖、時序圖繪製
- [ ] 使用者手冊、部署手冊
- [ ] 專題書面報告

---

## 10. 風險與緩解

| 風險 | 可能性 | 影響 | 緩解措施 |
|------|-------|------|---------|
| 單一 ASR 模型台語辨識率不足 | 中 | 高 | 採用抽象介面設計，Qwen3-ASR 與 Breeze-26 可快速切換；在 Phase 2 收集評估數據後鎖定正式版 |
| ASR 輸出為漢字 (國語字形) 丟失語氣 | 高 | 低 | 接受此限制（LLM 仍能理解語意）；若需保留原貌可於 Log 中加掛第二份 ASR 輸出 |
| Barge-in 實作複雜度高估 | 中 | 中 | Phase 4 單獨一週；先接受「有時誤觸發」再逐步優化門檻 |
| WebRTC 網路問題（NAT 穿透失敗） | 中 | 高 | 開發階段強制用 ngrok；Demo 前用同網段手機測過 |
| LLM API 費用超支 | 低 | 中 | 開發用 gpt-4o-mini 或本地 Llama；設定每日預算上限 |
| Piper 某些羅馬字發音怪異 | 中 | 低 | 字典系統本身就是解法；Phase 5 的後台讓非工程同學也能修 |
| 專題期限壓縮 | 高 | 高 | Phase 6 (RAG+Tools) 可砍至最小；Phase 5 後台可簡化成 Prisma Studio |

---

## 11. 已明確排除的範圍

以下項目**本專題不處理**，列於此避免範圍蔓延：

* 多使用者併發（一次只服務一人）
* 跨 session 長期記憶（每次對話結束就遺忘）
* 水平擴展 / 負載均衡
* 使用者帳號系統 / 權限管理（管理後台用單一 admin 帳密即可）
* 聲紋辨識 / 多人對話分離
* 情緒偵測 / 語氣調整
* 對話摘要壓縮（滑動視窗已足夠，見 §3.4）

這些皆可在 README 的「Future Work」章節列出。

---

## 附錄 A：專題報告建議結構

若此文件同時作為書面報告骨架，建議對應到以下章節：

| 報告章節 | 本文件對應 |
|---------|-----------|
| 研究動機 | §0.1 |
| 系統設計 | §1, §2 |
| 核心演算法（Barge-in / Splitter / 記憶） | §3, §4 |
| 實作細節 | §4, §5, §6 |
| 系統部署 | §8 |
| 開發歷程 | §9 |
| 風險討論與未來工作 | §10, §11 |

## 附錄 B：關鍵名詞對照

| 英文 | 中文 | 備註 |
|------|------|------|
| FTTA | 首次音訊延遲 | First-Time-To-Audio |
| VAD | 語音活動偵測 | Voice Activity Detection |
| AEC | 聲學回音抑制 | Acoustic Echo Cancellation |
| ASR | 自動語音辨識 | Automatic Speech Recognition |
| TTS | 語音合成 | Text-to-Speech |
| Barge-in | 插話 / 打斷 | 擬真對話關鍵指標 |
| POJ | 白話字 | Peh-ōe-jī，台語羅馬字之一 |
| 漢羅 | 漢字與羅馬字混用 | HanloFlow 輸出格式 |