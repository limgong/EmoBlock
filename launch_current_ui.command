#!/bin/zsh
set -eu
task_root="$(cd -- "$(dirname -- "$0")" && pwd)"
task_python="$task_root/.venv/bin/python"
if [[ ! -x "$task_python" ]]; then
  task_python="$task_root/../../EmoBlock/.venv/bin/python"
fi
if [[ ! -x "$task_python" ]]; then
  print -u2 '未找到已有 Python 环境。请按项目 README 配置环境后运行 run.py。'
  exit 1
fi
cd "$task_root"
export PYTHONDONTWRITEBYTECODE=1
export EMOBLOCKS_DATA_DIR="${EMOBLOCKS_DATA_DIR:-$HOME/Library/Application Support/EmoBlocks/mainline-ui}"
exec "$task_python" -B run.py
