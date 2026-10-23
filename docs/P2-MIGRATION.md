# P2 · 结构计算内核搬迁 —— 完成记录

> 执行：2026-10-23 14:00–14:45（Oracle 真机）
> CPT 侧 commit：`94d8aa58b`（搬迁）+ `0421c4813`（依赖声明）+ `882bb24ff`（合并）+ `c0a841ffd`（契约改写）
> Emotion-CPT 侧 commit：`cc02f97`（判据本体）· tag `v0.1.0`

---

## 1. 搬了什么

| | |
|---|---|
| 从 | CPT `cpt/domain/` —— 17 个模块、3,581 行、**零三方依赖** |
| 到 | Emotion-CPT `emotion_cpt/structure/` —— 同样 17 个模块 |
| CPT 侧现在 | `cpt/domain/__init__.py`（**模块别名转发层**）+ `README.md` |
| 依赖方向 | **单向**：`cpt → emotion_cpt` |

---

## 2. ★ 为什么用「模块别名」而不是「re-export 壳」

我**先做的是壳**（`from emotion_cpt.structure.X import (a, b, c)`），实测出三个缺陷后推翻重做：

| # | 缺陷 | 实测症状 |
|---|---|---|
| 1 | **monkeypatch 打在壳上，真源不受影响** | `test_seconds_to_close_defaults_to_market_now` 假失败（`assert 0 == 60`） |
| 2 | **属性访问式引用扫不出来** | `ir.SHARES_PER_LOT` → `AttributeError`（我的全仓扫描只认 `from X import Y`，不认 `模块.属性`） |
| 3 | **壳与真源是两个模块对象** | 模块级状态会分叉 |

⇒ 改成别名后：`cpt.domain.market_time is emotion_cpt.structure.market_time` → **True**，
三个缺陷全部消失，CPT 现有 117 个引用点**一行都不用改**。

> 教训：迁移方案本身也要被验证，不能"看起来对"就上。

---

## 3. 验证（四道门，全过）

| 门 | 判据 | 结果 |
|---|---|---|
| ① **逐字节比对** | 17 个模块 vs git 原文（还原 import 改写 + 去迁移注释后 diff） | ✅ **全部为空** |
| ② **parity** | 同批 **1250 根真实 K 线 × 5 只票**，门槛 `None` 与 `6` 两档，6 类输出逐字段比 | ✅ **完全一致** |
| ③ **CPT 全量测试** | 隔离 HOME（够不到生产库） | ✅ **FAILED=0 / SKIPPED=49**，与搬迁前基线逐条一致 |
| ④ **生产重启前后对比** | 11 个端点结构 diff（排除时间戳/轮询计数/实时行情） | ✅ 9 个完全一致；2 个差异分别是「计时器年龄」与「实时 BTC 行情」 |

**② 的具体数字**（门槛 `None`）：600519 → 43 分型 / 27 笔 / 5 中枢 / 2 走势；
门槛 `6` 时 → 43 / 17 / 3 / 1（门槛合并端点，笔数下降符合语义）。

**④ 用的端点**：`health` `snapshot` `engine-state` `a-share/snapshot` `a-share/recommendation`
`levels` `signal-overview` `intraday-status` `parity` `structure-events` `signal-stats`。

---

## 4. 搬迁过程中踩的坑（都记在这，避免再犯）

| # | 坑 | 症状 | 根因 | 修法 |
|---|---|---|---|---|
| 1 | `__all__` 漏名 | 壳缺 `_is_more_extreme` / `_make_bi` / `transition_first_sell` / `_event_type_for` ⇒ **生产 ImportError** | 全仓扫描只认 `from X import Y` | 壳导出集 = `__all__` ∪ 全仓实际引用名（后来直接改别名，绕开整个问题） |
| 2 | `from __future__` 位置 | `SyntaxError: from __future__ imports must occur at the beginning of the file` | 迁移说明**前置**成独立 docstring，原 docstring 变第二条语句 | 迁移说明改插成**注释**（PEP 236 允许 docstring/注释/空行在 `__future__` 之前） |
| 3 | 引号被弄丢 | `invalid character '（'` | 并入 docstring 时开引号/闭引号处理错 | 同上，改注释方案；**教训：并入 docstring 要处理开/闭引号、前缀、内部转义** |
| 4 | 脚本自身语法错 | `unmatched ')'` | 嵌套 heredoc 转义 | 整个文件干净重写，不打补丁 |
| 5 | 编译错误被吞 | 明明有 SyntaxError 却打印「全部通过编译」 | `cmd \| head && echo` 的退出码是 `head` 的 | 改用 `if cmd; then` 判退出码 |
| 6 | 端口挑错 | 影子实例 `Address already in use` | **8099 是门户的端口**（nginx `/dashboard/` 反代到它） | 改用 `ss` 找空闲端口；env 文件本身也警告过 8000 被占 |
| 7 | 影子被连带杀 | 影子中途死 | 工具调用超时连带杀掉后台进程 | 改用「重启前后对比」，不需要影子 |
| 8 | `HOME` 污染 | `Author identity unknown` + push 要密码 | 我为测试隔离 `export HOME=/tmp/iso-home`，**泄漏到了后面的 git 命令** | 用环境前缀 `HOME=... cmd` 代替 export |

---

## 5. 顺带修正的两件事

### 5.1 一个测试契约被改写（**更严，不是放宽**）

`test_core_dependencies_stay_empty` 原断言 `dependencies == []`。
判据迁出后核心依赖不再为空，但**约束的意图不变**：「核心不引入任何三方库」。
新规则精确表述为：

- 允许且**仅**允许 `emotion-cpt`（自家判据内核 —— 原先就是仓内的 `cpt/domain`）；
- **不得**出现任何第三方库；
- `emotion-cpt` 必须钉到 **tag**（`main` 是移动目标，重建环境会拿到不确定的判据版本）。

### 5.2 4 个「读源码文本做断言」的测试改为**跟随已安装包定位**

原来硬编码 `ROOT / "cpt" / "domain" / "xxx.py"`。判据搬家后这些路径失效。
现改为 `Path(module.__file__)` —— **不硬编码任何路径**，以后再搬家也不会静默失效
（读不到文件 → 断言空过，是最隐蔽的失败模式）。

---

## 6. 依赖与 CI

CPT `pyproject.toml`：

```toml
dependencies = [
    "emotion-cpt @ git+https://github.com/nxz1026/Emotion-CPT.git@v0.1.0",
]
```

**CI 等价验证**：全新 venv 里 `pip install -e ".[db]"` ⇒ 自动装上 `emotion-cpt 0.1.0`，
且 `cpt.domain.models.Fractal` 正确解析到 `emotion_cpt.structure.models`。

`import-linter`：**6 条契约 kept，0 broken**（判据层现在连本仓任何包都不依赖，
只依赖 `emotion_cpt` 这一个纯标准库的判据内核 —— 语义上比搬迁前**更严**）。

---

## 7. ⚠️ 顺带发现的一个生产数据问题（与本次搬迁无关）

生产日志里出现：

```
600519 2026-04-26~2026-10-23：尾部 2026-10-23 缺复权因子，整段退到不复权（上次有因子 2026-10-22）
```

⇒ **茅台 2026-10-23 的复权因子没入库** ⇒ 该票尾部的结构计算退化为不复权。
这会让 `price_ratio`（adj→raw）判不出，结构位退到百分比兜底。
**属上游因子采集链路的问题，建议单独查（与合并无关，但会污染结构位）。**
