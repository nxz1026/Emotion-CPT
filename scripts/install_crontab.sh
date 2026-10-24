#!/usr/bin/env bash
# 把 crontab **真相源**装到线上机器。
#
# ★ 为什么需要它：真相源在 Emotion-CPT 包内（随包分发），而线上 crontab 是
#   机器上的状态 —— 两者之间必须有**一条确定性的路径**，否则就回到
#   「改了仓、忘了装、线上还在跑旧的」这类静默漂移。
#   2026-10-24 实测：因子重算的日志重定向在改调度时被弄丢，
#   而线上 crontab 与仓内副本**已经不一致了**，没人发现。
#
# 用法：
#   scripts/install_crontab.sh            # 装 + 校验
#   scripts/install_crontab.sh --check    # 只校验，不装
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${EMOTION_CPT_REPO:-$(cd "$HERE/.." && pwd)}"
TRUTH="${TRUTH:-$REPO/src/emotion_cpt/deploy/cron/crontab}"
BACKUP_DIR="${BACKUP_DIR:-/home/ubuntu/logs}"

if [[ ! -f "$TRUTH" ]]; then
  echo "❌ 找不到 crontab 真相源：$TRUTH" >&2
  exit 1
fi

echo "真相源：$TRUTH"

if [[ "${1:-}" == "--check" ]]; then
  if crontab -l 2>/dev/null | diff -q - "$TRUTH" >/dev/null; then
    echo "✅ 线上 crontab 已与真相源一致"
    exit 0
  fi
  echo "❌ 线上 crontab 与真相源不一致" >&2
  diff <(crontab -l 2>/dev/null) "$TRUTH" >&2 || true
  exit 1
fi

mkdir -p "$BACKUP_DIR"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$BACKUP_DIR/crontab.backup.$ts"
crontab -l > "$backup" 2>/dev/null || : # 原本就没有 crontab 也不该失败
echo "已备份原 crontab → $backup"

crontab "$TRUTH"
echo "已安装。校验中……"
if crontab -l 2>/dev/null | diff -q - "$TRUTH" >/dev/null; then
  echo "✅ 线上 crontab 已与真相源一致"
else
  echo "❌ 安装后校验不一致（已保留备份 $backup）" >&2
  diff <(crontab -l 2>/dev/null) "$TRUTH" >&2 || true
  exit 1
fi
