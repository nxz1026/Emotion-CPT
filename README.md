# Emotion-CPT

> **CPT（Chan_Pattern_Trader） × emotion-core 的统一层**
> 独立项目 —— 不搬运、不 import、不依赖 `cpt` / `emotion_core` 的任何模块。

[![CI](https://img.shields.io/badge/CI-pending-lightgrey)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.14-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 1. 一句话

**Emotion-CPT 是 CPT 与 emotion-core 的共用底座：数据层、结构计算（快照）、web 界面层入口，三样都在这里。**

它把两边之间"谁拥有什么、哪个判据说了算"的约定，从 markdown 和手抄常量，变成**可执行的代码与门禁**；
同时把**真正共用的那几层**（数据访问、结构计算、web 入口）**收拢到一处**，
让两个上游项目各自变薄、而不是各自胖。

⚠️ **它不接管业务逻辑。** emotion-core 的情绪判据、CPT 的行情接入与回测框架**都留在原处**。
Emotion-CPT 拿走的是**共用件**，不是**实现**。

---

## 2. 背景：为什么需要它

`nxz1026/Chan_Pattern_Trader`（下称 **CPT**）与 `nxz1026/emotion-core`（下称 **emotion-core**）
是两个独立运行的项目，跑在同一台 Oracle 机器、同一个 PostgreSQL 库 `emotion_core` / `public` schema 上。

它们之间**早已存在双向耦合**，但耦合方式是**约定式**的，而不是代码式的：

```
emotion-core ──写──▶ 7 张共享表 ──▶ CPT 读
CPT ──写──────────▶ intraday_seal_snapshot ──▶ emotion-core 读
emotion-core ──HTTP 127.0.0.1:8010（8 端点，含写）──▶ CPT
CPT ──不反向调 emotion-core
```

后果是**约定漂移**。2026-10-23 的勘察实测到（全部以代码/真机为准，不采信文档）：

| 漂移 | 实测 |
|---|---|
| 表数口径 | 文档写过 8 / 10 / 28 / 33 / 36 / 41，真值 **52** |
| 契约表清单 | 写在 `cpt/docs/shared-tables-contract.md` 的 markdown 表格里，**不受任何门禁保护** |
| `intraday_seal_snapshot` 9 列 | CPT 的 `_INSERT_SQL` 与 emotion 的 `_COLUMNS` **各手抄一份** |
| 5 个价格常量 | emotion-core **手抄** CPT 的值（`BUY_BUFFER` 等），改一边不传播，**且没有测试会红** |
| crontab | 线上 13 条，仓内只有 9 条 —— **4 条线上作业不在任何仓里** |
| systemd unit | 真相源在 `portal` 仓，两个项目仓里**各存一份副本**，要手动同步 |

**"判据只许一处"（ADR 0003 §E2）这条原则在跨仓范围上从未达成。**
Emotion-CPT 就是为了让这条原则**有地方落地**。

### 2.1 搬迁规模实测（AST 传递闭包，2026-10-23）

决定"抽哪一层"的关键数字。**抽 web 层不是抽一层，是抽一串**：

| 层 | 闭包模块 | 行数 | 拖进来什么 | 切口质量 |
|---|---|---|---|---|
| CPT `domain`（缠论内核） | 18 | **3,581** | 只有 domain，**零三方依赖** | 🟢 **唯一干净切口** |
| emotion `presentation` | 19 | **2,770** | presentation11 + services3 + utils3 | 🟢 轻 |
| emotion `data` | 37 | 5,996 | data27 + utils5 + domain5 | 🟢 中等 |
| emotion `lab` | 17 | 2,456 | lab13 + utils3 | 🟢 轻 |
| CPT **快照链** | 71 | 20,243 | application25 + domain15 + adapters14… | 🟡 搬 CPT 大半 |
| CPT **web 层** | 98 | **28,519** | application40 + domain16 + adapters17 + storage10 + llm7 | 🔴 搬 CPT 的 6/7 个包 |

⇒ **正确的顺序是「先抽内核，让 web 层自动变薄」**，而不是「先抽 web 层」。
CPT 的 web 层直接依赖 **39 个 application 模块 / 8,380 行**，
所以它天然是厚的；但一旦结构计算与数据访问归位，web 层就只剩"编排 + 呈现"。

---

## 3. 定位与边界

### 3.1 Emotion-CPT 持有

| 能力 | 内容 | 来源 |
|---|---|---|
| **统一数据层** | `~/.dbconfig` 解析（唯一实现）、psycopg 连接参数、52 张表的 manifest、迁移索引、契约门禁 | 两仓的 `_dbconfig.py` + `utils/db.py` + `data/schema.py` + `scripts/migrations/` |
| **结构计算内核** | 分型 / 笔 / 中枢 / 包含 / 递归 / 趋势 / 背驰 / 结构位 / 买卖点判据 | CPT `cpt/domain/`（18 模块 / 3,581 行 / 零三方依赖） |
| **快照** | 「K 线 → 结构 → overlays → 结构位 → 结论」的**计算部分** | CPT `cpt/application/a_share_snapshot.py`（1,959 行）的计算部分 |
| **统一 web 界面层** | 统一入口门面（门户 + 同票并排聚合页 + 两边 API/静态的挂载） | 新增 + 复用 `DSH/portal` |
| **跨项目契约** | 表归属、9 列声明、5 个价格常量、共享表清单 | 从 markdown 与手抄收敛为代码 |

### 3.2 Emotion-CPT 明确**不做**

- ❌ 不接管业务逻辑：emotion-core 的**情绪判据**（`algorithms/` 9,184 行）留在原处；
  CPT 的**行情接入**（`adapters/`）与**回测框架**（`backtest/`）留在原处
- ❌ 不 import 上游、不依赖上游的内部实现（依赖方向单向，见 §3.3）
- ❌ 不合并进程（保持 8010 / 8098 / 8091 三个独立故障域）
- ❌ 不裁决「三套买点谁为准」（只**暴露**差异，裁决是业务决策）
- ❌ 不搬前端代码：两套前端各自保留在原处，作为静态资源被**挂载**
- ❌ 不改 `~/.dbconfig` 的 `$KEY=value` 格式（两仓共用的既有口径）
- ❌ 不拆分 schema、不改表结构、不动数据

### 3.3 依赖方向（**单向**）

```
   cpt ─────────┐
                ├──▶ emotion_cpt.contracts   （契约）
emotion_core ───┤
                ├──▶ emotion_cpt.db          （数据层）
                ├──▶ emotion_cpt.structure   （结构计算）
                └──▶ emotion_cpt.snapshot    （快照计算）

   emotion_cpt ──✗──▶ cpt / emotion_core      （禁止反向依赖）
```

这个方向是「统一」与「不纠缠」能同时成立的关键：
**Emotion-CPT 永远不知道上游的实现细节；上游只知道"共用件长什么样"。**
门禁（`check_contracts.py` 的依赖方向检查）会强制这条线。

---

## 4. 能力清单（当前状态）

| 模块 | 状态 | 说明 |
|---|---|---|
| `emotion_cpt.contracts` | ✅ 可用 | 表归属（52 张）、9 列声明、5 常量 —— **唯一定义处** |
| `emotion_cpt.db` | ✅ 可用 | `~/.dbconfig` 解析（唯一实现）+ psycopg 连接参数 + 契约指纹探针 |
| `emotion_cpt.schema` | ✅ 可用 | manifest 加载与指纹 + 迁移目录 |
| `emotion_cpt.structure` | 🚧 骨架 | 结构计算内核接口（待自 CPT `cpt/domain/` 逐字搬迁） |
| `emotion_cpt.snapshot` | 🚧 骨架 | 快照计算流水线接口 |
| `emotion_cpt.web` | 🚧 骨架 | 入口门面 + 聚合页（只读客户端与冲突检测已可用） |
| `emotion_cpt.cli` | ✅ 部分可用 | `check_contracts` / `check_manifest` / `check_crontab` / `check_unit_paths` / `probe` |

> 本仓当前处于**文档 + 骨架**阶段。实现按 [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)
> 的阶段推进，每个阶段都有可验证的验收标准。

---

## 5. 文档

| 文档 | 内容 |
|---|---|
| [README.md](README.md) | 本文件 —— 项目定位与边界 |
| [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) | 实施文档：阶段划分、验收、回滚、风险 |
| [docs/CODE-FRAMEWORK.md](docs/CODE-FRAMEWORK.md) | 代码框架文档：目录、包职责、依赖方向、公共 API |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | 契约总览：表归属、列定义、常量、跨仓读取点 |
| [docs/MIGRATION.md](docs/MIGRATION.md) | 搬迁映射：上游哪个文件搬到本仓哪个模块 |
| [docs/adr/](docs/adr/) | 架构决策记录（ADR） |

---

## 6. 相关仓库

| 仓库 | 角色 | 关系 |
|---|---|---|
| [`nxz1026/Chan_Pattern_Trader`](https://github.com/nxz1026/Chan_Pattern_Trader) | CPT · 确定性缠论结构 + 看板 | **独立运行**；契约的消费方 |
| [`nxz1026/emotion-core`](https://github.com/nxz1026/emotion-core) | emotion-core · 情绪周期判据 + 日更选股 | **独立运行**；契约的消费方 |

---

## 7. 环境与凭据

- **PostgreSQL**：库 `emotion_core`，schema `public`，用户 `postgres`。
  连接参数按既有口径从 `~/.dbconfig` 读取（字面量 `$KEY=value` 行，**不是 shell 脚本**）：
  `$RDSHOST` / `$DB_PW` / `$DBNAME`。
  **不得**把凭据写进仓；`~/.dbconfig` 权限须为 `600`。
- **Python**：`>= 3.12`（与两个上游仓对齐，CI 跑 3.12 / 3.14 矩阵）。
- **部署主机**：Oracle（`aarch64`）。仓路径约定 `/home/ubuntu/DSH/<Project>`。

---

## 8. 许可

MIT，见 [LICENSE](LICENSE)。
