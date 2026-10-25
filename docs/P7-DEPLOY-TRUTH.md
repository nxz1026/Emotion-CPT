# P7 · 部署真相源归一

> 阶段 7 / 9。2026-10-24。
> 一句话：**线上跑的东西（systemd unit + crontab）此前散落在三个仓里各有一份副本，
> 现在只有一份，随契约包分发，谁装了 `emotion-cpt` 谁读到的就是同一份。**

---

## 1. 为什么要做

P2~P6 把**判据**统一到了 Emotion-CPT（唯一真源）。但**部署配置**没跟上：

| 资产 | 迁移前 | 问题 |
|------|--------|------|
| systemd unit | Emotion-CPT 无 / CPT 5 个 / emotion-core 15 个 | 三份副本，实测**逐字节一致**（还没漂），但**注定了会漂** |
| crontab | 只有线上 crontab + CPT 仓一份 | 线上那份**只活在机器上**，重建环境就消失 |
| `emotion-dash-watchdog.sh` | **只活在线上 crontab 里，任何仓都没有** | 重建环境 ⇒ 看板挂了没人知道 |
| 日报的 `JOBS` 清单 | CPT 仓手抄一份 | 与 crontab 各漂各的 |

历史上已经漂出过**真实故障**（2026-10-07 审计）：生产 `/etc/systemd/system/`
与仓内副本严重漂移，且 `emotion-core-dash.service` 等 4 个单元**只存在于生产**。

---

## 2. 目标结构

```
Emotion-CPT/
├── src/emotion_cpt/deploy/
│   ├── __init__.py
│   ├── systemd/          ← ★ unit 真相源（21 个，随包分发）
│   ├── cron/crontab      ← ★ crontab 真相源（16 条作业，随包分发）
│   └── cron_spec.py      ← ★ crontab 解析的**唯一实现**
└── deploy/cron/*.sh      ← 运行时脚本（唯一一份，在仓里）
```

**为什么 unit / crontab 放包内**：
emotion-core 有一条很有价值的架构测试钉住
「退出码不被吞 / OnCalendar 必须带显式时区 / drop-in 不得与本体矛盾 /
`-m` 目标真有入口 / timer 依赖指向真实单元」。
它需要读 unit 真相源。真相源只在仓根 ⇒ 别的仓读不到 ⇒ 放进包里 ⇒
**任何装了契约包的仓都能读到同一份** ⇒ 那条测试从「仓内自检」升级成**跨仓对账**。

**为什么运行时脚本还留在仓根**：脚本是仓库资产，线上从仓里跑；
真相源是**数据**，随包分发供跨仓对账。两者角色不同，各归其位。

---

## 3. 变更清单

### Emotion-CPT（本仓）

| 文件 | 变更 |
|------|------|
| `src/emotion_cpt/deploy/systemd/*` | 从 `deploy/systemd/` 搬进来（21 个 unit） |
| `src/emotion_cpt/deploy/cron/crontab` | 从 `deploy/cron/` 搬进来（16 条作业） |
| `src/emotion_cpt/deploy/cron_spec.py` | 新增：crontab 解析的**唯一实现** |
| `src/emotion_cpt/deploy/__init__.py` | 新增（否则 `emotion_cpt.deploy` 是命名空间包，`__file__` 为 None） |
| `pyproject.toml` | 加 `package-data`，unit 随包分发 |
| `cli/check_unit_paths.py` | 真相源路径改指包内 |
| `cli/check_crontab.py` | 真相源路径改指包内；**`_jobs()` 的 key 从「命令」改为「整行」** |
| `deploy/cron/emotion-dash-watchdog.sh` | 新增：看板存活看门狗（原先只活在线上） |
| `scripts/install_crontab.sh` | 新增：真相源 → 线上机器的确定性安装路径（带备份 + 校验） |
| `scripts/install_units.sh` | 新增：同上（unit） |

