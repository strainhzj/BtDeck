# 数据库迁移管理（强制）

🔴 **核心原则**：所有数据库层面的修改必须通过 Alembic 迁移脚本管理，应用程序启动时必须自动执行数据库迁移。

## 严格禁止

- ❌ 直接在数据库中修改表结构（使用 DDL 语句）
- ❌ 仅修改 SQLAlchemy 模型代码而不生成迁移文件
- ❌ 手动创建或删除数据库表、索引、约束

## 必须执行

- ✅ 任何 Schema 变更（新增/修改表、字段、索引）**必须**生成对应的 Alembic revision
- ✅ 使用 `alembic revision --autogenerate -m "描述"` 生成迁移脚本
- ✅ 审查自动生成的迁移文件，确保变更符合预期
- ✅ 提交前执行 `alembic heads`，确保只有 **1 个 head**（避免 Multiple Heads）

## 应用启动流程要求

四轨治理后，迁移由 `migrate_database()` 统一负责（`app/core/migration.py`）：
- 空库自动建全表（alembic upgrade head）
- 已有库增量升级
- 历史"幽灵版本"库（production schema 初始化遗留）自动救援
- 迁移前自动备份（支持回滚，见 `docs/operations/rollback-guide.md`）
- DEV 分流：DEV=true 失败告警继续；DEV=false 失败终止

**启动顺序**（FastAPI lifespan）：
```
1. init_config_file() + yaml.reload()
2. migrate_database()   ← 统一迁移入口
3. init_db()            ← 仅 seed 数据（不再 create_all）
4. init_routers / 启动后台任务
5. 服务就绪
```

## 迁移可回滚性标注规范（强制）

每个迁移文件的 docstring **必须**标注可回滚性，便于回滚决策（见 rollback-guide.md）：

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

**CI 检查**：含 `op.drop_column`/`op.alter_column`/`op.drop_table` 的迁移，
docstring 必须含【不可回滚】或【受限回滚】字样，否则 CI 失败（lint_btdeck.py 扩展）。

## 迁移命令

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 检查head数量（应该只有1个）
alembic heads
```
