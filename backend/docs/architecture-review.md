# architecture-deep-dive.md 独立审查

审查对象：`backend/docs/architecture-deep-dive.md`

审查方式：对照当前源码静态核查，重点查看 `backend/app/config.py`、`backend/app/core/config.py`、`backend/app/database.py`、`backend/alembic/env.py`、`backend/btdeck_startup.sh`、`backend/app/main.py`、`backend/app/startup/lifecycle.py`、`backend/app/tasks/cron_executor.py`、`backend/app/tasks/enhanced_python_executor.py`、`backend/app/api/endpoints/cron_tasks.py` 等文件。

## 一、事实核查

### 1. 配置系统双轨

| 验证点 | 结论 | 说明 |
| --- | --- | --- |
| `SECRET_KEY` 默认值 | 准确 | `app/config.py` 为 `YM4nwx3QBbZ227i5itqf`，`app/core/config.py` 为 `your-secret-key-for-jwt`。 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` 实际值 | 准确 | `app/config.py` 为 `600`，`app/core/config.py` 为 `30`。认证创建 token 的主要路径引用 `app.config.settings`，因此登录默认过期时间实际是 600 分钟。 |
| `DATABASE_URL` 不被消费 | 准确 | `rg DATABASE_URL` 显示应用代码没有读取该变量；`app/database.py` 使用 `settings.DATABASE_PATH` 构造同步/异步 URL，`alembic/env.py` 只读取 `DATABASE_PATH` 或 `settings.DATABASE_PATH`。根目录 `docker-compose.yml`、`backend/docker-compose.yml`、`backend/README.md` 和报告文档中出现 `DATABASE_URL`，但不是运行时代码消费。 |
| `DATABASE_URL=sqlite:///data/app.db` 在 Docker 中失效 | 准确 | Dockerfile 设置 `CONFIG_DIR=/app/config`，`settings.DATABASE_PATH` 固定落到 `/app/config/app.db`。Compose 的 `/app/data` 挂载不会因 `DATABASE_URL` 被应用使用。 |
| 报告中的 `app.config.settings` 引用分布 | 部分准确 | 生产代码列举完整：`app/api/endpoints/login.py`、`app/api/router.py`、`app/auth/utils.py`、`app/auth/security.py`、`app/auth/dependencies.py`。测试引用不完整：除 `backend/tests/auth/test_auth_edge_cases.py` 外，`backend/tests/conftest.py` 也 patch 了 `app.config.settings`。 |
| 报告中的 `app.core.config.settings` 引用分布 | 部分准确 | 报告列出的生产代码主要准确，但漏了 `app/factory.py`；未列 `backend/tests/conftest.py` 对 `app.core.config.settings` 的 patch。 |
| `.env` 加载差异 | 部分准确 | `app/config.py` 显式 `load_dotenv()` 且也设置 `env_file`；`core.config` 设置 `env_file`。报告说“仅 env_file”可接受，但没有指出两者都依赖 Pydantic settings 的解析行为。 |

补充发现：`app/core/config.py` 的 `TORRENTS_PATH` 属性确实递归访问自身，报告准确识别。

### 2. 数据库迁移双轨

| 验证点 | 结论 | 说明 |
| --- | --- | --- |
| `init_db()` 中存在 `create_all()` | 准确 | `backend/app/database.py` 的 `init_db()` 无条件执行 `Base.metadata.create_all(bind=engine)`。 |
| `ensure_database_initialized()` 返回值语义 | 准确 | 函数返回“是否成功确保数据库存在”。空库初始化成功返回 `True`，已有数据库也返回 `True`。`main.py` 却把 `True` 当作“从生产 schema 初始化并跳过 Alembic”，导致 `else: run_alembic_migrations()` 基本不可达。 |
| Docker 启动脚本重复执行 Alembic | 准确 | `btdeck_startup.sh` 执行 `alembic upgrade head`，随后启动 `uvicorn app.main:app`，FastAPI lifespan 又调用 `run_alembic_migrations()`。 |
| `main.py` 硬编码路径 | 准确 | `main.py` 使用 `Path(__file__).parent.parent / 'config' / settings.DATABASE_NAME`，没有使用 `settings.DATABASE_PATH`；当 `CONFIG_DIR` 覆盖时会出现初始化检查路径与真实数据库连接路径不一致。 |
| 生产 schema 快照写入固定 Alembic 版本 | 准确 | `init_schema_from_production.py` 执行 SQL 快照后写入 `alembic_version = 9aea25308aff`。 |
| `backend/alembic/env.py` 不读取 `DATABASE_URL` | 准确 | 只读取 `DATABASE_PATH` 环境变量或 `settings.DATABASE_PATH`。 |

