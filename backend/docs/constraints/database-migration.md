# 数据库迁移管理（强制）

🔴 **核心原则**：所有数据库层面的修改必须通过 Alembic 迁移脚本管理，应用程序启动时自动执行数据库迁移。

## 四轨治理后的架构（v1.0.5-db-governance）

数据库 schema 管理已从历史"四轨冗余"统一为**单一 Alembic 轨**：

| 历史轨道 | 状态 |
|----------|------|
| Alembic 迁移链 | ✅ **唯一正道，保留** |
| `Base.metadata.create_all()`（init_db 兜底） | ❌ 已删除（无法 ALTER，掩盖迁移遗漏） |
| 生产 schema 快照 `ensure_database_initialized` | ❌ 已下线（写入幽灵版本 9aea25308aff，保留文件作 frozen 灾备） |
| search_templates 原生 SQL 自建 | ❌ 已归位 Alembic（新建 ORM + 迁移） |

**统一入口**：`migrate_database()`（`app/core/migration.py`）
- 编程式 alembic API（`command.upgrade`，frozen 模式也可用）
- 空库自动建全表 / 已有库增量升级
- 幽灵版本（`KNOWN_GHOST_VERSIONS`）自动 stamp 救援
- 未知版本（回滚场景）只告警不降级
- 迁移前自动备份（`config/app.db.pre-migration-*`，保留 3 个主备份文件）
- 备份须通过 integrity_check、Alembic 版本和 SHA-256 验证；失败在
  DEV/生产环境均无条件阻止迁移
- DEV 分流：DEV=true 失败告警继续；DEV=false 失败终止

## 当前迁移链（2026-07-26）

```
e2a02abcf912 (base, down_revision=None)
    └─ 创建 21 张基础业务表（users/configs/bt_downloaders/torrent_info/tracker_info/...）

d0e58437af70 (down_revision: e2a02abcf912)
    └─ 新增 tracker_reannounce_config 表

a0ada9774936 (down_revision: d0e58437af70)
    └─ 新增 notification 表

95ef8bd8b47a (down_revision: a0ada9774936)
    └─ 新增 search_templates 表（第四轨归位，inspect 守卫）

c3f1a8b7d902 → b075727f7182 → e6d8a20c41f3
    └─ orphan file / lifecycle / operation journal 增量迁移

6132b66d14a7 (down_revision: e6d8a20c41f3)
    └─ ratio/ratio_limit String→Float，严格清洗并保全 partial index

8f4c2d1a9b7e (down_revision: 6132b66d14a7) ← 当前 HEAD
    └─ 为已执行旧 6132 的数据库补清洗和有限非负 CHECK
```

- 单 head，无分叉
- `alembic heads` 必须输出且只输出 `8f4c2d1a9b7e`

`6132` 与 follower 采用混合兼容策略：尚未执行 `6132` 的数据库直接获得修正后的
严格迁移；已执行旧版 `6132` 的数据库由 `8f4c2d1a9b7e` 幂等补齐约束。旧版曾
折叠成 0 的值无法可靠反推，必须通过备份/下载器对账。

## 严格禁止

- ❌ 直接在数据库中修改表结构（使用 DDL 语句）
- ❌ 仅修改 SQLAlchemy 模型代码而不生成迁移文件
- ❌ 手动创建或删除数据库表、索引、约束
- ❌ 在代码中用原生 SQL `CREATE TABLE`（search_templates 已归位，不再允许第四轨）
- ❌ 调用 `Base.metadata.create_all()`（已从 init_db 移除，仅测试 fixture 允许）

## 必须执行

- ✅ 任何 Schema 变更（新增/修改表、字段、索引）**必须**生成对应的 Alembic revision
- ✅ 使用 `alembic revision --autogenerate -m "描述"` 生成迁移脚本
- ✅ 审查自动生成的迁移文件，确保变更符合预期
- ✅ 提交前执行 `alembic heads`，确保只有 **1 个 head**（避免 Multiple Heads）
- ✅ 迁移文件 docstring 标注可回滚性（见下文规范）

## 应用启动流程

**启动顺序**（FastAPI lifespan，`app/startup/lifecycle.py`）：
```
1. init_config_file() + yaml.reload()
2. migrate_database()   ← 统一迁移入口（编程式 alembic API）
3. init_db()            ← 仅 seed 数据（不再 create_all）
4. init_routers / 启动后台任务
5. 服务就绪
```

其中备份失败是独立硬门禁，不受 DEV 容错分流影响。一般 migration 异常仍沿用
DEV=true 告警、DEV=false 终止的历史策略。

## 发布后只读验证

```bash
cd backend
python scripts/ratio_migration_report.py \
  --database config/app.db \
  --fail-on-findings
```

报告核对当前 revision、SQLite 完整性、ratio 列类型、CHECK、非法值样本、
零值对账提示和可恢复备份。工具以 immutable 只读模式打开 SQLite，不生成备份
侧车文件。完整两阶段发布与恢复步骤见 rollback-guide。

## 表/字段增删改操作指南（详细）

### 场景 A：新增表

