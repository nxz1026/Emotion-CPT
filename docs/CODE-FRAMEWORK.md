# 代码框架文档 —— Emotion-CPT

> 状态：**v1 冻结**（2026-10-23）
> 配套：[README.md](../README.md)（边界）· [IMPLEMENTATION.md](IMPLEMENTATION.md)（阶段）

---

## 1. 设计准则

| # | 准则 | 落地方式 |
|---|---|---|
| 1 | **本仓不实现业务逻辑** | `src/emotion_cpt/` 下只有**约定**与**校验**，没有缠论/情绪/信号算法 |
| 2 | **不 import 上游** | 门禁强制：`emotion_cpt` 不得 import `cpt` / `emotion_core` |
| 3 | **单向依赖** | 上游 → 本仓；本仓 → 上游 = 禁止 |
| 4 | **契约用声明式表达** | 不用 SQL 字符串拼贴，用 dataclass 声明，机器可读 |
| 5 | **语义随契约走** | 单位、量纲、判据归属写进契约本体，不只写进注释 |
| 6 | **门禁先证明自己会红** | 每个检查脚本都要有"注入假数据 → 必须报错"的验收用例 |
| 7 | **零第三方依赖（核心）** | 核心包只用 stdlib；`psycopg` 是唯一可选依赖，且只被 `db` 子包需要 |

---

## 2. 目录结构

```
Emotion-CPT/
├── README.md
├── LICENSE
├── pyproject.toml
├── .gitignore
├── .github/workflows/ci.yml
│
├── docs/
│   ├── IMPLEMENTATION.md          # 实施文档
│   ├── CODE-FRAMEWORK.md          # 本文件
│   ├── CONTRACTS.md               # 契约总览（人读版，机器版在 contracts/）
│   └── adr/
│       ├── 0001-独立项目与单向依赖.md
│       ├── 0002-不合并进程.md
│       └── 0003-契约用声明式表达.md
│
├── src/emotion_cpt/
│   ├── __init__.py
│   ├── contracts/                 # ★ 跨项目契约（唯一定义处）
│   │   ├── __init__.py
│   │   ├── tables.py              #   47 张表的归属 / 写入方 / 读取方 / 新鲜度
│   │   ├── intraday_seal.py       #   9 列声明（带单位与语义）
│   │   ├── pricing.py             #   6 个契约常量
│   │   ├── shared_tables.py       #   7 张共享表清单 + 新鲜度判据
│   │   └── errors.py
│   ├── db/                        # 数据访问层
│   │   ├── __init__.py
│   │   ├── config.py              #   ~/.dbconfig 解析（$KEY=value 口径）
│   │   ├── connection.py          #   psycopg 连接参数（唯一实现）
│   │   └── probe.py               #   只读探针：契约指纹 / 表清单
│   ├── schema/                    # schema 真相源
│   │   ├── __init__.py
│   │   ├── manifest.py            #   表 manifest 的加载与查询
│   │   └── migrations/            #   迁移目录（跨项目统一时间线）
│   ├── structure/                 # ★ 结构计算内核（缠论判据唯一实现处）
│   │   ├── __init__.py
│   │   ├── models.py              #   Fractal / Bi / ZhongShu / TrendType + overlays 契约
│   │   ├── bi.py                  #   笔（含 min_bi_len 门槛：跨度不足合并端点）
│   │   ├── fractal.py             #   分型
│   │   ├── levels.py              #   级别
│   │   ├── contain.py             #   包含关系
│   │   ├── containment_trace.py   #   包含关系追踪
│   │   ├── recursion.py           #   递归
│   │   ├── signal.py              #   信号
│   │   ├── structure_events.py    #   结构事件
│   │   ├── trend_type.py          #   趋势类型
│   │   ├── zhongshu.py            #   中枢
│   │   ├── types.py               #   共享类型
│   │   ├── config.py              #   内核配置
│   │   ├── first_buy.py           #   一买判据
│   │   ├── a_share_rules.py       #   A 股判据
│   │   ├── intraday_rules.py      #   盘中判据
│   │   ├── market_time.py         #   交易时段
│   │   └── price.py               #   ★ 价格口径（整数分算法，P6）
│   ├── snapshot/                  # ★ 快照计算（K 线 → 结构 → overlays → 结构位）
│   │   ├── __init__.py
│   │   ├── pipeline.py            #   compute_snapshot()
│   │   └── points.py              #   ★ 结构位算式（P3 统一：取整 2 位）
│   ├── web/                       # 统一 web 入口
│   │   ├── __init__.py
│   │   ├── app.py                 #   ★ 入口门面（:8092，零三方依赖）
│   │   ├── facade.py              #   门户 + 挂载
│   │   └── aggregate/             #   同票并排（只读聚合页）
│   │       ├── __init__.py
│   │       ├── server.py
│   │       └── clients.py         #   对 CPT / emotion 的只读 HTTP 客户端
│   └── cli/                       # 命令行入口
│       ├── __init__.py
│       ├── check_contracts.py
│       ├── check_manifest.py
│       ├── check_crontab.py
│       ├── check_unit_paths.py
│       ├── check_doc_drift.py      #   ★ 文档 ↔ 代码 漂移
│       └── probe.py
│
├── scripts/                       # 门禁脚本（薄封装，逻辑在 cli/）+ 安装器
│   ├── check_contracts.sh
│   ├── check_crontab.sh
│   ├── check_manifest.sh
│   ├── install_crontab.sh         # ★ crontab 真相源 → 线上（带备份 + 校验）
│   └── install_units.sh           # ★ unit 真相源 → 线上（带备份 + 校验）
├── tests/
│   ├── test_contracts.py
│   ├── test_manifest.py
│   ├── test_gate_selftest.py      # ★ 门禁自证：注入假数据必须报错
│   ├── test_price_equivalence.py  # ★ 价格口径三方穷举对等
│   ├── test_aggregate.py
│   ├── test_web_aggregate.py
│   ├── test_facade.py
│   └── test_probe.py
└── deploy/                        # 仓根只放**运行时**资产
    ├── cron/
    │   ├── emotion-dash-watchdog.sh   # ★ 看板存活看门狗
    │   └── README.md
    ├── nginx/
    │   ├── ecpt-facade.conf
    │   └── README.md
    └── systemd/README.md           # unit 真相源在包内（见下）
```

