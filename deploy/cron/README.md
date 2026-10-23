# crontab 真相源

**本目录是 crontab 的唯一真相源**（计划态，见 `docs/IMPLEMENTATION.md` §6）。

搬迁时需把**线上全部 14 条**作业收进本目录 —— 包括目前**只活在线上、不在任何仓里**的 5 条：

```cron
*/5  * * * * curl -sf --max-time 8 -o /dev/null http://127.0.0.1:8098/ || sudo -n systemctl restart emotion-core-dash
*/10 * * * * bash /home/ubuntu/bin/jc-ingest-run.sh
0    1 * * 0 /home/ubuntu/bin/backup-db.sh
0    18 * * * /home/ubuntu/bin/jc-staging-retention.sh --apply
30   18 * * * /home/ubuntu/bin/jc-ops-retention.sh
```

其中第 1 条是 **emotion 看板进程存活的唯一保障** —— 丢了它，看板挂了没人拉起。

**执行位**：所有 `*.sh` 在 git 里必须是 `100755`。cron 不经过 shell，
没有执行位就是 `Permission denied`，而且**静默**。
