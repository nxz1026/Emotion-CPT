#!/usr/bin/env bash
# P0-C：没有平台相关二进制（emotion_core_rust.so, ELF aarch64）时，
#        emotion-core 的测试是否仍全绿？
#
# 意义：决定单仓 CI 要不要引入 Rust 工具链。
# 做法：把 emotion-core 复制到 /tmp 并**删掉 .so**（副本，不动生产仓），
#        用它自己的 venv 跑全量测试。
# 安全闸：跑前/跑后快照表行数，动了就报。
set -u
EMO=/home/ubuntu/DSH/emotion-core
WORK=/tmp/p0c
COPY=$WORK/emotion-core-noso
LOG=$WORK/p0c.log
mkdir -p "$WORK"

snapshot() {
  local PGHOST=$(sed -n 's/^\$RDSHOST=//p' /home/ubuntu/.dbconfig | head -1)
  local PGPW=$(sed -n 's/^\$DB_PW=//p' /home/ubuntu/.dbconfig | head -1)
  local DBN=$(sed -n 's/^\$DBNAME=//p' /home/ubuntu/.dbconfig | head -1)
  PGPASSWORD="$PGPW" psql -X -A -t -h "$PGHOST" -U postgres -d "${DBN:-emotion_core}" -c \
    "SELECT relname||'='||n_live_tup FROM pg_stat_user_tables WHERE schemaname='public' ORDER BY relname;" 2>/dev/null
}

echo "==================== P0-C 无 .so 兼容性实验 ====================" >>"$LOG"
date -u '+%Y-%m-%dT%H:%M:%SZ' >>"$LOG"

if [ ! -d "$COPY" ]; then
  echo "--- 复制仓到 $COPY 并移除 .so ---" >>"$LOG"
  cp -a "$EMO" "$COPY"
  rm -f "$COPY/src/core_lib/emotion_core_rust.so"
  rm -rf "$COPY/.git"
fi
echo "--- .so 是否已移除: $([ -f "$COPY/src/core_lib/emotion_core_rust.so" ] && echo 仍在 || echo 已移除) ---" >>"$LOG"
echo "--- 生产仓的 .so 是否还在: $([ -f "$EMO/src/core_lib/emotion_core_rust.so" ] && echo 在 || echo 不在) ---" >>"$LOG"

echo "--- 生产仓基线(有 .so) ---" >>"$LOG"
(cd "$EMO" && "$EMO/.venv/bin/python" -m pytest tests -q --no-header -p no:cacheprovider > "$WORK/baseline.txt" 2>&1)
echo "baseline 退出码=$?" >>"$LOG"
snapshot > "$WORK/snap_a.txt"

echo "--- 副本(无 .so) ---" >>"$LOG"
(cd "$COPY" && PYTHONPATH="$COPY/src" "$EMO/.venv/bin/python" -m pytest tests -q --no-header -p no:cacheprovider > "$WORK/noso.txt" 2>&1)
echo "noso 退出码=$?" >>"$LOG"
snapshot > "$WORK/snap_b.txt"

echo "--- 失败名单对比 ---" >>"$LOG"
grep -E '^(FAILED|ERROR)' "$WORK/baseline.txt" | sort > "$WORK/f_base.txt"
grep -E '^(FAILED|ERROR)' "$WORK/noso.txt"    | sort > "$WORK/f_noso.txt"
echo "基线(有 .so)失败条数: $(wc -l < "$WORK/f_base.txt")" >>"$LOG"
echo "无 .so 失败条数:      $(wc -l < "$WORK/f_noso.txt")" >>"$LOG"
echo "[仅无 .so 时失败(新增)]:" >>"$LOG"
comm -13 "$WORK/f_base.txt" "$WORK/f_noso.txt" >>"$LOG" 2>&1
echo "[仅基线失败(无 .so 时消失)]:" >>"$LOG"
comm -23 "$WORK/f_base.txt" "$WORK/f_noso.txt" >>"$LOG" 2>&1
echo "--- 写库检查 ---" >>"$LOG"
echo "行数变化 diff 行数=$(diff "$WORK/snap_a.txt" "$WORK/snap_b.txt" | wc -l)" >>"$LOG"
echo "--- 结论 ---" >>"$LOG"
if diff -q "$WORK/f_base.txt" "$WORK/f_noso.txt" >/dev/null; then
  echo "✅ 无 .so 与有 .so 失败名单一致 ⇒ CI 不需要 Rust 工具链" >>"$LOG"
else
  echo "⚠️ 无 .so 会新增失败 ⇒ CI 需要提供该二进制或加 Rust 构建步骤" >>"$LOG"
fi
date -u '+%Y-%m-%dT%H:%M:%SZ' >>"$LOG"
echo "P0C_DONE" >>"$LOG"
