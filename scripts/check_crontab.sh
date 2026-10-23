#!/usr/bin/env bash
# crontab 双向对账门禁。
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" -m emotion_cpt.cli.check_crontab "$@"
