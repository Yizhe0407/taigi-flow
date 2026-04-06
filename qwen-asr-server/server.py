"""Qwen3-ASR HTTP Streaming Server。

提供 HTTP chunk streaming API：
  POST /api/start                         → {"session_id": "<uuid>"}
  POST /api/chunk?session_id=<id>         → {"language": "<lang>", "text": "<partial>"}
  POST /api/finish?session_id=<id>        → {"language": "<lang>", "text": "<final>"}

音訊格式：Float32 binary，16kHz，mono
注意：transformers backend 不支援 streaming ASR，改用累積音訊後批次辨識。
環境變數：
  MODEL_NAME  本地模型路徑或 HuggingFace model ID
  PORT        HTTP port（預設 8001）
  DEVICE      cpu | cuda | mps（預設 cpu）
"""

import os
import uuid

import numpy as np
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

MODEL_NAME = os.environ.get("MODEL_NAME", "/model/checkpoint-20340")
PORT = int(os.environ.get("PORT", "8001"))
DEVICE = os.environ.get("DEVICE", "cpu")

app = FastAPI(title="Qwen3-ASR Streaming Server")

_model = None
_sessions: dict[str, list] = {}  # session_id → list of audio chunks


@app.on_event("startup")
async def load_model():
    global _model
    from qwen_asr import Qwen3ASRModel

    print(f"Loading model: {MODEL_NAME} on {DEVICE}")
    kwargs = {"low_cpu_mem_usage": True}
    if DEVICE == "cuda":
        kwargs["device_map"] = "cuda"
    elif DEVICE == "mps":
        kwargs["device_map"] = "mps"
    _model = Qwen3ASRModel.from_pretrained(MODEL_NAME, **kwargs)
    print(f"Model loaded: {MODEL_NAME}")


@app.post("/api/start")
async def start_session():
    session_id = uuid.uuid4().hex
    _sessions[session_id] = []
    return {"session_id": session_id}


@app.post("/api/chunk")
async def process_chunk(request: Request, session_id: str = Query(...)):
    if session_id not in _sessions:
        return JSONResponse({"error": "invalid session"}, status_code=400)

    body = await request.body()
    audio = np.frombuffer(body, dtype=np.float32).copy()
    _sessions[session_id].append(audio)

    # 批次辨識累積的全部音訊
    accumulated = np.concatenate(_sessions[session_id])
    results = _model.transcribe((accumulated, 16000), language="zh")
    result = results[0] if results else None

    return {
        "language": result.language if result else "zh",
        "text": result.text if result else "",
    }


@app.post("/api/finish")
async def finish_session(session_id: str = Query(...)):
    if session_id not in _sessions:
        return JSONResponse({"error": "invalid session"}, status_code=400)

    chunks = _sessions.pop(session_id)
    if not chunks:
        return {"language": "zh", "text": ""}

    accumulated = np.concatenate(chunks)
    results = _model.transcribe((accumulated, 16000), language="zh")
    result = results[0] if results else None

    return {
        "language": result.language if result else "zh",
        "text": result.text if result else "",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME, "device": DEVICE}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
