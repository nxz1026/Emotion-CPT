# nginx 配置片段

统一入口的 location 片段由 `emotion_cpt.web.facade.nginx_location_snippet()` 生成。

**公网路径 = `/ecpt/`**（与 `/emotion/`、`/cpt/` 对称，三个项目各一个入口）；
`/dsh/` 作为**兼容别名**保留（旧链接不失效），同样指向 8092。

装到线上用 `scripts/install_nginx_route.sh`（备份 → 替换 → `nginx -t` → reload）。
⚠️ **备份绝不能放在 `sites-enabled/` 里** —— nginx 的 `include sites-enabled/*`
会把**所有文件**都加载 ⇒ 多个同 `server_name _` 的 server 块 ⇒ **互相冲突**
⇒ 改的那块可能压根没生效（2026-10-24 实测：刚加的 `/ecpt/` 返回 404，却 `nginx -t` 全绿）。

**反向代理由 nginx 承担**（不在应用层重做）：nginx 已承担 TLS、`auth_basic`、
以及插件门卫依赖的 Host/Origin 改写 —— 在应用层重做一遍只会多出一套不一致的规则。