### 3. 定时任务执行

| 验证点 | 结论 | 说明 |
| --- | --- | --- |
| `cron_executor.py` 中 `exec()` 调用点完整 | 准确 | 共有两处：异步代码 `exec(wrapped_code, exec_globals)`，同步代码 `exec(code, exec_globals)`。均使用完整 `__builtins__`。 |
| 全项目 `exec()` 调用点完整 | 部分准确 | 报告只覆盖 `cron_executor.py` 和 `enhanced_python_executor.py`，这对“定时任务执行器”是够的；但如果按全项目代码执行面统计，还应列出 `enhanced_python_executor.py` 两处 `exec()`。 |
| 脚本子进程执行路径完整 | 部分准确 | `cron_executor.py` 中 Shell/CMD/PowerShell/Python 脚本均使用 `create_subprocess_shell`，报告准确。另有 `validation_service.py` 使用 `create_subprocess_exec` 调用 `bash -n` 和 PowerShell 做语法校验；它不是任务执行，但属于用户提交脚本内容触发的外部进程路径，应在安全分析中补充。 |
| `enhanced_python_executor.py` 的 `safe_modules` 包含 `os`、`sys` | 准确 | `safe_modules` 明确暴露 `os` 和 `sys`。 |
| `cron_executor.py` 是否使用 `enhanced_python_executor` | 准确 | `cron_executor.py` 没有 import 或调用 `enhanced_python_executor`。 |
| 任务管理权限只有 token、无角色粒度 | 准确 | `cron_tasks.py::verify_token()` 仅调用 `utils.verify_access_token()`，未检查角色或权限。 |

### 4. 旧路由文件

| 验证点 | 结论 | 说明 |
| --- | --- | --- |
| `backend/app/api/router.py` 是未挂载旧文件 | 准确 | 主路由通过 `app/api/api.py` 挂载；`routers_initializer.py` 中只有注释引用旧 `router`。 |
| 旧路由包含硬编码 JWT key 和 SQL 拼接 | 准确 | `user_update()` 中使用固定 key 解码，并拼接 `update users set two_factor_secret=0 where username=`。 |

## 二、方案可行性审查

### 1. 配置合并方案

| 方案/问题 | 结论 | 说明 |
| --- | --- | --- |
| `app/config.py` 改为转发层 | 可行 | `app/core/config.py` 不 import `app.config`，当前不存在明显循环导入。`app.database` 依赖 `core.config`，认证模块依赖 `app.config`；转发后会统一到同一对象。需要注意测试 patch 路径会变。 |
| 逐步替换 `from app.config import settings` | 可行 | 生产代码约 5 个文件直接引用：`login.py`、`api/router.py`、`auth/utils.py`、`auth/security.py`、`auth/dependencies.py`。`auth/utils.py` 同时引用两套 settings，是优先处理对象。测试还需调整 `tests/auth/test_auth_edge_cases.py`、`tests/conftest.py` 以及若干 patch `app.auth.utils.settings` 的用例。迁移工作量小到中。 |
| `DATABASE_URL` 属性合并方案 | 需调整 | 报告提出的 SQLite 专项处理方向正确，但异步 URL 只覆盖 `sqlite:///`，没有覆盖 `sqlite:////abs/path`、相对路径、`sqlite+aiosqlite://` 已传入、未来 PostgreSQL/MySQL 的 async driver 映射。建议显式限制“当前仅支持 SQLite”，或使用 SQLAlchemy URL parser 分支处理。 |
| 从 Compose 删除 `DATABASE_URL` | 可行 | 如果短期不准备支持通用 DB URL，删除无效变量并保留 `CONFIG_DIR=/app/config` 是最小风险做法。 |
| 生产强制提供 `SECRET_KEY` | 需调整 | 安全方向正确，但必须先处理现有用户 token 失效预期和部署文档。直接改默认值会让未配置环境变量的部署重启后行为变化。 |

