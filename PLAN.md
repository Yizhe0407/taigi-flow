# Taigi-Flow Agent Worker 架構規劃

## Context

建立一個即時台語語音對話 AI 系統的核心 Agent Worker。使用者透過語音輸入，經由 STT → LLM → HanloFlow（繁中→台語）→ TTS 管線產生台語語音回應。目前 STT/TTS/LLM/HanloFlow 各元件已個別驗證，需要將它們串接為完整的即時語音管線，並加入監控後台。

---

## 核心設計決策

### 1. 模組化原則：Protocol + 依賴注入 + Config 驅動

所有可替換元件都定義 `Protocol`（介面），透過 config 決定使用哪個實作，`TaigiAgent` 透過建構子注入依賴。**換任何元件只需：新增實作 + 改 config，不動 Agent 核心邏輯。**

```
┌─────────────────────────────────────────────────┐
│  config.yaml / .env                             │
│  stt_backend: "qwen"    ← 改這裡就換 STT        │
│  llm_backend: "ollama"  ← 改這裡就換 LLM        │
│  tts_backend: "piper"   ← 改這裡就換 TTS        │
│  converter_backend: "hanloflow"  ← 改這裡就換轉換器 │
└──────────────────┬──────────────────────────────┘
                   ▼
         ┌── ComponentFactory ──┐
         │  根據 config 建立實例   │
         └──────────┬───────────┘
                    ▼
    TaigiAgent(stt, llm, tts, converter, ...)
```

### 2. 元件介面定義

每個可替換元件定義 Protocol，放在 `src/taigi_flow/protocols.py`：

```python
from typing import Protocol, AsyncIterable

class TextConverter(Protocol):
    """文字轉換器介面（HanloFlow 或未來替代方案）"""
    async def stream_convert(self, text_stream: AsyncIterable[str]) -> AsyncIterable[str]: ...
    def convert(self, text: str) -> str: ...

class Synthesizer(Protocol):
    """TTS 合成器介面（Piper 或未來替代方案）"""
    async def synthesize_stream(self, text: str) -> AsyncIterable[bytes]: ...

class SpeechRecognizer(Protocol):
    """STT 辨識器介面 — 包裝 LiveKit stt.STT，統一額外行為"""
    def create_stt(self) -> "stt.STT": ...

class LanguageModel(Protocol):
    """LLM 介面 — 包裝 LiveKit llm.LLM 或 OpenAI 相容 API"""
    def create_llm(self) -> "llm.LLM": ...
```

| 元件 | Protocol | 目前實作 | 未來可替換為 |
|------|----------|---------|-------------|
| STT | `SpeechRecognizer` | `QwenSTT`（WebSocket） | Whisper、Sensevoice、Google STT |
| LLM | `LanguageModel` | `OllamaLLM`（OpenAI 相容） | vLLM、直接 API、Claude |
| 轉換器 | `TextConverter` | `HanloBridge`（HanloFlow） | 其他台語轉換方案、直接 LLM 台語輸出 |
| TTS | `Synthesizer` | `PiperSynthesizer`（HTTP） | CosyVoice、Edge TTS、本地 VITS |
| VAD | LiveKit 內建 | `silero.VAD` | WebRTC VAD、其他 |

### 3. 元件工廠 (`ComponentFactory`)

```python
# src/taigi_flow/factory.py
class ComponentFactory:
    """根據 config 建立所有元件實例"""

    @staticmethod
    def create_stt(settings: Settings) -> stt.STT:
        match settings.stt_backend:
            case "qwen": return QwenSTT(ws_url=settings.qwen_asr_ws_url)
            case "whisper": return WhisperSTT(...)
            case _: raise ValueError(f"Unknown STT backend: {settings.stt_backend}")

    @staticmethod
    def create_llm(settings: Settings) -> llm.LLM:
        match settings.llm_backend:
            case "ollama": return openai.LLM(base_url=settings.llm_base_url, model=settings.llm_model)
            case _: raise ValueError(...)

    @staticmethod
    def create_converter(settings: Settings) -> TextConverter:
        match settings.converter_backend:
            case "hanloflow": return HanloBridge(data_dir=settings.hanloflow_data_dir)
            case "passthrough": return PassthroughConverter()  # 不轉換，直接透傳
            case _: raise ValueError(...)

    @staticmethod
    def create_synthesizer(settings: Settings) -> Synthesizer:
        match settings.tts_backend:
            case "piper": return PiperSynthesizer(base_url=settings.piper_url, voice=settings.piper_voice)
            case _: raise ValueError(...)
```

