# P3 · 结构位算式统一（共享内核的第二块）

> 执行：2026-10-23 21:00–21:40（Oracle 真机）
> Emotion-CPT commit：见下方 · CPT commit：见下方 · emotion-core commit：见下方

---

## 1. 搬的是什么

**「结构位 → 买卖参考位」** 的算式。此前**两边各写一份**：

| | CPT `cpt/application/track_points.py` | emotion-core `algorithms/levels.py` |
|---|---|---|
| 公式 | 中枢下沿/向下笔低点取 min、÷ratio×1.02；上沿取 max、÷ratio×0.97 | **同一份** |
| 取整 | 2 位 | **3 位** |
| 载荷 | dict（reference/confirmed/stop_loss_reference + condition/rationale） | `Levels` dataclass + 百分比兜底 |
| 兜底 | 无兜底（不可用就空） | 百分比兜底（−3%/−8%/+5%） |

⇒ **同一只票、同一时刻，两个系统印出的买/卖点价可能不同。**
实测：7 只票 × 4 个 ratio = 36 个价里 **29 个不一致**，最大差 0.005 元。

统一后：`emotion_cpt.snapshot.points` 是**唯一实现**；
两侧各自的**载荷、文案、兜底策略保持原样**（那属于消费方，不是判据）。

---

## 2. 取整位数：统一到 2 位

`emotion_cpt.contracts.pricing.PRICE_ROUND_DIGITS = 2`。

理由：**A 股价格最小变动单位是 0.01 元**，3 位小数（0.001 元）是**伪精度** —— 盘口没有这个刻度。
CPT 侧原本就是 2 位 ⇒ **CPT 侧一字不变**；emotion 侧的展示价最多变 0.005 元。

⚠️ 共享实现是**对真值取一次** 2 位，而旧 emotion 侧是「先取 3 位、再显示」。
两者在边界上差 0.01（如真值 94.8549999…：旧显示 94.855，新显示 94.85）——
**单次取整才是对的**（双重取整会放大误差）。

---

## 3. 验证

| 门 | 判据 | 结果 |
|---|---|---|
| ① CPT 侧无回归 | 7 票 × 4 ratio 的 28 组，before/after 逐字段比 | ✅ **一字不变（0 差异）** |
| ② emotion 侧取整正确 | 36 个价全部 == `round(真值, 2)` | ✅ **36/36 符合** |
| ③ 共享实现 == CPT 侧 | after 里 shared vs cpt 逐字段比 | ✅ **0 不一致** |
| ④ CPT 全量测试 | 隔离 HOME（够不到生产库） | ✅ FAILED=0 / SKIPPED=49，与基线一致 |
| ⑤ emotion-core 全量测试 | `git stash` 取基线逐条比 | ✅ 基线 19 / 改后 19，**失败名单逐条一致** |
| ⑥ 生产重启前后 | 5 个端点结构 diff（排除时间戳/文案） | ✅ **全部完全一致** |

生产侧：两个服务重启后各 1 秒就绪，`/api/cpt/points` 的 `buy_reference=1273.06` /
`sell_reference=1269.61`（2 位），与黄金参考里 CPT 的值**一致**。

---

## 4. 改了一处上游断言（不是放宽，是口径变更的同步）

`emotion-core/tests/unit/test_presentation_holding.py` 里写死了 3 位小数的 `14.901`。
口径收敛后应为 `14.9` ⇒ 断言改为 `round(14.901, PRICE_ROUND_DIGITS)`，
**直接引用契约常量** ⇒ 以后再改位数不用再动测试。

---

## 5. 依赖

emotion-core 的 `pyproject.toml` 也声明了 `emotion-cpt @ git+…@v0.1.0`
（单向依赖：**emotion_core → emotion_cpt**）。
生产 venv 已 `pip install -e`，systemd 仍用 `PYTHONPATH=src`（未改部署模型）。

---

## 6. 顺带发现（与本次无关，但更要紧）

**CPT 看板的 A 股结构位现在全是百分比兜底** —— 因为 `price_ratio` 取不到。
根因有两条，都不是本次搬迁造成的：

1. **因子表断更**：因子重算日志（10-23 04:18Z）显示
   `已覆盖 5211 只 / 失败 5227 只`、`覆盖日期 2026-10-22 → 2026-10-22`
   ⇒ 今日因子没落库，`price_ratio = adj ÷ raw` 判不出。
2. **连接被掐后不重连**：10-22 那轮的第一条错误是
   `AdminShutdown: terminating connection due to administrator command`，
   之后全部变成 `OperationalError: the connection is closed`。
   脚本握着**一条连接跑 2 小时**且**从不重连** ⇒ RDS 一重启/故障转移，
   **后半程全部静默失败，而它 `rc=0` 还报成功**。

⇒ 建议单独开一条线修（重连 + 失败计数进退出码 + 因子时序）。
