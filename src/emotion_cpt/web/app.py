"""Emotion-CPT 的**统一入口**门面（纯标准库，零第三方依赖）。

## 它做什么

一个 origin 下的四个入口：

============================  ==========================================
路径                          内容
============================  ==========================================
``/``                         **统一门户**：并列各入口
``/aggregate``                同票并排（带代码输入框）
``/aggregate/stock/{code}``   同票并排
``/api/aggregate/stock/{code}``  同票并排的 JSON
``/api/health``               自己 + 三个上游的可达性
============================  ==========================================

## 它不做什么（边界）

- **不搬前端代码** —— CPT 的看板、emotion 的页面都留在原处，nginx 层各自反代；
  本门面只提供**门户与聚合页**。
- **不合并进程** —— 8010 / 8098 / 8091 三个故障域原样保留
  （emotion-core 的降级设计依赖「CPT 可能挂」这个前提）。
- **不 import 上游** —— 只走 HTTP，这是「不纠缠」在展示层的体现。
- **不裁决口径** —— 聚合页只把差异**摆出来**，不替 owner 做决定。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from emotion_cpt.contracts.pricing import PRICE_ROUND_DIGITS

from .aggregate.server import build_stock_payload
from .facade import (  # noqa: F401  （入口定义在 facade 里）
    DEFAULT_PORT,
    ENTRIES,
    HOST,
    entry_href,
)

#: 允许的公网挂载前缀（**白名单**）。
#:
#: ⚠️ 2026-10-25 静态审计：``X-Forwarded-Prefix`` 原来**完全信任**客户端
#: ⇒ ``"><script>…`` ⇒ 反射型 XSS（门面挂在公网 /ecpt/、/dsh/ 下 ⇒ 可达）
#: ⇒ 只接受白名单里的前缀，其余一律丢弃。
ALLOWED_PREFIXES: tuple[str, ...] = ("/ecpt/", "/dsh/", "")

_LOG = logging.getLogger("emotion_cpt.web")

_CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e6e9ef;--dim:#8b93a3;
--up:#3fb950;--down:#f85149;--flat:#d29922;--none:#6e7681;--accent:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px}
.card h3{margin:0 0 4px;font-size:16px}
.card .tag{display:inline-block;font-size:11px;color:var(--dim);
border:1px solid var(--line);border-radius:4px;padding:1px 6px;margin-bottom:8px}
.card p{margin:0;color:var(--dim);font-size:13px}
form{display:flex;gap:8px;margin:18px 0 26px}
input[type=text]{flex:1;background:var(--card);border:1px solid var(--line);
color:var(--fg);border-radius:8px;padding:11px 13px;font-size:15px}
button{background:var(--accent);border:0;color:#06121f;border-radius:8px;
padding:11px 20px;font-size:15px;font-weight:600;cursor:pointer}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:500;font-size:12px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.cols{grid-template-columns:1fr}}
.badge{display:inline-block;padding:2px 9px;border-radius:5px;font-size:12px;font-weight:600}
.badge.up{background:rgba(63,185,80,.16);color:var(--up)}
.badge.down{background:rgba(248,81,73,.16);color:var(--down)}
.badge.flat{background:rgba(210,153,34,.16);color:var(--flat)}
.badge.none{background:rgba(110,118,129,.16);color:var(--none)}
.warn{border-left:3px solid var(--flat);padding:8px 12px;background:rgba(210,153,34,.08);
margin-top:8px;font-size:13px}
.kv{display:grid;grid-template-columns:96px 1fr;gap:4px 12px;font-size:13px;margin-top:8px}
.kv dt{color:var(--dim)}.kv dd{margin:0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.note{color:var(--dim);font-size:12px;margin-top:18px;
border-top:1px solid var(--line);padding-top:12px}
"""


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · Emotion-CPT</title><style>{_CSS}</style></head>
<body><div class="wrap">{body}</div></body></html>""".encode()


def _portal(prefix: str = "") -> bytes:
    cards = "\n".join(
        f'<div class="card"><span class="tag">{escape(tag)}</span>'
        f'<h3><a href="{escape(entry_href(path, prefix))}">{escape(name)}</a></h3>'
        f"<p>{escape(desc)}</p></div>"
        for path, name, desc, tag in ENTRIES
    )
    body = f"""
