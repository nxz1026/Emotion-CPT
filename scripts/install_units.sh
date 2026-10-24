#!/usr/bin/env bash
# 把 systemd unit **真相源**装到线上机器。
#
# ★ 为什么需要它：unit 真相源在 Emotion-CPT 包内（随包分发），
#   而 `/etc/systemd/system/` 是机器上的状态 —— 两者之间必须有
#   **一条确定性的路径**，否则就回到「改了仓、忘了装、线上还在跑旧的」。
#   2026-10-07 审计实测过：生产与仓内副本严重漂移，4 个单元只存在于生产。
#
# 用法：
#   scripts/install_units.sh              # 装 + daemon-reload + 校验
#   scripts/install_units.sh --check      # 只校验，不装
#   scripts/install_units.sh --no-restart # 装但不重启（reload 而已）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${EMOTION_CPT_REPO:-$(cd "$HERE/.." && pwd)}"
TRUTH="${TRUTH:-$REPO/src/emotion_cpt/deploy/systemd}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
BACKUP_DIR="${BACKUP_DIR:-/home/ubuntu/logs/systemd-backup}"

if [[ ! -d "$TRUTH" ]]; then
  echo "❌ 找不到 unit 真相源：$TRUTH" >&2
  exit 1
fi

mapfile -t UNITS < <(find "$TRUTH" -maxdepth 1 \( -name '*.service' -o -name '*.timer' \) | sort)
if [[ ${#UNITS[@]} -eq 0 ]]; then
  echo "❌ 真相源里没有 unit：$TRUTH" >&2
  exit 1
fi
echo "真相源：$TRUTH（${#UNITS[@]} 个单元）"

check() {
  local bad=0
  for u in "${UNITS[@]}"; do
    local name rel
    name="$(basename "$u")"
    rel="${u#"$TRUTH"/}"
    if [[ -f "$SYSTEMD_DIR/$rel" ]] && diff -q "$u" "$SYSTEMD_DIR/$rel" >/dev/null; then
      continue
    fi
    echo "  ⚠️ $rel 与线上不一致" >&2
    bad=1
  done
  return $bad
}

if [[ "${1:-}" == "--check" ]]; then
  if check; then
    echo "✅ 线上 unit 已与真相源一致"
    exit 0
  fi
  echo "❌ 线上 unit 与真相源不一致" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$BACKUP_DIR/$ts"
mkdir -p "$backup"
for u in "${UNITS[@]}"; do
  rel="${u#"$TRUTH"/}"
  [[ -f "$SYSTEMD_DIR/$rel" ]] && cp -a "$SYSTEMD_DIR/$rel" "$backup/$(echo "$rel" | tr '/' '_')" || true
done
echo "已备份线上同名单元 → $backup"

for u in "${UNITS[@]}"; do
  rel="${u#"$TRUTH"/}"
  # ⚠️ /etc/systemd/system 要 root ⇒ 必须 sudo（这台机器上免密）
  sudo -n install -D -m 0644 "$u" "$SYSTEMD_DIR/$rel"
done

sudo -n systemctl daemon-reload
echo "已安装并 daemon-reload。"

if [[ "${1:-}" != "--no-restart" ]]; then
  echo "重启单元……"
  for u in "${UNITS[@]}"; do
    rel="${u#"$TRUTH"/}"
    name="$(basename "$rel")"
    if [[ "$name" == *.timer ]]; then
      sudo -n systemctl restart "$name" || echo "  ⚠️ 重启 $name 失败"
    else
      sudo -n systemctl try-restart "$name" || true  # 没在跑就不动
    fi
  done
fi

echo "校验中……"
if check; then
  echo "✅ 线上 unit 已与真相源一致"
else
  echo "❌ 校验不一致（已保留备份 $backup）" >&2
  exit 1
fi
