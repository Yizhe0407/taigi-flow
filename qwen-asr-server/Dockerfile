FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    qwen-asr \
    fastapi \
    uvicorn \
    numpy

COPY server.py ./

ENV MODEL_NAME=/model/checkpoint-20340
ENV PORT=8001
ENV DEVICE=cpu

EXPOSE 8001

CMD ["python", "server.py"]
