#!/usr/bin/env python3
"""Emotion-CPT 的**公网反代**门禁：路径存在 + 真相源一致。

## 为什么要有

「Emotion-CPT 和 emotion / CPT 一样有 nginx 反代」本来是**一句声明**
⇒ 配置被无声删掉、或者改了仓忘了装 ⇒ **没有任何东西会报警**。

⇒ 门禁把它变成**可执行**的：

| 判据 | 在哪跑 | 查什么 |
|---|---|---|
| **静态一致** | CI | facade 的 ``NGINX_PREFIX`` 与 ``deploy/nginx/*.conf`` 真相源**必须一致** |
| **活体注册** | 真机 | 探公网路径 ⇒ 401/403 = **已注册且要鉴权**（200 反而危险 ⇒ 没鉴权） |

⚠️ 2026-10-24 实测踩过：nginx conf 的备份文件躺在 ``sites-enabled/`` 里
⇒ nginx 把它们一起加载 ⇒ 同 ``server_name _`` 的 server 块**互相冲突**
⇒ 刚加的 ``/ecpt/`` 返回 **404**（压根没生效）却 ``nginx -t`` 全绿。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import urllib.error
import urllib.request

from emotion_cpt.web.facade import NGINX_PREFIX

#: nginx 真相源片段（仓内）
SNIPPET_DIR = pathlib.Path(__file__).resolve().parents[1].parent.parent / "deploy" / "nginx"

#: 公网入口（真机探测用；CI 里没有网络 ⇒ 跳过）
PUBLIC_BASE = "https://140.83.62.161"


def _snippets() -> list[pathlib.Path]:
    if not SNIPPET_DIR.is_dir():
        return []
    return sorted(p for p in SNIPPET_DIR.glob("*.conf"))


def check_static() -> list[str]:
    """facade 的前缀与 nginx 真相源片段必须一致。"""
    issues: list[str] = []
    snippets = _snippets()
    if not snippets:
        return [f"找不到 nginx 真相源片段：{SNIPPET_DIR}"]
    hit = False
    for p in snippets:
        text = p.read_text(encoding="utf-8")
        if f"location {NGINX_PREFIX} " in text:
            hit = True
    if not hit:
        issues.append(
            f"nginx 真相源片段里没有 `location {NGINX_PREFIX} `"
            f"（门面用的前缀是 {NGINX_PREFIX}）"
        )
    return issues


def check_live(base: str) -> tuple[list[str], bool]:
    """探公网路径：401/403 = 已注册且要鉴权。"""
    url = f"{base}{NGINX_PREFIX}"
    # ⚠️ 机器上用的是**自签 / IP 证书** ⇒ 默认校验会失败 ⇒ 探不到
    #    ⇒ 活体判据被"跳过" ⇒ 而**跳过看起来像"一切正常"** ⇒ 正好掩盖问题
    #    ⇒ 关闭校验（这条只读探一个状态码，不传任何凭据）。
    import ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=15, context=ctx) as resp:  # noqa: S310
            code = int(resp.status)
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
    except (urllib.error.URLError, OSError) as exc:
        print(f"  (探不到公网：{exc} ⇒ 跳过活体判据)", file=sys.stderr)
        return [], False
    if code in (401, 403):
        return [], True
    if code == 404:
        return [f"公网 {NGINX_PREFIX} 返回 404 ⇒ **反代没生效**（nginx 里没这个 location）"], True
    if code == 200:
        return [
            f"公网 {NGINX_PREFIX} 返回 **200** ⇒ **没有鉴权**！"
            f"聚合页会显示买卖点与持仓口径，不该裸奔"
        ], True
    return [f"公网 {NGINX_PREFIX} 返回 {code}（期望 401/403）"], True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emotion-CPT 公网反代门禁")
    parser.add_argument("--skip-live", action="store_true", help="不探公网（CI 用）")
    parser.add_argument("--public-base", default=PUBLIC_BASE)
    args = parser.parse_args(argv)

    issues = check_static()
    live_note = "（未探测公网）"
    if not args.skip_live:
        live_issues, probed = check_live(args.public_base)
        issues.extend(live_issues)
        live_note = "已探测公网" if probed else "探不到公网 ⇒ 跳过活体判据"

    if issues:
        print(f"❌ 反代门禁失败（{len(issues)} 项）：", file=sys.stderr)
        for i in issues:
            print(f"  {i}", file=sys.stderr)
        return 1
    print(f"✅ 反代一致（静态：{NGINX_PREFIX} 与真相源一致；活体：{live_note}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
