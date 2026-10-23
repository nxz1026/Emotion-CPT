#!/usr/bin/env bash
# P0-A：单 venv 兼容性实验
#
# 问题：emotion-core 的依赖（akshare/httpx/jinja2）装进同一个环境后，CPT 的全量测试还绿吗？
#
# 安全闸：跑前/跑后快照所有可能被写入的表的行数。
#   若**基线**（CPT 自己的 venv + 自己的测试）都动了生产库 ⇒ 立即中止，改隔离模式。
#
# 纪律：逐条对比失败名单，不数条数（上游有 2 个已知既存失败）。
set -u
DSH=/home/ubuntu/DSH
CPT=$DSH/Chan_Pattern_Trader
EMO=$DSH/emotion-core
WORK=/tmp/p0a
LOG=$WORK/p0a.log
mkdir -p "$WORK"

CPTVENV=$CPT/.venv/bin/python
MERGEDVENV=$WORK/venv/bin/python

snapshot() {
  # 只读：统计所有 cpt_* 表 + emotion 侧关键表的行数
  local PGHOST=$(sed -n 's/^\$RDSHOST=//p' /home/ubuntu/.dbconfig | head -1)
  local PGPW=$(sed -n 's/^\$DB_PW=//p' /home/ubuntu/.dbconfig | head -1)
  local DBN=$(sed -n 's/^\$DBNAME=//p' /home/ubuntu/.dbconfig | head -1)
  PGPASSWORD="$PGPW" psql -X -A -t -h "$PGHOST" -U postgres -d "${DBN:-emotion_core}" -c \
    "SELECT relname||'='||n_live_tup FROM pg_stat_user_tables WHERE schemaname='public' ORDER BY relname;" 2>/dev/null
}

echo "==================== P0-A 单 venv 兼容性实验 ====================" >>"$LOG"
date -u '+%Y-%m-%dT%H:%M:%SZ' >>"$LOG"
echo >>"$LOG"

if [ ! -x "$MERGEDVENV" ]; then
  echo "--- 建合并 venv（emotion 依赖 + CPT dev 依赖 + CPT db extra）---" >>"$LOG"
  python3 -m venv "$WORK/venv" >>"$LOG" 2>&1
  "$MERGEDVENV" -m pip install --quiet --upgrade pip >>"$LOG" 2>&1
  # emotion 的生产依赖
  "$MERGEDVENV" -m pip install --quiet -r "$EMO/requirements.txt" >>"$LOG" 2>&1
  # CPT 的开发依赖
  "$MERGEDVENV" -m pip install --quiet -r "$CPT/requirements-dev.txt" >>"$LOG" 2>&1
  # CPT 的 db extra（psycopg）
  (cd "$CPT" && "$MERGEDVENV" -m pip install --quiet -e '.[db]' >>"$LOG" 2>&1)
  echo "--- 建 venv 完成 ---" >>"$LOG"
fi

echo "--- 依赖版本对照 ---" >>"$LOG"
{
  echo "[CPT 原有 venv]"; "$CPTVENV" -m pip list 2>/dev/null | grep -iE '^(akshare|pandas|psycopg|httpx|jinja2|requests|ccxt|czsc|numpy|lxml) '
  echo "[合并 venv]"; "$MERGEDVENV" -m pip list 2>/dev/null | grep -iE '^(akshare|pandas|psycopg|httpx|jinja2|requests|ccxt|czsc|numpy|lxml) '
} >>"$LOG" 2>&1

echo "--- 快照(前) ---" >>"$LOG"
snapshot > "$WORK/snap_before.txt"

echo "--- 跑基线：CPT 自己的 venv ---" >>"$LOG"
(cd "$CPT" && "$CPTVENV" -m pytest tests -q --no-header -p no:cacheprovider > "$WORK/baseline.txt" 2>&1)
echo "baseline 退出码=$?" >>"$LOG"

echo "--- 快照(基线后) ---" >>"$LOG"
snapshot > "$WORK/snap_after_baseline.txt"
DIFF_BEFORE=$(diff "$WORK/snap_before.txt" "$WORK/snap_after_baseline.txt" | wc -l)
echo "基线是否动了生产库: diff 行数=$DIFF_BEFORE" >>"$LOG"
if [ "$DIFF_BEFORE" -gt 0 ]; then
  echo "!!! 基线就动了生产库 —— 中止，不跑合并环境 !!!" >>"$LOG"
  diff "$WORK/snap_before.txt" "$WORK/snap_after_baseline.txt" >>"$LOG" 2>&1
  exit 9
fi

echo "--- 跑合并环境 ---" >>"$LOG"
(cd "$CPT" && "$MERGEDVENV" -m pytest tests -q --no-header -p no:cacheprovider > "$WORK/merged.txt" 2>&1)
echo "merged 退出码=$?" >>"$LOG"

echo "--- 快照(合并后) ---" >>"$LOG"
snapshot > "$WORK/snap_after_merged.txt"
diff "$WORK/snap_after_baseline.txt" "$WORK/snap_after_merged.txt" >>"$LOG" 2>&1
echo "合并环境是否动了生产库: diff 行数=$(diff "$WORK/snap_after_baseline.txt" "$WORK/snap_after_merged.txt" | wc -l)" >>"$LOG"

echo "--- 失败名单对比 ---" >>"$LOG"
grep -E '^(FAILED|ERROR)' "$WORK/baseline.txt" | sort > "$WORK/fails_baseline.txt"
grep -E '^(FAILED|ERROR)' "$WORK/merged.txt"    | sort > "$WORK/fails_merged.txt"
echo "基线失败条数: $(wc -l < "$WORK/fails_baseline.txt")" >>"$LOG"
echo "合并失败条数: $(wc -l < "$WORK/fails_merged.txt")" >>"$LOG"
echo "[仅合并环境失败(新增)]:" >>"$LOG"
comm -13 "$WORK/fails_baseline.txt" "$WORK/fails_merged.txt" >>"$LOG" 2>&1
echo "[仅基线失败(合并后消失)]:" >>"$LOG"
comm -23 "$WORK/fails_baseline.txt" "$WORK/fails_merged.txt" >>"$LOG" 2>&1
echo "--- 结论 ---" >>"$LOG"
if diff -q "$WORK/fails_baseline.txt" "$WORK/fails_merged.txt" >/dev/null; then
  echo "✅ 失败名单完全一致 ⇒ 合并环境与基线等价（依赖兼容）" >>"$LOG"
else
  echo "⚠️ 失败名单有差异 ⇒ 见上面的新增/消失清单" >>"$LOG"
fi
date -u '+%Y-%m-%dT%H:%M:%SZ' >>"$LOG"
echo "P0A_DONE" >>"$LOG"
