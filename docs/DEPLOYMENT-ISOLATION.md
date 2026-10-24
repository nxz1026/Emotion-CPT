# 部署隔离说明 + 三方对比

> **本文件是生成的**（静态部分），别手改。重算：`python scripts/gen_deployment_isolation.py`（CI 用 `--check` 只校验静态部分）

## 0. 一句话

**Emotion-CPT 是独立运行的项目**：独立进程、独立端口、独立 systemd unit、独立 nginx 入口、**不依赖数据库**、不借上游的 venv。
它与 emotion-core / CPT 的关系是**单向的只读消费**（聚合页去读它们的 HTTP），**不是同一个进程、不是同一套生命周期**。

## 1. 隔离矩阵（静态，来自真相源）

| 维度 | Emotion-CPT | CPT | emotion-core |
|---|---|---|---|
| **systemd unit** | 本仓自己写 | 本仓自己写 | 本仓自己写 |
| **进程** | 独立（`python -m emotion_cpt.web.app`） | 独立 | 独立 |
| **Python 环境** | **系统 python3**（零三方依赖） | 仓内 `.venv` | 仓内 `.venv` |
| **依赖数据库** | **否** | 是 | 是 |
| **对外监听** | 仅 `127.0.0.1` | `127.0.0.1` | `0.0.0.0`（8098） |
| **nginx 入口** | `/ecpt/`（`/dsh/` 兼容别名） | `/cpt/` | `/emotion/` |
| **读上游** | 只读 HTTP | — | — |
| **被上游读** | 否（单向下游） | 是 | 是 |

> ⚠️ 「被上游读 = 否」是**方向性**的关键：
> emotion-core 与 CPT **不 import** Emotion-CPT 的运行时代码，
> 它们只 import **契约包**（`emotion_cpt.contracts`）—— 那是数据，不是进程。

## 2. 归属分组（静态，来自真相源）

Emotion-CPT 是**真相源的宿主**，但**不是所有作业/单元的 owner**。归属由真相源里的 `# owner:` 声明 ⇒ 门禁**按归属分组**报告。

### 2.1 systemd unit

| owner | 个数 | 单元 |
|---|---|---|
| **cpt** | 5 | `cpt-dashboard-ashare.service`、`cpt-dashboard-ashare.timer`、`cpt-dashboard.service`、`cpt-intraday-collect.service`、`cpt-intraday-collect.timer` |
| **emotion-core** | 15 | `emotion-core-daily.service`、`emotion-core-daily.timer`、`emotion-core-dash.service`、`emotion-core-pool.service`、`emotion-core-pool.timer`、`emotion-core-report.service`、`emotion-core-report.timer`、`emotion-core-strategy.service`、`emotion-core-strategy.timer`、`emotion-core-watchdog.service`、`emotion-core-watchdog.timer`、`emotion-intraday.service`、`emotion-lab-web.service`、`emotion-lab.service`、`emotion-lab.timer` |
| **emotion-cpt** | 1 | `emotion-cpt-web.service` |

### 2.2 crontab 作业

| owner | 条数 | 说明 |
|---|---|---|
| **cpt** | 11 | 代管：副本在此，**变更责任在 CPT 仓** |
| **emotion-cpt** | 1 | 本仓自己的作业（本仓负责） |
| **jc** | 3 | 外部：脚本不在任何仓，但**必须登记**（丢了只会静默消失） |
| **ops** | 1 | 外部：运维备份，同上 |

> ⚠️ **为什么代管是对的**：副本收在一处（消灭三份副本，这是 P7 的价值），但**变更责任仍在原仓**。宿主 ≠ owner —— 这两件事混在一起，才叫纠缠。

## 3. 隔离的三条**可执行**断言

「独立故障域」不是设计声明，是会失败的断言 ——
`tests/test_facade_isolation.py`：

| 层 | 断言 |
|---|---|
| 进程层 | 门面的 unit **不依赖 postgresql**、不借上游 venv |
| 数据层 | 上游**全部打死**时 `/api/health` 仍 200，逐源报「不可达 + 原因」 |
| 页面层 | 上游**全部打死**时聚合页仍 200（**降级展示**，不是 500） |

⇒ 上游挂了，Emotion-CPT 的门户、聚合页、契约门禁、部署真相源**照常工作**。这就是「独立运行」的可执行含义。

## 4. 纠缠点清单

| 纠缠点 | 状态 | 处置 |
|---|---|---|
| 真相源里混着 15/16 条上游作业 | ✅ **已解** | 归属 `# owner:` 显式化，门禁按归属分组报告 |
| 真相源里混着 20/21 个上游 unit | ✅ **已解** | 每个 unit 头加 `# owner:` 声明 |
| 门禁与 `cron_spec` 两份 crontab 解析实现 | ✅ **已解** | 门禁改用 `cron_spec`（唯一实现） |
| 门面读上游 | ⚠️ **保留**（单向只读） | 这是聚合页的**目的**；已用降级路径保证上游挂了不崩 |
| portal 仓的 24 个 unit 副本 | ⏸ **留着** | owner 裁决 Q7=C「不动」⇒ 那份漂移**没有自动化守护** |

<!-- machine-snapshot:start -->

## 5. 真机快照

> ⚠️ **快照，不是真相源** —— 真值在 `src/emotion_cpt/deploy/` 与 systemctl 里。
> 重采：`python scripts/gen_deployment_isolation.py --collect`

采集时间（UTC）：**2026-10-24 10:50:32Z**

### 5.1 监听端口

| 端口 | 归属 |
|---|---|
| `0.0.0.0:443` | nginx |
| `0.0.0.0:80` | nginx |
| `0.0.0.0:8098` | emotion-core-dash |
| `127.0.0.1:8021` | dsh-bridge |
| `127.0.0.1:8010` | cpt-dashboard |
| `127.0.0.1:8092` | emotion-cpt-web |
| `127.0.0.1:8091` | emotion-lab-web |
| `127.0.0.1:8077` | league-web |
| `127.0.0.1:8099` | portal |

### 5.2 nginx 的 location → 后端

| `/dashboard/jc/static/` | `http://127.0.0.1:8077/static/` |
| `/dashboard/jc/api/` | `http://127.0.0.1:8077/api/` |
| `/dashboard/` | `http://127.0.0.1:8099/` |
| `/cpt/api/` | `http://127.0.0.1:8010/api/` |
| `/emotion/` | `http://127.0.0.1:8098/` |
| `/trade/` | `http://127.0.0.1:8098/api/trade/` |
| `/bridge/` | `http://127.0.0.1:8021/` |
| `/` | `http://127.0.0.1:3080` |
| `/api/dsh-free-search-settings/` | `http://127.0.0.1:3080` |
| `/api/dsh-skill-explorer/` | `http://127.0.0.1:3080` |
| `/ecpt/` | `http://127.0.0.1:8092/` |
| `/dsh/` | `http://127.0.0.1:8092/` |

### 5.3 服务状态

| unit | 状态 |
|---|---|
| `emotion-cpt-web.service` | active |
| `cpt-dashboard.service` | active |
| `emotion-core-dash.service` | active |
| `emotion-intraday.service` | active |
| `emotion-lab-web.service` | active |

<!-- machine-snapshot:end -->
