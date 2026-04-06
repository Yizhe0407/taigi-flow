#!/usr/bin/env bash
set -euo pipefail

MODEL="frob/qwen3.5-instruct:4b"

echo "Pulling non-thinking Qwen3.5 4B model into Ollama: ${MODEL}"

if command -v ollama &>/dev/null; then
    ollama pull "${MODEL}"
else
    docker compose exec ollama ollama pull "${MODEL}"
fi

echo "Done. Verify with:"
echo "  docker compose exec ollama ollama list"
