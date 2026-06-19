# 第一阶段修复报告

## 修改文件清单

- `backend/app/config.py`
- `backend/app/core/config.py`
- `backend/app/auth/dependencies.py`
- `backend/app/api/endpoints/cron_tasks.py`
- `backend/app/api/_legacy_router_unused.py`
- `backend/app/startup/routers_initializer.py`
- `backend/app/factory.py`

## 任务 1：配置系统合并

- `backend/app/config.py` 已改为兼容转发层，保留 `from app.config import settings` 和 `Settings` 的旧导入路径。
- `backend/app/core/config.py` 作为唯一配置来源，统一 `SECRET_KEY`、`ACCESS_TOKEN_EXPIRE_MINUTES`、`ALGORITHM` 等认证配置。
- `SECRET_KEY` 优先从环境变量读取；开发环境未配置时生成临时密钥并记录警告，生产环境未配置时拒绝启动。
- `ACCESS_TOKEN_EXPIRE_MINUTES` 统一为 60 分钟。
- 移除了 `app.core.config` 中不必要的 `from app import api`，降低循环导入风险。

## 任务 2：认证依赖统一

- `backend/app/auth/dependencies.py` 新增 `AuthenticatedUserInfo` 和 `require_authenticated_user`。
- 新依赖支持 `X-Access-Token` 与 `Authorization: Bearer <token>`。
- 认证失败统一使用 `CommonResponse(status="error", code="401")` 结构。
- 保留并增强现有 `verify_token_dependency`，避免第一阶段批量改动 endpoint。
- 迁移方式已写入注释：后续 endpoint 可直接声明 `user_info: AuthenticatedUserInfo = Depends(require_authenticated_user)`。

## 任务 3：旧路由文件清理

- 已确认生产代码不挂载旧 `app.api.router`，仅剩初始化器中的归档提示注释。
- `backend/app/api/router.py` 已重命名为 `backend/app/api/_legacy_router_unused.py`。
- 归档文件顶部新增警告注释，说明不得在生产入口引用。
- `backend/app/startup/routers_initializer.py` 已删除旧挂载注释，改为明确提示旧路由已归档。

## 任务 4：定时任务安全加固

- `backend/app/core/config.py` 新增 `BTDECK_ALLOW_CUSTOM_SCRIPTS`，默认 `False`。
- `backend/app/api/endpoints/cron_tasks.py` 在创建任务时阻断 `0-shell`、`1-cmd`、`2-powershell`、`3-python` 脚本任务。
- 更新任务时按目标任务类型校验，防止通过更新接口把任务改成脚本任务，或继续修改既有脚本任务。
- 默认只允许内置任务类型 `4-python内部类`、`5-清理任务`、`6-审计日志导出`。
- 管理员显式设置 `BTDECK_ALLOW_CUSTOM_SCRIPTS=True` 后，才允许脚本任务入口恢复。

## 任务 5：CORS 安全加固

- `ALLOWED_HOSTS` 默认值改为开发前端来源：`http://localhost:8080` 和 `http://127.0.0.1:8080`。
- 生产环境 `DEV=False` 时必须通过 `ALLOWED_HOSTS` 环境变量显式配置来源，否则拒绝启动。
- `backend/app/factory.py` 增加运行期检查，`allow_credentials=True` 时禁止 `ALLOWED_HOSTS` 包含 `*`。
- `ALLOWED_HOSTS` 支持 JSON 数组或逗号分隔字符串两种环境变量格式。

## 向后兼容性说明

- 旧导入 `from app.config import settings` 保持可用，但实际对象已指向 `app.core.config.settings`。
- 第一阶段没有批量替换手动 token endpoint，现有接口调用形态保持不变。
- 既有脚本型定时任务未在调度器层删除；本次只阻断创建/更新入口。若确需继续维护脚本任务，需要显式配置 `BTDECK_ALLOW_CUSTOM_SCRIPTS=True`。
- 未修改测试文件。

## 需要手动验证的项目

- 开发环境未配置 `SECRET_KEY` 时能启动，并看到临时密钥警告。
- 生产环境设置 `DEV=False` 且缺少 `SECRET_KEY` 或 `ALLOWED_HOSTS` 时会拒绝启动。
- `ALLOWED_HOSTS` 配置为 `*` 时会拒绝启动。
- 登录后使用 `X-Access-Token` 和 `Authorization: Bearer <token>` 都能通过新认证依赖。
- 创建脚本型定时任务默认返回 403；设置 `BTDECK_ALLOW_CUSTOM_SCRIPTS=True` 后按预期恢复。
- 创建内置任务类型 4、5、6 能正常保存并进入调度逻辑。

## 自动验证记录

- 已执行 `python3 -m compileall` 检查本次修改的 Python 文件，语法编译通过。
- 已检查生产代码引用，旧 `app.api.router` 未被挂载或导入，仅剩归档提示注释。
- 当前 shell 的 Python 环境缺少 `pydantic`、`fastapi` 等项目依赖，导入级验证未能完成；需在安装 `backend/requirements.txt` 的运行环境中复核启动路径。
