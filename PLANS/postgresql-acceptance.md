# PostgreSQL 分支独立验收

日期：2026-10-03。结论：**分支功能验收通过**；未提交 Git、未发布。

范围：`feature/postgresql-migration`，实现基点 `91dade1`，验收修复保留在工作区。依据 `PLANS/v1.0.8.md` P0–P4 的 23 项任务及 `backend/docs/postgresql-contract.md`。支持范围为 PostgreSQL 16+、单应用实例、单 worker，SQLite 仍为默认数据源。

## 发现与修复

1. 迁移对账原先只验证主键和行数，非主键内容损坏可漏过。现按类型归一化全列 SHA-256，对齐 Unicode 主键排序、UTC 时间、原生 JSON，区分 SQL NULL 与 JSON null。
2. 数据与检查点原先分开提交，失败后可出现重复导入。现每表数据与检查点同事务，内存状态仅在提交成功后更新；基线、stamp 与首个拒启标记也同事务。
3. 自动包裹直接修改源库、文件摘要不包含 WAL。现通过只读 backup API 建立临时一致性快照，包裹仅修改副本，恢复校验快照摘要、工具版本、检查点及目标数据状态。
4. 预检补齐唯一 head、表/列集合、完整性/外键、NULL、字符串长度、整数范围、合法日期/布尔/JSON、任务适用字段和存量正则模板；补 SM4 同源密钥与备份文件可达性检查。
5. 同步 TLS 连接遗漏 CA 参数；现验证模式传入 sslrootcert，require 不隐式升级为证书验证。
6. asyncpg 速度采样/报表使用字符串时间、可空查询参数缺少类型；改为双方言时间参数和显式类型。修复速度规则 Boolean 裸 SQL。
7. CLI 升级事务未提交、降级可能跨越支持下限；修复显式事务及 downgrade 下限。无版本/空版本表在重放历史链前拒绝，多版本及 PG<16 也有守卫。
8. 基线对拍扩展到默认值、唯一约束与 FK 删除行为，补齐遗漏的 ORM server_default；真实 PG introspection 与 metadata 无漂移。
9. 正则共同子集检查补齐语法差异，修正点号、行尾和 NULL 行为；预算覆盖每条 SQL，超时取消后回滚，成功后恢复原 statement_timeout。
10. 主 compose 补 DB_* 透传以支持外部 PG；强制 PG CI 增加真实 TLS 测试步骤。

## 验收矩阵与结果

| 范围 | 验证结果 |
|---|---|
| SQLite 回归 | 全量 **5495 passed / 46 skipped / 0 failed**，396.02 秒。最后一轮仅补 PG 版本守卫与测试后，针对受影响核心模块复跑 **68 passed**。跳过项包含独立 PG 集成；不能将跳过计作通过。 |
| PG 16 实库 | 最终 **29 passed**：空库初始化/重复启动、真实 DDL 回滚、增量升级持久化/降级下限/空版本表拒绝、同步异步连接、种子与 Tracker 活动/软删 upsert、seed 幂等、速度聚合/报表/清理、租约、孤儿占用排除、JSON、迁移失败与中途恢复、sequence 校准及内容摘要。 |
| 搜索 | 正则共同子集矩阵、跨 SQL 总预算、实际服务超时回滚恢复；LIKE 在 C 与 en-US-x-icu 两种 collation 下验证 ASCII 折叠、非 ASCII、字面通配符、NULL 和否定条件。ICU 英文排序环境替代 libc en_US.UTF-8，未声称所有 locale/Unicode 表达式等价。 |
| TLS | 29 项 PG 测试中含 6 项 TLS：同步 psycopg2 与异步 asyncpg 的 disable/prefer/require/verify-ca/verify-full，以及 verify-full 主机名不符拒绝。另在无 TLS 服务端 **5 passed / 1 skipped**，三个强制 TLS 模式实际连接被拒绝；跳过项仅为 TLS 主机名测试。 |
| 迁移工具 | 工具 1.1.0；三状态、源快照只读、首表前/中途失败、检查点事务、版本不符拒绝恢复、全列损坏检出、JSON null 区别、密钥/备份检查均有回归。源库切换前持续停写和首次应用启动前无损回退窗口已写入文档。 |
| Schema 与最低版本 | SQLite 链 head 与 metadata 比较、真实 PG compare_metadata 均通过；PG15 拒绝/16与17接受的版本边界单测通过（真实数据库为16，未运行15/17实库）。 |
| 静态质量 | mypy **309 文件无错误**；black 检查通过；flake8 无错误（两条既有无效转义 SyntaxWarning）；架构检查无阻塞问题，19项已有白名单；git diff --check 通过。 |
| 前端 | npm run typecheck / lint / build 通过；本次未改前端业务源码。 |
| Compose | 默认 SQLite、内置 PG override、外部 PG 三种 docker compose config 解析及环境断言通过。 |
| 实际镜像 | Dockerfile 实际构建成功，Python **3.12.14** / asyncpg **0.31.0** / psycopg2 **2.9.13**。最终镜像在独立 PG 库启动，就绪接口 HTTP **200**，database/worker/eventLoopLag 均正常；旧实例先停止，避免并行调度。 |
| 环境入口 | 根目录 ./init.sh --ci（默认模式）通过，工具从 /tmp/pg-probe 提供。 |

## 证据与复跑入口

本地完整日志：

- `/tmp/btdeck-pg-full-final.log`：全量 SQLite；`/tmp/btdeck-pg-core-complete.log`：最后核心回归。
- `/tmp/btdeck-pg-complete.log`：最终真实 PG + TLS；`/tmp/btdeck-pg-no-tls-final.log`：无 TLS。
- `/tmp/btdeck-pg-{mypy,black,flake8,architecture}-complete.log`：最终质量检查。
- `/tmp/btdeck-pg-frontend-{types,lint,build}.log`：前端检查。
- `/tmp/btdeck-pg-image-complete.log`：最终镜像；`/tmp/btdeck-pg-init-final.log`：环境入口。
- `/tmp/btdeck-compose-{sqlite,internal,external}.json`：三种配置解析结果。

测试代码：`backend/tests/core/test_pg_baseline.py`、`test_baseline_schema_parity.py`、`test_migrate_sqlite_to_pg.py`、`test_pg_connection_config.py`、`test_dialect_sql.py` 和 `backend/tests/pg_integration/`。

PG 集成需设置 `DB_TYPE=postgresql`、连接参数及 `BTDECK_PG_TEST_ADMIN_DSN`（仅用可建删临时数据库的测试账号），执行 `pytest tests/pg_integration -q`；TLS 阶段另设置 `BTDECK_PG_TLS_PORT` 与 `BTDECK_PG_TLS_CA`。SQLite 回归不设置 PG 环境变量。CI 工作流已增加相同测试，未在远端 GitHub Actions 上执行。

## 发布边界

当前工作区有未提交修复，因此生成的正式 build-info 标记 dirty，原发布就绪门禁会返回 503（build_identity_invalid）。这是有效门禁，并未修改或伪造其结果。镜像功能启动测试仅在一次性容器内移开 build-info，按已记录的源码开发模式运行；原镜像保持 dirty 身份。**正式发布仍需用户授权提交后，从干净提交重新构建并通过发布身份门禁**，本次功能验收不代表产物已获准发布。

本地测试使用独立 PG 容器和临时数据库，无生产数据；验收完成后清理本次临时容器/网络及前端依赖软链接，镜像和 /tmp 日志留作证据。