### CPT（上游）

| 文件 | 变更 |
|------|------|
| `deploy/systemd/*.service`（5 个） | **删除**，降级为 `README.md` 指路 |
| `deploy/cron/crontab` | **删除**，降级为 `README.md` 指路 |
| `scripts/cron_daily_report.py` | `JOBS` 清单**从手抄改为推导** |
| `tests/test_cron_daily_report.py` | 读真相源；新增「仓内 cron 作业必须写日志」判据 |
| `tests/test_systemd_unit_policy.py` | 读真相源（跨仓对账） |
| `tests/test_intraday_collectd.py` | 读真相源（跨仓对账） |
| `tests/test_dashboard_run_store_prune.py` | 读真相源 |
| `tests/test_signal_overview_wiring.py` | 读真相源 |
| `scripts/check_test_mutation.py` | `rel` 支持 `pkg:` 前缀（可变异别的仓里的真相源） |

### emotion-core（上游）

| 文件 | 变更 |
|------|------|
| `src/emotion_core/orchestration/systemd/*`（15 个） | **删除**，降级为 `README.md` 指路 |
| `tests/architecture/test_systemd_units.py` | 读真相源；仓相关判据只对本仓 unit 判；时区判据放宽为「显式即可」 |

---

## 4. 本轮抓到的真缺陷

这一轮不是"搬文件"，**搬的过程中抓到了 4 个真问题**。每一个都已修 + 有判据钉住。

### 4.1 ★ 门禁漏掉同命令的多条作业（假绿）

`_jobs()` 原先**按命令做 key**。因子沿用的两条作业
（`09:45` 与 `11:30`）**命令完全相同** ⇒ 字典把它们合并成一条
⇒ 仓内 16 条作业，门禁只看到 **15 条** ⇒
**增删其中任何一条，门禁都不会报警**。

⇒ 判据的 key 改成**整行**（调度 + 命令）。这正是「断言了但什么都没断言」那一类。

### 4.2 ★ 因子重算的日志重定向被弄丢 ⇒ 失败彻底静默

P5 改因子重算的调度时间（02:20 → 09:50）时，
把 `>> /home/ubuntu/logs/factor-recompute.log 2>&1` **一起弄丢了**。

后果：**因子重算失败没有任何地方能看到**（表继续陈旧、因子继续过期）。
而日报因为「扫的日志名对不上 crontab」报的是**配置漂移** ——
**真正的故障没人提**。

⇒ 修回重定向；并新增判据：**仓内 cron 作业必须有日志**
（crontab 级 `>>` **或**脚本内部自己写日志，两种形态都算）。

### 4.3 ★ 搬 `deploy/cron/` 时把运行时脚本也搬走 ⇒ 线上 watchdog 作业失效

真相源进包时，`deploy/cron/` 整个目录被搬进包 ⇒
线上那条 `*/5 * * * * .../Emotion-CPT/deploy/cron/emotion-dash-watchdog.sh`
**路径当场失效，每 5 分钟失败一次，且无人知晓**
（cron 的失败邮件没人看，日报也没扫它）。

⇒ 修法：运行时脚本**留在仓根** `deploy/cron/`，只有**真相源数据 + 解析器**进包。
⇒ 门禁本来就有「作业引用的脚本不存在」的判据（这次是我自己把它跑崩了才没报出来），
⇒ 注入验证：路径改坏 / 去掉执行位 ⇒ **两条都报红** ✅

### 4.4 ★ `JOBS` 手抄清单与 crontab 各漂各的

日报的 `JOBS`（要扫哪些日志）是手抄的。它与 crontab 漂移过一次，
而且**漂的方向恰好会掩盖真故障**（见 4.2）。

⇒ 改为从真相源**推导** ⇒ 漂移在**结构上**不可能再发生。

### 4.5 ★ 看门狗探的是全 app 最慢的路径 ⇒ 会误杀健康看板