### 4. Agent 透過建構子注入所有依賴

```python
class TaigiAgent(Agent):
    def __init__(self, converter: TextConverter, synthesizer: Synthesizer):
        super().__init__(instructions="...")
        self._converter = converter
        self._synthesizer = synthesizer

    async def tts_node(self, text, model_settings):
        async for chunk in self._converter.stream_convert(text):
            async for frame in self._synthesizer.synthesize_stream(chunk):
                yield frame
```

Agent 不知道也不關心底層用的是 HanloFlow 還是其他轉換器、Piper 還是其他 TTS。

### 5. LiveKit 完全自架（不使用 Cloud）

LiveKit server 是 Apache 2.0 開源，完全可以自架：
- 開發階段：`livekit-server --dev` 一行啟動，不需要域名/SSL
- 生產環境：需要域名 + 受信任 SSL 憑證 + Redis（多副本時）
- 所有元件都跑在本地，自架避免多一層網路延遲
- docker-compose 內加一個 `livekit/livekit-server` service 即可

### 6. 上下文管理（使用 LiveKit 內建機制）

`livekit-agents` 已內建上下文壓縮，不需自行實作：
- **`ChatContext.truncate()`** — 保留最近 N 條訊息，自動保留 system prompt
- **`ChatContext._summarize()`** — 用 LLM 把舊對話壓縮成摘要，保留關鍵資訊
- **`before_llm_cb`** — 送出 LLM 前可動態修改 context（插入 RAG 結果等）
- 可整合外部記憶平台（Zep、Letta、Mem0）

### 7. Barge-in / 打斷控制

使用 LiveKit 內建的 `TurnHandlingOptions`，設定 `min_interruption_duration` 避免誤觸（台語語助詞多）。

### 8. Session 狀態

`SessionState` dataclass 存放於 `AgentSession.userdata`，記錄對話輪次、延遲指標、轉換紀錄。

---

## 專案結構

```
taigi-flow/
├── pyproject.toml
├── docker-compose.yml
├── .env.example
├── livekit-server.yaml
│
├── src/taigi_flow/
│   ├── __init__.py
│   ├── main.py                  # 入口：AgentServer + session 設定
│   ├── agent.py                 # TaigiAgent(Agent) — 覆寫 tts_node，依賴注入
│   ├── config.py                # Pydantic Settings（環境變數 + 元件選擇）
│   ├── protocols.py             # Protocol 定義（TextConverter, Synthesizer, ...）
│   ├── factory.py               # ComponentFactory — 根據 config 建立元件實例
│   │
│   ├── stt/                     # STT 實作（每個 backend 一個檔案）
│   │   ├── __init__.py
│   │   └── qwen.py              # QwenSTT — WebSocket 串流
│   │
│   ├── llm/                     # LLM 實作
│   │   ├── __init__.py
│   │   └── ollama.py            # OllamaLLM — OpenAI 相容 API
│   │
│   ├── tts/                     # TTS 實作
│   │   ├── __init__.py
│   │   └── piper.py             # PiperSynthesizer — HTTP client
│   │
│   ├── converter/               # 文字轉換器實作
│   │   ├── __init__.py
│   │   ├── hanlo_bridge.py      # HanloBridge — HanloFlow 非同步橋接
│   │   └── passthrough.py       # PassthroughConverter — 不轉換（測試/除錯用）
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   └── bus_routes.py        # 範例工具：公車路線查詢
│   │
│   ├── rag/
│   │   ├── __init__.py
│   │   └── knowledge_base.py    # 靜態知識庫 RAG
│   │
│   ├── session/
│   │   ├── __init__.py
│   │   └── state.py             # SessionState dataclass
│   │
│   └── monitoring/
│       ├── __init__.py
│       ├── metrics.py           # Prometheus 指標
│       ├── traces.py            # OpenTelemetry 追蹤
│       └── dashboard.py         # FastAPI 後台 API
│
├── hanloflow/                   # HanloFlow（git submodule）
│
├── tests/
│   ├── test_agent.py
│   ├── test_hanlo_bridge.py
│   └── ...
│
├── scripts/
│   ├── download_piper_model.sh
│   └── setup_ollama.sh
│
└── monitoring/
    ├── grafana/dashboards/taigi-flow.json
    └── prometheus.yml
```

---

## 關鍵檔案實作摘要

### `src/taigi_flow/protocols.py` — 元件介面