### 2. 迁移统一方案

| 方案/问题 | 结论 | 说明 |
| --- | --- | --- |
| `init_db()` 拆成只做 seed | 可行 | 方向正确，且 seed 当前是幂等查询后插入。删除 `create_all()` 后，前提是 Alembic 空库迁移能创建所有 seed 依赖表。必须先补一个“空库 alembic upgrade head + seed”测试。 |
| 删除 `create_all()` 后空库首次启动 seed | 需调整 | 如果 Alembic 链完整，seed 可正常写入；但当前 `init_db()` 导入的模型多于 Alembic env 中导入的模型，需核对是否所有表都有迁移覆盖。另外 seed 依赖默认任务、模板、关键词、通知表；任何迁移遗漏都会变成启动失败，这正是要通过测试暴露的问题。 |
| 删除 Docker shell 层 `alembic upgrade head` | 可行 | 只保留 lifespan 迁移入口更清晰。但当前 `run_alembic_migrations()` 在开发失败时继续启动；Docker 生产需要确保 `DEV=False` 或迁移失败时强制退出，否则删除 shell 层会降低失败可见性。 |
| 删除生产 schema 快照自动初始化路径 | 需调整 | 新部署应走 Alembic；但已有基于快照初始化、`alembic_version=9aea25308aff` 的数据库不能简单假设与迁移 head 等价。删除自动路径前需要 baseline/校验脚本。 |
| Alembic baseline 迁移处理已有数据库 | 需调整 | 需要区分三类库：空库、已有表但无 `alembic_version` 的旧库、已有 `alembic_version=9aea25308aff` 的快照库。对第二类应检测 schema 后 `alembic stamp` 到合适版本或提供一次性迁移；对第三类应校验 schema 与 head 差异，不能盲目升级。 |
| `production_complete_schema.sql` 仅作为灾备材料 | 需调整 | 可以从自动启动路径移除，但不建议立即删除文件。保留到至少一个版本周期，并在文档中说明不再作为 schema 来源。 |

### 3. 白名单任务注册表

| 方案/问题 | 结论 | 说明 |
| --- | --- | --- |
| 白名单任务注册表总体方案 | 可行 | 这是当前业务形态下最合适的默认安全方案：把用户输入从“代码”收敛为“任务类型 + 参数”。 |
| 现有内置任务覆盖范围 | 需调整 | 默认任务有 8 个 Python 内部类：缓存下载器同步、Tracker 消息记录、下载器路径扫描、标签同步、种子 Tracker 状态判断、种子信息同步、Tracker 状态同步、Tracker 汇报轮询。执行器另有内置类型 5 清理回收站、类型 6 审计日志导出，并有内部固定 job：分时段限速同步、版本检查。报告只举了部分例子，注册表需要覆盖这些现有路径。 |
| 是否覆盖当前用户使用场景 | 需调整 | 如果用户已经使用 Shell/CMD/PowerShell/Python 自定义脚本，白名单不能无损覆盖。需要先统计线上 `cron_task.task_type in (0,1,2,3)` 和 `task_type=4` 但 `executor` 不是允许类路径的记录。 |
| 旧任务数据迁移 | 需调整 | 不能只把 `executor` 改成 JSON 参数。应新增字段或兼容字段，例如 `task_kind`、`params_json`、`legacy_executor`、`is_legacy`、`migration_status`，保留旧数据只读/禁用，以便用户导出和手工迁移。 |
| `cron_task` 表结构变更 | 需调整 | 当前表包含 `task_code` unique、`task_type` int、`executor` text。建议新增注册表字段，不建议立刻复用 `executor` 语义，否则回滚和兼容困难。`task_type_name`、API 响应、前端类型配置也要同步。 |
| 前端表单改造 | 需调整 | 当前 API 仍暴露脚本类型 0-4 和 `executor` 文本；前端需要从代码编辑器改为任务类型选择、动态参数表单、参数 schema 校验、旧任务只读提示。工作量中等，不是纯后端改造。 |
| “短期禁用自定义脚本任务” | 需调整 | 安全上合理，但需要兼容策略：已有任务默认禁用会改变用户自动化行为，应提供版本公告、导出入口、一次性迁移报告和管理员确认开关。 |

