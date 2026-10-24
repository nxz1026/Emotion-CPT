"""门面的入口定义与 nginx 片段。"""

from __future__ import annotations

from emotion_cpt.web.facade import DEFAULT_PORT, ENTRIES, NGINX_PREFIX, nginx_location_snippet


def test_entries_have_unique_paths():
    paths = [e[0] for e in ENTRIES]
    assert len(paths) == len(set(paths))


def test_facade_port_not_conflicting():
    """8091=lab / 8098=emotion 看板 / 8099=旧门户 / 8010=CPT —— 门面不能占这些。"""
    assert DEFAULT_PORT not in (8010, 8091, 8098, 8099)


def test_nginx_snippet_shape():
    snippet = nginx_location_snippet()
    assert NGINX_PREFIX in snippet
    assert f"127.0.0.1:{DEFAULT_PORT}" in snippet
    assert "proxy_pass" in snippet
