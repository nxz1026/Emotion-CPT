#!/usr/bin/env bash
# emotion 看板存活看门狗 —— 每 5 分钟探一次，不通就拉起。
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
#
# ## ★ 探哪个路径（2026-10-24 实测改过）
#
# 原来探 `/` —— 那是**整个 app 最慢的路径**：
# **实测 5.97 秒**（服务端渲染整页看板 + 查库）。
# 而看门狗的超时是 8 秒 ⇒ 只剩 2 秒余量 ⇒
# 看板稍慢就会被判成「挂了」⇒ **每 5 分钟重启一次健康的看板**，
# 用户看到的是反复刷新和短暂 502。**那比没有看门狗更糟。**
#
# 现在探一个**廉价路径**（404 路径，实测 0.5ms 返回），并且
# **任何 HTTP 响应都算活着**（只有连不上 = 000 才算死）。
#
# 这不只是快：liveness 要问的是「这个进程还能处理请求吗」。
# 廉价路径若也超时，说明**连请求分发都卡住了**（线程池耗尽 / 假死）——
# 那正是要重启的故障。而整页渲染慢，可能只是数据多，**重启它也修不好**，
# 反而把好端端的进程换掉。
#
# ⚠️ 治本的方案是给 emotion-core 的 server 加一个真 `/health` 端点
#    （现在是 404），那样探活语义更清楚。已记为后续项。
set -uo pipefail

PORT="${EMOTION_DASH_PORT:-8098}"
LOG=/home/ubuntu/logs/ec-dash-watchdog.log
# SERVICE 可被环境变量覆盖 ⇒ **注入测试时不会真去重启生产看板**
SERVICE="${EMOTION_DASH_SERVICE:-emotion-core-dash.service}"
PROBE_PATH="${EMOTION_DASH_PROBE_PATH:-/__liveness_probe__}"
MAX_TIME="${EMOTION_DASH_MAX_TIME:-10}"
SLOW_MS="${EMOTION_DASH_SLOW_MS:-3000}"

mkdir -p "$(dirname "$LOG")"

# 任何 HTTP 响应都算活着；连不上（000）才算死
out="$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time "$MAX_TIME" \
  "http://127.0.0.1:${PORT}${PROBE_PATH}" 2>/dev/null || echo "000 0")"
code="${out%% *}"
secs="${out##* }"

if [[ "$code" == "000" ]]; then
  echo "[$(date -u +%FT%TZ)] ${SERVICE} 探活失败（:${PORT}${PROBE_PATH} 无响应，耗时 ${secs}s），拉起" >>"$LOG"
  sudo -n systemctl restart "$SERVICE" >>"$LOG" 2>&1
  exit 0
fi

# 活着但慢：只记不动（重启解决不了「数据多导致的慢」）
slow_ms="$(awk -v s="$secs" 'BEGIN{printf "%d", s*1000}')"
if [[ "$slow_ms" -gt "$SLOW_MS" ]]; then
  echo "[$(date -u +%FT%TZ)] ${SERVICE} 探活正常但偏慢（${slow_ms}ms > ${SLOW_MS}ms），未重启" >>"$LOG"
fi
exit 0