### 4. 受限执行与容器隔离方案

| 方案/问题 | 结论 | 说明 |
| --- | --- | --- |
| 方案 B：受限 Python 执行 | 需调整 | 只能作为误操作防护，不能作为安全边界。报告对此判断准确。若继续当前进程内 `exec()`，结论应更明确地标为不可用于生产安全隔离。 |
| 方案 C：容器级隔离 | 可行 | 技术上可行，但复杂度高。关键风险是不能让 Web 后端直接持有宿主 Docker socket；需要独立 runner/worker 或受控队列。Windows/PyInstaller 环境不一定具备 Docker，必须作为可选能力。 |

## 三、遗漏问题检查

1. 认证体系也存在“双轨/多轨”问题。部分接口使用 `app.auth.dependencies.get_current_user` / `verify_token_dependency`，部分接口手写读取 `X-Access-Token` 并调用 `utils.verify_access_token()`。Header 大小写、Cookie/Bearer 支持、返回格式和权限信息不一致。

2. JWT 库也有双轨。`auth/utils.py` 使用 `jwt` 包，`auth/dependencies.py` 和旧 `api/router.py` 使用 `jose.jwt`。这会增加算法参数、异常类型、payload 处理差异。

3. `auth/utils.py` 同时使用 JWT `SECRET_KEY` 和 YAML 中的 `login_status_secret`，且读取失败时回退硬编码 `[REDACTED-SECRET]`。报告提到 YAML 密钥边界不清，但没有把硬编码 fallback 作为安全风险展开。

4. 日志配置存在分散入口。`main.py` 使用 `logging.basicConfig(..., force=True)`，部分工具脚本也各自 `basicConfig`。这会影响库日志、Docker 日志、PyInstaller 日志的一致性，属于报告未覆盖的运行时双轨。

5. 定时任务有非 cron 的后台执行路径。`startup/lifecycle.py` 创建下载器加载、仪表盘统计、版本检查、版本通知后台任务；部分 API 也使用 `asyncio.create_task` 或 FastAPI `BackgroundTasks`。这些不是任意代码执行，但属于调度/生命周期治理范围，应纳入“定时任务隔离”之外的后台任务审计。

6. `validation_service.py` 会基于用户提交内容触发 `bash -n` 和 PowerShell 语法检查。虽然不是执行脚本本体，但仍是外部进程调用，需要超时、路径、可用性和平台兼容控制。

7. WebSocket 入口存在明显残留问题。`websocket_main.py` 导入 `app.factory.wsapp`，但 `factory.py` 当前只定义 `app`，没有 `wsapp`。这说明 WebSocket 服务很可能不可启动，且与主 FastAPI app 的生命周期、认证、配置没有统一。

8. `cron_task` 类型枚举语义不一致。`default_scheduled_tasks.py` 把 `TASK_TYPE_PYTHON = 4` 注释为 Python 脚本任务，而模型和执行器把 4 解释为 Python 内部类；API 配置也把 4 展示为 Python 内部类。这会影响迁移脚本和前端表单理解。

