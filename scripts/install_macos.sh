#!/usr/bin/env bash
# macOS (Apple Silicon) 安装脚本：建 venv、装依赖、跑体检。
#
#   bash scripts/install_macos.sh
#
# 需要先装好：Xcode Command Line Tools、Homebrew、Python 3.12、adb
#   xcode-select --install
#   brew install python@3.12 android-platform-tools

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"

echo "== 1/4 检查 Python =="
"$PY" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"需要 Python 3.11+，当前 {sys.version.split()[0]}")
print("python", sys.version.split()[0], sys.platform)
PY

echo "== 2/4 建虚拟环境 =="
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null

echo "== 3/4 装依赖 =="
# ok-script 的依赖里写死 pywin32，必须 --no-deps 分开装
if ! python -c "import ok" >/dev/null 2>&1; then
  pip install --no-deps "ok-script[ocr,qt]==2.0.6"
fi
pip install -r requirements-macos.txt

echo "== 4/4 体检 =="
python main_macos.py --selftest || {
  echo
  echo "体检没通过。把上面输出的最后一段贴出来再排查。"
  echo "常见原因：BlueStacks Air 没开 ADB、端口不是 5555、游戏没装。"
  exit 1
}

echo
echo "装好了。以后这样启动："
echo "  cd \"$ROOT\" && source .venv/bin/activate && python main_macos.py"
