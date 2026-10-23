# 搬迁映射

> 上游哪个文件 → 本仓哪个模块。**逐字搬迁，不趁机重构。**

## CPT（`nxz1026/Chan_Pattern_Trader`）

| 上游 | 本仓 | 阶段 |
|---|---|---|
| `cpt/domain/fractal.py` `bi.py` `zhongshu.py` `contain.py` `recursion.py` `trend_type.py` `signal.py` `first_buy.py` `levels.py` `models.py` `config.py` `types.py` `containment_trace.py` `a_share_rules.py` `intraday_rules.py` `market_time.py` `structure_events.py` | `emotion_cpt/structure/{models,rules}.py` | P2 |
| `cpt/adapters/_dbconfig.py` | `emotion_cpt/db/config.py` | P1 |
| `cpt/application/a_share_snapshot.py`（**计算部分**） | `emotion_cpt/snapshot/pipeline.py` | P3 |
| `cpt/application/track_points.py`（常量部分） | `emotion_cpt/contracts/pricing.py` | P1 |
| `cpt/storage/intraday_seal_store.py`（列定义部分） | `emotion_cpt/contracts/intraday_seal.py` | P1 |
| `cpt/scripts/migrations/*.sql` | `emotion_cpt/schema/migrations/`（索引） | P1 |

**留在 CPT 不搬**：`adapters/`（行情源）、`backtest/`、`llm/`、`storage/` 的表写入、
`web/` 的前端与端点（**逐步变薄**，不是一次性搬）。

## emotion-core（`nxz1026/emotion-core`）

| 上游 | 本仓 | 阶段 |
|---|---|---|
| `src/emotion_core/utils/db.py`（连接层） | `emotion_cpt/db/connection.py` | P1 |
| `src/emotion_core/data/schema.py`（DDL 字典） | `emotion_cpt/contracts/tables.py`（manifest）+ 迁移目录 | P1 |
| `src/emotion_core/presentation/`（门户部分） | `emotion_cpt/web/portal/` | P4 |
| `src/emotion_core/algorithms/levels.py`（手抄常量部分） | `emotion_cpt/contracts/pricing.py` | P1 |
| `src/emotion_core/data/providers/cpt_intraday.py`（列清单部分） | `emotion_cpt/contracts/intraday_seal.py` | P1 |

**留在 emotion-core 不搬**：`algorithms/`（情绪判据）、`services/`、`orchestration/`、
`lab/`、`llm/`（策略）。

## DSH/portal

| 上游 | 本仓 | 阶段 |
|---|---|---|
| `DSH/portal/app.py`（门户渲染） | `emotion_cpt/web/portal/` | P4 |
| `DSH/portal/deploy/systemd-units/`（unit 副本） | `emotion_cpt/deploy/systemd/`（**唯一真相源**） | P7 |

## 兼容策略

搬迁后**上游的旧模块变成 re-export**，而不是立刻删除：

```python
# CPT cpt/domain/levels.py（搬迁后）
from emotion_cpt.contracts.pricing import BUY_BUFFER, SELL_BUFFER, STOP_LOSS_RATIO
```

⇒ **上游零改动即可运行**，采纳是渐进的；任何一步都能单独回滚。
