# systemd unit 真相源

**本目录是 unit 的唯一真相源**（计划态）。

现状：线上 unit 的真相源在 `DSH/portal/deploy/systemd-units/`（`portal-sync-units.timer`
每日 04:00 拉取同步），而**两个上游项目仓里各存了一份副本** —— 实测逐字相同，
也就是说有**两份必须手动同步的重复**。本仓上线后，这个重复被消除。

搬迁时需改的写死路径：仓内 64 行 + 线上 43 处。
