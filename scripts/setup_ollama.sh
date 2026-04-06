#!/usr/bin/env bash
set -euo pipefail

echo "Pulling Qwen3.5 9B model into Ollama..."
ollama pull qwen3.5:9b

echo "Done. Verify with:"
echo "  ollama list"
