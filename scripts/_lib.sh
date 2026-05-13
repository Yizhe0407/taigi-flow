#!/usr/bin/env bash
# 共用函式庫 — 由 dev.sh / prod.sh 引入，不直接執行

# ── 前置檢查 ──────────────────────────────────────────────────────────────────

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

check_prereqs() {
  check_cmd tmux
  check_cmd docker
  check_cmd pnpm
  check_cmd uv
}

# ── 環境變數載入 ───────────────────────────────────────────────────────────────

load_env() {
  local env_file="$1"
  if [[ ! -f "$env_file" ]]; then
    echo "❌  找不到 $env_file"
    echo "    cp .env.example $env_file  # 並填入必要環境變數"
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "❌  $env_file 缺少 DATABASE_URL"
    exit 1
  fi
  echo "🔑  使用環境變數：$env_file"
}

# ── 清理殘留 port 程序 ─────────────────────────────────────────────────────────

kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "清除 port ${port} 上的舊程序 (PID: ${pids})"
    echo "${pids}" | xargs kill -TERM 2>/dev/null || true
    sleep 1
    # 強制殺掉還在的
    pids=$(lsof -ti tcp:"${port}" 2>/dev/null || true)
    [[ -n "${pids}" ]] && echo "${pids}" | xargs kill -KILL 2>/dev/null || true
  fi
}

kill_web_ports() {
  kill_port 3000
  kill_port 3001
}

# ── Docker + PostgreSQL ────────────────────────────────────────────────────────

start_infra() {
  local root="$1"
  echo "🐳  啟動 Docker 服務…"
  # 用完整 compose up 確保所有容器在同一 network
  docker compose -f "$root/docker-compose.yml" up -d 2>&1 \
    | grep -vE "^$|^Network|^Volume" || true

  echo -n "⏳  等待 PostgreSQL 就緒"
  for i in $(seq 1 30); do
    if docker exec taigi-flow-postgres-1 pg_isready -U admin -d agent_system &>/dev/null 2>&1; then
      echo " ✓"
      return 0
    fi
    echo -n "."
    sleep 1
  done
  echo ""
  echo "❌  PostgreSQL 30 秒後仍未就緒，請檢查 Docker 狀態"
  exit 1
}

# ── DB Migration ───────────────────────────────────────────────────────────────

run_migrations() {
  local root="$1"
  echo "🗄️   檢查 DB migration 狀態…"
  cd "$root/web/packages/db"
  local status
  status=$(pnpm exec prisma migrate status 2>&1 || true)
  if echo "$status" | grep -q "following migrations have not yet been applied"; then
    echo "📦  套用 pending migrations…"
    pnpm exec prisma migrate deploy 2>&1 | tail -5
  else
    echo "    migration 已是最新，跳過"
  fi
  cd "$root"
}

# ── tmux session ──────────────────────────────────────────────────────────────

kill_existing_session() {
  local session="$1"
  if tmux has-session -t "$session" 2>/dev/null; then
    echo "🔄  關閉既有 tmux session '$session'…"
    tmux kill-session -t "$session"
  fi
}

print_ready_msg() {
  local session="$1" mode="$2"
  echo ""
  echo "✅  [$mode] 啟動完成！"
  echo ""
  echo "   Playground → http://localhost:3000"
  echo "   Admin      → http://localhost:3001"
  echo ""
  echo "   ┌─ tmux 基本操作 ──────────────────────────────┐"
  echo "   │  Ctrl+B → 方向鍵   切換 pane                │"
  echo "   │  Ctrl+B → z         目前 pane 最大化/還原    │"
  echo "   │  Ctrl+B → d         detach（程序繼續跑）     │"
  echo "   │  Ctrl+B → [         進入捲動模式（q 退出）   │"
  echo "   └──────────────────────────────────────────────┘"
  echo ""
  echo "   停止所有服務：tmux kill-session -t $session"
  echo ""
}
