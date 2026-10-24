# 交叉引用 —— 契约 ↔ 上游实现的对应关系

> **本文件是生成的**，别手改。
> 重算：`python scripts/gen_cross_references.py`（CI 用 `--check` 只校验）
>
> 路径在生成时**逐个校验存在性** ⇒ 上游挪了文件 ⇒ **生成失败**，
> 而不是产出一份指向空气的文档。


## 1. 表归属（47 张）

| 归属 | 张数 | 写入方 | 被谁读 |
|---|---|---|---|
| **cpt** | 10 | cpt | emotion-core 10 |
| **emotion-core** | 37 | emotion-core | cpt 7、emotion-core 30 |

### 逐表明细

| 表 | 归属 | 写入方 | 读取方 | 遗留 |
|---|---|---|---|---|
| `cpt_dashboard_run` | cpt | cpt | emotion-core | — |
| `cpt_factor_epoch` | cpt | cpt | emotion-core | — |
| `cpt_llm_call` | cpt | cpt | emotion-core | — |
| `cpt_recommendation` | cpt | cpt | emotion-core | — |
| `cpt_run_metric` | cpt | cpt | emotion-core | — |
| `cpt_signal_event` | cpt | cpt | emotion-core | — |
| `cpt_structure_event` | cpt | cpt | emotion-core | — |
| `cpt_track` | cpt | cpt | emotion-core | — |
| `cpt_track_snapshot` | cpt | cpt | emotion-core | — |
| `intraday_seal_snapshot` | cpt | cpt | emotion-core | — |
| `alert` | emotion-core | emotion-core | emotion-core | — |
| `daily_bar` | emotion-core | emotion-core | cpt | — |
| `data_revision` | emotion-core | emotion-core | emotion-core | — |
| `derived_bar` | emotion-core | emotion-core | cpt | — |
| `eval_result` | emotion-core | emotion-core | emotion-core | — |
| `holding_decision` | emotion-core | emotion-core | emotion-core | — |
| `hot_rank` | emotion-core | emotion-core | cpt | — |
| `ingest_progress` | emotion-core | emotion-core | emotion-core | — |
| `ladder_day` | emotion-core | emotion-core | cpt | — |
| `limit_pool_em` | emotion-core | emotion-core | cpt | — |
| `llm_call_log` | emotion-core | emotion-core | emotion-core | — |
| `market_stat` | emotion-core | emotion-core | emotion-core | — |
| `ops_quota_ledger` | emotion-core | emotion-core | emotion-core | — |
| `ops_raw_manifest` | emotion-core | emotion-core | emotion-core | — |
| `pipeline_state` | emotion-core | emotion-core | emotion-core | — |
| `position` | emotion-core | emotion-core | emotion-core | — |
| `promotion_day` | emotion-core | emotion-core | emotion-core | — |
| `ref_dividend` | emotion-core | emotion-core | emotion-core | — |
| `ref_limit_rule` | emotion-core | emotion-core | emotion-core | — |
| `ref_limit_state` | emotion-core | emotion-core | emotion-core | — |
| `ref_limit_state_run` | emotion-core | emotion-core | emotion-core | — |
| `ref_rs` | emotion-core | emotion-core | emotion-core | — |
| `ref_security_status` | emotion-core | emotion-core | emotion-core | — |
| `ref_security_status_event` | emotion-core | emotion-core | emotion-core | — |
| `ref_security_status_window` | emotion-core | emotion-core | emotion-core | — |
| `review_report` | emotion-core | emotion-core | emotion-core | — |
| `signal` | emotion-core | emotion-core | emotion-core | — |
| `signal_outcome` | emotion-core | emotion-core | emotion-core | — |
| `stock_basic` | emotion-core | emotion-core | emotion-core | — |
| `strategy_signal` | emotion-core | emotion-core | cpt | — |
| `theme_group` | emotion-core | emotion-core | emotion-core | — |
| `theme_spot` | emotion-core | emotion-core | emotion-core | — |
| `theme_tag` | emotion-core | emotion-core | emotion-core | — |
| `trade_calendar` | emotion-core | emotion-core | cpt | — |
| `trade_event` | emotion-core | emotion-core | emotion-core | — |
| `trigger_log` | emotion-core | emotion-core | emotion-core | — |
| `watchlist` | emotion-core | emotion-core | emotion-core | — |

