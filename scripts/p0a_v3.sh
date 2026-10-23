#!/usr/bin/env bash
# P0-A v3：补齐 CPT 的 extras（db + crypto + chan）⇒ 合并 venv 才是真正的"并集"
# v2 的教训：缺 czsc/ccxt ⇒ 合并侧多 skip 22 条 ⇒ 表面全绿是假的
set -u
CPT=/home/ubuntu/DSH/Chan_Pattern_Trader
EMO=/home/ubuntu/DSH/emotion-core
W=/tmp/p0v3
M=/tmp/p0v2/venv/bin/python
[ -x "$M" ] || { python3 -m venv /tmp/p0v2/venv; }
mkdir -p "$W/isolated-home"
export HOME="$W/isolated-home"          # 无 .dbconfig ⇒ 够不到生产库
LOG=$W/p0a_v3.log

echo "==================== P0-A v3（补齐 extras）====================" >"$LOG"
date -u '+%Y-%m-%dT%H:%M:%SZ' >>"$LOG"

echo "--- 补装 CPT extras: db + crypto(ccxt) + chan(czsc) ---" >>"$LOG"
(cd "$CPT" && "$M" -m pip install --quiet -e '.[db,crypto,chan]' >>"$LOG" 2>&1)
echo "--- 合并 venv 依赖全量 ---" >>"$LOG"
"$M" -m pip list 2>/dev/null | grep -iE '^(akshare|pandas|psycopg|httpx|jinja2|requests|ccxt|czsc) ' >>"$LOG"
echo "--- 基线 venv 依赖全量 ---" >>"$LOG"
"$CPT/.venv/bin/python" -m pip list 2>/dev/null | grep -iE '^(akshare|pandas|psycopg|httpx|jinja2|requests|ccxt|czsc) ' >>"$LOG"

summary() {  # 抓 pytest 末尾摘要行
  grep -E '=+ .*(passed|failed|error).* =+' "$1" | tail -1
}
skips() { grep -c '^SKIPPED' "$1"; }

(cd "$CPT" && "$CPT/.venv/bin/python" -m pytest tests -q --no-header -p no:cacheprovider >"$W/base.txt" 2>&1)
(cd "$CPT" && "$M"                -m pytest tests -q --no-header -p no:cacheprovider >"$W/merged.txt" 2>&1)

echo "--- 基线 ---" >>"$LOG"; summary "$W/base.txt"   >>"$LOG"; echo "  skip 行数=$(skips "$W/base.txt")" >>"$LOG"
echo "--- 合并 ---" >>"$LOG"; summary "$W/merged.txt" >>"$LOG"; echo "  skip 行数=$(skips "$W/merged.txt")" >>"$LOG"

fails_of() { grep -E '^(FAILED|ERROR)' "$1" | sed -E 's/ - .*//' | sort -u; }
fails_of "$W/base.txt"   >"$W/f1.txt"
fails_of "$W/merged.txt" >"$W/f2.txt"
echo "失败条数: 基线=$(wc -l <"$W/f1.txt") 合并=$(wc -l <"$W/f2.txt")" >>"$LOG"
echo "[仅合并失败]:" >>"$LOG"; comm -13 "$W/f1.txt" "$W/f2.txt" >>"$LOG" 2>&1
echo "[仅基线失败]:" >>"$LOG"; comm -23 "$W/f1.txt" "$W/f2.txt" >>"$LOG" 2>&1
SB=$(skips "$W/base.txt"); SM=$(skips "$W/merged.txt")
if diff -q "$W/f1.txt" "$W/f2.txt" >/dev/null && [ "$SB" = "$SM" ]; then
  echo "✅ P0-A v3 结论：失败名单一致 且 skip 数一致（$SB）⇒ 单 venv 与现有 venv 等价" >>"$LOG"
else
  echo "⚠️ P0-A v3 结论：失败差异或 skip 数差异（基线 skip=$SB 合并 skip=$SM）⇒ 仍不等价" >>"$LOG"
fi
date -u '+%Y-%m-%dT%H:%M:%SZ' >>"$LOG"; echo "P0A_V3_DONE" >>"$LOG"
