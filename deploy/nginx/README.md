# nginx 配置片段

统一入口的 location 片段由 `emotion_cpt.web.facade.nginx_location_snippets()` 生成。

**反向代理由 nginx 承担**（不在应用层重做）：nginx 已承担 TLS、`auth_basic`、
以及插件门卫依赖的 Host/Origin 改写 —— 在应用层重做一遍只会多出一套不一致的规则。
