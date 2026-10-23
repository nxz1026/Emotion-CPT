# P0 前置验证实验 · 结论

> 执行：2026-10-23 13:05–13:31（Oracle 真机）
> 脚本：`scripts/p0a_venv_compat.sh`（v1，带安全闸）· `scripts/p0c_noso_compat.sh`（v1）·
> `scripts/p0_v2.sh`（v2，修假绿）· `scripts/p0a_v3.sh`（v3，补 extras）

---

## 0. 结论

| 实验 | 问题 | 结论 |
|---|---|---|
| **P0-A** | emotion 的依赖装进同一环境后，CPT 的全量测试还绿吗？ | ✅ **通过** —— 失败名单一致（0 = 0）**且 skip 数一致（49 = 49）** ⇒ 单 venv 成立 |
| **P0-B** | 契约能否不引用上游代码就提取出来？ | ✅ **通过** —— 9 列两侧逐字一致、5 常量当前一致、52 张表可无歧义划分 |
| **P0-C** | 没有平台相关二进制（`emotion_core_rust.so`，ELF aarch64）时测试还绿吗？ | ✅ **通过** —— 有/无 `.so` 失败名单完全一致 ⇒ **CI 不需要 Rust 工具链** |

---

## 1. P0-A · 单 venv 兼容性

**方法**：在 `/tmp` 建一个 venv，装 **emotion 的 `requirements.txt` + CPT 的 `requirements-dev.txt` + CPT 的全部 extras**（`.[db,crypto,chan]`），
用**隔离 HOME**（无 `~/.dbconfig` ⇒ 物理上够不到生产库）跑 CPT 全量测试，与 CPT 自己的生产 venv **逐条对比失败名单 + skip 数**。

**结果**：

```
基线(生产 venv)   失败 0 条   skip 49 条
合并 venv          失败 0 条   skip 49 条
[仅合并失败]  (空)
[仅基线失败]  (空)
✅ 失败名单一致 且 skip 数一致 ⇒ 单 venv 与现有 venv 等价
```

**依赖并集核对**（合并 venv 实际装到的东西）：

| 包 | 基线 venv | 合并 venv |
|---|---|---|
| pandas | 3.0.6 | 3.0.6 ✅ |
| psycopg | 3.3.6 | 3.3.6 ✅ |
| requests | 2.34.2 | 2.34.2 ✅ |
| ccxt | 4.5.85 | **4.5.90** ⚠️ |
| czsc | 1.0.1 | 1.0.1 ✅ |
| akshare | — | 1.18.97 |
| httpx | — | 0.28.1 |
| Jinja2 | — | 3.1.6 |

⚠️ **ccxt 版本不一致**：CPT 的 `crypto` extra 写的是范围 `ccxt>=4.0,<5`（**不是钉版**），
所以新装的环境拿到 4.5.90，而生产是 4.5.85。
⇒ **重建环境会得到不同的 ccxt**，而 CPT 的加密行情路径（binance_futures）依赖它。
**这是可重现性隐患，与合仓无关，但被这次实验暴露了。**
（生产真正钉死的是 `requirements.txt`；extra 只是范围。）

---

## 2. P0-B · 契约提取可行性

**已由契约门禁 `check_contracts.py` 在真机上实证**（不是纸面推演）：

| 契约 | 结果 |
|---|---|
| `intraday_seal_snapshot` 9 列 | CPT `_INSERT_SQL` vs emotion `_COLUMNS` **逐字一致** ✅ |
| 5 个价格常量 | 两侧当前值**一致**（1.02 / 0.97 / 0.95 / 3 / 2）✅ |
| 52 张表归属 | emotion 37 + CPT 14 + 反契约 1 —— **无重无漏** ✅ |
| 依赖方向 | 本仓零上游 import（门禁自检通过）✅ |

---

## 3. P0-C · 平台相关二进制

**方法**：把 emotion-core 复制两份到 `/tmp`（**目录名保持 `emotion-core`**，否则路径断言会假失败），
一份删掉 `src/core_lib/emotion_core_rust.so`，用**同一个** venv、**同样的** `PYTHONPATH=src` 跑全量测试。

**结果**：

```
有 .so：3094 passed，失败 21 条
无 .so：2513 passed，失败 21 条
[仅无 .so 时失败]  (空)
[仅有 .so 时失败]  (空)
✅ 失败名单完全一致
```

**注意**：无 `.so` 时通过数从 3094 掉到 2513 —— 少掉的 581 个是**被 skip**（不是失败），
因为 `core/__init__.py` 是**惰性加载 + 优雅降级**（`available()` 返回 False）。
⇒ **`.so` 不是测试必需；CI 不需要引入 Rust 工具链。**
⇒ 但也意味着：**CI 跑不出 Rust 算法路径的覆盖**，那部分覆盖只在本机。

---

## 4. ⚠️ 本轮实验暴露的两个独立隐患（与合仓无关，但该修）

### 4.1 CPT 的测试套件**会写生产库**

v1 实验的安全闸（跑前/跑后快照所有表行数）拦下了这件事：

```
基线(CPT 自己的 venv + 自己的测试) 跑完：
  cpt_run_metric  56093 → 56097     ← +4 行
```

⇒ **任何人在生产机上跑一次 `pytest`，CPT 的测试就会往 `cpt_run_metric` 写 4 行。**
写库面很小（只有 `test_structure_event_recorder.py` 与 `test_run_metric_persist_gate.py`
用 opt-in 的 `monkeypatch_prod_write` 夹具），但**它没有任何提示**。

**建议**（属于上游仓的改动，不在本仓范围）：
- 要么给这两个用例加"真库写入开关"（默认关），要么
- 在 `deploy/cron/` 里加一条每日对账，把 `cpt_run_metric` 的异常增量报出来

### 4.2 `ccxt` 未钉版

见 §1 的表格。`crypto` extra 是范围约束，重建环境会漂版本。

---

## 5. 实验方法论的三次翻车（记录下来，因为它们会再犯）

| 版本 | 现象 | 根因 | 修正 |
|---|---|---|---|
| v1 P0-C | 报告「无 .so 新增 1 个失败」 | 副本目录名改成 `emotion-core-noso`，触发**路径断言**假失败 | 两份副本**同名** `emotion-core` |
| v1 P0-C | 报告「基线 0 失败」（**假绿**） | 基线那轮**忘了带 `PYTHONPATH=src`** ⇒ conftest ImportError ⇒ **一个用例都没收集** | 两轮都带 `PYTHONPATH=src`；**必须校验 collected 数** |
| v2 P0-A | 报告「两边都 0 失败 ⇒ 等价」（**假绿**） | 合并 venv **缺 czsc/ccxt** ⇒ 合并侧多 skip 22 条，失败数当然都是 0 | 补齐 extras；**必须同时比对 skip 数** |
| v3 | venv 路径写错（`/tmp/p0v3/venv` vs 实际 `/tmp/p0v2/venv`）⇒ 合并侧没跑 ⇒ skip=0 | 脚本路径硬编码 | 修路径；**"合并侧 0 条 skip" 本身就是可疑信号** |

⇒ **纪律（写进本仓的测试规范）**：
1. 比对时**不能只比失败数** —— 还要比 **skip 数**和 **collected 数**
2. **"全绿"必须附 collected/passed/skipped 三个数**，否则无法区分"真绿"与"没跑"
3. 任何"通过/失败都是 0"的异常结果，先怀疑**用例根本没跑**

> 与上游 R45 的教训同源：**自制的验证工具第一版基本都错**。
> 本轮四次翻车里有三次是**假绿**（比假红更危险）。