<h1>Emotion-CPT 统一入口</h1>
<div class="sub">CPT × emotion-core 的共用底座 —— 判据单一真源、同一入口进。<br>
本页只做<b>并列与对照</b>，不裁决口径。</div>
<div class="cards">{cards}</div>
<div class="note">
Emotion-CPT 不合并进程：CPT（8010）/ emotion-core（8098）/ lab（8091）各自独立，
故障域不变。<br>
判据唯一真源在 <code>emotion_cpt.structure</code> 与 <code>emotion_cpt.snapshot</code>。
</div>"""
    return _page("统一入口", body)


def _ms_to_date(ms: Any) -> str:
    """epoch 毫秒 → 日期（拿不到就返回空串）。"""
    if not isinstance(ms, int) or ms <= 0:
        return ""
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _px(value: Any) -> str:
    """价格按**契约的取整口径**显示（P3 统一过：PRICE_ROUND_DIGITS）。

    ⚠️ 此前直接显示原值 ⇒ ``8536.18585785`` ⇒ 绕过了口径
    ⇒ 同一个价在页面/接口/库里长得不一样 ⇒ 对不上账。
    """
    if not isinstance(value, (int, float)):
        return "—"
    return f"{round(float(value), PRICE_ROUND_DIGITS):.{PRICE_ROUND_DIGITS}f}"


def _quote_block(q: dict[str, Any]) -> str:
    """CPT 侧**行情**块（数据早就在取，此前没显示）。"""
    if not q.get("available"):
        return ""
    amt = q.get("last_amount")
    amt_txt = f"{amt / 1e8:.2f} 亿" if isinstance(amt, (int, float)) else "—"
    chg = q.get("change_pct")
    chg_txt = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "—"
    return f"""
<h3>行情</h3>
<dl class="kv">
<dt>收盘</dt><dd class="mono">{escape(_px(q.get('close')))}
 <span style="color:var(--dim)">{escape(chg_txt)}</span></dd>
<dt>开/高/低</dt><dd class="mono">{escape(_px(q.get('open')))}
 / {escape(_px(q.get('high')))} / {escape(_px(q.get('low')))}</dd>
<dt>成交额</dt><dd class="mono">{escape(amt_txt)}</dd>
<dt>标的</dt><dd>{escape(str(q.get('board_label') or '—'))}
 · 周期 {escape(str(q.get('interval') or '—'))} · {escape(str(q.get('bar_count') or '—'))} 根</dd>
<dt>最后交易日</dt><dd class="mono">{escape(str(q.get('last_bar_date') or '—'))}</dd>
</dl>"""


def _levels_tree_block(t: dict[str, Any]) -> str:
    """CPT 的**结构级别树**（确定性缠论最硬的部分）。"""
    if not t.get("available"):
        return f"<div class='warn'>无结构级别树：{escape(str(t.get('error') or '—'))}</div>"
    rows = ""
    for lv in t.get("levels") or []:
        span = ""
        s0, e0 = lv.get("start_time"), lv.get("end_time")
        if s0 and e0:
            span = f"{_ms_to_date(s0)} ~ {_ms_to_date(e0)}"
        kinds = "、".join(lv.get("kinds") or [])
        rows += (
            f"<tr><td class='mono'>{escape(str(lv.get('level')))}</td>"
            f"<td>{escape(str(lv.get('count')))}</td>"
            f"<td class='mono'>{escape(_px(lv.get('high')))}</td>"
            f"<td class='mono'>{escape(_px(lv.get('low')))}</td>"
            f"<td>{escape(kinds)}</td>"
            f"<td class='mono'>{escape(span)}</td></tr>"
        )
    return (
        "<table><tr><th>级别</th><th>元素</th><th>最高</th><th>最低</th><th>类型</th><th>时间跨度</th></tr>"
        f"{rows}</table>"
    )


def _trust_block(cpt: dict[str, Any], quote: dict[str, Any]) -> str:
    """**数据可信度**：引擎状态 / 信号状态 / 数据质量 —— 结论建立在什么数据上。"""
    eng = cpt.get("engine") or {}
    qual = cpt.get("quality") or {}
    st = cpt.get("structure") or {}
    tags = qual.get("ashare_tags") or {}
    return f"""
<dl class="kv">
<dt>引擎</dt><dd class="mono">{escape(str(eng.get('status') or '—'))}
 · 缓冲 {escape(str(eng.get('buffer_size')))}
 · 待确认 {escape(str(eng.get('pending_count')))}
 · 陈旧 {escape(str(eng.get('stale')))}</dd>
