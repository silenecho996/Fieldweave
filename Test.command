#!/bin/bash
# Fieldweave tests for macOS. Double-click this file in Finder.
set -u

cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:$PATH"

find_python() {
    if [ -n "${PYTHON:-}" ]; then
        if "$PYTHON" -c 'import sqlite3, sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            printf '%s\n' "$PYTHON"
            return 0
        fi
        return 1
    fi
    for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python; do
        if ! command -v "$candidate" >/dev/null 2>&1; then
            continue
        fi
        if "$candidate" -c 'import sqlite3, sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN="$(find_python)"
if [ -z "$PYTHON_BIN" ]; then
    printf '\n未找到 Python 3.10 或更新版本。\n'
    printf '请从 https://www.python.org/downloads/macos/ 安装，\n'
    printf '或运行 brew install python 后重新双击 Test.command。\n\n'
    read -r -p '按回车键关闭窗口...' _
    exit 1
fi

printf '使用 %s 运行测试...\n' "$PYTHON_BIN"
"$PYTHON_BIN" -B -m unittest discover -s tests -v
status=$?
printf '\n测试结束（退出码 %s）。\n' "$status"
read -r -p '按回车键关闭窗口...' _
exit "$status"
