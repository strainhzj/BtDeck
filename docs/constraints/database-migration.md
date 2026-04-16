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

后端应用启动脚本（`app/main.py`）必须包含自动迁移执行逻辑，确保数据库结构始终是最新状态。

**启动顺序**：
```
1. 初始化配置文件
2. 执行数据库迁移（alembic upgrade head）
3. 初始化数据库连接
4. 启动 API 服务
```

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
