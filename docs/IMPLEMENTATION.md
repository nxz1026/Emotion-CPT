# 实施文档 —— Emotion-CPT

> 状态：**v1 冻结**（2026-10-23）
> 前置：[README.md](../README.md)（定位与边界）· [CODE-FRAMEWORK.md](CODE-FRAMEWORK.md)（代码结构）

---

## 0. 实施原则

1. **不改变两个上游项目的运行状态。** 本仓的推进**不得**导致 CPT 或 emotion-core 停摆。
   每个阶段要么只动本仓，要么以「可一键回滚」的方式动上游。
2. **契约先于代码。** 任何跨项目约定的**唯一定义处**必须在本仓，且**必须**有门禁钉住。
3. **门禁要先证明自己会红。** 自制的检查工具第一版基本都错 —— 必须注入假数据确认它能报。
   （沿用上游仓 R45 已立的纪律）
4. **区分「代码里存在」与「文档声称存在」。** 找不到就写"未找到 + 判定命令"，不用文档冒充现状。
5. **一次只解决一件事。** 合并 lint 债务、裁决业务口径这类事，不混进本仓的搬迁动作。

---

## 1. 阶段总览

| 阶段 | 目标 | 动上游? | 人日 | 出口条件 |
|---|---|---|---|---|
| **P0** | 前置验证实验 | ❌ 否 | 1 | 三个实验全部有明确结论 |
| **P1** | 契约 + 数据层就位 | ❌ 否 | 2.5 | 契约常量与连接层落地 + 门禁红绿自证 |
| **P2** | **结构计算内核搬迁** | ❌ 否 | 2 | `emotion_cpt.structure` 可算分型/笔/中枢，与 CPT 逐笔一致 |
| **P3** | **快照计算搬迁** | ❌ 否 | 2 | `emotion_cpt.snapshot` 产出的 overlays 与 CPT 生产一致 |
| **P4** | **web 界面层（门面）** | ✅ 是（挂载配置） | 1.5 | 统一入口 + 同票并排聚合页上线 |
| **P5** | 门禁接入上游 | ✅ 是（只加检查） | 1 | 上游 CI 里出现契约门禁 |
| **P6** | 上游切换到共用件 | ✅ 是 | 2 | CPT/emotion 改用 Emotion-CPT 的数据层与结构层 |
| **P7** | 部署真相源归一 | ✅ 是 | 1 | unit/crontab 单点真相源 + 双向对账 |
| **P8** | 收尾与治理 | ✅ 是 | 0.5 | 文档与门禁齐备 |
| | **合计** | | **13.5** | |

**顺序不可换**：P2（内核）必须早于 P4（web）。
先抽 web 层会连带拖走 CPT 的 98 个模块 / 28,519 行（6/7 个包）；
先抽内核，CPT 的 web 层自然从 28,519 行瘦下来。详见 README §2.1。

---

## 2. P0 · 前置验证实验（1 天，不动任何生产）

三个实验决定后续形态。**在 P0 出结论前，不写任何实现代码。**

### P0-A · 单 venv 兼容性

**问题**：emotion-core 的依赖（akshare / httpx / jinja2）装进同一个环境后，CPT 的全量测试还绿吗？

**做法**（在**拷贝**的环境里做，不动生产 venv）：
```bash
# 在临时目录建一个拷贝环境，装上 emotion 的全部依赖
python3 -m venv /tmp/ec-compat-venv
/tmp/ec-compat-venv/bin/pip install -r <emotion-core>/requirements.txt
/tmp/ec-compat-venv/bin/pip install -r <cpt>/requirements-dev.txt
/tmp/ec-compat-venv/bin/pip install -e "<cpt>[db]"
# 跑 CPT 全量测试
cd <cpt> && /tmp/ec-compat-venv/bin/python -m pytest tests -q
```

**通过标准**：CPT 全量测试**全绿**，且**零新增 skip**。
**失败处置**：若红 ⇒ 判定「上游不可共享环境」，本仓改为**自带独立 venv**（本仓是独立项目，
本来就不该和上游共用环境 —— 这也印证「独立不纠缠」的取向）。

> ⚠️ 注意：上游 CPT 的 CI 里有**已知既存失败**（`test_dashboard_runs_index` /
> `test_dashboard_wiring_d`），**逐条对比失败名单，不要数条数**。

### P0-B · 契约提取可行性

**问题**：把 9 列定义、5 个常量、表归属清单从两个仓抽到本仓，能否做到**不引用上游任何代码**？

**做法**：手工誊写一份契约草稿（不 import），逐条核对两侧实际值。

