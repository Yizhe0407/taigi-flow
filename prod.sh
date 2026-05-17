#!/usr/bin/env bash
# 正式環境一鍵啟動
# 用法：./prod.sh [--no-worker] [--skip-build]
#
# 特性：Next.js 靜態建置後以 next start 執行、Worker 使用穩定 start 模式
# 環境變數：優先讀取 .env.prod，若不存在則 fallback 到 .env
# 需求：tmux, docker, pnpm, uv  |  tmux 安裝：brew install tmux

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_lib.sh
source "$ROOT/scripts/_lib.sh"

SESSION="taigi-flow-prod"
NO_WORKER=false
SKIP_BUILD=false
for arg in "$@"; do
  [[ "$arg" == "--no-worker" ]]   && NO_WORKER=true
  [[ "$arg" == "--skip-build" ]]  && SKIP_BUILD=true
done

# ── 1. 檢查 & 環境 ────────────────────────────────────────────────────────────
check_prereqs

ENV_FILE="$ROOT/.env"
if [[ -f "$ROOT/.env.prod" ]]; then
  ENV_FILE="$ROOT/.env.prod"
fi
load_env "$ENV_FILE"

# ── 2. 基礎設施 & Migration ────────────────────────────────────────────────────
start_infra "$ROOT"
run_migrations "$ROOT"

# ── 3. 清理舊 web 程序 ────────────────────────────────────────────────────────
kill_web_ports

# ── 4. Next.js Build ──────────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" == "false" ]]; then
  echo "building Next.js (Playground + Admin)..."
  cd "$ROOT/web"
  pnpm --filter playground build 2>&1 | tail -5
  pnpm --filter admin build 2>&1 | tail -5
  cd "$ROOT"
  echo "build complete"
else
  echo "skipping build (--skip-build)"
fi

# ── 5. tmux session ───────────────────────────────────────────────────────────
kill_existing_session "$SESSION"
echo "building tmux session '${SESSION}' (prod mode)..."

# Step 1: Playground (pane 0, full window)
tmux new-session -d -s "$SESSION" -x 220 -y 50 \
  -e "DATABASE_URL=${DATABASE_URL}" \
  -c "$ROOT/web"
sleep 0.3
tmux send-keys -t "${SESSION}:0.0" "pnpm --filter playground start -p 3000" Enter

# Step 2: Worker (right half, full height)
if [[ "$NO_WORKER" == "false" ]]; then
  WORKER_PANE=$(tmux split-window -t "${SESSION}:0.0" -h -P -F "#{pane_id}" \
    -e "DATABASE_URL=${DATABASE_URL}" \
    -c "$ROOT/worker")
  tmux resize-pane -t "${WORKER_PANE}" -x "55%"
  sleep 0.3
  tmux send-keys -t "${WORKER_PANE}" "uv run python -m worker.main start" Enter

  INGEST_PANE=$(tmux split-window -t "${WORKER_PANE}" -v -P -F "#{pane_id}" \
    -e "DATABASE_URL=${DATABASE_URL}" \
    -c "$ROOT/worker")
  sleep 0.3
  tmux send-keys -t "${INGEST_PANE}" "uv run python -m worker.ingest" Enter

  RAG_PANE=$(tmux split-window -t "${INGEST_PANE}" -v -P -F "#{pane_id}" \
    -e "DATABASE_URL=${DATABASE_URL}" \
    -c "$ROOT/worker")
  sleep 0.3
  tmux send-keys -t "${RAG_PANE}" "uv run python -m worker.rag_server" Enter
fi

# Step 3: Admin (left bottom)
ADMIN_PANE=$(tmux split-window -t "${SESSION}:0.0" -v -P -F "#{pane_id}" \
  -e "DATABASE_URL=${DATABASE_URL}" \
  -c "$ROOT/web")
sleep 0.3
tmux send-keys -t "${ADMIN_PANE}" "pnpm --filter admin start -p 3001" Enter

if [[ "$NO_WORKER" == "false" ]]; then
  tmux select-pane -t "${WORKER_PANE}"
else
  tmux select-pane -t "${SESSION}:0.0"
fi

# ── 6. Attach ─────────────────────────────────────────────────────────────────
print_ready_msg "$SESSION" "PROD"
tmux attach-session -t "$SESSION"