<dt>信号状态</dt><dd class="mono">{escape(str(st.get('signal_status') or '—'))}
 · 背驰 {escape(str(st.get('divergence_status') or '—'))}</dd>
<dt>数据量</dt><dd class="mono">K 线 {escape(str(qual.get('closed_bar_count')))}
 / 预期 {escape(str(qual.get('expected_trade_days')))}
 · 缺口 {escape(str(qual.get('gap')))}</dd>
<dt>标记</dt><dd class="mono">已标记笔 {escape(str(tags.get('tagged_bis')))}
 / 全部笔 {escape(str(tags.get('total_bis')))}
 · 来源 {escape(str(tags.get('source') or '—'))}</dd>
</dl>"""


def _aggregate_page(code: str, payload: dict[str, Any] | None, prefix: str = "") -> bytes:
    input_box = f"""
<!-- ⚠️ action 指向**列表页**，靠 ?code= 传参。
     之前指向 /aggregate/stock/ 加**当时那个代码** ⇒ 浏览器导航到
     .../stock/600519?code=你输的 ⇒ **后端走路径参数路由** ⇒
     你输的代码被**忽略**，页面永远显示 600519。
     ⇒ 后端 `/aggregate` 本来就读 `?code=`（实测标题会变）⇒ 这里对齐它。
     ⚠️ 本段在 f-string 里 ⇒ 注释里的花括号会被**求值** ⇒ 不能写裸花括号。 -->
<form action="{escape(prefix or '/')}aggregate" method="get">
<input type="text" name="code" value="{escape(code)}" placeholder="6 位代码，如 600519">
<button type="submit">并排</button></form>"""
    if not payload or not payload.get("ok"):
        err = (payload or {}).get("error", "未知错误")
        body = (
            f"<h1>同票并排</h1>{input_box}"
            f"<div class='warn'>无法构造 payload：{escape(str(err))}</div>"
        )
        return _page("同票并排", body)

    panels = payload["panels"]
    cpt, emo, lv = panels["cpt"], panels["emotion"], panels["levels"]
    struct = cpt.get("structure") or {}
    counts = struct.get("counts") or {}

    def verdict_rows() -> str:
        rows = []
        for v in payload.get("verdicts", []):
            rows.append(
                f"<tr><td>{escape(str(v['source']))}</td>"
                f"<td><span class='badge {v['cls']}'>{escape(str(v['raw'] or '—'))}</span></td>"
                f"<td>{escape(str(v['direction']))}</td></tr>"
            )
        return "\n".join(rows)

    conflicts = payload.get("conflicts") or []
    conflict_html = ""
    if conflicts:
        items = "\n".join(
            f"<div class='warn'><b>{escape(c['kind'])}</b> · {escape(c.get('note',''))}<br>"
            f"CPT：{escape(c.get('cpt','—'))}<br>emotion：{escape(c.get('emotion','—'))}</div>"
            for c in conflicts
        )
        conflict_html = f"<h3>差异（{len(conflicts)}）</h3>{items}"
    else:
        conflict_html = (
            "<h3>差异</h3><div class='warn' style='border-color:#3fb950'>"
            "三套口径未见方向冲突</div>"
        )

    cpt_kv = ""
    if cpt.get("available"):
        cpt_kv = f"""
<dl class="kv">
<dt>结论</dt><dd><b>{escape(str(cpt.get('action') or '—'))}</b>
 {escape(str(cpt.get('action_label') or ''))}</dd>
<dt>说法</dt><dd>{escape(str(cpt.get('headline') or '—'))}</dd>
<dt>理由</dt><dd>{escape(str(cpt.get('reason') or '—'))}</dd>
<dt>信号类型</dt><dd class="mono">{escape(str(cpt.get('signal_type') or '—'))}</dd>
<dt>背驰</dt><dd class="mono">{escape(str(cpt.get('divergence_status') or '—'))}</dd>
<dt>结构</dt><dd class="mono">分型 {counts.get('分型', '—')} · 笔 {counts.get('笔', '—')}
 · 中枢 {counts.get('中枢', '—')} · 走势 {counts.get('走势', '—')}</dd>