**通过标准**：
- `intraday_seal_snapshot` 9 列：两侧列清单**逐字一致**（已实测一致）⇒ 契约可提取
- 5 个价格常量：两侧当前值**一致**（已实测一致）⇒ 契约可提取
- 表归属：52 张表能无歧义地划成「emotion 37 + CPT 14 + 反契约 1」（已实测）⇒ manifest 可建

**失败处置**：若发现某条契约两侧**已不一致**（即已经漂移），**不要在契约里选边** ——
记录为**待裁决项**上报 owner（这是业务决策，见 §6）。

### P0-C · 平台相关二进制

**问题**：`emotion_core_rust.so`（ELF aarch64，随仓分发，CI 不编译）在本仓语境下怎么处理？

**做法**：确认 `emotion_core/core/__init__.py` 的惰性加载 + 优雅降级（`available()`）确实让
「无 `.so` 环境」下测试仍绿。

**通过标准**：无 `.so` 环境下 emotion-core 全量测试全绿（CI 不引入 Rust 工具链）。
**本仓的处置**：本仓**不持有**那个 `.so`（它属于 emotion-core）。
本仓只在自己的聚合页里**通过 HTTP** 读 CPT 的结构位，不碰二进制。

---

## 3. P1 · 契约提取（2 天，不动上游）

### 3.1 产出物

```
src/emotion_cpt/contracts/
├── __init__.py            # 公共 API 汇总
├── tables.py              # TableManifest：52 张表 → 归属 / 写入方 / 读取方
├── intraday_seal.py       # 9 列的唯一 ColumnSpec 定义
├── pricing.py             # 5 个价格常量的唯一定义
└── shared_tables.py       # 7 张共享表 + 1 张反契约表的清单与新鲜度判据
```

### 3.2 关键设计

**列定义用「声明式」而不是「SQL 字符串」**，这样两侧都能校验：
```python
# intraday_seal.py
INTRADAY_SEAL_TABLE = "intraday_seal_snapshot"

@dataclass(frozen=True)
class Column:
    name: str
    dtype: str
    nullable: bool
    unit: str | None = None      # ← 单位陷阱必须写进来（bid1_lots 是「手」）
    semantics: str = ""           # ← 语义陷阱（distance_pct 是百分数不是小数）

INTRADAY_SEAL_COLUMNS: tuple[Column, ...] = (
    Column("at", "timestamptz", False, semantics="本轮采集时刻，UTC 存储 UTC 输出"),
    Column("code", "text", False, semantics="6 位纯代码，如 '600293'"),
    Column("sealed", "boolean", False, semantics="这一轮是否封在板上"),
    Column("bid1_lots", "double precision", True, unit="手（1 手 = 100 股）",
           semantics="买一挂单量；读方阈值用股时必须 ×100"),
    Column("limit_price", "double precision", True, semantics="本轮用的涨停价（Decimal 取整口径）"),
    Column("price", "double precision", True, semantics="本轮现价"),
    Column("prev_close", "double precision", True, semantics="昨收"),
    Column("distance_pct", "double precision", True, unit="百分数（非小数）",
           semantics="(limit-price)/limit*100；0.0=封在板上，负数=已超板"),
    Column("is_st", "boolean", True, semantics="ST 判定结果；NULL=没判。判据在 CPT"),
)
```
**为什么带 `unit` / `semantics`**：契约漂移里最贵的不是字段名，是**同名不同义**
（`bid1_lots` 是手不是股；`distance_pct` 是百分数不是小数）。把语义写进代码，
门禁才能查"读方是不是按错误的单位在用"。

**表归属 manifest**：
```python
@dataclass(frozen=True)
class TableSpec:
    name: str
    owner: str            # "emotion" | "cpt" | "shared"
    writer: str           # 谁写
    readers: tuple[str, ...]
    freshness: str | None = None   # 新鲜度判据（仅共享表有）

TABLES: tuple[TableSpec, ...] = ( ... 52 张 ... )
```

### 3.3 门禁与自证

```
scripts/
├── check_table_manifest.py    # manifest ↔ 真库 pg_tables 比对（多/少都红）
├── check_contracts.py         # 契约 ↔ 上游两侧实际代码值比对
└── check_crontab.py           # 仓内 ↔ 线上 crontab 双向比对（P4 再接线上）
```

**验收必须包含"注入假数据"**：
1. 故意改 `pricing.BUY_BUFFER` 的值 ⇒ `check_contracts.py` 必须红且指出差异
2. 往 manifest 里塞一张不存在的表 ⇒ `check_table_manifest.py` 必须红
3. 删掉一列定义 ⇒ 契约门禁必须红

