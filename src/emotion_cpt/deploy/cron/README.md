# crontab 真相源

`crontab` 是**唯一**的 crontab 真相源（随契约包分发）。
运行时脚本在**仓根** `deploy/cron/`，不在这里。
解析实现：`cron_spec.py`（门禁与日报共用，不重复实现）。
