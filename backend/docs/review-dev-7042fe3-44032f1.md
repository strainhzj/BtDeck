# dev 分支近期提交审查报告（7042fe3..HEAD）

审查范围：`7042fe3..HEAD`，当前 HEAD 为 `44032f1`。

已执行命令：
- `git log --oneline 7042fe3..HEAD`
- `git diff 7042fe3..HEAD --stat`
- `git diff 7042fe3..HEAD`
- `git diff 7042fe3..HEAD --check`：通过
- `./init.sh`：失败，`Permission denied`
- `cd backend && pytest ...`：失败，当前环境 `pytest: command not found`
- `cd frontend && npm run test:unit ...`：失败，当前环境 `jest: not found`

## Summary（总体评价）

本批提交覆盖面很大，主要包括认证统一、JWT 库从 jose 统一到 PyJWT、全局异常响应归一化、数据库四轨治理到 Alembic 单轨、查询模板 ORM 化、前后端契约修复和大规模 black 格式化。整体方向是正确的，尤其是 `require_authenticated_user`、PyJWT 收敛、Alembic 编程式迁移、全局异常处理器都降低了历史技术债。

但本批改动仍存在几个必须修复的回归：前端只发送 `Authorization: Bearer` 后，后端仍有下载器设置端点只读 `x-access-token`；搜索模板从 token 解析出的 `user_id` 变成 `int` 后，与 `search_templates.user_id` 的 `String` 字段直接比较，导致权限判断错误；搜索模板列表接口仍允许客户端指定任意 `user_id`；任务日志 cleanup 默认空参数会软删除全部日志。测试覆盖主要验证“认证未拒绝”，没有覆盖真实业务权限与前后端 header 契约。

## Critical Issues（必须修复）

1. 前端认证 header 收敛后，下载器设置端点会被误判未认证。

   位置：
   - `frontend/src/utils/request.ts:63` 仅发送 `Authorization: Bearer`
   - `backend/app/api/endpoints/downloader_settings.py:190`
   - `backend/app/api/endpoints/downloader_settings.py:324`
   - `backend/app/api/endpoints/downloader_settings.py:855`
   - `backend/app/api/endpoints/downloader_settings.py:916`
   - `backend/app/api/endpoints/downloader_settings.py:1099`

   后端这 5 个端点仍只读取 `req.headers.get("x-access-token")`，不会识别前端新发的 Bearer token。影响下载器配置读取、保存、限速规则排序、应用配置、配置测试等核心 UI 流程。应统一迁移到 `Depends(require_authenticated_user)`，或至少复用 `_extract_access_token()`。

2. 搜索模板权限判断存在 `str`/`int` 类型不一致，用户可能无法操作自己的模板。

   位置：
   - `backend/app/auth/dependencies.py:64` 将 JWT `user_id` 转成 `int`
   - `backend/app/models/search_template.py:47` 表字段是 `String(36)`
   - `backend/app/api/endpoints/advanced_search.py:197`
   - `backend/app/services/advanced_search.py:947`
   - `backend/app/services/advanced_search.py:994`
   - `backend/app/services/advanced_search.py:1028`

   新 endpoint 把 `user_info.user_id` 传入 service，实际是 `int`；ORM 读出的 `template["user_id"]` 是字符串。`"1" != 1` 会导致 update/delete/apply 被错误判定为无权限。应在认证层保持 `user_id` 为字符串，或在进入 search template service 前统一 `str(user_info.user_id)`，并补真实 CRUD 权限测试。

3. 搜索模板列表接口允许读取任意用户私有模板。

   位置：
   - `backend/app/api/endpoints/advanced_search.py:134`
   - `backend/app/api/endpoints/advanced_search.py:152`
   - `backend/app/services/advanced_search.py:615`

   `GET /advanced-search/search-templates` 仍接受必填 query 参数 `user_id`，并直接用它作为查询目标。任意认证用户可以传入其他用户 ID，在 `is_public=false` 时读取对方私有模板。应忽略客户端传入的 `user_id`，默认使用当前 token 的用户；如需管理员查看其他用户模板，必须引入显式权限判断。