> 这条来自上游 R45 的教训：**「自制的验证工具第一版基本都错」** ——
> 跑全绿还不够，**必须注入假数据确认它还能报**。

---

## 4. P2 · 门禁接入上游（1 天）

本仓的门禁要在**上游 CI 里**跑，才能真正守住边界。

**做法**：本仓提供一个只读探针（`emotion_cpt.cli.contracts_probe`），输出机器可读的契约指纹；
上游仓的 CI 加一个 job：拉取本仓的契约指纹，与自己代码里的实际值比对，不一致就红。

**为什么不是让上游 import 本仓**：见 §7 的依赖方向论证 —— 先用**校验**建立约束，
确认稳定后再（P5，可选）升级为**依赖**。

**验收**：
- 在上游 emotion-core 的 `levels.py` 里把 `BUY_BUFFER` 改成 1.03 ⇒ 上游 CI 红
- 改回 ⇒ 绿

---

## 5. P3 · 统一 web 入口（1 天）

### 5.1 现状（真机实测）

`/etc/nginx/sites-enabled/dsh-web` **已经是统一入口**：
`/cpt/`→8010 · `/emotion/`→8098 · `/dashboard/`→门户 8099 · `/dashboard/jc/`→8077 · `/bridge/`→8021。
门户 `DSH/portal/app.py:799-800` 里**「CPT 看板」「Emotion Core」按钮已存在**。

⇒ **本阶段不是"造入口"，是"把入口纳入治理 + 补上真正缺的那块"。**

### 5.2 本仓产出

```
src/emotion_cpt/web/
├── portal/          # 门户（自 DSH/portal 迁入，只读引用其渲染）
└── aggregate/       # ★ 新增：同票并排聚合页（只读）
```

**聚合页 `GET /aggregate/stock/{code}`**：
- 左栏：CPT 的结构（分型/笔/中枢/背驰）—— 来自 `http://127.0.0.1:8010/api/dashboard/a-share/snapshot`
- 右栏：emotion-core 的判据（情绪阶段、`buy_window`、策略信号）—— 来自 `:8098/api/...`
- 底部：**两套口径的差异对照表**（含"两边是否打架"的显式标注）

**硬约束**：
- **只读**：不写任何库、不调任何写端点
- **不 import 上游**：只走 HTTP（这正是"不纠缠"在展示层的体现）
- **降级**：任一侧不可达 ⇒ 该栏显示"不可用 + 原因"，另一侧照常渲染
  （沿用上游 `cpt_client` 的"绝不抛、降级出结果"原则）

### 5.3 为什么做聚合页

本仓不裁决"三套买点谁为准"（业务决策），但**有责任让差异可见**：
现在 CPT 看板与 emotion 看板各有一半内容来自对方，谁都不标注来源口径。
聚合页把两套并排放出来，是裁决之前的最低成本一步。

---

## 6. P4 · 部署真相源归一（1 天）

### 6.1 触碰点（真机实测）

| 类别 | 数量 |
|---|---|
| systemd unit 文件 | 20（5 CPT + 15 emotion） |
| 线上 `/etc/systemd/system` 里的写死路径 | **43 处** |
| 仓内硬编码仓路径 | **64 行** |
| cron 脚本 | 10（CPT 仓内） |
| 线上 crontab 作业 | **13 条**（仓内 9 + **仓外 4**） |
| unit 真相源副本 | **3 份**（portal + 两个项目仓） |

### 6.2 目标

```
本仓 deploy/systemd/      ← 唯一一份 unit 真相源
本仓 deploy/cron/crontab  ← 全部 13 条作业（含原来仓外的 4 条）
portal 仓                  ← 只保留拉取脚本，不再存 unit 副本
```

### 6.3 crontab 双向对账门禁

**仓内 → 线上**：仓里有、线上没有 ⇒ 红
**线上 → 仓内**：线上有、仓里没有 ⇒ 红（这条正是那 4 条仓外作业的 catcher）

**cron 的静默失败陷阱**（必须写进门禁的检查项）：
- 路径不存在 ⇒ cron 直接跳过，**不报错**
- 脚本丢了执行位 ⇒ `Permission denied`，**同样静默**
  （上游 R43 踩过：仓内 git 模式 `100644`，靠 `install -m 755` 复制才拿到执行位）
⇒ 门禁必须查：① 路径存在 ② `git ls-files -s` 显示 `100755` ③ 手动跑一次不报错

