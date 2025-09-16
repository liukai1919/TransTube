#!/bin/bash

# TransTube 本地启动脚本（非 Docker）
# 支持: start | stop | restart | status | logs [backend|frontend] | install

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
VENV_DIR="$PROJECT_ROOT/.venv"
LOG_DIR="$PROJECT_ROOT/.logs"
RUN_DIR="$PROJECT_ROOT/.run"

BACKEND_PORT=${BACKEND_PORT:-8001}
FRONTEND_PORT=${FRONTEND_PORT:-3002}

BACKEND_PID="$RUN_DIR/backend.pid"
FRONTEND_PID="$RUN_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

ensure_dirs() {
  mkdir -p "$LOG_DIR" "$RUN_DIR"
  mkdir -p "$BACKEND_DIR/static/videos" "$BACKEND_DIR/static/subtitles" "$BACKEND_DIR/tasks" "$BACKEND_DIR/downloads"
  # 预创建日志文件，避免 tail 报错
  touch "$BACKEND_LOG" "$FRONTEND_LOG"
}

check_ffmpeg() {
  if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "⚠️  未检测到 ffmpeg，某些音视频处理功能将不可用。"
    echo "   安装示例: sudo apt-get update && sudo apt-get install -y ffmpeg"
  fi
}

ensure_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    echo "🧪 创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
  fi
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
}

install_python_deps() {
  echo "📦 安装后端 Python 依赖..."
  # 根依赖
  if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/requirements.txt"
  fi
  # backend 依赖
  if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
  fi
  # 运行所需
  "$VENV_DIR/bin/pip" install -U fastapi uvicorn[standard] python-multipart

  # 可配置的 PyTorch 安装（仅在缺失或强制重装时执行）
  # 支持环境变量：
  #  - PYTORCH_FORCE_REINSTALL=1         强制重装 torch 系列
  #  - PYTORCH_INDEX_URL=<url>          直接指定 index-url
  #  - PYTORCH_CUDA=cu128|cu124|cu121|cpu  选择 CUDA/CPU 版本，默认 cu124
  #  - PYTORCH_NIGHTLY=1                使用 nightly 通道
  need_torch_install=0
  if ! "$VENV_DIR/bin/python" -c 'import torch' >/dev/null 2>&1; then
    need_torch_install=1
  fi
  if [ "${PYTORCH_FORCE_REINSTALL:-0}" = "1" ]; then
    need_torch_install=1
    "$VENV_DIR/bin/pip" uninstall -y torch torchvision torchaudio >/dev/null 2>&1 || true
  fi
  if [ "$need_torch_install" = "1" ]; then
    cuda_flavor="${PYTORCH_CUDA:-cu124}"
    if [ -n "${PYTORCH_INDEX_URL:-}" ]; then
      index_url="$PYTORCH_INDEX_URL"
    else
      base="https://download.pytorch.org/whl"
      if [ "${PYTORCH_NIGHTLY:-0}" = "1" ]; then
        base="$base/nightly"
      fi
      if [ "$cuda_flavor" = "cpu" ]; then
        index_url="$base/cpu"
      else
        index_url="$base/$cuda_flavor"
      fi
    fi
    echo "⚙️  安装 PyTorch (${PYTORCH_NIGHTLY:+nightly }${cuda_flavor}) via $index_url"
    "$VENV_DIR/bin/pip" install --index-url "$index_url" torch torchvision torchaudio || true
  fi

  # Whisper + 相关
  "$VENV_DIR/bin/pip" install whisper-timestamped || true
}

ensure_nvm() {
  export NVM_DIR="$HOME/.nvm"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    echo "⬇️  安装 nvm..."
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  fi
  # shellcheck disable=SC1090
  . "$NVM_DIR/nvm.sh"
}

ensure_node() {
  ensure_nvm
  nvm install 20 >/dev/null
  nvm use 20 >/dev/null
}

is_running() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file" 2>/dev/null || echo "")
    if [ -n "${pid}" ] && kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

start_backend() {
  if is_running "$BACKEND_PID"; then
    echo "✅ 后端已在运行 (PID $(cat "$BACKEND_PID"))"
    return 0
  fi
  echo "🚀 启动后端 (FastAPI @ :$BACKEND_PORT)..."
  ensure_dirs
  "$VENV_DIR/bin/python" -c 'import sys; print(sys.version)'>/dev/null || ensure_venv
  "$VENV_DIR/bin/python" -c 'import fastapi' >/dev/null 2>&1 || install_python_deps
  check_ffmpeg
  # 若端口被占用，尝试清理旧进程
  if ss -ltn 2>/dev/null | grep -q ":$BACKEND_PORT\\b"; then
    echo "ℹ️  端口 $BACKEND_PORT 被占用，尝试清理旧的 uvicorn..."
    pkill -f "uvicorn main:app" 2>/dev/null || true
    sleep 1
  fi
  (
    cd "$BACKEND_DIR"
    # 载入根目录 .env（若存在）
    if [ -f "$PROJECT_ROOT/.env" ]; then
      set -a
      # shellcheck disable=SC1090
      . "$PROJECT_ROOT/.env"
      set +a
    fi
    nohup "$VENV_DIR/bin/python" -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload \
      >>"$BACKEND_LOG" 2>&1 & echo $! >"$BACKEND_PID"
  )
  sleep 1
  if is_running "$BACKEND_PID"; then
    echo "✅ 后端已启动，日志: $BACKEND_LOG"
  else
    echo "❌ 后端启动失败，查看日志: $BACKEND_LOG"
    return 1
  fi
}

