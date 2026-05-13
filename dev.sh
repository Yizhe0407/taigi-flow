#!/usr/bin/env bash
# 開發環境一鍵啟動
# 用法：./dev.sh [--no-worker]
#
# 特性：Next.js hot-reload、Worker 自動重載（livekit-agents dev 模式）
# 需求：tmux, docker, pnpm, uv  |  tmux 安裝：brew install tmux

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_lib.sh
source "$ROOT/scripts/_lib.sh"

SESSION="taigi-flow-dev"
NO_WORKER=false
for arg in "$@"; do [[ "$arg" == "--no-worker" ]] && NO_WORKER=true; done

# ── 1. 檢查 & 環境 ────────────────────────────────────────────────────────────
check_prereqs
load_env "$ROOT/.env"

# ── 2. 基礎設施 & Migration ────────────────────────────────────────────────────
start_infra "$ROOT"
run_migrations "$ROOT"

# ── 3. 清理舊 web 程序 ────────────────────────────────────────────────────────
kill_web_ports

# ── 4. tmux session ───────────────────────────────────────────────────────────
kill_existing_session "$SESSION"
echo "building tmux session '${SESSION}' (dev mode)..."

# Layout:
#  ┌─────────────┬─────────────────────────────────┐
#  │ Playground  │                                  │
#  │   :3000     │         Worker                   │
#  ├─────────────┤        (right half)              │
#  │   Admin     │                                  │
#  │   :3001     │                                  │
#  └─────────────┴─────────────────────────────────┘

# Step 1: Playground on full window (pane 0)
tmux new-session -d -s "$SESSION" -x 220 -y 50 \
  -e "DATABASE_URL=${DATABASE_URL}" \
  -c "$ROOT/web"
sleep 0.3
tmux send-keys -t "${SESSION}:0.0" "pnpm --filter playground dev" Enter

# Step 2: Split right → Worker (right half, full height)
if [[ "$NO_WORKER" == "false" ]]; then
  WORKER_PANE=$(tmux split-window -t "${SESSION}:0.0" -h -P -F "#{pane_id}" \
    -e "DATABASE_URL=${DATABASE_URL}" \
    -c "$ROOT/worker")
  # Right pane gets 55% width, leaving 45% for left column
  tmux resize-pane -t "${WORKER_PANE}" -x "55%"
  sleep 0.3
  tmux send-keys -t "${WORKER_PANE}" "uv run python -m worker.main dev" Enter
fi

# Step 3: Split left column vertically → Playground (top) + Admin (bottom)
ADMIN_PANE=$(tmux split-window -t "${SESSION}:0.0" -v -P -F "#{pane_id}" \
  -e "DATABASE_URL=${DATABASE_URL}" \
  -c "$ROOT/web")
sleep 0.3
tmux send-keys -t "${ADMIN_PANE}" "pnpm --filter admin dev" Enter

# Focus worker (or playground if no-worker)
if [[ "$NO_WORKER" == "false" ]]; then
  tmux select-pane -t "${WORKER_PANE}"
else
  tmux select-pane -t "${SESSION}:0.0"
fi

# ── 5. Attach ─────────────────────────────────────────────────────────────────
print_ready_msg "$SESSION" "DEV"
tmux attach-session -t "$SESSION"
