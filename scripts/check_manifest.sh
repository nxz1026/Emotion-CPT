#!/usr/bin/env bash
# 表 manifest 门禁（只读，需要凭据与 psycopg）。
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" -m emotion_cpt.cli.check_manifest "$@"
