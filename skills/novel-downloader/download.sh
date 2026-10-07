#!/usr/bin/env bash
# 一步式下载 80ge 小说：搜索 -> 选择 -> 打开浏览器 -> 按回车确认 -> 处理。
# 用法： ./download.sh "书名"
# 可选环境变量： PYTHON=python3  OUTPUT_DIR=~/Downloads/novels
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

OUTPUT_ARG=()
if [ -n "${OUTPUT_DIR:-}" ]; then
  OUTPUT_ARG=(--output-dir "$OUTPUT_DIR")
fi

exec "$PYTHON" "$DIR/scripts/quick_download.py" "$@" "${OUTPUT_ARG[@]}"
