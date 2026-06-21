# 版本回滚操作指南

> 本文档适用于 BtDeck 四轨治理后的版本回滚场景。
> 数据库 schema 由 Alembic 迁移链统一管理，回滚需谨慎操作。

## 回滚前必读

### 数据库版本查看

```bash
cd backend
sqlite3 config/app.db "SELECT version_num FROM alembic_version"
alembic heads     # 当前代码支持的最新版本
alembic current   # 当前数据库实际版本
```

### 关键概念

- **纯增量变动**（加表/加列/加索引）：回滚相对安全
- **破坏性变动**（删列/改列类型/删表）：回滚风险高，可能丢数据
- **迁移可回滚性标注**：每个迁移文件 docstring 标注【可回滚】/【受限回滚】/【不可回滚】

## 三级回滚方案

### Level 1：代码回滚，数据库不动（推荐·最安全）

**适用**：新版本（如 v1.0.6）的数据库变动是**纯增量**（加表/加列），旧版本代码（v1.0.5）能容忍多余 schema。

**步骤**：
1. 安装旧版本（v1.0.5）
2. 启动服务——migrate_database() 检测数据库版本超前于代码版本
3. 此时会出现 error 日志："数据库版本 xxxx 不在当前代码的迁移链中"，**这是预期的**，功能不受影响

**前置检查（强制）**：
- ⚠️ 回滚前必须 grep 代码库所有 `SELECT *` + 位置参数解包的裸查询。
  若 DB 会多列，这类代码会 `TypeError` 崩溃。
- v1.0.5 已修复 `app/core/downloader.py` 的 `BtDownloaders(*row)` 裸查询（改为 ORM）。
- 若旧版本代码含裸查询且无法修复，**不能**用 Level 1，改用 Level 2。

**行为说明**：
- 数据库 schema 保持新版本（v1.0.6），version 保持新版本 head
- 旧版本代码（v1.0.5）忽略未映射的多余列/表（SQLAlchemy ORM 默认行为）
- 功能正常，version 暂时不匹配但**无害**
- 下次升级到更新版本时，alembic 自动对齐

### Level 2：备份还原（推荐用于破坏性变动）

**适用**：新版本有删列/改列等破坏性变动，旧版本代码会崩溃。

**步骤**：
1. **停止服务**（必须）
2. **删除 WAL 侧车文件**（WAL 模式强制步骤，否则数据不一致）：
   ```bash
   cd backend/config
   rm -f app.db-wal app.db-shm
   ```
3. **还原迁移前备份**（由 migrate_database() 自动生成）：
   ```bash
   cd backend/config
   ls app.db.pre-migration-*        # 列出可用备份
   cp app.db.pre-migration-YYYYMMDD-HHMMSS app.db
   ```
4. 安装旧版本，启动服务

**注意**：
- 备份是 `migrate_database()` 在每次迁移前自动生成的，保留最近 3 份
- 还原会丢失**升级后产生的新数据**（v1.0.6 运行期间的新增数据）
- WAL 侧车文件（`-wal`/`-shm`）必须先删，否则旧 db 被新 wal 污染

### Level 3：alembic downgrade（最后手段·高风险）

**适用**：无备份，且必须回滚 schema。

**步骤**：
```bash
cd backend
alembic history                    # 查看迁移链
alembic downgrade <目标版本>        # 降级到目标版本
```

**⚠️ 风险警告**：
- downgrade 会执行迁移的 `downgrade()` 函数
- 对【不可回滚】迁移（如删列/改列），downgrade **会丢数据**，且无法恢复
- **禁止 downgrade 越过 `a0ada9774936`**（base 迁移 `e2a02abcf912` 的 downgrade 会 drop 全部 21 表）

**现有迁移可回滚性**：
| 迁移 | revision | 标注 |
|------|----------|------|
| base | e2a02abcf912 | 【不可回滚】downgrade 会 drop 全部 21 表 |
| tracker_reannounce_config | d0e58437af70 | 【可回滚】仅 drop 该表 |
| notification | a0ada9774936 | 【可回滚】仅 drop 该表 |
| search_templates | 95ef8bd8b47a | 【可回滚】仅 drop 该表 |

## 回滚决策树

```
新版本（v1.0.6）的数据库变动类型？
│
├─ 纯增量（加表/加列/加索引）
│   └─ Level 1：代码回滚，DB 不动
│       （前提：旧代码无 SELECT * 裸查询，或已修复）
│
├─ 破坏性（删列/改列/删表）+ 有自动备份
│   └─ Level 2：备份还原
│       （记得删 WAL 侧车文件）
│
└─ 破坏性 + 无备份
    ├─ Level 3：alembic downgrade（高风险，确认目标区间迁移都标注【可回滚】）
    └─ 或：放弃回滚，修复新版本 bug 发新版本
```

## 何时放弃回滚

- 夹有【不可回滚】迁移且无备份：**放弃回滚**，修复新版本 bug 发新版本
- 数据已严重不一致：从 `app.db.pre-migration-*` 恢复后重新升级
- 无法判断 schema 差异：运行 `alembic upgrade head --sql` 查看待应用的 SQL

## 常见问题

### Q: 回滚后启动报 "数据库版本 xxxx 不在迁移链"
A: 这是 Level 1 回滚的预期行为。数据库版本超前于代码，migrate_database 只告警不降级。
   功能正常，可忽略。参考 Level 1 说明。

### Q: 找不到 app.db.pre-migration-* 备份
A: 备份由 migrate_database() 在 `current != head` 时生成。若一直是 head（未发生迁移），
   不会有备份。此时只能用 Level 3 或放弃回滚。

### Q: 回滚后能再升级回新版本吗？
A: 可以。Level 1 回滚后，数据库版本仍是新版本 head，升级到更新版本时 alembic 会正常推进。
   Level 2/3 回滚后，数据库已降到旧版本，升级会重新应用被回滚的迁移。
