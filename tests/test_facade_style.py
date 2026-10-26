"""★ ``/ecpt/`` 门面页与门户主页**同款样式**的回归守卫（2026-10-26）。

## 为什么要有这条门禁

原来门面自带一套**深色**样式（自己的 ``:root`` 变量、10px 圆角、蓝色按钮、
独立字体栈）⇒ 同一个站点里两个页面长得完全不一样
⇒ owner 报「``/ecpt/`` 页面风格和主页要一致」。

⇒ 修法：页面骨架（顶栏 / 卡片 / 按钮 / 配色 / 深浅色）**全部**来自门户主页的
   ``/assets/portal.css``（门户仓是站点视觉的真相源）
⇒ 门面文件里**只**保留「同票并排」页专有的组件样式。

⇒ 这条门禁守住两件事：
   ① 门面页**确实**引用了门户的样式表；
   ② 门面**没有**又偷偷定义一套自己的配色/卡片/按钮（那会把两页又拆开）。
"""

from __future__ import annotations

from emotion_cpt.web import app


def test_page_links_portal_stylesheet() -> None:
    html = app._page("t", "b", "/ecpt/").decode("utf-8")
    assert 'href="/assets/portal.css"' in html


def test_page_has_the_same_topbar_skeleton() -> None:
    html = app._page("t", "b", "/ecpt/").decode("utf-8")
    for token in ('class="topbar"', 'class="brand"', 'class="nav"', "NDORACLE"):
        assert token in html, token


def test_facade_does_not_redefine_the_shared_look() -> None:
    """门面自己的 CSS 里**不许**再出现配色/卡片/按钮/顶栏的定义。"""
    for forbidden in (":root{", ".card{", ".btn{", ".topbar{", "body{", ".wrap{"):
        assert forbidden not in app._CSS, forbidden


def test_facade_components_are_namespaced() -> None:
    """门面专有组件必须带 ``ecpt-`` 前缀（否则会盖掉门户的同名类）。"""
    assert ".ecpt-kv" in app._CSS
    assert ".ecpt-badge" in app._CSS
    assert ".ecpt-warn" in app._CSS


def test_portal_page_uses_portal_layout_classes() -> None:
    html = app._portal("/ecpt/").decode("utf-8")
    for token in (
        'class="grid"',
        'class="card"',
        'class="desc"',
        'class="status"',
        'class="actions"',
        'class="btn primary"',
    ):
        assert token in html, token


def test_entries_are_prefix_aware() -> None:
    """入口链接必须按挂载前缀拼（否则点下去 404）。"""
    html = app._portal("/ecpt/").decode("utf-8")
    assert 'href="/ecpt/cpt/"' in html
    assert 'href="/ecpt/emotion/"' in html
    assert 'href="/ecpt/aggregate"' in html


def test_aggregate_page_keeps_its_components() -> None:
    """「同票并排」页的组件（表格/键值/徽标）不能被改没了。"""
    html = app._aggregate_page("600519", {"ok": False, "error": "x"}, "/ecpt/").decode("utf-8")
    assert "ecpt-form" in html
    assert "ecpt-warn" in html
    assert 'action="/ecpt/aggregate"' in html