## 2. 共享表与反契约表

| 表 | 方向 | 写入方 | 新鲜度日期列 | 数据来源 |
|---|---|---|---|---|
| `daily_bar` | 共享 | emotion-core | `date` | 东财 push2delay 全市场快照；502 回退新浪；pytdx 回填 |
| `derived_bar` | 共享 | emotion-core | `date` | 无外部源，纯 SQL 派生自 daily_bar |
| `hot_rank` | 共享 | emotion-core | `date` | 东财人气榜 top100 |
| `ladder_day` | 共享 | emotion-core | `date` | 无外部源，派生自 derived_bar / limit_pool_em |
| `limit_pool_em` | 共享 | emotion-core | `date` | akshare 涨停/炸板/跌停池 |
| `strategy_signal` | 共享 | emotion-core | `trade_date` | LLM 策略观察（15 个 YAML 策略） |
| `trade_calendar` | 共享 | emotion-core | `date` | akshare 新浪交易日历，刻意独立于库内行情数据 |
| `intraday_seal_snapshot` | **反契约** | cpt | `at` | CPT 盘中采集守护写入的每轮封板结论（只存结论，不存原始五档） |

## 3. 契约项 → 上游实现位置

| 契约项 | CPT 侧 | emotion-core 侧 | Emotion-CPT（唯一定义处） |
|---|---|---|---|
| **价格常量**（6 个） | `cpt/application/track_points.py`（`from emotion_cpt.contracts.pricing import ...`） | `src/emotion_core/algorithms/levels.py`（同上） | ``src/emotion_cpt/contracts/pricing.py`` |
| **9 列封板快照** | `cpt/storage/intraday_seal_store.py`（写入侧） | `src/emotion_core/data/providers/cpt_intraday.py`（读取侧） | ``src/emotion_cpt/contracts/intraday_seal.py`` |
| **取整位数** `PRICE_ROUND_DIGITS` | `cpt/application/track_points.py`（经 `emotion_cpt.snapshot.points`） | `src/emotion_core/algorithms/levels.py`（同上） | ``src/emotion_cpt/contracts/pricing.py`` |
| **结构位算式**（P3 统一） | `cpt/application/track_points.py`（`from emotion_cpt.snapshot.points import ...`） | `src/emotion_core/algorithms/levels.py`（同上） | ``src/emotion_cpt/snapshot/points.py`` |
| **A 股价制 / 涨跌停价口径**（P6） | `cpt/domain/__init__.py`（**别名层**：`cpt.domain.price is emotion_cpt.structure.price`） | `src/emotion_core/utils/price.py` + `src/emotion_core/algorithms/intraday.py`（转发层） | ``src/emotion_cpt/structure/price.py`（整数分算法；**Decimal 对照实现同在此文件**，逐分穷举一致）` |
| **结构计算内核**（P2 搬迁） | `cpt/domain/__init__.py`（**模块别名转发层**：`cpt.domain.X is emotion_cpt.structure.X`） | —（情绪判据留在 emotion-core，不搬） | ``src/emotion_cpt/structure/`（17 模块）` |
| **数据层**（`~/.dbconfig` 解析 / psycopg 参数） | `cpt/adapters/_dbconfig.py`（旧副本） | `src/emotion_core/utils/db.py`（旧副本） | ``src/emotion_cpt/db/config.py` + `connection.py`` |
| **表 manifest**（47 张） | — | `src/emotion_core/data/schema.py`（DDL 侧） | ``src/emotion_cpt/contracts/tables.py`` |
| **unit 真相源**（21 个） | — | — | ``src/emotion_cpt/deploy/systemd/`（随包分发）` |
| **crontab 真相源**（16 条作业） | — | — | ``src/emotion_cpt/deploy/cron/crontab`（随包分发）` |

## 4. 依赖方向（单向，不得成环）

```
CPT ────────┐
            ├──▶ emotion_cpt（契约 / 数据层 / 结构内核 / 部署真相源）
emotion-core┘
```

`emotion_cpt` **不 import 任何一方** ⇒ 不可能成环。
门禁：`emotion_cpt.cli.check_contracts` 的「依赖方向」判据。