<dt>price_ratio</dt><dd class="mono">{escape(str(cpt.get('price_ratio')))}</dd>
</dl>
{_quote_block(cpt.get('quote') or {})}"""
    else:
        cpt_kv = f"<div class='warn'>CPT 不可用：{escape(str(cpt.get('error')))}</div>"

    emo_kv = ""
    if emo.get("available"):
        stop = emo.get("stop") or {}
        # 止损没有价位时，把**原因**也显示出来（此前只有 None (pct_fallback)
        # ⇒ 看着像坏了。实际是「未上市 / 停牌超窗 / 尚未回补 ⇒ 不给价位（F6 不猜）」
        stop_detail = ""
        if (stop or {}).get("detail"):
            stop_detail = (
                '<br><span style="color:var(--dim)">'
                + escape(str((stop or {}).get("detail")))
                + "</span>"
            )
        strat_rows = ""
        for s in emo.get("strategies") or []:
            strat_rows += (
                f"<tr><td class='mono'>{escape(str(s.get('strategy')))}</td>"
                f"<td>{escape(str(s.get('action')))}</td>"
                f"<td>{escape(str(s.get('score')))}</td>"
                f"<td>{escape(str(s.get('reason') or ''))}</td></tr>"
            )
        strat_html = (
            f"<table><tr><th>策略</th><th>动作</th><th>分</th><th>理由</th></tr>{strat_rows}</table>"
            if strat_rows
            else "<p style='color:var(--dim)'>当日无该票的策略信号</p>"
        )
        emo_kv = f"""
<dl class="kv">
<dt>持仓决策</dt><dd><b>{escape(str(emo.get('action') or '—'))}</b>
 {escape(str(emo.get('action_label') or ''))}</dd>
<dt>市场阶段</dt><dd>{escape(str(emo.get('phase') or '—'))}
 · 涨停 {escape(str(emo.get('limit_up_count')))} 家
 · 最高 {escape(str(emo.get('max_limit_days')))} 连板</dd>
<dt>龙头环境</dt><dd class="mono">{escape(str(emo.get('dragon_env') or '—'))}</dd>
<dt>现价</dt><dd class="mono">{escape(str(emo.get('market_price')))}</dd>
<dt>止损</dt><dd class="mono">{escape(str((stop or {}).get('price')))}
 <span style="color:var(--dim)">({escape(str((stop or {}).get('basis')))})</span>
 {stop_detail}</dd>
</dl>
<h3>策略信号</h3>{strat_html}"""
    else:
        emo_kv = f"<div class='warn'>emotion-core 不可用：{escape(str(emo.get('error')))}</div>"

    lv_kv = ""
    if lv.get("available"):
        lv_kv = f"""
<dl class="kv">
<dt>口径</dt><dd class="mono">{escape(str(lv.get('basis')))}</dd>
<dt>买参考</dt><dd class="mono">{escape(str(lv.get('buy_reference')))}</dd>
<dt>卖参考</dt><dd class="mono">{escape(str(lv.get('sell_reference')))}</dd>
<dt>止损</dt><dd class="mono">{escape(str(lv.get('stop_price')))}</dd>
<dt>目标</dt><dd class="mono">{escape(str(lv.get('target_price')))}</dd>
</dl>"""
    else:
        lv_kv = f"<div class='warn'>结构位不可用：{escape(str(lv.get('error')))}</div>"

    tree_kv = _levels_tree_block(cpt.get("levels_tree") or {})
    trust_kv = _trust_block(cpt, cpt.get("quote") or {})

    body = f"""
<h1>同票并排 · {escape(code)}</h1>
<div class="sub">{escape(payload['notice'])}<br>
生成于 <span class="mono">{escape(payload['generated_at'])}</span></div>
{input_box}
<table><tr><th>口径</th><th>结论</th><th>方向</th></tr>
{verdict_rows()}</table>
{conflict_html}
<div class="cols">
  <div class="card"><h3>CPT · 确定性缠论</h3>{cpt_kv}</div>
  <div class="card"><h3>emotion-core · 情绪周期</h3>{emo_kv}</div>
