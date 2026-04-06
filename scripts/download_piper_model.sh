#!/usr/bin/env bash
# 下載 Piper TTS 台語模型，放到 piper-tts-http-server 的 data 目錄
# 用法：./scripts/download_piper_model.sh
set -euo pipefail

DATA_DIR="${PIPER_DATA_DIR:-./piper-tts-http-server/data}"
MODEL_URL="${PIPER_MODEL_URL:-}"
VOICE="${PIPER_VOICE:-taigi_epoch1339}"

mkdir -p "$DATA_DIR"

if [ -z "$MODEL_URL" ]; then
    echo "請設定 PIPER_MODEL_URL 環境變數指向 .onnx 模型的下載位址。"
    echo "範例："
    echo "  PIPER_MODEL_URL=https://... ./scripts/download_piper_model.sh"
    exit 1
fi

echo "下載 Piper 台語模型: $VOICE"
curl -L "$MODEL_URL" -o "$DATA_DIR/${VOICE}.onnx"

# 若有對應的 .onnx.json config 檔
if [ -n "${PIPER_CONFIG_URL:-}" ]; then
    curl -L "$PIPER_CONFIG_URL" -o "$DATA_DIR/${VOICE}.onnx.json"
fi

echo "完成。模型存放於: $DATA_DIR"
echo "請確認 .env.local 中的 PIPER_VOICE=${VOICE}"
