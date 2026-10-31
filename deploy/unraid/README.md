# unraid 实机部署（database-migration-ui W6 / v1.0.8）

> 基于 2026-10-31 用户现网 compose 修正。**镜像必须是 dev≥163deca 构建**（v1.0.8 未发版，
> 迁移控制面端点与 control-ready 探针均为 dev 新增）。

## 文件

| 文件 | 用途 |
|------|------|
| `docker-compose.yml` | 主栈（保留原挂载/端口/user:root；三处修正见文件头注释） |
| `docker-compose.postgres.yml` | PG 变体叠加文件（全新采用 PG / 迁移目标库） |

## 三处关键修正（相对现网配置）

1. **backend healthcheck**：`curl -f /docs` → `python3 /health/control-ready`
   - v1.0.8 镜像已移除 curl（安全治理）；`/docs` 非维护感知探针
   - 迁移冻结期 control-ready 返回 200（businessReady=false）——容器保持 healthy，无重启风暴
2. **frontend depends_on**：`service_healthy` → `service_started`
   - 冻结期业务 API 503，healthy 门控会让前端永不启动，维护页不可达
3. **`BTD_MIGRATION_MANAGED_RESTART=1`**：迁移提交→优雅退出→restart 策略拉起→激活 redo 闭环

## W6 迁移实测步骤（SQLite → PG）

1. **重建镜像**至 dev≥163deca（unraid 本地构建或经构建通道推送）
2. 主栈 SQLite 正常运行，写入真实数据（下载器/种子/配置）
3. 备份：`./data/backend/config` 与 `./data/backend/data` 快照
4. 起目标 PG：`docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d postgres`
   （叠加后 backend 会切换 DB_TYPE=postgresql——迁移实测请按 runbook 走应用内迁移，
   而非直接叠加重启；目标库也可用独立 PG 实例）
5. Web UI「设置→数据库」：填目标（postgres:5432/btdeck）→测试连接→发起迁移
6. 冻结→导入→核对（进度页 `/#/maintenance`）→提交→**托管自动重启**→激活确认
7. 验证：`/api/v1/database/status` effective=active postgresql；业务数据一致；回滚演练见 runbook §5

运维决策树/凭据丢失/回退：`docs/operations/database-migration-runbook.md`。
