"""crontab 真相源的**唯一解析实现**。

⚠️ 为什么单独一个模块：这份解析逻辑需要被**三方**共用 ——
`emotion_cpt.cli.check_crontab`（门禁）、CPT 的 `cron_daily_report`（日报扫哪些日志）、
以及各仓的守护测试（双向比对）。**以前 CPT 仓自己抄了一份手写清单**
（`scripts/cron_daily_report.py` 的 ``JOBS``）⇒ 因子重算的日志重定向被弄丢时，
日报扫着一个**不存在的日志**，而真正的作业失败**没人知道**。

⇒ 现在只有这一个实现，日报的 JOBS 由 ``jobs_from_crontab()`` **推导**，
不再手抄 ⇒ 漂移在结构上不可能发生。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: crontab 真相源（随包分发）
CRONTAB_PATH: Path = Path(__file__).resolve().parent / "cron" / "crontab"

#: 日志重定向：``>> /path/to.log`` 或 ``>> /path/to.log 2>&1``
_LOG_RE = re.compile(r">>\s*(\S+)")


#: 归属分组注释：``# owner: <名字>``
#: ⚠️ 这是**归属声明**，不是注释 —— 门禁按它分组报告。
_OWNER_RE = re.compile(r"^#\s*[-─]*\s*owner:\s*([A-Za-z0-9_.-]+)", re.M)


@dataclass(frozen=True)
class CronJob:
    """一条 crontab 作业。

    ⚠️ 身份是**整行**（调度 + 命令），不是命令 —— 两条不同时间、**同一条命令**
    的作业（``factor-carry-forward.sh`` 的 09:45 与 11:30）按命令做 key
    会被字典合并成一条，门禁视野里少一条 ⇒ 增删可能完全不报警。
    """

    line: str
    schedule: str
    command: str
    script: str
    log: str | None
    #: **归属**：这条作业归哪个仓（``emotion-cpt`` / ``cpt`` / ``jc`` / ``ops`` …）
    #: ⚠️ 「真相源的宿主」≠「作业的 owner」—— Emotion-CPT 存着全部副本，
    #:    但变更责任在原仓。归属显式化，报红时才能说清「这条归谁」。
    owner: str = ""


def parse_crontab(text: str) -> tuple[CronJob, ...]:
    """把 crontab 文本解析成作业序列（保持文件里的顺序）。

    **归属**由 ``# owner: <名字>`` 分组注释声明 ⇒ 每条作业带上它的 owner。
    没声明 owner 的作业归 ``""``（⇒ 门禁会当「未归属」单独点名）。
    """
    # 先算出每个分组注释的**行号**，再顺着走
    owner_at: list[tuple[int, str]] = [
        (m.start(), m.group(1)) for m in _OWNER_RE.finditer(text)
    ]

    jobs: list[CronJob] = []
    pos = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            pos += len(raw) + 1
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            # 形如 ``SHELL=/bin/bash`` 的环境赋值行，不是作业
            pos += len(raw) + 1
            continue
        schedule = " ".join(parts[:5])
        command = parts[5].strip()
        m = _LOG_RE.search(command)
        log = m.group(1) if m else None
        script = command.split()[0] if command.split() else ""
        # 归属 = 最后一个出现在本行**之前**的分组注释
        owner = ""
        for at, name in owner_at:
            if at < pos:
                owner = name
            else:
                break
        jobs.append(
            CronJob(
                line=line,
                schedule=schedule,
                command=command,
                script=script,
                log=log,
                owner=owner,
            )
        )
        pos += len(raw) + 1
    return tuple(jobs)


def load_crontab(path: Path | None = None) -> tuple[CronJob, ...]:
    """读 crontab 真相源并解析。"""
    p = path or CRONTAB_PATH
    return parse_crontab(p.read_text(encoding="utf-8"))


def group_by_owner(
    jobs: tuple[CronJob, ...] | None = None,
) -> dict[str, list[CronJob]]:
    """按归属分组（保持组内顺序）。"""
    jobs = load_crontab() if jobs is None else jobs
    out: dict[str, list[CronJob]] = {}
    for job in jobs:
        out.setdefault(job.owner or "(未归属)", []).append(job)
    return out


def jobs_from_crontab(path: Path | None = None) -> tuple[tuple[str, str], ...]:
    """从真相源推导出「要扫哪些日志」：``((作业名, 日志路径), ...)``。

    ★ 这是 CPT 日报 ``JOBS`` 的**唯一来源** —— 不再手抄清单。
    只有**写了日志重定向**的作业才进列表（没有日志的作业本来就没日志可扫）。
    作业名取日志文件名（去后缀），与历史行为一致。
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for job in load_crontab(path):
        if not job.log:
            continue
        name = Path(job.log).name
        if name.endswith(".log"):
            name = name[:-4]
        if name in seen:
            continue
        seen.add(name)
        out.append((name, job.log))
    return tuple(out)
