# BtDeck 数据库配置指南（v1.0.8 双数据库架构）

> 契约文档：`backend/docs/postgresql-contract.md`（配置/基线/语义契约）
> 迁移计划：`PLANS/v1.0.8.md`（五轮审查 + 基线刷新 v7）

## SQLite（默认，零配置）

无需任何配置。数据库文件落在 `CONFIG_DIR/app.db`（Docker 部署为 `./data/backend/config/app.db` 持久化卷）。
可选环境变量 `DATABASE_PATH` 指定绝对路径（应用与 alembic 迁移双源一致）。

## PostgreSQL（可选数据源）

### 前置要求

- **PostgreSQL 16+**（启动和迁移入口执行最低版本检查）
- **单应用实例、单 worker**：PG 模式 `WORKERS=1` 强制（多 worker 启动即拒绝；多实例扩展另行立项）
- 连接预算：`(sync pool+overflow) + (async pool+overflow)` ≤ PG `max_connections`（默认 10+20 双侧 = 60）

### 配置项（环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `DB_TYPE` | `sqlite` | **唯一方言判据**；`postgresql`（别名 postgres/pg）切换；非法取值启动即报错 |
| `DB_HOST` / `DB_PORT` | localhost / 5432 | 连接地址 |
| `DB_USER` / `DB_PASSWORD` / `DB_NAME` | btdeck / 空 / btdeck | 凭据与库名 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | 10 / 20 / 30 | 连接池（SQLite 不消费） |
| `DB_SSLMODE` | prefer | disable/prefer/require/verify-ca/verify-full |
| `DB_SSL_ROOT_CERT` | — | verify-ca/verify-full 的 CA 证书路径 |

`DATABASE_PATH` 在 PG 模式下不被消费。

### 形态一：内置 PG（compose override 文件）

```bash
# .env 设置 DB_PASSWORD（必需）
echo "DB_PASSWORD=强密码" >> .env

docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d
```

- 自动启用 `postgres:16-alpine` 服务（healthcheck + 持久化卷 `./data/postgres`）并注入 backend 的 DB 配置
- 默认 SQLite 部署不受影响（不依赖 PG 服务）

### 形态二：外部 PG

```bash
DB_TYPE=postgresql DB_HOST=pg.internal DB_PORT=5432 DB_USER=btdeck \
DB_PASSWORD=*** DB_NAME=btdeck WORKERS=1 python main.py
```

Docker 外部数据库同样使用主 compose：在 `.env` 设置这些 `DB_*` 变量后执行
`docker compose -f docker-compose.yml up -d`，不引入 PostgreSQL override 文件。
主 compose 会透传全部连接参数，不拉起内置数据库。证书应挂载到容器，例如
放入持久化配置目录并设置 `DB_SSL_ROOT_CERT=/app/config/pg-ca.crt`。

### 首次启动行为

PG 空库自动走 **squash 基线**：应用启动时 `migrate_database()` 检测空库（无版本且无业务表）→
单事务 `create_all + stamp`（共享连接原子提交）→ 随后 init_db 正常 seed。
手工 `alembic upgrade head` 对 PG 空库会被守卫拒绝（会重放 SQLite 专属历史链）。

## SQLite → PG 存量数据迁移

工具：`backend/scripts/migrate_sqlite_to_pg.py`（契约 §3 三状态规则）。

```bash
# 1. 停止应用写入（维护窗口；最终快照前停写并保持至切换完成）
# 2. 预检（不连 PG）：版本/JSON 按字段契约/布尔取值/日期格式/软删同键报告
python scripts/migrate_sqlite_to_pg.py --source /path/app.db --precheck \
  --source-config /old/config/config.yaml --target-config /new/config/config.yaml \
  --backup-root /new/backend
# 3. 完整迁移（需 DB_TYPE=postgresql 环境）：
#    全新目标库 → 基线建表+stamp（不 seed）→ 依赖序分批导入 → sequence 校准 → 行数/主键/摘要核对
python scripts/migrate_sqlite_to_pg.py --source /path/app.db
# 中断恢复（检查点续传）：
python scripts/migrate_sqlite_to_pg.py --source /path/app.db --resume
```

- 预检发现 JSON 裸标量：`--auto-wrap-scalar` 包裹（出报告）；对象/类型不符恒拒绝
- 软删同键记录**保留不清理**（合法状态，仅报告）
- **无损回退窗口**：仅限导入完成后、应用首次正常启动前的离线核对阶段；首次启动即结束窗口，
  此后回切旧库将丢失切换后写入
- 切换：`.env` / compose 设 `DB_TYPE=postgresql` 后启动应用


### 迁移验收与恢复（工具 1.1.0）

完整迁移及 `--resume` 使用与预检相同的 `--source-config`、`--target-config`、
`--backup-root` 参数。有 `sm4:` 下载器凭据时，源/目标配置必须包含同一个有效
`security.secret_key`；工具只比较密钥，不打印密钥。有效种子备份的相对路径从
目标后端根目录解析，文件不可读则在建目标库前拒绝。路径映射按原文导入并纳入
全列摘要；移动部署位置后，仍需确保映射的实际存储挂载可达。

- 源库只读：SQLite backup API 创建包含已提交 WAL 的一致性临时快照；
  `--auto-wrap-scalar` 只改快照。最终迁移仍要求停止源应用写入，快照不会复制后续写入。
- 预检包含唯一 head、表/列集合、外键、NULL、长度、数值范围、日期、JSON
  按任务适用性及存量正则模板共同子集；不兼容模板按 ID 报告。
- schema、stamp 和首次拒启标记同事务；每张表的数据与检查点同事务。
  中断后保留拒启标记，`--resume` 校验源摘要、工具版本、版本 head、检查点前缀和行数。
  旧 1.0.0 检查点不能用 1.1.0 恢复；保留源库，用新的空目标库重跑。
- 分批读取每批 500 行；每表一个事务。对账流式比较行数、主键及全部内容，
  固定文本主键排序并保留原生 JSON 的 SQL NULL/JSON null 差别。
- 清除拒启标记前完成全表对账和 sequence 校准。首次正常启动前可回切停写的源库；
  首次启动会运行 seed/后台任务，此后不再承诺无损回退。
- 未提交修改生成的 `dirty=true` 镜像身份会按发布门禁返回 readiness 503。
  源码模式功能验收与正式发布身份验收分别记录；发布需提交后重新构建，不应修改身份绕过门禁。
