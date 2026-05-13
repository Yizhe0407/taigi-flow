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

# ── 3. tmux session ───────────────────────────────────────────────────────────
kill_existing_session "$SESSION"
echo "🖥️   建立 tmux session '$SESSION'（開發模式）…"

# Layout:
#  ┌─────────────────────┬─────────────────────┐
#  │  Playground :3000   │  Admin :3001         │
#  ├─────────────────────┴─────────────────────┤
#  │  Worker（dev 自動重載）                    │
#  └────────────────────────────────────────────┘

tmux new-session -d -s "$SESSION" -x 220 -y 50 \
  -e "DATABASE_URL=$DATABASE_URL" \
  -c "$ROOT/web"
tmux send-keys -t "$SESSION:0.0" "pnpm --filter playground dev" Enter

tmux split-window -t "$SESSION:0.0" -h \
  -e "DATABASE_URL=$DATABASE_URL" \
  -c "$ROOT/web"
tmux send-keys -t "$SESSION:0.1" "pnpm --filter admin dev" Enter

if [[ "$NO_WORKER" == "false" ]]; then
  tmux split-window -t "$SESSION:0.0" -v \
    -e "DATABASE_URL=$DATABASE_URL" \
    -c "$ROOT/worker"
  tmux send-keys -t "$SESSION:0.2" "uv run python -m worker.main dev" Enter
  tmux resize-pane -t "$SESSION:0.2" -y "40%"
  tmux select-pane -t "$SESSION:0.2"
else
  tmux select-pane -t "$SESSION:0.0"
fi

# ── 4. Attach ─────────────────────────────────────────────────────────────────
print_ready_msg "$SESSION" "DEV"
tmux attach-session -t "$SESSION"
