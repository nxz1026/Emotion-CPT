#!/usr/bin/env bash
# P0 复测 v2 —— 修掉 v1 的两个设计缺陷：
#   ① v1 的 P0-C 基线没带 PYTHONPATH=src ⇒ conftest ImportError ⇒ 一个用例没收集 ⇒ **假绿**
#   ② v1 的 P0-C 副本目录名改了 ⇒ 触发路径断言假失败
#   ③ v1 的 P0-A 用真 dbconfig 跑测试 ⇒ CPT 测试会写生产库（已实证 +4 行）⇒ 改用隔离 HOME
set -u
CPT=/home/ubuntu/DSH/Chan_Pattern_Trader
EMO=/home/ubuntu/DSH/emotion-core
WORK=/tmp/p0v2
LOG=$WORK/p0v2.log
mkdir -p "$WORK" "$WORK/isolated-home"
CPTVENV=$CPT/.venv/bin/python
MERGEDVENV=$WORK/venv/bin/python
EMOVENV=$EMO/.venv/bin/python

# 隔离 HOME：故意**不**放 .dbconfig ⇒ 测试够不到生产库
export HOME="$WORK/isolated-home"

fails_of() { grep -E '^(FAILED|ERROR)' "$1" | sed -E 's/ - .*//' | sort -u; }

echo "==================== P0 复测 v2 ====================" >"$LOG"
date -u '+%Y-%m-%dT%H:%M:%SZ' >>"$LOG"

# ────────── P0-C：无 .so ──────────
echo >>"$LOG"; echo "########## P0-C：无平台相关二进制 ##########" >>"$LOG"
C1=$WORK/withso/emotion-core
C2=$WORK/noso/emotion-core
mkdir -p "$WORK/withso" "$WORK/noso"
[ -d "$C1" ] || { cp -a "$EMO" "$C1"; rm -rf "$C1/.git"; }
[ -d "$C2" ] || { cp -a "$EMO" "$C2"; rm -rf "$C2/.git"; rm -f "$C2/src/core_lib/emotion_core_rust.so"; }
# 两份副本**同名** emotion-core ⇒ 路径断言不再有差异
echo "副本1(有 .so): $([ -f "$C1/src/core_lib/emotion_core_rust.so" ] && echo 有 || echo 无)" >>"$LOG"
echo "副本2(无 .so): $([ -f "$C2/src/core_lib/emotion_core_rust.so" ] && echo 有 || echo 无)" >>"$LOG"
echo "目录名: $(basename $C1) / $(basename $C2)（必须同名）" >>"$LOG"

(cd "$C1" && PYTHONPATH="$C1/src" "$EMOVENV" -m pytest tests -q --no-header -p no:cacheprovider >"$WORK/c_withso.txt" 2>&1)
echo "有 .so 退出码=$? 收集=$(grep -oE '[0-9]+ collected' "$WORK/c_withso.txt" | head -1) 通过=$(grep -oE '[0-9]+ passed' "$WORK/c_withso.txt" | head -1)" >>"$LOG"
(cd "$C2" && PYTHONPATH="$C2/src" "$EMOVENV" -m pytest tests -q --no-header -p no:cacheprovider >"$WORK/c_noso.txt" 2>&1)
echo "无 .so 退出码=$? 收集=$(grep -oE '[0-9]+ collected' "$WORK/c_noso.txt" | head -1) 通过=$(grep -oE '[0-9]+ passed' "$WORK/c_noso.txt" | head -1)" >>"$LOG"
fails_of "$WORK/c_withso.txt" >"$WORK/f_c1.txt"
fails_of "$WORK/c_noso.txt"   >"$WORK/f_c2.txt"
echo "有 .so 失败条数: $(wc -l <"$WORK/f_c1.txt")" >>"$LOG"
echo "无 .so 失败条数: $(wc -l <"$WORK/f_c2.txt")" >>"$LOG"
echo "[仅无 .so 时失败]:" >>"$LOG"; comm -13 "$WORK/f_c1.txt" "$WORK/f_c2.txt" >>"$LOG" 2>&1
echo "[仅有 .so 时失败]:" >>"$LOG"; comm -23 "$WORK/f_c1.txt" "$WORK/f_c2.txt" >>"$LOG" 2>&1
if diff -q "$WORK/f_c1.txt" "$WORK/f_c2.txt" >/dev/null; then
  echo "✅ P0-C 结论：失败名单完全一致 ⇒ .so 不是测试必需 ⇒ CI 不需要 Rust 工具链" >>"$LOG"
