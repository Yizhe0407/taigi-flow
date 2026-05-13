FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir piper-tts flask

EXPOSE 5000

# Model files are mounted at /models at runtime.
# CMD can be overridden via docker-compose to point at a different .onnx file.
CMD ["python", "-m", "piper.http_server", \
     "--model", "/models/taigi.onnx", \
     "--port", "5000", \
     "--host", "0.0.0.0"]