`emotion-dash-watchdog.sh` 原来探 `http://127.0.0.1:8098/`，
而 `/` 是**服务端渲染整页看板 + 查库** ⇒ **实测 5.97 秒**。
看门狗的超时是 8 秒 ⇒ **只剩 2 秒余量** ⇒ 看板稍慢就被判成「挂了」
⇒ **每 5 分钟重启一次健康的看板** ⇒ 用户看到反复刷新和短暂 502。
**那比没有看门狗更糟。**

⇒ 改探**廉价路径**（404 路径，实测 **0.5ms**），且**任何 HTTP 响应都算活着**
（只有连不上 = 000 才算死）。这不是单纯图快：
liveness 要问的是「这个进程还能处理请求吗」——
廉价路径若也超时，说明**连请求分发都卡住了**（线程池耗尽 / 假死），
那正是要重启的故障；而整页渲染慢，可能只是数据多，**重启它也修不好**，
反而把好端端的进程换掉。

⇒ 实测：探活耗时 **5.97s → 0.021s**，健康时不重启、不写日志；
注入（死端口 + 假 service 名）确认走「探活失败 → 拉起」分支，且**不碰生产**。

⚠️ 治本方案是给 emotion-core 的 server 加一个真 `/health` 端点（现在探的是 404），
已记为后续项。

---

## 5. 判据的设计原则（本轮沿用并强化）

1. **判据要能自己证明会红**：每条新判据都做了**注入**验证
   （改坏脚本路径 / 去掉执行位 / 删一条作业 / 改坏一条 unit），确认报红才收工。
2. **不缩范围**：与仓无关的判据（时区、drop-in、timer 依赖）对**全部 21 个 unit** 判，
   只有需要仓内上下文的判据（「`-m` 目标有入口」「`Environment=PYTHONPATH`」）
   才限定在本仓 unit —— 且**不是跳过**，是**在 unit 自己的仓里判**（CPT 的测试读真相源）。
3. **判据本身也要能被证伪**：本轮发现
   「时区判据只认 `Asia/Shanghai`」是**过严**的
   （`OnCalendar=*-*-* 08:00:00 UTC` = 北京 16:00，A 股快照收盘后跑**完全正确**）
   ⇒ 判据改为「**有没有显式时区**」，不是「时区是不是某一个」。

---

## 6. 遗留与后续

| 项 | 状态 | 说明 |
|----|------|------|
| `watchlist-snapshot.sh` / `watch-period-check.sh` 的失败可见性 | **既有缺口** | 它们的日志没进日报（脚本内部写「还在跑，跳过」⇒ 日报会报「未执行」⇒ 狼来了，会把真问题埋掉）。**需要日报支持"按作业跳过 skip 检测"才能收。** |
| portal 仓 `deploy/systemd-units/`（24 个副本） | 待处置 | 其 `sync.sh` 是 **pull 方向 = 线上快照** ⇒ 应改成从 Emotion-CPT 拉，或明确标注「快照非真相源」 |
| 线上 crontab 的历史注释 | 已保留 | 真相源文件头保留原归属注释 |

---

## 7. 验证

```
CPT         FAILED=0  SKIPPED=49   （与基线一致）
emotion-core FAILED=19 SKIPPED=5    （与基线逐条一致）
Emotion-CPT 46 passed
门禁         check_crontab=0  check_unit_paths=0
注入验证     脚本路径改坏→红 / 去执行位→红 / 删作业→红 / 改 unit→红
```

---

## 8. 决策记录（2026-10-25 追加）

### 8.1 ★ `.wants` 符号链接**不备份**（owner 裁决）

**背景**：线上 `/etc/systemd/system/*.wants/` 里是**符号链接**
（`multi-user.target.wants/foo.service` → `foo.service`），它们表示的是
**enable 状态**，**不是单元定义**。

