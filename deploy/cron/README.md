# crontab 真相源在 Emotion-CPT 包内

**真相源**：`src/emotion_cpt/deploy/cron/crontab`（随契约包分发）。

本目录放**运行时脚本**（唯一一份，线上从这里跑）。
改 crontab 请改包内真相源，然后由 `scripts/install_crontab.sh` 装到线上。