```bash
# 1. 创建 ORM 模型（app/models/<name>.py）
#    class NewEntity(Base):
#        __tablename__ = 'new_entities'
#        id = Column(Integer, primary_key=True)
#        ...

# 2. 在 alembic/env.py 补 import（确保 autogenerate 能感知）
#    from app.models.<name> import NewEntity

# 3. 生成迁移（用临时库避免污染开发库）
DATABASE_PATH=/tmp/autogen.db alembic upgrade head  # 先建 baseline
DATABASE_PATH=/tmp/autogen.db alembic revision --autogenerate -m "add new_entities table"

# 4. 补 docstring 标注（纯加表 = 【可回滚】）

# 5. 审查迁移文件（确认 create_table + 索引 + server_default 正确）

# 6. 测试 upgrade + downgrade 对称性
DATABASE_PATH=/tmp/test.db alembic upgrade head
DATABASE_PATH=/tmp/test.db alembic downgrade -1
DATABASE_PATH=/tmp/test.db alembic upgrade head

# 7. 提交（模型 + env.py import + 迁移文件一起）
```

### 场景 B：新增字段（加列）

```bash
# 1. 改 ORM 模型，加 Column
#    class User(Base):
#        ...
#        avatar = Column(String(500), nullable=True)  # 新增

# 2. 生成迁移
DATABASE_PATH=/tmp/autogen.db alembic upgrade head
DATABASE_PATH=/tmp/autogen.db alembic revision --autogenerate -m "add user avatar column"

# 3. 补标注（加列 = 【可回滚】）
# 4. 审查（确认 add_column 的 nullable/server_default）
# 5. 测试 + 提交
```

### 场景 C：修改字段（改类型/改约束）

```bash
# 1. 改 ORM 模型
# 2. 生成迁移（autogenerate 对类型变更可能检测不全，需手动检查）
DATABASE_PATH=/tmp/autogen.db alembic revision --autogenerate -m "alter user name length"

# 3. ⚠️ SQLite 不支持直接 ALTER COLUMN，alembic 会用 batch_alter_table
#    手动检查迁移文件是否用了 op.batch_alter_table

# 4. 标注【受限回滚】或【不可回滚】（类型变更 downgrade 可能丢数据）

# 5. 重点测试 batch_alter_table 的数据迁移正确性
# 6. 提交
```

### 场景 D：删除字段（删列）/ 删除表

```bash
# 1. 改 ORM 模型（删除 Column 或整个类）
# 2. 生成迁移
DATABASE_PATH=/tmp/autogen.db alembic revision --autogenerate -m "drop deprecated column"

# 3. ⚠️ 必须标注【不可回滚】（删列 downgrade 会丢用户数据）
# 4. CI 会检查：drop_column/drop_table 的迁移必须含标注（lint_btdeck.py BTD401）
# 5. 重点评估：是否有代码仍引用该字段？是否影响 API 契约？
# 6. 提交
```

## 迁移可回滚性标注规范（强制）

每个迁移文件的 docstring **必须**标注可回滚性，便于回滚决策（见 `docs/operations/rollback-guide.md`）：

| 标注 | 含义 | 示例 |
|------|------|------|
| 【可回滚】 | 纯增量，downgrade 安全 | 加表/加列/加索引 |
| 【受限回滚】 | downgrade 可能丢数据，需手工处理 | 数据迁移/默认值变更 |
| 【不可回滚】 | downgrade 会丢用户数据，禁止自动执行 | 删列/改列类型/删表 |

标注示例（迁移文件头部 docstring）：
```python
"""add user_avatar column

【可回滚】纯增量加列，downgrade 安全。

Revision ID: xxxx
...
"""
```

**CI 检查**：`upgrade()` 含 `op.drop_column`/`op.alter_column`/`op.drop_table` 的迁移，
docstring 必须含【不可回滚】或【受限回滚】字样，否则 CI 失败（`lint_btdeck.py` BTD401）。
纯增量迁移（create_table/add_column）不强制标注。

## 后续开发建议

### 日常开发
1. **改模型后立即生成迁移**：不要积累多个模型变更再生成，避免 autogenerate 混淆
2. **用临时库生成迁移**：`DATABASE_PATH=/tmp/x.db`，避免污染开发库的 alembic_version
3. **审查 autogenerate 产出**：autogenerate 不是万能的，尤其类型变更和数据迁移需手动检查
4. **提交前测 upgrade + downgrade**：`alembic upgrade head && alembic downgrade -1 && alembic upgrade head`

### 新增业务表
1. ORM 模型放 `app/models/`，遵循现有命名（`__tablename__` 复数形式）
2. **必须在 `alembic/env.py` 补 import**——否则 autogenerate 检测不到（历史盲区根因）
3. 如需 seed 初始数据，在 `app/data/default_*.py` 加幂等初始化函数，在 `init_db()` 调用

### 存量用户兼容
1. **不要删除 downgrade 函数**——即使标注【不可回滚】，downgrade 函数仍需存在（rollback-guide Level 3 可能用到）
2. **破坏性变更需在 release notes 声明**——告诉用户"此版本不可回滚"
3. **新增字段尽量 nullable 或有 server_default**——避免老代码插入时 NOT NULL 约束失败

### 测试
1. 新增表/字段后，在 `tests/core/test_db_migration.py` 更新 `EXPECTED_HEAD` 和表数断言
2. 迁移含 inspect 守卫的，补"表存在+索引存在"的 no-op 分支测试
3. 破坏性迁移补 downgrade 测试（参考 `test_db_governance_extended.py`）

## 迁移命令

```bash
# 生成迁移脚本（推荐用临时库）
DATABASE_PATH=/tmp/autogen.db alembic upgrade head
DATABASE_PATH=/tmp/autogen.db alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 降级一步（测试回滚）
alembic downgrade -1

# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 检查 head 数量（应该只有 1 个）
alembic heads
```

## 相关文档

- [跨环境数据库一致性](./database-consistency.md)
- [版本回滚操作指南](../operations/rollback-guide.md)
- [架构审查报告](../architecture-review.md)
