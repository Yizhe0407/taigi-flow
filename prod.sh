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

# 優先用 .env.prod
ENV_FILE="$ROOT/.env"
if [[ -f "$ROOT/.env.prod" ]]; then
  ENV_FILE="$ROOT/.env.prod"
fi
load_env "$ENV_FILE"

# ── 2. 基礎設施 & Migration ────────────────────────────────────────────────────
start_infra "$ROOT"
run_migrations "$ROOT"

# ── 3. Next.js Build ──────────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" == "false" ]]; then
  echo "🔨  建置 Next.js（Playground + Admin）…"
  cd "$ROOT/web"
  pnpm --filter playground build 2>&1 | tail -5
  pnpm --filter admin build 2>&1 | tail -5
  cd "$ROOT"
  echo "    建置完成 ✓"
else
  echo "⏭️   略過建置（--skip-build）"
fi

# ── 4. tmux session ───────────────────────────────────────────────────────────
kill_existing_session "$SESSION"
echo "🖥️   建立 tmux session '$SESSION'（正式模式）…"

# Layout:
#  ┌─────────────────────┬─────────────────────┐
#  │  Playground :3000   │  Admin :3001         │
#  ├─────────────────────┴─────────────────────┤
#  │  Worker（start 穩定模式）                  │
#  └────────────────────────────────────────────┘

tmux new-session -d -s "$SESSION" -x 220 -y 50 \
  -e "DATABASE_URL=$DATABASE_URL" \
  -c "$ROOT/web"
tmux send-keys -t "$SESSION:0.0" "pnpm --filter playground start -p 3000" Enter

tmux split-window -t "$SESSION:0.0" -h \
  -e "DATABASE_URL=$DATABASE_URL" \
  -c "$ROOT/web"
tmux send-keys -t "$SESSION:0.1" "pnpm --filter admin start -p 3001" Enter

if [[ "$NO_WORKER" == "false" ]]; then
  tmux split-window -t "$SESSION:0.0" -v \
    -e "DATABASE_URL=$DATABASE_URL" \
    -c "$ROOT/worker"
  tmux send-keys -t "$SESSION:0.2" "uv run python -m worker.main start" Enter
  tmux resize-pane -t "$SESSION:0.2" -y "40%"
  tmux select-pane -t "$SESSION:0.2"
else
  tmux select-pane -t "$SESSION:0.0"
fi

# ── 5. Attach ─────────────────────────────────────────────────────────────────
print_ready_msg "$SESSION" "PROD"
tmux attach-session -t "$SESSION"