---

## 7. P5 · 契约采纳（可选，2 天）

**这一步是唯一会让上游产生代码依赖的阶段，可以不做。**

### 7.1 依赖方向论证

```
   cpt ─────────┐
                ├──▶ emotion_cpt.contracts
emotion_core ───┘

   emotion_cpt ──✗──▶ cpt / emotion_core      ← 禁止
```

单向依赖 = **被治理**，不是**被纠缠**。本仓永远不知道上游的实现细节；
上游只知道"契约长什么样"。这满足「独立项目、不和原来纠缠」。

### 7.2 采纳方式

上游在 `pyproject.toml` 里加：
```toml
dependencies = ["emotion-cpt>=0.1,<1"]
```
然后把原来手抄的常量改为从契约包 import：
```python
# 改造前（手抄，改一边不传播，无测试会红）
BUY_BUFFER: Final[float] = 1.02

# 改造后
from emotion_cpt.contracts.pricing import BUY_BUFFER
```

### 7.3 风险与前置条件

- ⚠️ **契约冻结**：一旦上游 import 契约包，契约就成了对外 API，
  改动要走版本号 + 弃用期。**这是采纳的真实成本**，必须 owner 认可。
- ⚠️ **发布链路**：本仓必须先有可安装的发布物（PyPI 或 Git URL 依赖）。
  在此之前 P2 的**校验式**约束是更现实的选择。

---

## 8. P6 · 收尾与治理（0.5 天）

- 本仓文档与上游文档的**交叉引用**建立（哪条契约在哪个上游实现里）
- 门禁全部接入 CI，且**门禁自证**记录在案
- 本仓自身的 `check_doc_drift.py`：文档里的表数/列数/契约声明与代码一致
- 剩余待裁决项归档（见 §9）

---

## 9. 风险登记

| # | 风险 | 影响 | 概率 | 缓解 |
|---|---|---|---|---|
| R1 | 契约被上游 import 后难以演进 | 高 | 中 | 契约冻结 + 版本号 + 弃用期；P5 设为可选 |
| R2 | 上游拒绝采纳契约（保持现状） | 中 | 中 | P2 的**校验式**约束不依赖采纳，仍能挡住漂移 |
| R3 | 聚合页被误当作"已裁决"的结论 | 高 | 中 | 页面顶部显式标注「并排展示，未裁决」 |
| R4 | 凭据泄漏进仓 | 极高 | 低 | `.gitignore` 禁 `.env`/`*.key`/`~/.dbconfig`；CI 加 secret 扫描 |
| R5 | 部署路径改错导致静默停摆 | 高 | 中 | P4 逐条验证 + 双向对账门禁 + 先切后删 |
| R6 | 本仓被当成"第三个实现"而重复造轮子 | 中 | 中 | README 明确「不实现业务逻辑」；契约层只放约定 |
| R7 | 真机连接受限速/超时（勘察期间实测多次） | 低 | 高 | 所有远程操作带重试；本仓 CI 不依赖真机 |

---

## 10. 待裁决项（**不是工程能单独决定的**）

以下问题由本仓**暴露**但**不裁决**，需要 owner 给口径：

1. **三套买点谁为准** —— CPT 的 `buy/sell/watch/hold`、emotion 的 `BUY/WATCH/PASS`、
   LLM 缠论策略的自然语言结论。聚合页会并排展示。
2. **Wind 逐日涨跌停对账的 40/33/22/5 只 only_self 分歧** —— 上游 watchdog 正为此亮红
   （4 条断档未 ack）。这是「本库判涨停 vs Wind 未列」，属数据源口径。
3. **缠论上游授权** —— 机器上存在第三套缠论实现 `chanlun-pro`（未被引用）
   与一个授权存疑的 `chanlun-pro-replica`（审计结论：反编译改名重发）。
4. **CPT 侧 5 张遗留表（21,961 行 R67 迁移丢弃数据）删不删。**

---

## 11. 里程碑

| 里程碑 | 达成时 | 标志 |
|---|---|---|
| **M1 契约就位** | P1 末 | 契约常量 + 三个门禁红绿自证通过 |
| **M2 上游受约束** | P2 末 | 上游 CI 里契约门禁生效，改一个值就红 |
| **M3 入口统一** | P3 末 | 门户 + 聚合页上线，同票并排可见 |
| **M4 部署单点化** | P4 末 | unit/crontab 单点真相源 + 双向对账 |
| **M5（可选）契约采纳** | P5 末 | 上游 import 契约包，漂移通道物理关闭 |
