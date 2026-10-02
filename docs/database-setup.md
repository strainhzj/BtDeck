# BtDeck 数据库配置指南（v1.0.8 双数据库架构）

> 契约文档：`backend/docs/postgresql-contract.md`（配置/基线/语义契约）
> 迁移计划：`PLANS/v1.0.8.md`（五轮审查 + 基线刷新 v7）

## SQLite（默认，零配置）

无需任何配置。数据库文件落在 `CONFIG_DIR/app.db`（Docker 部署为 `./data/backend/config/app.db` 持久化卷）。
可选环境变量 `DATABASE_PATH` 指定绝对路径（应用与 alembic 迁移双源一致）。

## PostgreSQL（可选数据源）

### 前置要求

- **PostgreSQL 16+**（JSON 守卫依赖 `IS JSON` 谓词）
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

不引入 override 文件（不拉起内置数据库）。

### 首次启动行为

PG 空库自动走 **squash 基线**：应用启动时 `migrate_database()` 检测空库（无版本且无业务表）→
单事务 `create_all + stamp`（共享连接原子提交）→ 随后 init_db 正常 seed。
手工 `alembic upgrade head` 对 PG 空库会被守卫拒绝（会重放 SQLite 专属历史链）。

## SQLite → PG 存量数据迁移

工具：`backend/scripts/migrate_sqlite_to_pg.py`（契约 §3 三状态规则）。

```bash
# 1. 停止应用写入（维护窗口；最终快照前停写并保持至切换完成）
# 2. 预检（不连 PG）：版本/JSON 按字段契约/布尔取值/日期格式/软删同键报告
python scripts/migrate_sqlite_to_pg.py --source /path/app.db --precheck
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
