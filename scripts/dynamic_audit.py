#!/usr/bin/env python3
"""Emotion-CPT / portal 的**动态审计**（运行时观测，不改代码）。

静态审计看不出「跑起来会怎样」。这里在真机上量：

1. **端点耗时**（多次采样 ⇒ 看 p95 和抖动）
2. **并发行为**（N 路同时打 ⇒ 会不会打爆上游 / 竞态）
3. **资源趋势**（反复请求后 fd / 内存 / DB 连接有没有涨 ⇒ 泄漏检测）
4. **上游失败时的行为**（拔掉上游会怎样 ⇒ 假红还是假绿）
5. **定时任务**（实际跑没跑、日志新鲜度）
"""

from __future__ import annotations

import json
import os
import pathlib
import statistics
import subprocess
import time
import urllib.error
import urllib.request

PORTAL = "http://127.0.0.1:8099"
ECPT = "http://127.0.0.1:8092"
CPT = "http://127.0.0.1:8010"
EMO = "http://127.0.0.1:8098"

ENDPOINTS = [
    ("portal /api/status", f"{PORTAL}/api/status"),
    ("portal /api/today", f"{PORTAL}/api/today"),
    ("portal /api/attention", f"{PORTAL}/api/attention"),
    ("portal /api/systemd", f"{PORTAL}/api/systemd"),
    ("portal /api/repos", f"{PORTAL}/api/repos"),
    ("portal /api/systemd-units", f"{PORTAL}/api/systemd-units"),
    ("portal /api/daily", f"{PORTAL}/api/daily"),
    ("ecpt /api/health", f"{ECPT}/api/health"),
    ("ecpt /api/aggregate", f"{ECPT}/api/aggregate/stock/600519"),
    ("cpt snapshot", f"{CPT}/api/dashboard/a-share/snapshot?code=600519"),
    ("emotion status", f"{EMO}/api/status"),
]


def timed(url: str, timeout: float = 90.0) -> tuple[int, float, bytes]:
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read()
            code = int(r.status)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        code = int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return -1, time.time() - t0, str(exc).encode()
    return code, time.time() - t0, body


def proc_count(unit: str) -> int:
    try:
        out = subprocess.run(
            ["systemctl", "show", unit, "-p", "MainPID", "--value"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip()
        pid = int(out or 0)
        if pid <= 0:
            return 0
        return len(list(pathlib.Path(f"/proc/{pid}/fd").iterdir()))
    except Exception:  # noqa: BLE001
        return -1


def db_conns() -> int:
    try:
        pw = pathlib.Path.home().joinpath(".dbconfig").read_text().split("$DB_PW=")[1].splitlines()[0]
        host = pathlib.Path.home().joinpath(".dbconfig").read_text().split("$RDSHOST=")[1].splitlines()[0]
        name = pathlib.Path.home().joinpath(".dbconfig").read_text().split("$DBNAME=")[1].splitlines()[0]
        env = {**os.environ, "PGPASSWORD": pw}
        out = subprocess.run(
            ["psql", "-h", host, "-U", "postgres", "-d", name, "-tAc", "SELECT count(*) FROM pg_stat_activity"],
            capture_output=True, text=True, timeout=20, check=False, env=env,
        ).stdout.strip()
        return int(out) if out.isdigit() else -1
    except Exception:  # noqa: BLE001
        return -1


def main() -> int:
    print("=" * 70)
    print("① 端点耗时（3 次采样）")
    print("=" * 70)
    slow = []
    for name, url in ENDPOINTS:
        samples = []
        codes = []
        for _ in range(3):
            c, dt, _b = timed(url)
            samples.append(dt)
            codes.append(c)
        p95 = max(samples)
        flag = "  ⚠️ 慢" if p95 > 5 else ""
        print(f"  {name:28} {codes[-1]:>4}  max={p95:6.2f}s{flag}")
        if p95 > 5:
            slow.append((name, p95))
    if slow:
        print("  ⇒ 慢端点：" + "、".join(f"{n}({t:.1f}s)" for n, t in slow))

    print()
    print("=" * 70)
    print("② 资源趋势（前后各测一次，中间打 40 次）")
    print("=" * 70)
    before = {
        "portal fd": proc_count("portal.service"),
        "cpt fd": proc_count("cpt-dashboard.service"),
        "ecpt fd": proc_count("emotion-cpt-web.service"),
        "emo fd": proc_count("emotion-core-dash.service"),
        "DB 连接": db_conns(),
    }
    for _ in range(40):
        for _n, url in ENDPOINTS:
            timed(url, timeout=30)
    time.sleep(2)
    after = {
        "portal fd": proc_count("portal.service"),
        "cpt fd": proc_count("cpt-dashboard.service"),
        "ecpt fd": proc_count("emotion-cpt-web.service"),
        "emo fd": proc_count("emotion-core-dash.service"),
        "DB 连接": db_conns(),
    }
    print(f"  {'指标':<12} {'前':>8} {'后':>8}  变化")
    for k in before:
        d = after[k] - before[k]
        mark = "  ⚠️ 涨了" if d > 5 else ""
        print(f"  {k:<12} {before[k]:>8} {after[k]:>8}  {d:+d}{mark}")

    print()
    print("=" * 70)
    print("③ 并发行为（8 路同时打同一端点）")
    print("=" * 70)
    import threading

    for name, url in (("portal /api/today", f"{PORTAL}/api/today"),
                      ("portal /api/attention", f"{PORTAL}/api/attention"),
                      ("ecpt /api/aggregate", f"{ECPT}/api/aggregate/stock/600519")):
        results = []
        lock = threading.Lock()

        def worker():
            c, dt, body = timed(url, timeout=90)
            with lock:
                results.append((c, dt, body))

        t0 = time.time()
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total = time.time() - t0
        codes = [r[0] for r in results]
        bodies = {r[2][:200] for r in results}
        print(f"  {name:26} 总耗时={total:5.2f}s 状态码={set(codes)}  "
              f"最慢={max(r[1] for r in results):5.2f}s 响应一致={'是' if len(bodies) == 1 else '否'}")

    print()
    print("=" * 70)
    print("④ 定时任务：最近有没有真的跑")
    print("=" * 70)
    for log in ("/home/ubuntu/logs/cron-daily-report.log",
                "/home/ubuntu/logs/factor-recompute.log",
                "/home/ubuntu/logs/track-maintenance.log",
                "/home/ubuntu/logs/ec-dash-watchdog.log",
                "/home/ubuntu/logs/ops-retention.log"):
        p = pathlib.Path(log)
        if not p.exists():
            print(f"  {p.name:32} (不存在)")
            continue
        age = (time.time() - p.stat().st_mtime) / 60
        flag = "  ⚠️ 很久没写" if age > 60 else ""
        print(f"  {p.name:32} 最后写入 {age:7.1f} 分钟前{flag}")

    print()
    print("=" * 70)
    print("⑤ 上游失败时的行为（**只读探测**，不改配置）")
    print("=" * 70)
    # 拨一个一定不通的端口 ⇒ 看客户端怎么处理
    c, dt, body = timed("http://127.0.0.1:1/api/status", timeout=10)
    print(f"  连死端口: 状态码={c} 耗时={dt:.2f}s 响应={body[:80]!r}")
    # 门户的上游是否真的活着
    for label, url in (("CPT", f"{CPT}/api/dashboard/health"),
                       ("emotion", f"{EMO}/api/status")):
        c, dt, _b = timed(url, timeout=15)
        print(f"  {label:8} 状态码={c} 耗时={dt:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