</div>
<div class="card" style="margin-top:14px"><h3>结构位（emotion 口径）</h3>{lv_kv}</div>
<div class="card" style="margin-top:14px"><h3>结构级别树（CPT 确定性缠论）</h3>{tree_kv}</div>
<div class="card" style="margin-top:14px"><h3>数据可信度</h3>{trust_kv}</div>
<div class="note">本页<b>只读</b>：不写任何库、不改任何状态。差异只陈述事实，不裁决。</div>"""
    return _page(f"同票并排 {payload['code']}", body)


class FacadeHandler(BaseHTTPRequestHandler):
    """统一入口的请求处理。

    只读：所有路径都不写任何数据。
    """

    server_version = "EmotionCPT/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        _LOG.info("%s - %s", self.address_string(), fmt % args)

    # ── 响应工具 ──
    def _send(
        self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        self._send(
            json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            status,
            "application/json; charset=utf-8",
        )

    def _prefix(self) -> str:
        r"""本门面的**公网挂载前缀**（如 ``/ecpt/``）。

        nginx 剥掉了前缀（\`proxy_pass ...:8092/\`）⇒ 后端看不到自己在哪
        ⇒ 由 nginx 用 \`X-Forwarded-Prefix\` 头告诉它。
        ⇒ 直连 8092 时没有该头 ⇒ 前缀为空 ⇒ 链接走根路径 ⇒ **自洽**。

        ⚠️ 不返回前缀 ⇒ 页面上的「同票并排」会指向 \`/aggregate\`
        ⇒ 那是 nginx 上**不存在**的 location ⇒ 404。
        """
        raw = self.headers.get("X-Forwarded-Prefix", "") or ""
        raw = raw.strip()
        if not raw:
            return ""
        if not raw.startswith("/"):
            raw = "/" + raw
        raw = raw if raw.endswith("/") else raw + "/"
        # ⚠️ 2026-10-25 静态审计：原来**完全信任**客户端给的头
        #    ⇒ `X-Forwarded-Prefix: /"><script>alert(1)</script>` ⇒ 拼进 404 页的
        #    href 属性 ⇒ **反射型 XSS** ⇒ 门面挂在公网 /ecpt/、/dsh/ 下 ⇒ **可达**
        # ⇒ 只接受**白名单**里的前缀，其余一律丢弃。
        if raw not in ALLOWED_PREFIXES:
            return ""
        return raw

    def do_GET(self) -> None:  # noqa: N802
        prefix = self._prefix()
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if path == "/":
            self._send(_portal(prefix))
            return
        if path == "/aggregate":
            code = (query.get("code") or ["600519"])[0]
            self._send(_aggregate_page(code, build_stock_payload(code), prefix))
            return
        m = re.fullmatch(r"/aggregate/stock/([0-9]{1,6})", path)
        if m:
            self._send(_aggregate_page(m.group(1), build_stock_payload(m.group(1)), prefix))
            return
        m = re.fullmatch(r"/api/aggregate/stock/([0-9]{1,6})", path)
        if m:
            self._json(build_stock_payload(m.group(1)))
            return
        if path == "/api/health":
            self._json(_health())
            return
        # ⚠️ 一律 escape：前缀来自请求头 ⇒ 不可信
        self._send(
            _page(
                "404",
                "<h1>404</h1><p>没有这个路径。"
                f"<a href='{escape(prefix or '/')}'>回门户</a></p>",
            ),
            404,
        )

    def do_HEAD(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _health() -> dict[str, Any]:
    """自己 + 三个上游的可达性（只读探活）。"""
    from .aggregate.clients import (
        fetch_cpt_recommendation,
        fetch_emotion_status,
    )

    out: dict[str, Any] = {"ok": True, "self": "emotion-cpt-facade"}
    _, err = fetch_cpt_recommendation("600519")
    out["cpt"] = {"base": "127.0.0.1:8010", "ok": err is None, "error": err}
    data, err = fetch_emotion_status()
    out["emotion_core"] = {"base": "127.0.0.1:8098", "ok": err is None, "error": err,
                           "phase": (data or {}).get("phase")}
    # ⚠️ lab 的 ``/`` 返回 **HTML**，不能按 JSON 解析 ⇒ 用「只看状态码」的探活
    lab_ok, lab_err = _probe_http("http://127.0.0.1:8091", "/")
    out["lab"] = {"base": "127.0.0.1:8091", "ok": lab_ok, "error": lab_err}
    return out


def _probe_http(base: str, path: str, *, timeout: float = 2.0) -> tuple[bool, str | None]:
    """只看 HTTP 状态码的探活（给返回 HTML 的服务用）。"""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(f"{base}{path}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return (200 <= int(resp.status) < 400), None
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emotion-CPT 统一入口门面")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    server = ThreadingHTTPServer((args.host, args.port), FacadeHandler)
    _LOG.info("Emotion-CPT 门面已启动 http://%s:%d/", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _LOG.info("收到中断，退出")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
