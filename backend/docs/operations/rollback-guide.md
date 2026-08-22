# 版本回滚操作指南

> 本文档适用于 BtDeck 四轨治理后的版本回滚场景。
> 数据库 schema 由 Alembic 迁移链统一管理，回滚需谨慎操作。

## 回滚前必读

### ratio/ratio_limit 类型迁移的发布门禁

`6132b66d14a7` 会把 `torrent_info.ratio` / `ratio_limit` 从文本列重建为
数值列，属于受限、不可凭 downgrade 恢复原始脏值的迁移。发布必须按两阶段执行：

1. 停止所有后端实例，确保 SQLite 没有并发写入。
2. 在旧库上运行只读基线报告：
   ```bash
   cd backend
   python scripts/ratio_migration_report.py --database config/app.db --json
   ```
   旧 revision、VARCHAR 列和缺少 CHECK 此时属于“待迁移”发现；但
   `integrity_check` 必须为 `ok`，且至少确认一份外部备份可用。
3. 只启动一个新后端实例。启动迁移会 checkpoint WAL、复制数据库并验证
   完整性、Alembic 版本和 SHA-256；任一备份步骤失败时，所有环境都会终止迁移。
4. 后端启动后执行：
   ```bash
   python scripts/ratio_migration_report.py \
     --database config/app.db \
     --fail-on-findings
   ```
   必须得到 `status: healthy`、revision `8f4c2d1a9b7e`、两列数值类型、
   两个 CHECK 均存在且 invalid=0。
5. 先验证后端高级搜索/模板接口，再发布前端。前端协议由后端
   `app/contracts/advanced_search_contract.json` 生成，禁止前端先行发布。
6. 观察同步日志中的单批 `ratio normalization summary`。`unavailable`
   增长代表下载器数据暂不可用，更新路径会保留旧值；qB `-1/-2` 作为
   `explicit_null` 是正常状态。

报告中的 zero 告警不能自动清零：零本身是合法值，也可能来自历史有损迁移，
必须和已验证的迁移前备份或下载器最新快照核对，禁止猜测。

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
2. 从报告的 `backups` 中选择主备份文件（文件名不能以 `-wal`/`-shm`
   结尾），先验证完整性、摘要和版本。回退本次迁移时通常应为
   `e6d8a20c41f3`：
   ```bash
   cd backend
   python scripts/ratio_migration_report.py \
     --database config/app.db.pre-migration-YYYYMMDD-HHMMSS-ffffff \
     --file-only \
     --expected-version e6d8a20c41f3 \
     --fail-on-findings
   ```
3. 另存当前失败库，保留升级后的新数据用于人工对账。
4. **删除 WAL 侧车文件**（WAL 模式强制步骤，否则数据不一致）：
   ```bash
   cd backend/config
   rm -f app.db-wal app.db-shm
   ```
5. **还原迁移前备份**（由 migrate_database() 自动生成）：
   ```bash
   cd backend/config
   ls app.db.pre-migration-*        # 列出可用备份
   cp app.db.pre-migration-YYYYMMDD-HHMMSS-ffffff app.db
   ```
6. 再用 `--file-only --expected-version e6d8a20c41f3 --fail-on-findings`
   验证已恢复的 `app.db`，然后安装旧版后端和前端并启动。

**注意**：
- 备份是 `migrate_database()` 在每次迁移前自动生成并验证的，保留最近
  3 个**主备份文件**；SQLite `-wal/-shm` 不计入份数
- 还原会丢失**升级后产生的新数据**（v1.0.6 运行期间的新增数据）
- WAL 侧车文件（`-wal`/`-shm`）必须先删，否则旧 db 被新 wal 污染
- 不要用 `alembic downgrade` 跨过 `6132b66d14a7` 来恢复历史文本：
  downgrade 只能把当前数值格式化为字符串，无法重建迁移前的非法内容

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
| orphan_file_tables | c3f1a8b7d902 | 纯增量 |
| orphan_lifecycle | b075727f7182 | 纯增量 |
| orphan_operation_journal | e6d8a20c41f3 | 纯增量 |
| ratio String→Float | 6132b66d14a7 | 【受限回滚】优先恢复迁移前备份 |
| ratio CHECK follower | 8f4c2d1a9b7e | 可移除约束，但不能恢复历史脏值 |
| orphan background scan | 7b2c9d4e6f10 | 【受限回滚】会移除后台统计、超量复核记录与稳定明细指针；大表仅允许单次 batch |

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
- ratio 迁移后没有已验证的迁移前备份：禁止尝试推断历史零值，采用前向修复

## 常见问题

### Q: 回滚后启动报 "数据库版本 xxxx 不在迁移链"
A: 这是 Level 1 回滚的预期行为。数据库版本超前于代码，migrate_database 只告警不降级。
   功能正常，可忽略。参考 Level 1 说明。

### Q: 找不到 app.db.pre-migration-* 备份
A: 备份由 migrate_database() 在 `current != head` 时生成。若一直是 head（未发生迁移），
   不会有备份。已有数据库的备份创建或验证失败会阻断本次迁移；若迁移后备份被外部
   删除，只能使用外部备份或前向修复，不能用 ratio downgrade 猜测原值。

### Q: 回滚后能再升级回新版本吗？
A: 可以。Level 1 回滚后，数据库版本仍是新版本 head，升级到更新版本时 alembic 会正常推进。
   Level 2/3 回滚后，数据库已降到旧版本，升级会重新应用被回滚的迁移。
