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
#  ┌─────────────────────┬─────────────────────┐
#  │  Playground :3000   │  Admin :3001         │
#  ├─────────────────────┴─────────────────────┤
#  │  Worker（dev 自動重載）                    │
#  └────────────────────────────────────────────┘

# Pane 0: Playground
tmux new-session -d -s "$SESSION" -x 220 -y 50 \
  -e "DATABASE_URL=${DATABASE_URL}" \
  -c "$ROOT/web"
sleep 0.3
tmux send-keys -t "${SESSION}:0.0" "pnpm --filter playground dev" Enter

# Pane 1: Admin（水平切右側）
ADMIN_PANE=$(tmux split-window -t "${SESSION}:0.0" -h -P -F "#{pane_id}" \
  -e "DATABASE_URL=${DATABASE_URL}" \
  -c "$ROOT/web")
sleep 0.3
tmux send-keys -t "${ADMIN_PANE}" "pnpm --filter admin dev" Enter

# Pane 2: Worker（從 pane 0 垂直切下）
if [[ "$NO_WORKER" == "false" ]]; then
  WORKER_PANE=$(tmux split-window -t "${SESSION}:0.0" -v -P -F "#{pane_id}" \
    -e "DATABASE_URL=${DATABASE_URL}" \
    -c "$ROOT/worker")
  sleep 0.3
  tmux send-keys -t "${WORKER_PANE}" "uv run python -m worker.main dev" Enter
  tmux resize-pane -t "${WORKER_PANE}" -y 15
  tmux select-pane -t "${WORKER_PANE}"
else
  tmux select-pane -t "${SESSION}:0.0"
fi

# ── 5. Attach ─────────────────────────────────────────────────────────────────
print_ready_msg "$SESSION" "DEV"
tmux attach-session -t "$SESSION"