---

## 3. 包职责与依赖方向

```
            ┌──────────────────────────────┐
            │        emotion_cpt.web        │  门户 + 聚合页（只读）
            │  （只走 HTTP，不 import 上游） │
            └───────────────┬──────────────┘
                            │
            ┌───────────────▼──────────────┐
            │      emotion_cpt.cli         │  门禁命令
            └───────────────┬──────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐ ┌────────▼─────────┐ ┌───────▼────────┐
│ emotion_cpt.   │ │ emotion_cpt.     │ │ emotion_cpt.   │
│   contracts    │ │      db          │ │    schema      │
│  （纯数据，     │ │ （唯一连库实现）  │ │ （manifest +   │
│    无 I/O）    │ │                 │ │   迁移）        │
└───────┬────────┘ └──────────────────┘ └────────────────┘
        │
        │  上游（cpt / emotion_core）在此方向上依赖本仓
        ▼
```

**规则**：
- `contracts` **零 I/O、零依赖**（纯 stdlib）⇒ 可被任何环境 import，校验成本极低
- `db` 是**唯一的连库实现**；本仓其它地方不直接碰 psycopg
- `web` **只走 HTTP 调上游**，不 import 上游 ⇒ 展示层也不纠缠
- `schema` 只描述"谁拥有什么"，不执行迁移（执行由上游各自的迁移流程负责）

---

## 4. 公共 API 面

### 4.1 `emotion_cpt.contracts`

```python
from emotion_cpt.contracts.pricing import BUY_BUFFER, SELL_BUFFER, STOP_LOSS_RATIO
from emotion_cpt.contracts.intraday_seal import INTRADAY_SEAL_COLUMNS, INTRADAY_SEAL_TABLE
from emotion_cpt.contracts.tables import TABLES, table_of, tables_of
from emotion_cpt.contracts.shared_tables import SHARED_TABLES, REVERSE_TABLES
```

**所有导出都是不可变（frozen dataclass / tuple）**，避免契约本身被就地改写。

### 4.2 `emotion_cpt.db`

```python
from emotion_cpt.db.config import read_dbconfig      # -> dict[str, str]
from emotion_cpt.db.connection import connection_kwargs, connect
```

