"""★ crontab 门禁的**自证**：读不到 ≠ 线上是空的。

纪律来源：上游 R45 —— *「自制的验证工具第一版基本都错」*，
以及 2026-11-01 的**真实误诊**：在 DSH bash 沙箱里跑门禁，
``crontab -l`` 因 ``/var/spool/cron/crontabs/`` 权限被拒而**读不到**，
旧实现把 stdout 的空串当成「线上没有作业」⇒ 报「仓内有、线上没有」16 条
⇒ 白查一轮线上 crontab。

所以这里钉死三件事：

1. **权限类失败** ⇒ ``_live_crontab()`` 返回 ``None``，门禁跳过双向对账并明说；
2. **确实没有 crontab**（``no crontab for <user>``）⇒ 返回 ``""``，
   门禁照旧报红（真实丢作业**不能**被新逻辑吞掉）；
3. **读到了** ⇒ 返回原文，双向对账正常比对。
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from emotion_cpt.cli import check_crontab as cc

#: 一行干净的作业（脚本用 /bin/true，保证存在 + 有执行位）
JOB = "*/5 * * * * /bin/true >> /tmp/x.log 2>&1"


def _repo_crontab(tmp_path):
    p = tmp_path / "crontab"
    p.write_text(f"# owner: emotion-cpt\n{JOB}\n", encoding="utf-8")
    return p


def _stub(monkeypatch, *, returncode, stdout="", stderr=""):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0] if args else [], returncode=returncode, stdout=stdout, stderr=stderr
        )

    monkeypatch.setattr(cc.subprocess, "run", fake_run)


def test_live_read_permission_denied_is_unknown_not_empty(monkeypatch):
    """权限被拒 ⇒ None（未知），**不是**空串（线上没有）。"""
    _stub(
        monkeypatch,
        returncode=1,
        stderr="crontabs/ubuntu/: fopen: Permission denied",
    )
    assert cc._live_crontab() is None


def test_live_read_no_crontab_is_empty(monkeypatch):
    """``no crontab for <user>`` 是**真实状态**：该用户没有 crontab。"""
    _stub(monkeypatch, returncode=1, stderr="no crontab for ubuntu")
    assert cc._live_crontab() == ""


def test_live_read_ok_returns_text(monkeypatch):
    _stub(monkeypatch, returncode=0, stdout=f"{JOB}\n")
    assert cc._live_crontab() == f"{JOB}\n"


def test_live_read_oserror_is_unknown(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("crontab: not found")

    monkeypatch.setattr(cc.subprocess, "run", boom)
    assert cc._live_crontab() is None


def test_gate_skips_reconcile_when_unreadable(monkeypatch, tmp_path, capsys):
    """读不到 ⇒ **不报**「仓内有、线上没有」，但要**明说**没对账。"""
    repo = _repo_crontab(tmp_path)
    _stub(monkeypatch, returncode=1, stderr="crontabs/ubuntu/: fopen: Permission denied")

    rc = cc.main(["--crontab-file", str(repo)])
    out, err = capsys.readouterr()

    assert rc == 0
    assert "仓内有、线上没有" not in err
    assert "未对账" in out
    assert "跳过双向对账" in err


def test_gate_still_red_when_live_really_empty(monkeypatch, tmp_path, capsys):
    """线上**确实**没有 crontab ⇒ 必须照旧报红（新逻辑不能吞掉真丢作业）。"""
    repo = _repo_crontab(tmp_path)
    _stub(monkeypatch, returncode=1, stderr="no crontab for ubuntu")

    rc = cc.main(["--crontab-file", str(repo)])
    _, err = capsys.readouterr()

    assert rc == 1
    assert "仓内有、线上没有" in err


def test_gate_green_when_live_matches(monkeypatch, tmp_path, capsys):
    repo = _repo_crontab(tmp_path)
    _stub(monkeypatch, returncode=0, stdout=f"{JOB}\n")

    rc = cc.main(["--crontab-file", str(repo)])
    out, _ = capsys.readouterr()

    assert rc == 0
    assert "crontab 一致" in out
    assert "未对账" not in out


def test_gate_red_when_live_has_extra_job(monkeypatch, tmp_path, capsys):
    """线上独有 ⇒ 报红（会静默消失的那类）。"""
    repo = _repo_crontab(tmp_path)
    extra = "0 3 * * * /bin/true >> /tmp/y.log 2>&1"
    _stub(monkeypatch, returncode=0, stdout=f"{JOB}\n{extra}\n")

    rc = cc.main(["--crontab-file", str(repo)])
    _, err = capsys.readouterr()

    assert rc == 1
    assert "线上有、仓内没有" in err


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
