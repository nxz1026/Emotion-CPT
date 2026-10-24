# P6 · A 股价制与涨跌停价口径统一

> 执行：2026-10-24 21:00–22:30（Oracle 真机）
> Emotion-CPT tag `v0.3.0` · emotion-core 侧 commit 见仓内历史

## 1. 问题：两套涨停价实现并存

| | 位置 | 算法 | 覆盖面 |
|---|---|---|---|
| emotion-core | `utils/price.py` | 整数分 `(x*1000+pct+500)//1000` | 涨停+**跌停**+`is_limit_up/down` |
| CPT | `cpt/domain/intraday_rules.py`（已随判据内核搬进本仓） | `Decimal` + `ROUND_HALF_UP` | 只有涨停价 |

数值等价（跨仓对账用例穷举 3000 分位 × 11 代码，0 差异），
但**两套实现并存**正是 emotion-core 自己那条门禁（`test_price_unique_impl.py`）要防的事 ——
它防得住**仓内**，防不住**跨仓**。

## 2. 决策：统一到 Emotion-CPT，选整数分算法

理由三条：

1. **无浮点** —— 全程整数，没有 `0.1+0.2` 那类误差；
2. **与生产 SQL 整数式逐分同源** —— 生产 `derive.py` 的
   `up_c = (round(pre_close*100)::bigint * pct + 50) / 100`；
3. **覆盖面更广** —— 跌停价与 `is_limit_up/down` 只有这一份有。

**CPT 那份 Decimal 实现保留在本仓**（`structure/intraday_rules.py`）作为**对照实现**：
两套算法同仓、同契约、穷举验证逐分一致 —— 这比「只有一份实现」更安全
（上游的跨仓对账测试当初就是这么设计的）。

## 3. 改动

| 侧 | 改动 |
|---|---|
| Emotion-CPT | 新增 `structure/price.py`：整数分算法 + CPT 那份的名字感知板制判定（`board_of`/`board_pct_limit`/`is_st_name`/`SHARES_PER_LOT`） |
| emotion-core | `utils/price.py` → **转发层**（4 个调用点零改动）；`algorithms/intraday.py` 的 `board_pct_limit`/`is_st_name` → 转发；私有 `_PCT_LIMIT_*` 删除 |
| emotion-core 门禁 | 「只许定义在 utils/price.py」→ 升级为「**本仓内一个定义都不许有**」+ 断言转发层真的是转发；Python 侧前缀全集改从 Emotion-CPT 取 ⇒ **Rust 跨语言对等门禁不变** |

## 4. 验证

| 门 | 判据 | 结果 |
|---|---|---|
| ① 三方穷举等价 | 12 代码 × 6 名字 × 35 分位（含 .5 边界） | ✅ 整数分 vs emotion 逐分相同；vs CPT Decimal 逐分等价 |
| ② emotion-core 全量 | 与基线逐条比 | ✅ FAILED=19 / SKIPPED=5，**零新增零消失** |
| ③ 跨仓对账 + 架构 + 价口径 | — | ✅ **84 passed** |
| ④ 生产重启前后 | 5 个端点结构 diff | ✅ **逐字节一致** |

## 5. 顺带修的门禁自身缺陷

`test_price_unique_impl.py` 的前缀提取器只认 `ast.Constant` 的返回值，
遇到**命名常量**（`return _PCT_MILLI_BSE`）会抛 `AttributeError` 或抽出空字典
⇒ 后续「Rust 覆盖 Python 前缀」的对等断言会**空转通过**。

⇒ 修法：解析模块级命名常量，让提取器真的能提取。
**这条测试自己的 docstring 就写着：「断言了但什么都没断言的测试比没有测试更危险」。**

## 6. 剩下的

情绪周期判据（`state/ladder/entry/promotion/accelerate`，pandas + aarch64 `.so`）**留在 emotion-core**：
CPT 不需要它们，搬过去只是「换个仓放」，没有统一收益，还会把重依赖拖进零依赖内核。
⇒ 这是评估结论，不是待办。