**口径（必须与上游一致，否则连接会失败）**：
- `~/.dbconfig` 是**字面量 `$KEY=value` 行**，不是 shell 脚本（`source` 不生效）
- 只认以 `$` 开头且含 `=` 的行；其余（注释、空行）静默跳过
- 库名取 `$DBNAME`，默认 `emotion_core`；用户 `postgres`；端口 `5432`
- `sslmode=prefer`

### 4.3 `emotion_cpt.web.aggregate`

```python
from emotion_cpt.web.aggregate.clients import CptClient, EmotionClient
from emotion_cpt.web.aggregate.server import build_stock_payload
```

**客户端硬约束**（沿用上游 `cpt_client` 的纪律）：
- 只走回环 `127.0.0.1`，**不接受调用方传 host**
- 超时上限明确（建议 3s）
- **绝不抛异常** —— 任何失败返回 `None` + 结构化的"不可用原因"
- 只调**读**端点（`/api/dashboard/a-share/snapshot`、`/api/status` 等），**不调写端点**

---

## 5. 门禁清单

| 脚本 | 检查什么 | 红了意味着 |
|---|---|---|
| `check_contracts.py` | 本仓契约 ↔ 上游两侧实际代码值 | 有一侧漂移了，**必须裁决** |
| `check_table_manifest.py` | manifest ↔ 真库 `pg_tables` | 有表没登记，或登记了表不存在 |
| `check_crontab.py` | 仓内 ↔ 线上 crontab **双向** | 有作业只活在一侧（**静默停摆的 catcher**） |
| `check_unit_paths.py` | systemd unit 里的写死路径是否存在 | unit 会指向不存在的目录 |
| `check_doc_drift.py` | 本仓文档里的数字/声明 ↔ 代码 | 文档开始漂移（上游同款问题，不重蹈） |
| `test_gate_selftest.py` | 每个门禁注入假数据后**必须报错** | 门禁本身是坏的（上游 R45 教训） |

---

## 6. 编码约定

| 项 | 约定 |
|---|---|
| Python | `>= 3.12`；核心包零三方依赖 |
| 行宽 | 100（CPT 口径，ruff） |
| 类型 | 全量注解（mypy strict 口径） |
| 命名 | 模块/函数 `snake_case`，常量 `UPPER_SNAKE`，契约类 `CamelCase` |
| 注释 | **解释"为什么"**，不解释"是什么"；口径陷阱必须留注释 |
| 契约变更 | 任何契约常量变更 = **破坏性变更**，需版本号 + 弃用期 |
| 日志 | 禁打凭据；契约探针输出**只含指纹**，不含任何业务数据 |
| 提交 | 一个提交一件事；跨项目契约变更**必须**在 commit message 写明影响的上游 |

---

## 7. 扩展点（未来若要吸收上游，本仓怎么长）

本仓**当前不实现**这些，但结构上预留了位置：

- **共享内核形态**：若将来要把 `cpt.domain`（纯 stdlib 的确定性缠论内核）抽成公共包，
  它应该落在这里 —— `emotion_cpt.kernel` 或独立仓 + 本仓做 facade。
  ⚠️ 前提是 owner 认可"对外冻结缠论判据"这件事。
- **全量 monorepo 形态**：本仓的目录结构（`packages/` 预留）可作为落点，
  但那是**另一个决定**，不在本仓 v1 范围内。
- **更多上游**：契约层是通用的 —— 再接入第三个项目时，只需在 `tables.py` 加一批 `TableSpec`，
  不需要动其它包。

---

## 8. 测试策略

| 层次 | 测什么 | 要点 |
|---|---|---|
| 单元 | 契约常量的值与不可变性 | 纯数据，零 I/O，最快 |
| 契约 | manifest 与契约表清单自洽 | 47 张表全覆盖、无重无漏 |
| 门禁自证 | 注入假数据 ⇒ 门禁必须红 | **每个门禁都要有**（上游 R45 教训） |
| 探针 | 只读探针的输出格式稳定 | 指纹算法变更 = 破坏性变更 |
| 集成 | 连真库跑 manifest 比对 | 需 `~/.dbconfig`；CI 用 service 容器 |

**CI 矩阵**：Python 3.12 / 3.14（与上游 CPT 对齐）。
**CI 门禁分层**：本仓自身是新建的，门禁可以从第一天就硬挂（不像上游 emotion-core 有 291 条历史债务）。