4. 任务日志 cleanup 空参数会软删除全部日志，存在数据丢失风险。

   位置：
   - `backend/app/api/endpoints/cron_tasks.py:615`
   - `backend/app/api/endpoints/cron_tasks.py:618`
   - `backend/app/api/endpoints/cron_tasks.py:633`
   - `backend/app/tasks/cron_crud.py:405`
   - `backend/app/tasks/cron_crud.py:417`

   `payload` 默认 `{}`，`days=None`、`keep_success=False`、`keep_error=False` 时，`cleanup_task_logs()` 对 `TaskLogs.dr == 0` 的全集执行 update，等价于清空全部任务日志。应要求至少一个清理条件，或设置安全默认值，并为“空 payload 不删除任何记录”补测试。

## Warnings（建议修复）

1. Alembic `env.py` 兜底路径缺少 `Path` import。

   位置：`backend/alembic/env.py:66`、`backend/alembic/env.py:68`

   `settings` 导入失败时会进入兜底分支，但 `Path` 未导入，会再次抛 `NameError`，导致 Alembic 独立命令或异常配置场景诊断失败。影响面不如主路径大，但应修复。

2. 登出端点没有 token 撤销机制。

   位置：`backend/app/api/endpoints/cuser.py:24`

   代码注释已明确这是最低实现，登出后旧 JWT 在过期前仍有效。若用户把“登出”理解为服务端失效 token，这是安全语义缺口。建议至少在文档/产品语义上标明，后续用 `jti` + 黑名单实现撤销。

3. 全局异常处理器与 endpoint 内部 `CommonResponse(code="500")` 并存，错误语义仍未完全统一。

   位置：`backend/app/exception_handlers.py:104`、`backend/app/api/endpoints/advanced_search.py:88` 等

   新 handler 能兜底未捕获异常，但大量 endpoint 仍捕获 `Exception` 后返回 HTTP 200 + `code="500"`。前端已能归一化业务错误，但 OpenAPI/HTTP 语义仍不一致。建议后续逐步把真正的服务端错误改成 HTTP 5xx。

4. `advanced_search` 分页响应仍使用 `data/limit/total_pages`，不符合全栈约束的 `list/pageSize`。

   位置：`backend/app/api/endpoints/advanced_search.py:75`

   计划中说明分页统一推迟，但这是约束文件中的强制项。若前端已依赖旧格式，应在后续 P3 契约收敛中一次性迁移并补兼容测试。

## Suggestions（可选优化）

1. `backend/app/api/api.py` 仍重复导入 `tracker_keywords_pools`，可在后续非功能提交中清理。

2. `backend/app/api/endpoints/advanced_search.py` 多处重复 `if not user_info.user_id` 和同样的 401 detail，可提取小 helper，降低后续遗漏概率。

3. `backend/app/core/db_backup.py:53` 调用了两次 `datetime.now()` 拼时间戳，极小概率跨毫秒不一致；可用一次 `now = datetime.now()` 提升可读性。

4. `_logs_to_csv()` 当前空日志导出为空文件，没有表头。若前端/用户期望稳定 CSV schema，建议空结果也输出固定表头。

## Test Coverage Assessment（测试覆盖评估）

已有新增测试覆盖了不少迁移治理场景、搜索模板 ORM 基础 CRUD、认证拒绝路径、PyJWT 成功路径和前端错误归一化逻辑，方向是好的。

主要缺口：
- 缺少前端 `Authorization: Bearer` 调用后端 `downloader_settings.py` 的契约测试，未捕获 header 收敛回归。
- 搜索模板 API 测试只断言有效 token “不是 401”，没有用真实 DB 覆盖 create -> update/delete/apply 的权限链路，因此未发现 `str`/`int` user_id 比较问题。
- 缺少“用户 A 不能读取用户 B 私有模板”的越权测试。
- 缺少任务日志 cleanup 空 payload / 非法 payload 不删除数据的回归测试。
- 当前环境无法执行 pytest/jest/init 验证：`pytest`、`jest` 缺失，`./init.sh` 不可执行。合并前应在完整环境中跑 `./init.sh --full`、后端认证/迁移相关 pytest、前端 `npm run test:unit` 与 `npm run lint`。
