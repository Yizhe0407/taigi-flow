#!/usr/bin/env bash
set -euo pipefail

echo "Pulling Qwen3.5 9B model into Ollama..."

if command -v ollama &>/dev/null; then
    ollama pull qwen3.5:9b
else
    docker compose exec ollama ollama pull qwen3.5:9b
fi

echo "Done. Verify with:"
echo "  docker compose exec ollama ollama list"