9. 执行器定义了 `timeout_seconds`、`max_retry_count`、`retry_interval` 字段，但脚本执行路径没有实际使用这些字段进行超时和重试控制。报告指出无资源限制，但没有点出“字段存在但语义未生效”的产品风险。

10. CORS 默认 `ALLOWED_HOSTS=["*"]` 且 `allow_credentials=True`，这在浏览器安全模型下通常不是可接受生产配置。报告没有覆盖。

11. 默认管理员账号 `admin/admin` 在 `init_db()` 自动创建。报告重点在迁移和任务执行，未覆盖首次启动凭据风险。

## 四、风险评估

| 风险项 | 评估 |
| --- | --- |
| 向后兼容性 | 报告的路线方向正确，但兼容性描述不足。配置合并会影响 token 时长和密钥；任务白名单会影响现有脚本任务；删除 schema 快照会影响直接运行/PyInstaller 路径。 |
| 数据迁移风险 | 中到高。`cron_task` 旧任务、`alembic_version` 状态、已有数据库是否从生产快照初始化、默认 seed 数据幂等性都需要迁移前审计。 |
| Docker 部署风险 | 中。删除 shell 层 Alembic 前必须确保 lifespan 迁移失败能让容器失败退出；同时需要明确 `DEV`、`CONFIG_DIR`、`DATABASE_PATH/DATABASE_URL` 的生产语义。 |
| PyInstaller / 直接运行风险 | 高。当前 `python app/main.py` 走独立初始化路径，且硬编码 `backend/config/app.db`。删除快照初始化前，需要决定是否仍支持该入口。 |
| Windows 风险 | 中。CMD/PowerShell 任务和语法校验依赖 Windows 命令；Linux Docker 下 PowerShell 可能不存在。方案 C 的 `resource`、seccomp、AppArmor 也不是 Windows 可用能力。 |
| 安全回滚风险 | 中。直接禁用旧脚本任务能止血，但可能中断用户自动化。应提供只读保留、导出、手工确认和审计报告。 |

## 五、整体评价

报告的主结论基本成立：配置系统确实双轨，`DATABASE_URL` 确实是失效配置；数据库初始化确实同时存在 Alembic、`create_all()` 和生产 schema 快照；定时任务系统确实允许高权限代码执行，不能称为安全沙箱。

报告最需要加强的是落地迁移细节。当前方案在方向上正确，但对已有数据库、已有自定义任务、PyInstaller/直接运行入口、Docker 生产失败策略和前端迁移成本考虑不足。建议把修复路线从“删除/替换”改成“审计 -> 兼容层 -> 迁移工具 -> 默认关闭旧能力 -> 最终删除”的版本化过程。

## 六、改进建议

1. 先新增诊断脚本或管理命令，输出当前配置来源、数据库路径、`DATABASE_URL` 是否被忽略、Alembic 当前版本、cron 任务类型分布、旧脚本任务清单。

2. 配置合并先做 `app/config.py` 转发层，并新增测试覆盖 token 创建/校验使用同一 `SECRET_KEY` 和过期时间；随后再替换 import。

3. 数据库迁移先补“空 SQLite 库 `alembic upgrade head` + seed 初始化”测试，再移除 `create_all()`。对已有无版本库和快照库提供 baseline/stamp 策略。

4. Docker 只保留一个迁移入口，但要保证生产迁移失败会终止启动。建议显式设置和文档化 `DEV=False` 的生产行为。

5. 定时任务先禁止新建/更新脚本类型任务，已有脚本任务标记为 legacy 并保留只读和导出；注册表覆盖现有 8 个默认内部类、清理任务、审计导出、分时段限速同步等实际内置任务。

6. WebSocket 入口应单独清理：要么删除残留 `websocket_main.py`，要么补齐 `wsapp`、认证和生命周期集成。

7. 将认证依赖统一为一个 FastAPI dependency，明确 Header/Cookie/Bearer 支持范围和角色权限模型；定时任务管理接口应要求管理员权限。

