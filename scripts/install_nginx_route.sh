#!/usr/bin/env bash
# 把 Emotion-CPT 的 nginx 反代装到线上（可重现 ⇒ 不手改线上 conf）。
#
# ## 为什么要有这个脚本
# nginx conf 是**机器上的状态**，仓里的片段是**真相源**。两者之间必须有
# **一条确定性的路径** ⇒ 否则就回到「改了仓、忘了装、线上还是旧的」。
# 2026-10-24 首次上线时就漏过 `auth_basic` ⇒ **外网直接 200**（裸奔）。
#
# ## 幂等靠「替换」而不是「没有才插」
# 片段里同时有 `/ecpt/` 与兼容别名 `/dsh/`，而线上**已经有** `/dsh/`
# ⇒ 直接插 ⇒ **重复 location** ⇒ `nginx -t` 报错
# ⇒ 所以：先把这两个 location 的旧块**删掉**，再插新块。
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
LOCATIONS="${LOCATIONS:-/ecpt/ /dsh/}"

[[ -f "$SNIPPET" ]] || { echo "❌ 找不到真相源片段：$SNIPPET" >&2; exit 1; }
[[ -f "$NGINX_SITE" ]] || { echo "❌ 找不到 nginx 站点配置：$NGINX_SITE" >&2; exit 1; }

# ── 替换式安装：删掉旧的 location 块，插入真相源片段 ──
# ⚠️ 写 /etc 要 root ⇒ 整段用 sudo -n python3 跑
sudo -n mkdir -p "$BACKUP_DIR"
sudo -n cp -a --no-dereference "$NGINX_SITE" "$BACKUP_DIR/dsh-web.$(date -u +%Y%m%dT%H%M%SZ).bak"
sudo -n python3 - "$NGINX_SITE" "$SNIPPET" "$LOCATIONS" <<'PYEOF'
import re
import sys

site, snippet, locs = sys.argv[1], sys.argv[2], sys.argv[3].split()
s = open(site, encoding="utf-8").read()
removed = 0
for loc in locs:
    pat = re.compile(r"\n[ \t]*location " + re.escape(loc) + r"\s*\{.*?\n[ \t]*\}\n", re.S)
    s, n = pat.subn("\n", s)
    removed += n
block = open(snippet, encoding="utf-8").read().rstrip() + "\n"
idx = s.rstrip().rfind("}")
assert idx > 0, "找不到 server 块结尾"
s = s[:idx] + "\n" + block + s[idx:]
open(site, "w", encoding="utf-8").write(s)
print(f"  ✓ 删掉旧 location 块 {removed} 个，插入真相源片段（{', '.join(locs)}）")
PYEOF

echo "  校验 nginx 配置……"
sudo -n nginx -t
sudo -n systemctl reload nginx
echo "✅ 已 reload（没有 restart）"

# ── 校验：装没装、有没有重复 ──
echo "  线上 location："
grep -nE "^\s*location /(ecpt|dsh)/" "$NGINX_SITE" | sed 's/^/    /'
for loc in $LOCATIONS; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' "https://140.83.62.161${loc}" || echo 000)
  echo "    ${loc} → ${code}（期望 401 = 已注册且要鉴权）"
done