⇒ 备份口径：**单元定义**进镜像；**enable 状态**由 `enablement-state.txt`
（`sync.sh pull` 生成的快照）负责。**两件事分开，不互相冒充。**

⇒ 后果（都是想要的）：
- 镜像里**不会**有 `*.wants/` 符号链接（绝对路径的符号链接换个机器就是死的）
- 备份卡片的「镜像缺 N 个线上单元」**不再被符号链接刷屏**
  （2026-10-25 实测：修前 20 条，修后 **0 条**；真缺单元仍然会报）
- `portal.sync.sh` 的白名单加 `portal.`（**带点**）——
  原来只有 `portal-`（带横杠）⇒ `portal.service` 自己匹配不上
  ⇒ 它此前**连镜像里都没有** ⇒ **完全没有备份**（2026-10-25 已修）

### 8.2 10 个「无归属」单元纳入真相源（2026-10-25）

`dsh-*` / `league-*` / `portal*` 这 10 个此前既不在真相源、也没有 `# owner:` 声明
⇒ 门禁 `check_unit_paths` 的双向对账**看不见它们** ⇒ 「仓外的运维知识」。

⇒ 现已纳入（线上补 `# owner:` 首行 + 真相源 + `_MANAGED` 扩前缀）：

```
✅ systemd unit 一致（31 个：cpt 5、dsh 2、emotion-core 15、emotion-cpt 1、league 3、portal 5）
```

⇒ 教训：**把单元纳入真相源 = 门禁开始看它 ⇒ 此前藏着的坑会一次性冒出来**
（`portal-sync-units.timer` 的 `OnCalendar` 没写时区就是这么被挖出来的）
⇒ **改完必须跑全仓测试，不能只看自己那个仓绿。**

### 8.3 时序错开：strategy ↔ 因子重算（2026-10-25）

⚠️ **机器时区是 `Etc/UTC`，crontab 用 UTC；而 timer 的 `OnCalendar` 写 `Asia/Shanghai`**
⇒ 两者换算极易看错：

| 谁 | 声明 | 实际 UTC |
|---|---|---|
| `emotion-core-strategy.timer` | `Mon..Fri 17:50 Asia/Shanghai` | 09:50 |
| crontab `factor-recompute-daily.sh` | `50 9 * * *`（机器本地时区） | 09:50 |

⇒ **同一分钟起跑**。因子重算日常 46 秒（有账本跳过），但**首次全量 ~2 小时** ⇒ 撞上就重叠。
⇒ 已把 strategy 挪到 **18:15**（错开 25 分钟，落在 report 18:00 / watchdog 18:05 之后）。

### 8.4 对账「尺子」（2026-10-25）

`scripts/parity_czsc.py` + `tests/test_parity_czsc.py` + CI 一步
⇒ 用**固定种子的合成行情**（不连库）比自研与 czsc 参照侧的
**笔数差 / 中枢数差 / 力度口径差**。

⇒ **没有这把尺子，结构语义改动就是盲改**（改完只能靠「图看着对」判断）。
⇒ 门禁的判据是**差距不能无声变大**（预算写在脚本头部）
⇒ 差距**变小**时请**同时收紧预算**，否则「收敛」会被悄悄丢掉。

已知差距（2026-10-25 实测，合成行情 6 轮 × 400 根）：

| 门槛 | 笔数差 | 中枢数差 | 力度口径差 |
|---|---|---|---|
| 1 / 2 | **+0**（逐笔相等） | -2 | **0.0000** |
| 3 | -485（自研少一半） | -52 | 11.21 |
| 6（生产默认） | +36（自研多两成） | +19 | 9.59 |

⇒ 门槛 ≥3 的落差**不是噪声**：按端点时间配对后力度仍差 9~11
⇒ 连「同一笔」的两端都不同 ⇒ 真实的语义差（量纲 + 端点选取 + 不成笔策略）
⇒ **这也是「重要 9 条」里最需要尺子的一批。**
