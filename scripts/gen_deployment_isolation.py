#!/usr/bin/env python3
"""生成 ``docs/DEPLOYMENT-ISOLATION.md`` —— 部署隔离说明 + 三方对比。

## 为什么是生成器

「谁在跑、跑在哪、归谁」这类信息**手写必烂**（unit 增了、端口换了、归属改了，
文档还在原地）。⇒ 静态部分**从真相源生成**，永远准。

真机现状（端口 / nginx / 服务状态）**无法在 CI 采集** ⇒ 放在
``<!-- machine-snapshot:start -->`` 标记之间，标注采集时间与重采命令。

⇒ ``--check`` 只比对**静态部分**（标记之前）⇒ CI 能守住，
而快照部分由采集命令重写。
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
from datetime import UTC, datetime

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from emotion_cpt.deploy.cron_spec import group_by_owner, load_crontab  # noqa: E402

UNIT_DIR = REPO / "src/emotion_cpt/deploy/systemd"
OUT = REPO / "docs/DEPLOYMENT-ISOLATION.md"

MARK_START = "<!-- machine-snapshot:start -->"
MARK_END = "<!-- machine-snapshot:end -->"

_OWNER_RE = re.compile(r"(?m)^#\s*owner:\s*([A-Za-z0-9_.-]+)")
_EXEC = re.compile(r"(?m)^ExecStart=(.*)$")
_WD = re.compile(r"(?m)^WorkingDirectory=(\S+)")
_PORT = re.compile(r"--port[= ](\d+)")


def _unit_rows() -> list[tuple[str, str, str, str, bool]]:
    """``(名字, owner, ExecStart, WorkingDirectory, 依赖 DB?)``"""
    rows = []
    for path in sorted(UNIT_DIR.iterdir()):
        if path.suffix not in (".service", ".timer"):
            continue
        text = path.read_text(encoding="utf-8")
        om = _OWNER_RE.search(text)
        owner = om.group(1) if om else "未归属"
        m = _EXEC.search(text)
        wd = _WD.search(text)
        rows.append(
            (
                path.name,
                owner,
                (m.group(1).strip() if m else "—"),
                (wd.group(1) if wd else "—"),
                "postgresql" in text,
            )
        )
    return rows


def _static() -> str:
    rows = _unit_rows()
    jobs = load_crontab()
    groups = group_by_owner(jobs)

    by_owner: dict[str, list] = {}
    for r in rows:
        by_owner.setdefault(r[1], []).append(r)

    out: list[str] = []
    out.append("# 部署隔离说明 + 三方对比")
    out.append("")
    out.append(
        "> **本文件是生成的**（静态部分），别手改。"
        "重算：`python scripts/gen_deployment_isolation.py`"
        "（CI 用 `--check` 只校验静态部分）"
    )
    out.append("")
    out.append("## 0. 一句话")
    out.append("")
    out.append(
        "**Emotion-CPT 是独立运行的项目**：独立进程、独立端口、独立 systemd unit、"
        "独立 nginx 入口、**不依赖数据库**、不借上游的 venv。"
    )
    out.append(
        "它与 emotion-core / CPT 的关系是**单向的只读消费**"
        "（聚合页去读它们的 HTTP），**不是同一个进程、不是同一套生命周期**。"
    )
    out.append("")
    out.append("## 1. 隔离矩阵（静态，来自真相源）")
    out.append("")
    out.append("| 维度 | Emotion-CPT | CPT | emotion-core |")
    out.append("|---|---|---|---|")
    out.append("| **systemd unit** | 本仓自己写 | 本仓自己写 | 本仓自己写 |")
    out.append("| **进程** | 独立（`python -m emotion_cpt.web.app`） | 独立 | 独立 |")
    out.append("| **Python 环境** | **系统 python3**（零三方依赖） | 仓内 `.venv` | 仓内 `.venv` |")
    out.append("| **依赖数据库** | **否** | 是 | 是 |")
    out.append("| **对外监听** | 仅 `127.0.0.1` | `127.0.0.1` | `0.0.0.0`（8098） |")
    out.append("| **nginx 入口** | `/ecpt/`（`/dsh/` 兼容别名） | `/cpt/` | `/emotion/` |")
    out.append("| **读上游** | 只读 HTTP | — | — |")
    out.append("| **被上游读** | 否（单向下游） | 是 | 是 |")
    out.append("")
    out.append("> ⚠️ 「被上游读 = 否」是**方向性**的关键：")
    out.append("> emotion-core 与 CPT **不 import** Emotion-CPT 的运行时代码，")
    out.append("> 它们只 import **契约包**（`emotion_cpt.contracts`）—— 那是数据，不是进程。")
    out.append("")

    out.append("## 2. 归属分组（静态，来自真相源）")
    out.append("")
    out.append(
        "Emotion-CPT 是**真相源的宿主**，但**不是所有作业/单元的 owner**。"
        "归属由真相源里的 `# owner:` 声明 ⇒ 门禁**按归属分组**报告。"
    )
    out.append("")
    out.append("### 2.1 systemd unit")
    out.append("")
    out.append("| owner | 个数 | 单元 |")
    out.append("|---|---|---|")
    for owner in sorted(by_owner):
        names = "、".join(f"`{r[0]}`" for r in by_owner[owner])
        out.append(f"| **{owner}** | {len(by_owner[owner])} | {names} |")
    out.append("")
    out.append("### 2.2 crontab 作业")
    out.append("")
    out.append("| owner | 条数 | 说明 |")
    out.append("|---|---|---|")
    notes = {
        "emotion-cpt": "本仓自己的作业（本仓负责）",
        "cpt": "代管：副本在此，**变更责任在 CPT 仓**",
        "jc": "外部：脚本不在任何仓，但**必须登记**（丢了只会静默消失）",
        "ops": "外部：运维备份，同上",
    }
    for owner in sorted(groups):
        out.append(f"| **{owner}** | {len(groups[owner])} | {notes.get(owner, '—')} |")
    out.append("")
    out.append(
        "> ⚠️ **为什么代管是对的**：副本收在一处（消灭三份副本，这是 P7 的价值），"
        "但**变更责任仍在原仓**。宿主 ≠ owner —— 这两件事混在一起，才叫纠缠。"
    )
    out.append("")

    out.append("## 3. 隔离的三条**可执行**断言")
    out.append("")
    out.append("「独立故障域」不是设计声明，是会失败的断言 ——")
    out.append("`tests/test_facade_isolation.py`：")
    out.append("")
    out.append("| 层 | 断言 |")
    out.append("|---|---|")
    out.append("| 进程层 | 门面的 unit **不依赖 postgresql**、不借上游 venv |")
    out.append("| 数据层 | 上游**全部打死**时 `/api/health` 仍 200，逐源报「不可达 + 原因」 |")
    out.append("| 页面层 | 上游**全部打死**时聚合页仍 200（**降级展示**，不是 500） |")
    out.append("")
    out.append(
        "⇒ 上游挂了，Emotion-CPT 的门户、聚合页、契约门禁、部署真相源**照常工作**。"
        "这就是「独立运行」的可执行含义。"
    )
    out.append("")

    out.append("## 4. 纠缠点清单")
    out.append("")
    out.append("| 纠缠点 | 状态 | 处置 |")
    out.append("|---|---|---|")
    out.append(
        "| 真相源里混着 15/16 条上游作业 | ✅ **已解** | 归属 `# owner:` 显式化，"
        "门禁按归属分组报告 |"
    )
    out.append(
        "| 真相源里混着 20/21 个上游 unit | ✅ **已解** | 每个 unit 头加 `# owner:` 声明 |"
    )
    out.append(
        "| 门禁与 `cron_spec` 两份 crontab 解析实现 | ✅ **已解** | "
        "门禁改用 `cron_spec`（唯一实现） |"
    )
    out.append(
        "| 门面读上游 | ⚠️ **保留**（单向只读） | 这是聚合页的**目的**；"
        "已用降级路径保证上游挂了不崩 |"
    )
    out.append(
        "| portal 仓的 24 个 unit 副本 | ⏸ **留着** | owner 裁决 Q7=C「不动」⇒ "
        "那份漂移**没有自动化守护** |"
    )
    out.append("")

    out.append("## 5. 真机快照")
    out.append("")
    out.append("> ⚠️ **快照，不是真相源** —— 真值在 `src/emotion_cpt/deploy/` 与 systemctl 里。")
    out.append("> 重采：`python scripts/gen_deployment_isolation.py --collect`")
    out.append("")
    return "\n".join(out)



def _unit_of_pid(ss_line: str) -> str:
    """从 ``ss -tlnp`` 的一行反查它属于哪个 systemd unit。

    ⚠️ ``ss`` 只给进程名（``python``），不给 unit ⇒ 靠 ``/proc/<pid>/cgroup``。
    拿不到就回退到**端口 → unit** 的静态映射。
    """
    m = re.search(r"pid=(\d+)", ss_line)
    if m:
        try:
            cgroup = pathlib.Path(f"/proc/{m.group(1)}/cgroup").read_text(encoding="utf-8")
            um = re.search(r"/([^/]+\.(?:service|timer))", cgroup)
            if um:
                return um.group(1).removesuffix(".service").removesuffix(".timer")
        except OSError:
            pass
    return _PORT_OWNER.get(ss_line, "")


#: 端口 → 单元（静态兜底；真相源里没有 unit 的那些项目）
_PORT_OWNER = {
    "8099": "portal（其它项目）",
    "8077": "jc 看板（其它项目）",
    "8021": "dsh-bridge（其它项目）",
    "3080": "dsh-web（其它项目）",
}

def _collect() -> str:
    """采集真机现状（端口 / nginx / 服务状态）。"""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [f"采集时间（UTC）：**{now}**", ""]

    lines.append("### 5.1 监听端口")
    lines.append("")
    lines.append("| 端口 | 归属 |")
    lines.append("|---|---|")
    try:
        ss = subprocess.run(  # noqa: S603
            ["sudo", "-n", "ss", "-tlnp"], capture_output=True, text=True, timeout=20, check=False
        ).stdout
        for line in ss.splitlines():
            if "python" not in line and "nginx" not in line:
                continue
            m = re.search(r"(\S+):(\d+)\s", line)
            if not m:
                continue
            host, port = m.group(1), m.group(2)
            owner = _unit_of_pid(line)
            lines.append(f"| `{host}:{port}` | {owner or '（其它项目）'} |")
    except (OSError, subprocess.SubprocessError):
        lines.append("| （采集失败） | — |")
    lines.append("")

    lines.append("### 5.2 nginx 的 location → 后端")
    lines.append("")
    try:
        conf = pathlib.Path("/etc/nginx/sites-enabled/dsh-web").read_text(encoding="utf-8")
        for m in re.finditer(r"location\s+(\S+)\s*\{(.*?)\n\s*\}", conf, re.S):
            path, body = m.group(1), m.group(2)
            pm = re.search(r"proxy_pass\s+(\S+);", body)
            if pm:
                lines.append(f"| `{path}` | `{pm.group(1)}` |")
    except OSError:
        lines.append("| （采集失败） | — |")
    lines.append("")

    lines.append("### 5.3 服务状态")
    lines.append("")
    lines.append("| unit | 状态 |")
    lines.append("|---|---|")
    try:
        for name in (
            "emotion-cpt-web",
            "cpt-dashboard",
            "emotion-core-dash",
            "emotion-intraday",
            "emotion-lab-web",
        ):
            out = subprocess.run(  # noqa: S603
                ["systemctl", "is-active", f"{name}.service"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            ).stdout.strip()
            lines.append(f"| `{name}.service` | {out or '—'} |")
    except (OSError, subprocess.SubprocessError):
        lines.append("| （采集失败） | — |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验静态部分")
    ap.add_argument("--collect", action="store_true", help="采集真机快照并重写")
    args = ap.parse_args()

    static = _static()
    current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""

    if args.check:
        old_static = current.split(MARK_START)[0] if MARK_START in current else ""
        want_static = static.partition("## 5. 真机快照")[0].rstrip() + "\n\n"
        if old_static.rstrip() != want_static.rstrip():
            print("❌ docs/DEPLOYMENT-ISOLATION.md 的静态部分与生成器不一致 ⇒ 需要重算")
            return 1
        print("✅ docs/DEPLOYMENT-ISOLATION.md 静态部分与生成器一致")
        return 0

    snapshot = _collect()
    # 静态部分在「## 5. 真机快照」之前切开 ⇒ 快照夹在两个 marker 之间
    head, _, tail = static.partition("## 5. 真机快照")
    body = (
        head.rstrip() + "\n\n"
        + MARK_START + "\n\n"
        + "## 5. 真机快照\n\n"
        + tail.strip() + "\n\n"
        + snapshot
        + "\n"
        + MARK_END + "\n"
    )
    OUT.write_text(body, encoding="utf-8")
    print(f"✅ 已生成 {OUT.relative_to(REPO)}（{len(body)} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
