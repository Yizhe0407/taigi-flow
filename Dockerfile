FROM python:3.12-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# 安裝 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 複製依賴設定
COPY pyproject.toml ./

# 複製 HanloFlow submodule（需要 --recurse-submodules clone）
COPY hanloflow/ ./hanloflow/

# 複製 source code
COPY src/ ./src/

# 安裝依賴（不含 dev）
RUN uv pip install --system -e .

CMD ["taigi-flow", "start"]
