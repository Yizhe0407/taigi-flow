#!/usr/bin/env bash
# 台語即時語音 Agent — 一鍵開發環境啟動腳本
# 用法：./dev.sh [--no-worker]
#
# 需求：tmux, docker, pnpm, uv
# tmux 尚未安裝者：brew install tmux

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION="taigi-flow"
NO_WORKER=false

for arg in "$@"; do
  [[ "$arg" == "--no-worker" ]] && NO_WORKER=true
done

# ── 1. 前置檢查 ────────────────────────────────────────────────────────────────

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "❌  找不到 '$1'。請先安裝後再執行。"
    case "$1" in
      tmux)   echo "    brew install tmux" ;;
      docker) echo "    https://www.docker.com/products/docker-desktop/" ;;
      pnpm)   echo "    npm install -g pnpm" ;;
      uv)     echo "    curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
    esac
    exit 1
  fi
}

check_cmd tmux
check_cmd docker
check_cmd pnpm
check_cmd uv

if [[ ! -f "$ROOT/.env" ]]; then
  echo "❌  找不到 .env 檔案。請先執行："
  echo "    cp .env.example .env  # 並填入必要環境變數"
  exit 1
fi

# 讀取 .env（取出 DATABASE_URL 用於 migration 檢查）
set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "❌  .env 中缺少 DATABASE_URL"
  exit 1
fi

# ── 2. 啟動 Docker 基礎設施 ────────────────────────────────────────────────────

echo "🐳  啟動 Docker 服務…"
docker compose -f "$ROOT/docker-compose.yml" up -d postgres redis livekit 2>&1 | grep -v "^$" || true

echo -n "⏳  等待 PostgreSQL 就緒"
for i in $(seq 1 30); do
  if docker exec taigi-flow-postgres-1 pg_isready -U admin -d agent_system &>/dev/null 2>&1; then
    echo " ✓"
    break
  fi
  echo -n "."
  sleep 1
  if [[ $i -eq 30 ]]; then
    echo ""
    echo "❌  PostgreSQL 30 秒後仍未就緒，請檢查 Docker 狀態"
    exit 1
  fi
done

# ── 3. 執行 DB Migration（有 pending 才跑）────────────────────────────────────

echo "🗄️   檢查 DB migration 狀態…"
cd "$ROOT/web/packages/db"
MIGRATE_OUTPUT=$(pnpm exec prisma migrate status 2>&1 || true)
if echo "$MIGRATE_OUTPUT" | grep -q "following migrations have not yet been applied"; then
  echo "📦  套用 pending migrations…"
  pnpm exec prisma migrate deploy 2>&1 | tail -5
else
  echo "    migration 已是最新，跳過"
fi
cd "$ROOT"

# ── 4. 啟動 tmux session ──────────────────────────────────────────────────────

# 若已存在同名 session，先刪除
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "🔄  關閉既有 tmux session '$SESSION'…"
  tmux kill-session -t "$SESSION"
fi

echo "🖥️   建立 tmux session '$SESSION'…"

# Layout:
#  ┌─────────────────────┬─────────────────────┐
#  │  Playground :3000   │  Admin :3001         │
#  ├─────────────────────┴─────────────────────┤
#  │  Worker (Python)                           │
#  └────────────────────────────────────────────┘

# 建立 session + 第一個 pane（Playground）
tmux new-session -d -s "$SESSION" -x 220 -y 50 \
  -e "DATABASE_URL=$DATABASE_URL" \
  -c "$ROOT/web"

tmux send-keys -t "$SESSION:0.0" "pnpm --filter playground dev" Enter

# 垂直分割右側（Admin）
tmux split-window -t "$SESSION:0.0" -h \
  -e "DATABASE_URL=$DATABASE_URL" \
  -c "$ROOT/web"
tmux send-keys -t "$SESSION:0.1" "pnpm --filter admin dev" Enter

# 水平分割下方（Worker）
if [[ "$NO_WORKER" == "false" ]]; then
  tmux split-window -t "$SESSION:0.0" -v \
    -e "DATABASE_URL=$DATABASE_URL" \
    -c "$ROOT/worker"
  tmux send-keys -t "$SESSION:0.2" "uv run python -m worker.main dev" Enter
  # 讓下方 pane 佔 40% 高度
  tmux resize-pane -t "$SESSION:0.2" -y "40%"
fi

# 選取 Worker pane（或 Playground）
if [[ "$NO_WORKER" == "false" ]]; then
  tmux select-pane -t "$SESSION:0.2"
else
  tmux select-pane -t "$SESSION:0.0"
fi

# ── 5. Attach ──────────────────────────────────────────────────────────────────

echo ""
echo "✅  啟動完成！"
echo ""
echo "   Playground → http://localhost:3000"
echo "   Admin      → http://localhost:3001"
echo ""
echo "   tmux 操作："
echo "   Ctrl+B + 方向鍵   切換 pane"
echo "   Ctrl+B + z         pane 最大化/還原"
echo "   Ctrl+B + d         detach（服務繼續跑）"
echo "   tmux kill-session -t $SESSION  關閉所有服務"
echo ""

tmux attach-session -t "$SESSION"
