# 迁移目录

**跨两个上游项目的统一迁移时间线**（计划，见 `docs/IMPLEMENTATION.md`）。

命名：`NNN_YYYY-MM-DD_slug.sql`，`NNN` 连续递增。
每次迁移必须在 `emotion_cpt.contracts.tables` 的 manifest 里登记归属与方向。

> 现状：迁移仍由各上游仓自己执行（`Chan_Pattern_Trader/scripts/migrations/`）。
> 本目录是**统一索引**，不接管执行 —— 执行权留在上游，避免本仓变成「第三个实现」。
