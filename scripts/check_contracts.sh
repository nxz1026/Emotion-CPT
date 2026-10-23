#!/usr/bin/env bash
# 契约一致性门禁（只读）。CI 与本地同一条命令。
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" -m emotion_cpt.cli.check_contracts "$@"
