# BtDeck CI 代码质量集成报告

## 目标

将诊断脚本中的关键架构、安全和认证检查前移到代码质量门禁，确保 CI/CD 能在不启动应用、不导入项目代码的情况下发现高风险变更。

## 已集成检查

- 配置系统：禁止生产代码直接 `import app.config.settings`，应统一使用 `app.core.config`。
- 配置系统：禁止硬编码 `SECRET_KEY`、密码、token、API key 等敏感字面量。
- 认证方式：统计 `Depends(get_current_user)` 与手动解析 `X-Access-Token` 的比例。
- 认证方式：禁止 endpoint 新增手动读取 `X-Access-Token`。
- 安全调用：检测 `exec()`、`eval()`、`os.system()`、`subprocess.call(shell=True)`。
- SQL 安全：检测疑似 SQL 字符串拼接和动态 SQL 变量执行。

## 本地运行

```bash
cd backend
make lint
make test
make check-all
```

也可以只运行自定义门禁：

```bash
cd backend
python3 scripts/lint_btdeck.py --show-allowed
```

## CI 用法

已提供 GitHub Actions 示例：

```text
backend/.github/workflows/code-quality.yml
```

关键步骤：

```bash
python scripts/lint_btdeck.py --show-allowed
ruff check app/
pytest tests/ -v
```

## 白名单策略

当前存在少量历史兼容或特定设计场景，例如旧 endpoint 手动 token 解析、任务执行器中的 `exec()`。这些点在 `backend/scripts/lint_btdeck.py` 的 `ALLOWLIST` 中显式登记。

白名单只用于防止当前历史问题阻塞 CI，不代表推荐写法。新增同类问题不会自动通过，必须先完成迁移或经过代码审查后显式登记。

## 规则编号

- `BTD101`：直接导入 `app.config.settings`
- `BTD102`：硬编码 `SECRET_KEY`
- `BTD103`：疑似硬编码密码或密钥
- `BTD201`：endpoint 手动读取 `X-Access-Token`
- `BTD301`：`exec()` 调用
- `BTD302`：`eval()` 调用
- `BTD303`：`os.system()` 调用
- `BTD304`：`subprocess.call(shell=True)` 调用
- `BTD305`：疑似 SQL 字符串拼接

## 运行特性

- 扫描器只使用 Python 标准库。
- 不 import `app` 包，不触发应用配置初始化。
- 错误输出包含规则编号、文件路径和行号。
- pytest 架构测试可独立运行：`pytest tests/test_architecture_constraints.py -v`。