```python
from typing import Protocol, AsyncIterable

class TextConverter(Protocol):
    """文字轉換器（HanloFlow 或未來替代品）"""
    async def stream_convert(self, text_stream: AsyncIterable[str]) -> AsyncIterable[str]: ...
    def convert(self, text: str) -> str: ...

class Synthesizer(Protocol):
    """TTS 合成器（Piper 或未來替代品）"""
    async def synthesize_stream(self, text: str) -> AsyncIterable[bytes]: ...
```

> STT 和 LLM 直接使用 LiveKit 的 `stt.STT` / `llm.LLM` 介面，不額外包一層。

### `src/taigi_flow/factory.py` — 元件工廠

```python
class ComponentFactory:
    @staticmethod
    def create_stt(settings: Settings) -> stt.STT:
        match settings.stt_backend:
            case "qwen":   return QwenSTT(ws_url=settings.qwen_asr_ws_url)
            case _:         raise ValueError(f"Unknown STT: {settings.stt_backend}")

    @staticmethod
    def create_llm(settings: Settings) -> llm.LLM:
        match settings.llm_backend:
            case "ollama":  return openai.LLM(base_url=settings.llm_base_url, model=settings.llm_model)
            case _:         raise ValueError(f"Unknown LLM: {settings.llm_backend}")

    @staticmethod
    def create_converter(settings: Settings) -> TextConverter:
        match settings.converter_backend:
            case "hanloflow":   return HanloBridge(data_dir=settings.hanloflow_data_dir)
            case "passthrough": return PassthroughConverter()
            case _:             raise ValueError(...)

    @staticmethod
    def create_synthesizer(settings: Settings) -> Synthesizer:
        match settings.tts_backend:
            case "piper":  return PiperSynthesizer(base_url=settings.piper_url, voice=settings.piper_voice)
            case _:        raise ValueError(...)
```

### `src/taigi_flow/agent.py` — 核心 Agent（依賴注入）

```python
class TaigiAgent(Agent):
    def __init__(self, converter: TextConverter, synthesizer: Synthesizer):
        super().__init__(instructions="你是台語對話助手，用繁體中文回答。")
        self._converter = converter      # 不知道底層是 HanloFlow 還是其他
        self._synthesizer = synthesizer  # 不知道底層是 Piper 還是其他

    async def tts_node(self, text: AsyncIterable[str], model_settings) -> AsyncIterable[rtc.AudioFrame]:
        async for converted_chunk in self._converter.stream_convert(text):
            async for frame in self._synthesizer.synthesize_stream(converted_chunk):
                yield frame
```

### `src/taigi_flow/converter/hanlo_bridge.py` — HanloFlow 實作

```python
class HanloBridge:
    """實作 TextConverter protocol"""
    def __init__(self, data_dir: Path = None):
        self._converter = TaigiConverter(data_dir=data_dir)

    async def stream_convert(self, text_stream: AsyncIterable[str]) -> AsyncIterable[str]:
        buffer = ""
        sentence_delimiters = {"。", "！", "？", "，", "；", "\n"}

        async for token in text_stream:
            buffer += token
            while any(d in buffer for d in sentence_delimiters):
                idx = min(buffer.index(d) for d in sentence_delimiters if d in buffer)
                sentence = buffer[:idx + 1]
                buffer = buffer[idx + 1:]
                if sentence.strip():
                    result = await asyncio.to_thread(self._converter.convert, sentence.strip())
                    yield result.taibun_number_tone

        if buffer.strip():
            result = await asyncio.to_thread(self._converter.convert, buffer.strip())
            yield result.taibun_number_tone
```

### `src/taigi_flow/stt/qwen.py` — Qwen STT 實作

```python
class QwenSTT(stt.STT):
    """實作 LiveKit stt.STT 介面，透過 WebSocket 串流"""
    def __init__(self, *, ws_url: str, model: str = "qwen3-asr"):
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=True))
        self._ws_url = ws_url
        self._model = model

    def stream(self, *, conn_options=...) -> "QwenRecognizeStream":
        return QwenRecognizeStream(self._ws_url, self._model, conn_options)
```

### `src/taigi_flow/tts/piper.py` — Piper TTS 實作

```python
class PiperSynthesizer:
    """實作 Synthesizer protocol，呼叫 piper-tts-http-server"""
    def __init__(self, base_url: str, voice: str):
        self._base_url = base_url
        self._voice = voice

    async def synthesize_stream(self, text: str) -> AsyncIterable[bytes]:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", f"{self._base_url}/v1/audio/speech",
                json={"input": text, "voice": self._voice, "format": "wav"}
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
```