start_frontend() {
  if is_running "$FRONTEND_PID"; then
    echo "✅ 前端已在运行 (PID $(cat "$FRONTEND_PID"))"
    return 0
  fi
  echo "🚀 启动前端 (Next.js @ :$FRONTEND_PORT)..."
  ensure_node
  (
    cd "$FRONTEND_DIR"
    if [ -f package-lock.json ]; then
      npm ci --no-audit --no-fund >/dev/null
    else
      npm install --no-audit --no-fund >/dev/null
    fi
    nohup npm run dev >>"$FRONTEND_LOG" 2>&1 & echo $! >"$FRONTEND_PID"
  )
  sleep 1
  if is_running "$FRONTEND_PID"; then
    echo "✅ 前端已启动，日志: $FRONTEND_LOG"
  else
    echo "❌ 前端启动失败，查看日志: $FRONTEND_LOG"
    return 1
  fi
}

stop_proc() {
  local name="$1" pid_file="$2"
  if is_running "$pid_file"; then
    local pid
    pid=$(cat "$pid_file")
    echo "🛑 停止 $name (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    for i in {1..20}; do
      if kill -0 "$pid" 2>/dev/null; then sleep 0.2; else break; fi
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "⚠️  进程未退出，强制杀死..."
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
    echo "✅ $name 已停止"
  else
    echo "ℹ️  $name 未在运行"
  fi
}

status_port() {
  local port="$1" label="$2"
  if ss -ltn 2>/dev/null | grep -q ":$port\b"; then
    echo "🔌 $label 端口 $port: LISTENING"
  else
    echo "🔌 $label 端口 $port: DOWN"
  fi
}

status() {
  echo "==== 服务状态 ===="
  if is_running "$BACKEND_PID"; then
    echo "后端: RUNNING (PID $(cat "$BACKEND_PID"))  日志: $BACKEND_LOG"
  else
    echo "后端: STOPPED"
  fi
  status_port "$BACKEND_PORT" "后端"
  if is_running "$FRONTEND_PID"; then
    echo "前端: RUNNING (PID $(cat "$FRONTEND_PID"))  日志: $FRONTEND_LOG"
  else
    echo "前端: STOPPED"
  fi
  status_port "$FRONTEND_PORT" "前端"
}

logs() {
  local target="${1:-all}"
  # 移除第一个参数（目标），保留其余作为日志选项
  if [ $# -gt 0 ]; then shift; fi
  local follow=""
  local lines=200
  # 解析简单参数 -f/--follow 与 -n N 或 --lines=N
  while [ $# -gt 0 ]; do
    case "$1" in
      -f|--follow)
        follow="-f"; shift ;;
      -n)
        shift; lines="${1:-200}"; shift ;;
      --lines=*)
        lines="${1#*=}"; shift ;;
      *)
        # 未知参数，忽略
        shift ;;
    esac
  done
  ensure_dirs
  [ -f "$BACKEND_LOG" ] || touch "$BACKEND_LOG"
  [ -f "$FRONTEND_LOG" ] || touch "$FRONTEND_LOG"
  case "$target" in
    backend) tail -n "$lines" $follow "$BACKEND_LOG" ;;
    frontend) tail -n "$lines" $follow "$FRONTEND_LOG" ;;
    *) echo "--- backend ($BACKEND_LOG) ---"; tail -n "$lines" "$BACKEND_LOG" || true; echo ""; echo "--- frontend ($FRONTEND_LOG) ---"; tail -n "$lines" "$FRONTEND_LOG" || true ;;
  esac
}

install_all() {
  ensure_dirs
  ensure_venv
  install_python_deps
  ensure_node
  echo "✅ 依赖安装完成"
}

usage() {
  cat <<EOF
用法: $(basename "$0") <command>

命令:
  start           启动后端与前端
  stop            停止后端与前端
  restart         重启后端与前端
  status          查看状态与端口
  logs [name]     查看日志（backend|frontend|all）
                  选项: -n N 显示最近 N 行（默认 200）
                        -f, --follow 跟随输出
  install         安装/更新依赖（Python 与 Node）
EOF
}

cmd="${1:-start}"
case "$cmd" in
  start)
    ensure_dirs
    start_backend
    if [ "${SKIP_FRONTEND:-0}" != "1" ]; then
      start_frontend
    else
      echo "⏭️  已跳过前端启动 (SKIP_FRONTEND=1)"
    fi
    status
    ;;
  start-backend)
    ensure_dirs
    start_backend
    status_port "$BACKEND_PORT" "后端"
    ;;
  start-frontend)
    ensure_dirs
    start_frontend
    status_port "$FRONTEND_PORT" "前端"
    ;;
  stop)
    stop_proc "后端" "$BACKEND_PID"
    stop_proc "前端" "$FRONTEND_PID"
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  status)
    status
    ;;
  logs)
    shift || true
    logs "${1:-all}"
    ;;
  install)
    install_all
    ;;
  *)
    usage
    exit 1
    ;;
esac
