# 跨环境数据库一致性保障（强制）

🔴 **核心原则**：确保所有开发环境和生产环境的数据库结构始终保持一致，避免因迁移版本不同步导致的功能异常。

## 严格禁止

- ❌ 启动应用前不检查数据库版本
- ❌ 在不同环境间切换时直接启动应用
- ❌ 迁移失败时强制启动应用
- ❌ 手动修改数据库结构而不生成迁移脚本

## 必须执行

- ✅ **每次启动前检查版本**：`alembic current` 与 `alembic heads` 对比
- ✅ **版本不一致时立即升级**：`alembic upgrade head`
- ✅ **git pull后自动检查**：配置 `.git/hooks/post-merge` 自动验证
- ✅ **部署前强制验证**：CI/CD流程中加入版本一致性检查
- ✅ **定期备份正常数据库**：保留已知可用的数据库副本

## 快速诊断与修复

```bash
# 检查版本一致性
alembic current   # 应输出: 9aea25308aff (head)
alembic heads     # 确认最新版本

# 版本不一致时立即升级
alembic upgrade head

# 验证表结构完整性
sqlite3 config/app.db ".tables" | wc -l  # 应为 27 个表
```

## 备份恢复方案（迁移失败时）

```bash
cd config
mv app.db app.db.failed_$(date +%Y%m%d_%H%M%S)
cp app_backup_YYYYMMDD.db app.db
```

## 预防措施

### 环境变量配置

```bash
MIGRATION_TIMEOUT=300              # 迁移超时（秒）
ALLOW_MIGRATION_FAILURE=0          # 生产环境必须终止启动
```

### Git Hook自动化（`.git/hooks/post-merge`）

```bash
#!/bin/bash
cd btpManager
python scripts/ensure_database_consistency.py
```

**重要提醒**：数据库版本不一致隐蔽且危险，可能导致数据丢失或功能异常，务必严格遵守上述流程！