### `src/taigi_flow/main.py` — 入口（工廠組裝）

```python
settings = Settings()
factory = ComponentFactory()

@server.rtc_session(agent_name="taigi-agent")
async def taigi_session(ctx: agents.JobContext):
    session = AgentSession(
        stt=factory.create_stt(settings),
        llm=factory.create_llm(settings),
        tts=None,  # tts_node 完全覆寫
        vad=silero.VAD.load(),
    )
    agent = TaigiAgent(
        converter=factory.create_converter(settings),
        synthesizer=factory.create_synthesizer(settings),
    )
    await session.start(room=ctx.room, agent=agent)
```

### `src/taigi_flow/monitoring/dashboard.py` — 監控後台

FastAPI 提供：
- `GET /api/sessions` — 即時活躍 session 列表
- `GET /api/sessions/{id}` — session 詳情（對話記錄、延遲）
- `GET /metrics` — Prometheus 格式指標
- Grafana dashboard JSON 預設面板

---

## Config 範例 (`.env.example`)

```bash
# === 元件選擇（改這裡就換實作）===
STT_BACKEND=qwen           # qwen | whisper | ...
LLM_BACKEND=ollama         # ollama | vllm | ...
TTS_BACKEND=piper          # piper | cosyvoice | ...
CONVERTER_BACKEND=hanloflow # hanloflow | passthrough | ...

# === 各元件連線設定 ===
QWEN_ASR_WS_URL=ws://localhost:8001/ws
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3.5:q4_k_m
PIPER_URL=http://localhost:5000
PIPER_VOICE=taiwanese-medium
HANLOFLOW_DATA_DIR=./hanloflow/data

# === LiveKit（自架）===
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret

# === 監控 ===
METRICS_PORT=9090
OTLP_ENDPOINT=http://localhost:4317
```

## 依賴 (`pyproject.toml`)

```toml
[project]
name = "taigi-flow"
requires-python = ">=3.12"
dependencies = [
    "livekit-agents[openai,silero,turn-detector]~=1.5",
    "pydantic-settings>=2.0",
    "httpx>=0.27",
    "msgpack>=1.0",
    "prometheus-client>=0.20",
    "opentelemetry-api>=1.20",
    "opentelemetry-sdk>=1.20",
    "opentelemetry-exporter-otlp>=1.20",
    "fastapi>=0.110",
    "uvicorn>=0.29",
]
```

---

## Docker Compose 服務（全部自架）

```yaml
services:
  livekit-server:        # 自架 LiveKit（開發用 --dev 模式）
  ollama:                # Qwen3.5 Q4_K_M LLM
  qwen-asr:              # Qwen3 ASR 語音辨識服務
  piper-tts:             # Piper TTS HTTP Server
  prometheus:            # 指標收集
  grafana:               # 監控面板
  taigi-agent:           # Agent Worker（生產環境容器化）
```

開發階段 LiveKit server 用 `--dev` 模式啟動，無需域名和 SSL。生產部署時加上正式域名、SSL 憑證及 Redis。

---

## 實作階段

### Phase 1：骨架
- 建立專案結構、`pyproject.toml`、`config.py`
- 實作 `main.py` + `TaigiAgent`（placeholder tts_node）
- 驗證：agent 連上 LiveKit room，LLM 透過 Ollama 回應

### Phase 2：HanloFlow 整合
- 加入 HanloFlow git submodule
- 實作 `HanloBridge` 句子緩衝 + 非同步轉換
- 驗證：繁中輸入 → Taibun 輸出

### Phase 3：STT + TTS
- 實作 `QwenSTT` WebSocket 串流 plugin
- 實作 `PiperSynthesizer` HTTP client
- 完整串接 tts_node
- 驗證：端對端語音對話

### Phase 4：監控
- Prometheus 指標（各階段延遲、session 數、轉換次數）
- OpenTelemetry 追蹤
- FastAPI 後台 + Grafana dashboard
- docker-compose 完整環境

### Phase 5：工具層 + RAG（選配）
- 公車路線查詢工具
- 靜態知識庫 RAG

---

## 驗證方式

1. **單元測試**：`HanloBridge` 句子緩衝邏輯、`SessionState` 更新
2. **整合測試**：LiveKit room 內完整 STT→LLM→HanloFlow→TTS 流程
3. **手動測試**：用 LiveKit Playground 或自訂前端連入，進行台語對話
4. **監控驗證**：確認 Prometheus 指標正確、Grafana dashboard 顯示即時數據
