#!/usr/bin/env bash
# emotion 看板存活看门狗 —— 每 5 分钟探一次 8098，不通就拉起。
#
# ## 为什么它归 Emotion-CPT
#
# 它守的是 **emotion-core-dash.service**（统一入口体系的一环）。
# 此前这条作业**只活在线上 crontab 里、任何仓都没有** ⇒
# 重建环境时它会静默消失，而看板挂了**没人知道**（因为没有告警，只有没人看）。
#
# 现在它是 Emotion-CPT 仓内文件，仓内 crontab 真相源里有它，
# 且门禁（`check_crontab.py`）会检查它**存在且有执行位**。
#
# ## 为什么不用 systemd timer
#
# systemd 的 `Restart=on-failure` 只在**进程退出**时触发；
# 进程还在但**端口不响应**（线程卡死 / 假死）时 systemd 不会管。
# 端口探活补的正是这个洞。
set -uo pipefail

PORT="${EMOTION_DASH_PORT:-8098}"
LOG=/home/ubuntu/logs/ec-dash-watchdog.log
SERVICE=emotion-core-dash.service

mkdir -p "$(dirname "$LOG")"

if curl -sf --max-time 8 -o /dev/null "http://127.0.0.1:${PORT}/"; then
  exit 0
fi

echo "[$(date -u +%FT%TZ)] ${SERVICE} 探活失败（:${PORT}），拉起" >>"$LOG"
sudo -n systemctl restart "$SERVICE" >>"$LOG" 2>&1
