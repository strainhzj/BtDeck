# 安全配置

BtDeck 可以在局域网内使用，也可以通过反向代理提供跨网络访问。公网部署前请先完成本页配置。

## 必须设置的生产变量

```dotenv
DEV=false
SECRET_KEY=替换为强随机值
ALLOWED_HOSTS=https://your-domain.example
DEBUG=false
```

后端会在 `DEV=false` 时拒绝缺少 `SECRET_KEY` 或 `ALLOWED_HOSTS` 的配置。`SECRET_KEY` 不应写入 Wiki、镜像标签、日志或 Git；可用 Python 的 `secrets` 模块生成随机值。

## TLS 与访问边界

默认 Compose 只把前端端口映射到宿主机。生产环境建议由 Nginx、Caddy 或其他反向代理终止 TLS，再转发到前端容器。参考 `deploy/nginx-tls.conf.example`，并限制管理端口仅对必要网络开放。

纯 HTTP 部署会暴露登录凭据和 token，不能作为公网方案。`ALLOWED_HOSTS` 应填写真实访问来源，避免用过宽的通配配置。

## 账号与二次验证

BtDeck 使用 JWT 会话和 TOTP 二次验证。首次登录后应立即修改初始化密码；修改密码后其他设备会被要求重新登录。请为不同环境使用不同密码，并保护 TOTP 种子和恢复流程。

## 数据和备份

SQLite 数据库、配置、下载器凭据、审计记录和备份文件都属于敏感数据。绑定目录应限制主机权限，并纳入定期备份。恢复前先停止写入服务、保留原始备份，再验证迁移版本和文件路径。

## 运行参数

- 后端保持单 worker，以维持 SQLite 锁、资源准入和调度器的进程内一致性。
- 默认时区为 UTC；定时任务按应用约定的 Asia/Shanghai 触发规则执行，日志和 API 时间仍按统一时间契约处理。
- 生产环境关闭 `DEBUG`，避免错误响应泄露堆栈。

