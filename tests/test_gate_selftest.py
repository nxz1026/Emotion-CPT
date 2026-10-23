"""★ 门禁自证：注入假数据后门禁**必须报错**。

纪律来源：上游 R45 —— *「自制的验证工具第一版基本都错」*。
跑全绿还不够，**必须注入假数据确认它还能报**。
"""

from __future__ import annotations

from pathlib import Path

from emotion_cpt.cli import check_crontab, check_manifest, check_unit_paths
from emotion_cpt.contracts.tables import TableSpec


def test_manifest_detects_missing_table():
    """登记了但库里没有 ⇒ 必须报。"""
    manifest = (TableSpec(name="ghost_table", owner="x", writer="x", readers=()),)
    issues = check_manifest.compare(manifest, set())
    assert issues and "ghost_table" in issues[0]


def test_manifest_detects_extra_table():
    """库里有但没登记 ⇒ 必须报。"""
    manifest = (TableSpec(name="known", owner="x", writer="x", readers=()),)
    issues = check_manifest.compare(manifest, {"known", "surprise"})
    assert issues and "surprise" in issues[0]


def test_manifest_clean_when_equal():
    manifest = (TableSpec(name="known", owner="x", writer="x", readers=()),)
    assert check_manifest.compare(manifest, {"known"}) == []


def test_crontab_parser_finds_jobs():
    text = "*/5 * * * * /bin/a.sh\n# comment\n\n0 1 * * 0 /bin/b.sh --flag\n"
    jobs = check_crontab._jobs(text)
    assert set(jobs) == {"/bin/a.sh", "/bin/b.sh --flag"}


def test_crontab_detects_missing_exec_bit(tmp_path: Path):
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o644)  # 故意丢执行位
    assert check_crontab._exec_bits([script]) == [str(script)]


def test_unit_paths_detect_missing_path(tmp_path: Path):
    unit = tmp_path / "x.service"
    unit.write_text("WorkingDirectory=/home/definitely/not/here\n", encoding="utf-8")
    issues = check_unit_paths.check_units(tmp_path)
    assert issues and "/home/definitely/not/here" in issues[0]
