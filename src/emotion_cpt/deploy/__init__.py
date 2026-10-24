"""部署真相源（随包分发）。

**这个包是「部署配置」的唯一真源**：systemd unit 与 crontab 都在这里，
随 `emotion-cpt` 一起安装，于是**任何装了契约包的仓都能读到同一份**，
而不是各留一份副本各漂各的（历史上已经漂出过真实静默故障）。

- `systemd/` —— systemd unit 真相源
- `cron/crontab` —— crontab 真相源
- `cron_spec.py` —— 解析 crontab 的**唯一实现**（门禁与日报共用，不重复实现）
"""