else
  echo "⚠️ P0-C 结论：无 .so 会新增失败（见上）" >>"$LOG"
fi

# ────────── P0-A：单 venv 兼容性（隔离 HOME，不碰生产库）──────────
echo >>"$LOG"; echo "########## P0-A：单 venv 兼容性（隔离 HOME）##########" >>"$LOG"
if [ ! -x "$MERGEDVENV" ]; then
  echo "建合并 venv..." >>"$LOG"
  python3 -m venv "$WORK/venv" >>"$LOG" 2>&1
  "$MERGEDVENV" -m pip install --quiet --upgrade pip >>"$LOG" 2>&1
  "$MERGEDVENV" -m pip install --quiet -r "$EMO/requirements.txt" >>"$LOG" 2>&1
  "$MERGEDVENV" -m pip install --quiet -r "$CPT/requirements-dev.txt" >>"$LOG" 2>&1
  (cd "$CPT" && "$MERGEDVENV" -m pip install --quiet -e '.[db]' >>"$LOG" 2>&1)
fi
echo "--- 依赖版本对照 ---" >>"$LOG"
{ echo "[CPT 原有 venv]"; "$CPTVENV" -m pip list 2>/dev/null | grep -iE '^(akshare|pandas|psycopg|httpx|jinja2|requests|ccxt|czsc) '
  echo "[合并 venv]"; "$MERGEDVENV" -m pip list 2>/dev/null | grep -iE '^(akshare|pandas|psycopg|httpx|jinja2|requests|ccxt|czsc) '; } >>"$LOG" 2>&1

(cd "$CPT" && "$CPTVENV"    -m pytest tests -q --no-header -p no:cacheprovider >"$WORK/a_base.txt" 2>&1)
echo "基线退出码=$? 收集=$(grep -oE '[0-9]+ collected' "$WORK/a_base.txt"|head -1) 通过=$(grep -oE '[0-9]+ passed' "$WORK/a_base.txt"|head -1)" >>"$LOG"
(cd "$CPT" && "$MERGEDVENV" -m pytest tests -q --no-header -p no:cacheprovider >"$WORK/a_merged.txt" 2>&1)
echo "合并退出码=$? 收集=$(grep -oE '[0-9]+ collected' "$WORK/a_merged.txt"|head -1) 通过=$(grep -oE '[0-9]+ passed' "$WORK/a_merged.txt"|head -1)" >>"$LOG"
fails_of "$WORK/a_base.txt"   >"$WORK/f_a1.txt"
fails_of "$WORK/a_merged.txt" >"$WORK/f_a2.txt"
echo "基线失败条数: $(wc -l <"$WORK/f_a1.txt")" >>"$LOG"
echo "合并失败条数: $(wc -l <"$WORK/f_a2.txt")" >>"$LOG"
echo "[仅合并环境失败(新增)]:" >>"$LOG"; comm -13 "$WORK/f_a1.txt" "$WORK/f_a2.txt" >>"$LOG" 2>&1
echo "[仅基线失败(合并后消失)]:" >>"$LOG"; comm -23 "$WORK/f_a1.txt" "$WORK/f_a2.txt" >>"$LOG" 2>&1
if diff -q "$WORK/f_a1.txt" "$WORK/f_a2.txt" >/dev/null; then
  echo "✅ P0-A 结论：失败名单完全一致 ⇒ 单 venv 与现有 venv 等价" >>"$LOG"
else
  echo "⚠️ P0-A 结论：失败名单有差异（见上）" >>"$LOG"
fi
date -u '+%Y-%m-%dT%H:%M:%SZ' >>"$LOG"
echo "P0V2_DONE" >>"$LOG"
