#!/usr/bin/env bash
# 把 Emotion-CPT 的 nginx 反代装到线上（可重现 ⇒ 不手改线上 conf）。
#
# ## 为什么要有这个脚本
# nginx conf 是**机器上的状态**，仓里的片段是**真相源**。两者之间必须有
# **一条确定性的路径** ⇒ 否则就回到「改了仓、忘了装、线上还是旧的」。
#
# ## 怎么保证确定性（2026-10-26 重写）
# 旧版是「正则删 location 块 + 插到**全文最后一个 }**」，有两个结构性隐患：
#   ① 插入点 = 全文最后一个 } ⇒ **站点里一旦有第二个 server 块**（default_server、
#      独立 ACME 块……），片段会插进错的那个块 ⇒ /ecpt/ 直接失效，
#      而 `nginx -t` **全绿不报错**（这坑已经踩过一次：2026-10-24 /ecpt/ 返回 404）；
#   ② 删块正则非贪婪到第一个 `\n\s*}\n` ⇒ location 内**不能再有嵌套花括号**。
# ⇒ 改成**标记区间替换**：线上用一对标记把受管片段夹住
#      # === EMOTION-CPT FACADE BEGIN === / END ===
#   替换只看标记 ⇒ 与 server 块数量、嵌套层级、location 顺序**全部无关**。
#
# ## 2026-10-26：/dsh/ 腾给 DeepSeek Harness
# 本门面**不再**有 /dsh/ 兼容别名（原 /dsh/ 指向 8092 ⇒ 现在指向 DSH 本体）。
# ⇒ 受管前缀只有 /ecpt/ 一个。
#
# 用法：
#   scripts/install_nginx_route.sh            # 装 + nginx -t + reload
#   scripts/install_nginx_route.sh --check    # 只校验装没装
#   scripts/install_nginx_route.sh --remove   # 摘掉（回滚用）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${EMOTION_CPT_REPO:-$(cd "$HERE/.." && pwd)}"
SNIPPET="${SNIPPET:-$REPO/deploy/nginx/ecpt-facade.conf}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/dsh-web}"
#: ⚠️ 备份**绝不能**放在 sites-enabled/ 里 —— nginx 的
#:    ``include sites-enabled/*`` 会把**所有文件**都加载
#:    ⇒ 多个同 ``server_name _`` 的 server 块 ⇒ **互相冲突**
#:    ⇒ 改的那块可能压根没生效（2026-10-24 实测踩过：/ecpt/ 返回 404）。
BACKUP_DIR="${BACKUP_DIR:-/home/ubuntu/logs/nginx-backup}"
#: 受管前缀（装完后的公网自检用）。⚠️ 2026-10-26 起**只有 /ecpt/**：
#:    /dsh/ 已归 DeepSeek Harness，不是本门面的了。
PREFIX="${PREFIX:-/ecpt/}"

#: 标记：线上受管区间的边界。
BEGIN_MARK="# === EMOTION-CPT FACADE BEGIN ==="
END_MARK="# === EMOTION-CPT FACADE END ==="
#: 首次安装用的锚点（必须在 **443 server 块内**）。
ANCHOR_MARK="# === EMOTION-CPT FACADE ANCHOR ==="

MODE="install"
case "${1:-}" in
  --check)  MODE="check" ;;
  --remove) MODE="remove" ;;
  "")       MODE="install" ;;
  *) echo "用法：$0 [--check|--remove]" >&2; exit 2 ;;
esac

[[ -f "$SNIPPET" ]] || { echo "❌ 找不到真相源片段：$SNIPPET" >&2; exit 1; }
[[ -f "$NGINX_SITE" ]] || { echo "❌ 找不到 nginx 站点配置：$NGINX_SITE" >&2; exit 1; }

sudo -n mkdir -p "$BACKUP_DIR"

# ── 写 /etc 要 root ⇒ 整段用 sudo -n python3 跑 ──
sudo -n python3 - "$NGINX_SITE" "$SNIPPET" "$MODE" "$BEGIN_MARK" "$END_MARK" "$ANCHOR_MARK" <<'PYEOF'
import re
import sys

