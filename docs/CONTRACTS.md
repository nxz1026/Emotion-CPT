# 契约总览（人读版）

> **机器可读版本是代码**：`src/emotion_cpt/contracts/`。
> 本文只是它的说明；两者冲突时**以代码为准**。

<!-- contract-facts
tables: 52
columns: 9
constants: 6
shared_tables: 7
reverse_tables: 1
owner_emotion: 37
owner_cpt: 14
owner_reverse: 1
-->

> **上面那块 `contract-facts` 是契约数字的机器可读真源**，
> `emotion_cpt.cli.check_doc_drift` 逐项跟代码对账。
> 改代码改了数字 ⇒ **必须回来改这一块**，否则门禁会红。
>
> ⚠️ 别的文档里散落的数字**不自动对账** —— 同一个「5 个价格常量」，
> 在「迁移前的痛点」里是**历史陈述**（当时确实 5 个），
> 在「产出物清单」里是**当前声明**（现在是 6 个）。
> 正则分不清这两者 ⇒ 所以数字**只在这一处**，别处引用它。

## 1. 表归属（52 张 = 37 + 14 + 1）

| 归属 | 张数 | 说明 |
|---|---|---|
| emotion-core 自有 | **37** | 与 `emotion_core/data/schema.py` 的 DDL **一一对应，零漂移**（真机实测） |
| CPT 自有 `cpt_*` | **14** | 9 张在用 + **5 张迁移遗留的备份/隔离表**（21,961 行） |
| 反契约表 | **1** | `intraday_seal_snapshot`（CPT 写 → emotion 读） |

## 2. 跨仓数据流

```
emotion-core ──写──▶ 7 张共享表 ──▶ CPT 读
CPT ──写──────────▶ intraday_seal_snapshot ──▶ emotion-core 读
```

| 方向 | 表 | 写入方 | 新鲜度判据 |
|---|---|---|---|
| → | `daily_bar` `derived_bar` `hot_rank` `ladder_day` `limit_pool_em` `strategy_signal` `trade_calendar` | emotion-core | 收盘（北京时间 15:00）已过的最近一个交易日 |
| ← | `intraday_seal_snapshot` | CPT | 盘中每 2 分钟一轮（**日频判据不适用**） |

## 3. `intraday_seal_snapshot` 的 9 列（含单位陷阱）

| 列 | 类型 | 可空 | 单位 | 语义 |
|---|---|---|---|---|
| `at` | timestamptz | 否 | — | 本轮采集时刻（UTC 存、UTC 出） |
| `code` | text | 否 | — | 6 位纯代码 |
| `sealed` | boolean | 否 | — | 这一轮是否封在板上 |
| `bid1_lots` | double | 是 | **手**（1 手 = 100 股） | 买一挂单量；读方阈值用股时 **×100** |
| `limit_price` | double | 是 | — | 本轮用的涨停价（Decimal 取整口径） |
| `price` | double | 是 | — | 本轮现价 |
| `prev_close` | double | 是 | — | 昨收 |
| `distance_pct` | double | 是 | **百分数**（非小数） | (limit-price)/limit×100；0.0 = 封在板上，负数 = 已超板 |
| `is_st` | boolean | 是 | — | ST 判定结果；NULL = 没判。**判据归 CPT** |

⚠️ 「没行」= **判不了**，不是「没封板」。

## 4. 6 个契约常量（唯一定义处）

| 常量 | 值 | 迁移前的真源 |
|---|---|---|
| `BUY_BUFFER` | 1.02 | CPT `cpt/application/track_points.py:45` |
| `SELL_BUFFER` | 0.97 | 同上 `:48` |
| `STOP_LOSS_RATIO` | 0.95 | 同上 `:50` |
| `BI_LOOKBACK` | 3 | 同上 `:53` |
| `ZHONGSHU_LOOKBACK` | 2 | 同上 `:54` |
| `PRICE_ROUND_DIGITS` | 2 | **P3 新增**（A 股最小变动单位 0.01 元，3 位是伪精度） |

⇒ 这 5 个价格常量原先被 emotion-core **手抄**了一份，且手抄副本的**行号引用已全部差 1 行**。
统一后只有一份，任何一侧改动都会被门禁抓到。

⇒ 现在的**唯一定义处**是 `src/emotion_cpt/contracts/pricing.py`；
两个上游都改成 `from emotion_cpt.contracts.pricing import ...` ⇒
「手抄副本」这个漂移通道**物理关闭**了。

## 5. 判据归属（ADR 0003 §E2「判据只许一处」）

| 判据 | 归谁 | 备注 |
|---|---|---|
| 分型 / 笔 / 中枢 / 背驰 / 趋势 | **CPT → 本仓 `emotion_cpt.structure`** | 确定性计算，零三方依赖 |
| 封板判定（`sealed`） | CPT `domain/intraday_rules.py` | emotion 侧**不得**再拿 `limit_price`/`is_at_limit` 判一遍 |
| ST 判定 | CPT `is_st_name` | 结论存 `is_st` 布尔，读方不再解析股票名 |
| 情绪阶段 / `buy_window` | emotion-core `algorithms/` | 情绪周期判据，**不搬** |
| 涨跌停价（北交所 / ST） | 各侧自己的制度表 | ⚠️ 上游曾因 ST 判定顺序错算偏低涨停价 |

## 6. 跨仓 HTTP 契约（emotion-core → CPT）

`emotion_core/services/cpt_client.py` 调 CPT `127.0.0.1:8010` 的 8 个端点：
`/api/dashboard/a-share/snapshot` · `/api/dashboard/a-share/recommendation` ·
`/api/dashboard/track`（增/删/恢复）· `/api/dashboard/track/{code}/advice` ·
`/api/dashboard/track/{code}/speak`。

⚠️ 其中**含写操作**（track 增删恢复会写 `cpt_track`）。
历史事故：自交付起该组写路径一直是坏的（裸路径 `POST /api/dashboard/track` 线上返回 405，
因为 CPT 只认 `/add` `/remove` `/restore` 三条字面量），**"从未成功过"**。

## 7. 契约指纹

`python -m emotion_cpt.cli.probe --fingerprint-only` 输出版本化指纹。
上游 CI 用它做**校验式**约束（不改代码也能守住漂移）；
`check_contracts.py` 则是**自检式**约束（直接读两侧源码比对）。