site, snippet, mode, begin_mark, end_mark, anchor_mark = sys.argv[1:7]

text = open(site, encoding="utf-8").read()
block = open(snippet, encoding="utf-8").read().rstrip() + "\n"

# ⚠️ 护栏：/dsh/ 已归 DeepSeek Harness ⇒ 真相源里**不许**再出现 location /dsh/
if mode != "remove" and re.search(r"location\s+/dsh/", block):
    sys.exit("❌ 真相源片段里出现 `location /dsh/` ⇒ /dsh/ 已归 DeepSeek Harness，拒绝安装")


def region(content: str):
    """返回受管区间 (start, end)，没有则 None。"""
    i = content.find(begin_mark)
    j = content.find(end_mark)
    if i < 0 or j < 0 or j < i:
        return None
    return i, j + len(end_mark)


if mode == "check":
    cur = region(text)
    if cur is None:
        sys.exit(f"❌ 线上没有受管区间（找不到 {begin_mark} / {end_mark}）⇒ 没装")
    installed = text[cur[0]:cur[1]]
    want = f"{begin_mark}\n{block}{end_mark}\n"
    if installed.strip() == want.strip():
        print("  ✓ 线上受管区间与真相源**一致**")
        raise SystemExit(0)
    sys.exit("❌ 线上受管区间与真相源**不一致** ⇒ 跑 scripts/install_nginx_route.sh 重装")

if mode == "remove":
    cur = region(text)
    if cur is None:
        print("  · 线上本来就没有受管区间，无需摘除")
        raise SystemExit(0)
    text = text[:cur[0]] + text[cur[1]:]
    open(site, "w", encoding="utf-8").write(text)
    print("  ✓ 已摘除受管区间")
    raise SystemExit(0)

# ── install ──
cur = region(text)
if cur is not None:
    text = text[:cur[0]] + f"{begin_mark}\n{block}{end_mark}\n" + text[cur[1]:]
    print("  ✓ 替换受管区间（标记区间替换 ⇒ 与 server 块数量/顺序无关）")
else:
    # 首次安装：必须找到锚点，否则**大声失败**（fail closed）
    idx = text.find(anchor_mark)
    if idx < 0:
        sys.exit(
            f"❌ 线上找不到锚点 {anchor_mark!r}\n"
            "   ⇒ 不猜插入位置（旧版就是靠「全文最后一个 }」猜 ⇒ 插错过一次）。\n"
            "   请在 443 server 块内加一行锚点注释后重跑。"
        )
    line_end = text.find("\n", idx)
    assert line_end > 0, "锚点行没有结尾换行"
    insert_at = line_end + 1
    text = text[:insert_at] + f"{begin_mark}\n{block}{end_mark}\n" + text[insert_at:]
    print("  ✓ 首次安装：在锚点后插入受管区间")

open(site, "w", encoding="utf-8").write(text)
PYEOF

if [[ "$MODE" == "check" || "$MODE" == "remove" ]]; then
  exit 0
fi

echo "  备份并校验 nginx 配置……"
sudo -n cp -a --no-dereference "$NGINX_SITE" "$BACKUP_DIR/dsh-web.$(date -u +%Y%m%dT%H%M%SZ).bak"
sudo -n nginx -t
sudo -n systemctl reload nginx
echo "✅ 已 reload（没有 restart）"

# ── 校验：装没装、有没有重复 ──
echo "  线上 location："
grep -nE "^\s*location /(ecpt|dsh)/" "$NGINX_SITE" | sed 's/^/    /'
code=$(curl -sk -o /dev/null -w '%{http_code}' "https://140.83.62.161${PREFIX}" || echo 000)
echo "    ${PREFIX} → ${code}（期望 401 = 已注册且要鉴权）"
if [[ "$code" != "401" && "$code" != "403" ]]; then
  echo "❌ ${PREFIX} 返回 ${code}，期望 401/403" >&2
  exit 1
fi

