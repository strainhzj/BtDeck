# BtDeck 架构深度分析与修复方案

本文基于当前代码静态分析，覆盖两个关键问题：

1. 配置系统、数据库迁移、旧路由文件的“双轨”问题。
2. 定时任务代码执行的隔离与收敛方案。

## 一、配置系统双轨

### 现状

项目存在两个配置入口：

- `backend/app/config.py`
- `backend/app/core/config.py`

`app/config.py` 是轻量配置，仅包含认证和数据库名称相关字段：

```python
PROJECT_NAME = "btdeck"
DATABASE_NAME = "app.db"
SECRET_KEY = os.getenv("SECRET_KEY", "YM4nwx3QBbZ227i5itqf")
ACCESS_TOKEN_EXPIRE_MINUTES = 600
ALGORITHM = "HS256"
```

`app/core/config.py` 是主配置，除认证字段外，还包含网络、运行模式、目录、数据库路径、YAML 路径等运行时配置：

```python
API_V1_STR = "/api/v1"
HOST = "0.0.0.0"
PORT = 5001
DEV = True
DB_ECHO = True
CONFIG_DIR = None
DATABASE_NAME = "app.db"
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-for-jwt")
ACCESS_TOKEN_EXPIRE_MINUTES = 30
DATABASE_PATH = CONFIG_PATH / "app.db"
YAML_PATH = CONFIG_PATH / "config.yaml"
```

引用分布如下：

| 配置入口 | 主要引用 |
| --- | --- |
| `app.config.settings` | `app/api/endpoints/login.py`, `app/api/router.py`, `app/auth/utils.py`, `app/auth/security.py`, `app/auth/dependencies.py`, `backend/tests/auth/test_auth_edge_cases.py` |
| `app.core.config.settings` | `app/database.py`, `app/main.py`, `app/factory.py`, `app/startup/routers_initializer.py`, `app/core/migration.py`, `app/yamlConfig.py`, `app/utils/encryption.py`, `app/websocket_main.py`, `app/migrations/database_migrator.py`, `app/api/endpoints/torrents_async.py`, `app/services/seed_transfer_service.py`, `app/downloader/qbittorrent.py` |

`docker-compose.yml` 和 `backend/docker-compose.yml` 都设置了：

```yaml
DATABASE_URL=sqlite:///data/app.db
```

但代码没有消费 `DATABASE_URL`。实际消费路径是：

- `app/database.py` 使用 `settings.DATABASE_PATH` 构造同步和异步 SQLite URL。
- `backend/alembic/env.py` 只读取 `DATABASE_PATH` 环境变量；没有读取 `DATABASE_URL`。
- `app/core/config.py` 通过 `CONFIG_DIR` 计算 `DATABASE_PATH`，Dockerfile 中设置 `CONFIG_DIR=/app/config`，因此 Docker 实际使用 `/app/config/app.db`。

结论：Compose 中的 `DATABASE_URL=sqlite:///data/app.db` 当前是失效配置，容易误导运维。

### 冲突默认值

| 字段 | `app/config.py` | `app/core/config.py` | 风险 |
| --- | --- | --- | --- |
| `SECRET_KEY` | `YM4nwx3QBbZ227i5itqf` | `your-secret-key-for-jwt` | 认证工具链引用两套配置，默认 JWT 密钥可能不一致 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `600` | `30` | token 有效期在不同模块语义不一致 |
| `DATABASE_NAME` | `app.db` | `app.db` | 值一致，但 `app/config.py` 没有路径语义 |
| `DATABASE_PATH` | 不存在 | `CONFIG_PATH / "app.db"` | 旧配置无法表达 Docker/PyInstaller/自定义配置目录 |
| `CONFIG_DIR` | 不存在 | 可由环境变量覆盖 | 旧配置无法参与运行时目录决策 |
| `.env` 加载 | 显式 `load_dotenv()` + `env_file` | 仅 `env_file` | 环境变量加载行为不完全一致 |

另外，`app/core/config.py` 中 `TORRENTS_PATH` 属性递归访问自身：

```python
@property
def TORRENTS_PATH(self):
    if self.TORRENTS_PATH:
        return Path(self.TORRENTS_PATH)
```

这不是本次主问题，但说明主配置类也需要整理。

### 问题

1. 认证模块分裂：`auth/utils.py` 同时引入 `app.config.settings` 和 `app.core.config.settings`，JWT 生成、JWT 校验、YAML 安全密钥读取之间边界不清。
2. Docker 配置误导：`DATABASE_URL` 看似控制数据库路径，实际不生效。
3. 默认安全值不一致：两个默认 `SECRET_KEY` 都是硬编码值，其中 `app/core/config.py` 的默认值还是模板文案。
4. 路径语义分裂：数据库、YAML、日志、cookies 等路径只在 `core.config` 中完整表达。

### 影响

- 在不同入口启动时，认证 token 有效期和密钥来源可能出现非预期差异。
- 运维人员修改 `DATABASE_URL` 不会改变实际数据库位置，Docker 数据可能仍写入 `/app/config/app.db`。
- 测试需要同时 patch 两套 settings，增加测试脆弱性。
- 后续增加配置项时容易继续分裂。

### 方案

保留 `app/core/config.py`，删除 `app/config.py` 的独立配置定义。

迁移步骤：

1. 在 `app/config.py` 先改为兼容转发层：

```python
from app.core.config import Settings, settings

__all__ = ["Settings", "settings"]
```

2. 将生产代码中的 `from app.config import settings` 逐步替换为 `from app.core.config import settings`。
3. 统一认证配置字段，仅保留 `core.config.Settings.SECRET_KEY`、`ACCESS_TOKEN_EXPIRE_MINUTES`、`ALGORITHM`。
4. 引入显式数据库 URL 规则，二选一：

```python
DATABASE_URL: Optional[str] = None

@property
def SQLALCHEMY_DATABASE_URL(self) -> str:
    if self.DATABASE_URL:
        return self.DATABASE_URL
    return f"sqlite:///{self.DATABASE_PATH}"
```

异步 URL 不应简单字符串替换所有数据库类型，SQLite 可先专项处理：

```python
@property
def ASYNC_SQLALCHEMY_DATABASE_URL(self) -> str:
    if self.DATABASE_URL and self.DATABASE_URL.startswith("sqlite:///"):
        return self.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return f"sqlite+aiosqlite:///{self.DATABASE_PATH}"
```

5. Docker Compose 要么改为实际生效的：

```yaml
CONFIG_DIR=/app/config
```

要么让代码正式支持 `DATABASE_URL`，然后保留当前 Compose 写法。

6. 一到两个版本后删除 `app/config.py`，同时更新测试 patch 路径。

### 推荐

推荐采用“保留 `app/core/config.py`，`app/config.py` 先转发后删除”的低风险迁移。`DATABASE_URL` 应正式纳入 `core.config`，否则应从 Compose 删除，避免虚假配置。

安全默认值建议改为强约束：生产环境必须通过环境变量提供 `SECRET_KEY`，开发环境可自动生成但打印警告。

## 二、数据库迁移双轨

### 现状

当前存在三类 schema 初始化/迁移行为：

1. Alembic 迁移：
   - `app/core/migration.py::run_alembic_migrations()` 通过 `subprocess.run(["alembic", "upgrade", "head"])` 执行。
   - `app/startup/lifecycle.py` 在 FastAPI lifespan 启动时调用。
   - `backend/btdeck_startup.sh` 在 Docker 启动 uvicorn 前也调用 `alembic upgrade head`。
   - `app/main.py` 的 `__main__` 路径也可能调用。

2. SQLAlchemy `create_all()`：
   - `app/database.py::init_db()` 中无条件执行 `Base.metadata.create_all(bind=engine)`。
   - `init_db()` 还负责创建默认 admin、默认配置、默认模板、默认定时任务、默认关键词、欢迎通知。

3. 生产 schema 快照初始化：
   - `app/main.py` 的 `__main__` 分支调用 `ensure_database_initialized(db_path)`。
   - `app/core/init_schema_from_production.py` 读取 `backend/config/production_complete_schema.sql`，执行完整 SQL，并手动写入 `alembic_version = 9aea25308aff`。

关键调用点：

| 调用点 | 行为 |
| --- | --- |
| `backend/btdeck_startup.sh` | `python -c init_config_file` 后执行 `alembic upgrade head`，再启动 `uvicorn app.main:app` |
| `app/startup/lifecycle.py` | FastAPI lifespan 中再次执行 `run_alembic_migrations()`，然后 `init_db()` |
| `app/main.py::__main__` | 直接运行 `python app/main.py` 时执行 config 初始化、生产 schema 初始化或 Alembic、`init_db()`、`initialQb()`、`Server.run()` |
| `app/database.py::init_db()` | `create_all()` + 初始数据 seed |
| `backend/alembic/env.py` | 使用 `DATABASE_PATH` 环境变量或 `settings.DATABASE_PATH`，不使用 `DATABASE_URL` |

### 不同启动路径

#### 开发环境：`uvicorn app.main:app`

流程：

1. import `app.main`，创建 `app.factory.app`。
2. FastAPI lifespan 启动。
3. `init_config_file()`。
4. `run_alembic_migrations()`。
5. `init_db()`。
6. `Base.metadata.create_all()` 兜底创建缺失表。
7. seed 默认数据。
8. 注册路由、启动定时任务。

特点：不会进入 `app/main.py::__main__` 的生产 schema 初始化分支。

#### Docker：`btdeck_startup.sh`

流程：

1. `python -c "from app.database import init_config_file; init_config_file();"`
2. shell 层执行 `alembic upgrade head`。
3. `uvicorn app.main:app`。
4. FastAPI lifespan 再次执行 `run_alembic_migrations()`。
5. `init_db()` 再执行 `create_all()` 和 seed。

特点：Alembic 至少执行两次。虽然 Alembic 本身通常幂等，但增加启动时间和失败点。`DATABASE_URL` 不生效，实际数据库路径由 `CONFIG_DIR=/app/config` 决定。

#### 直接运行或 PyInstaller 类路径：`python app/main.py`

流程：

1. 进入 `__main__`。
2. `init_config_file()`。
3. `yaml.reload()`。
4. 构造 `db_path = Path(__file__).parent.parent / 'config' / settings.DATABASE_NAME`。
5. `ensure_database_initialized(db_path)`。
6. 当前实现中 `ensure_database_initialized()` 对“已存在且版本正确”和“刚初始化成功”都返回 `True`，导致 `main.py` 的 `else: run_alembic_migrations()` 基本不可达。
7. `init_db()` 执行 `create_all()` 和 seed。
8. 启动内置 `Server.run()`。

特点：`main.py` 使用硬编码 `backend/config/app.db` 风格路径，没有使用 `settings.DATABASE_PATH`。如果 `CONFIG_DIR` 指向其他目录，生产 schema 初始化检查和真实数据库连接可能指向两个不同文件。

### 当前迁移流程图

文字流程如下：

```text
Docker 启动
  -> btdeck_startup.sh
    -> init_config_file()
    -> alembic upgrade head
    -> uvicorn app.main:app
      -> FastAPI lifespan
        -> init_config_file()
        -> run_alembic_migrations()
        -> init_db()
          -> Base.metadata.create_all()
          -> seed admin/config/templates/tasks/keywords/notifications

开发 uvicorn 启动
  -> uvicorn app.main:app
    -> FastAPI lifespan
      -> init_config_file()
      -> run_alembic_migrations()
      -> init_db()
        -> Base.metadata.create_all()
        -> seed data

直接 python app/main.py
  -> __main__
    -> init_config_file()
    -> ensure_database_initialized(hardcoded backend/config/app.db)
      -> production_complete_schema.sql
      -> write alembic_version=9aea25308aff
    -> init_db()
      -> Base.metadata.create_all()
      -> seed data
    -> Server.run()
```

### 问题

1. Alembic 和 `create_all()` 双轨：`create_all()` 会掩盖缺失迁移，导致开发环境“能跑”，生产迁移脚本却不完整。
2. Alembic 和生产 schema 快照双轨：新库可能跳过历史迁移链，直接写入固定版本号，破坏 Alembic 作为唯一 schema 来源的原则。
3. Docker 重复迁移：启动脚本和 lifespan 都跑迁移。
4. 路径不一致：`main.py` 的初始化路径不等于 `settings.DATABASE_PATH`。
5. `ensure_database_initialized()` 返回值语义错误：函数名是“确保初始化”，调用方却把 `True` 当成“刚从生产 schema 初始化，因此跳过 Alembic”。

### 影响

- 迁移遗漏不容易暴露，直到真实生产升级才失败。
- 数据库版本状态可能被手工标记为 head，但实际 schema 未必等价。
- Docker 启动链路更复杂，迁移失败排查困难。
- 自定义 `CONFIG_DIR`、PyInstaller、Docker 环境可能读写不同数据库文件。

### 方案

目标是迁移到“纯 Alembic 管理 schema，`init_db()` 只负责 seed 数据”。

#### 阶段 1：拆分 schema 初始化和数据初始化

将 `init_db()` 拆成：

```python
def init_seed_data() -> None:
    create_default_admin()
    create_default_config()
    init_default_templates()
    init_default_scheduled_tasks()
    init_default_tracker_keywords()
    init_default_notifications()
```

`Base.metadata.create_all()` 移出启动流程，只允许测试或临时脚本显式调用。

#### 阶段 2：统一启动迁移入口

新增统一函数：

```python
def migrate_database() -> None:
    run_alembic_migrations_or_raise()
```

只在 FastAPI lifespan 中调用。Docker 启动脚本删除 `alembic upgrade head`，只负责设置环境和启动服务。

#### 阶段 3：废弃生产 schema 快照初始化

删除 `main.py` 对 `ensure_database_initialized()` 的调用。保留 `production_complete_schema.sql` 仅作为灾备文档或手工恢复材料，不进入自动启动路径。

如果担心历史迁移链有问题，应在 Alembic 中创建 baseline 迁移，而不是运行时执行 SQL 快照：

```text
空库 -> alembic upgrade head -> 完整 schema
旧库 -> alembic upgrade head -> 增量升级
```

#### 阶段 4：修正 Alembic 数据库 URL 来源

`backend/alembic/env.py` 与 `app/database.py` 使用同一个配置属性：

```python
from app.core.config import settings
config.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URL)
```

如果保留 `DATABASE_URL`，则 Alembic 和应用必须都消费它。

#### 阶段 5：增加启动前检查

在 CI 和启动时增加：

```bash
alembic heads
alembic current
```

并在测试中验证空 SQLite 库可以通过 `alembic upgrade head` 创建完整 schema。

### 推荐

推荐迁移顺序：

1. 先让 Docker、lifespan、Alembic 使用同一数据库路径。
2. 删除 Docker shell 中的重复 `alembic upgrade head`，保留 lifespan 作为唯一自动迁移入口。
3. 从 `init_db()` 删除 `create_all()`，改名为 `init_seed_data()`。
4. 删除启动时生产 schema 快照初始化。
5. 用一次空库迁移测试兜底，确保 Alembic 链完整。

## 三、残留路由文件

### 现状

`backend/app/api/router.py` 内容显示它是旧认证路由文件：

- 注释头仍写 `# app/auth/router.py`。
- 使用 `APIRouter(prefix="/user", tags=["authentication"])`。
- 引入 `debugpy.adapter.access_token`。
- 引入 `app.config.settings`。
- `user_update()` 中使用硬编码 JWT key `YM4nwx3QBbZ227i5itqf`。
- 存在危险 SQL 拼接：`"update users set two_factor_secret=0 where username=" + user.username`。

当前主路由是 `backend/app/api/api.py`：

- 统一创建 `api_router = APIRouter()`。
- include `login`, `downloader`, `cuser`, `torrents`, `tracker`, `tasks`, `cron_tasks` 等业务端点。
- 由 `app/startup/routers_initializer.py` 挂载到 `settings.API_V1_STR`。

引用搜索结果显示：

```text
backend/app/startup/routers_initializer.py:
  # from app.api import router
  # app.include_router(router.router, prefix="/api/public")
```

没有生产代码实际引用 `app.api.router`。

### 问题

`api/router.py` 是未挂载旧文件，但包含过期认证逻辑、硬编码密钥和 SQL 注入式写法。虽然当前不可达，但会误导维护者，也可能在未来被误挂载。

### 影响

- 新人可能误以为这是认证路由入口。
- 自动扫描会报出高危问题。
- 如果未来取消注释挂载，可能引入认证绕过或 SQL 注入风险。

### 方案

删除 `backend/app/api/router.py`。

删除前检查：

```bash
rg -n "app\\.api\\.router|from app\\.api import router|from app\\.api\\.router" backend/app backend/tests
```

删除后更新 `routers_initializer.py` 中的旧注释，避免继续指向已删除文件。

### 推荐

删除风险低。当前只有注释引用，没有实际 import。建议作为配置系统合并的同一批清理提交完成。

## 四、定时任务代码执行隔离现状

### 现状

定时任务 API 位于 `backend/app/api/endpoints/cron_tasks.py`。

权限控制方式：

```python
token = req.headers.get("X-Access-Token")
user_info = utils.verify_access_token(token)
```

所有创建、更新、启动、删除、校验接口都调用 `verify_token(request)`，但没有看到角色/权限粒度校验。只要拿到有效 token，就可以创建或修改任务。

任务执行器位于 `backend/app/tasks/cron_executor.py`：

| 任务类型 | 执行方式 | 隔离程度 |
| --- | --- | --- |
| Shell | `asyncio.create_subprocess_shell(script)` | 子进程，但无命令限制、无资源限制 |
| CMD | `cmd /c "{script}"` | 子进程，无限制 |
| PowerShell | `powershell -Command "{script}"` | 子进程，无限制 |
| Python 脚本 | `python -c "{script}"` | 子进程，无限制，且字符串拼接有引号注入风险 |
| Python 内部类 | 动态 `__import__` 或当前进程 `exec()` | 与后端同进程，权限最大 |
| 清理/导出任务 | 内置类 | 相对可控 |

`cron_executor.py` 中的 `exec()` 调用点：

- 异步 Python 代码：`exec(wrapped_code, exec_globals)`，`exec_globals["__builtins__"] = __builtins__`。
- 同步 Python 代码：线程池内 `exec(code, exec_globals)`，同样传入完整 `__builtins__`。

`backend/app/tasks/enhanced_python_executor.py` 提供了一个“安全执行器”，但当前 `cron_executor.py` 没有使用它。即便使用，它也仍然有明显漏洞：

- `safe_modules` 中包含 `os` 和 `sys`。
- `safe_builtins` 禁止了 `open`、`__import__`、`eval`、`exec` 等，但通过已暴露的 `os`、`sys` 仍可访问文件系统、环境变量、进程信息。
- `execute_sync_code()` 在当前进程执行 `exec(code, safe_globals, safe_locals)`。
- 没有 OS 级网络、文件、CPU、内存限制。

### 当前沙箱防护能力评估

| 能力 | 当前状态 |
| --- | --- |
| 访问文件系统 | 可以。Shell/Python 子进程可任意读写后端用户权限范围内文件；内部 `exec` 可通过完整 builtins 或 `os` 访问 |
| 访问网络 | 可以。Shell 可使用系统工具，Python 可 import 网络库或通过 `os.system` 间接执行 |
| 访问敏感模块 | 可以。`cron_executor.py` 使用完整 `__builtins__`；增强执行器也暴露 `os`、`sys` |
| 限制执行时间 | Shell/Python 子进程没有使用 `wait_for` 或 kill；增强执行器只有 async wait_for，sync exec 没有强制中断 |
| 限制 CPU/内存 | 没有 |
| 限制命令 | 没有 |
| 审计 | 有任务日志，但日志依赖执行器返回，恶意代码可逃避或污染 |

### 问题

这不是“沙箱”，而是“管理员可配置的远程代码执行”。如果这是设计目标，必须明确标为高危运维能力；如果不是设计目标，需要尽快收敛。

### 影响

管理员 token 泄露后，攻击者可以：

- 创建 Shell 任务读取 `/app/config/config.yaml`、数据库、日志、备份。
- 读取环境变量中的密钥、代理、第三方 token。
- 修改 SQLite 数据库，创建后门用户或关闭审计。
- 发起内网探测和 SSRF。
- 下载并执行恶意程序。
- 删除数据卷或备份。
- 在当前进程 `exec()` 路径中直接访问 Python 内存对象、数据库会话、应用模块。

Docker 下虽使用非 root `appuser`，但容器内 `/app/config`、`/app/logs`、`/app/data` 等挂载目录通常可写。宿主机影响范围取决于 volume 挂载权限和 Docker 隔离配置。

### 推荐

短期立刻禁用自定义 Shell/CMD/PowerShell/Python 文本任务，只保留内置任务类型。中期实现白名单任务注册表。长期如必须支持用户代码，使用进程级或容器级隔离，不要在后端主进程中执行用户代码。

## 五、隔离方案 A：白名单任务注册表

### 现状

项目已经有部分内置任务类型，如清理回收站、审计日志导出、仪表盘统计、版本检查、分时段限速同步。这些任务可以改造成注册表。

### 问题

当前用户提交的是“代码”，而不是“任务意图”。代码执行面过大。

### 影响

只要任务系统开放给管理员，管理员 token 就等价于系统命令执行权限。

### 方案

定义任务类型枚举、参数 schema 和函数注册表，用户只能选择任务类型和参数。

```python
from enum import StrEnum
from typing import Any, Awaitable, Callable
from pydantic import BaseModel, Field

class TaskKind(StrEnum):
    CLEANUP_RECYCLE_BIN = "cleanup_recycle_bin"
    AUDIT_LOG_EXPORT = "audit_log_export"
    SPEED_SCHEDULE_SYNC = "speed_schedule_sync"

class CleanupParams(BaseModel):
    cleanup_level_3: bool
    cleanup_level_4: bool
    days_threshold: int = Field(ge=1, le=365)

class AuditExportParams(BaseModel):
    days: int = Field(default=7, ge=1, le=90)
    format: str = Field(default="json", pattern="^(json|csv)$")

TaskHandler = Callable[[Any, BaseModel], Awaitable[dict]]

TASK_REGISTRY: dict[TaskKind, tuple[type[BaseModel], TaskHandler]] = {
    TaskKind.CLEANUP_RECYCLE_BIN: (CleanupParams, run_cleanup_recycle_bin),
    TaskKind.AUDIT_LOG_EXPORT: (AuditExportParams, run_audit_export),
}

async def execute_registered_task(kind: str, raw_params: dict, context: Any) -> dict:
    task_kind = TaskKind(kind)
    params_model, handler = TASK_REGISTRY[task_kind]
    params = params_model.model_validate(raw_params)
    return await handler(context, params)
```

数据库层改造：

```text
cron_task.task_type -> registered
cron_task.executor  -> JSON 参数，不再保存代码
cron_task.task_code -> TaskKind
```

API 层禁止保存任意脚本：

```python
class CronTaskCreate(BaseModel):
    task_name: str
    task_code: TaskKind
    params: dict = Field(default_factory=dict)
    cron_plan: str
    enabled: bool = True
```

### 实现复杂度

低到中。

主要是 API、前端表单、旧数据迁移。后端执行模型最简单。

### 安全等级

高。

因为不执行用户代码，攻击面收敛到每个内置任务自身的参数校验和业务权限。

### 性能影响

低。

执行仍在当前应用或后台协程中完成，无额外容器或进程开销。

### 推荐

作为默认方案。BtDeck 的定时任务多数是产品内置运维动作，白名单注册表最符合业务形态。

## 六、隔离方案 B：受限执行环境

### 现状

`enhanced_python_executor.py` 尝试做受限 builtins，但仍暴露 `os`、`sys`，并且在当前进程中 `exec()`。

### 问题

Python 进程内沙箱很难做成强安全边界。它适合降低误操作风险，不适合抵御恶意用户。

### 影响

即使移除 `os` 和 `sys`，仍可能通过对象反射、异常对象、已导入模块、第三方库漏洞等方式逃逸。CPU 和内存也难以在同进程可靠限制。

### 方案

如果短期必须继续支持 Python 代码，应至少做以下限制：

1. AST 静态检查禁止 import、属性双下划线、危险函数名。
2. builtins 白名单。
3. 不提供 `os`、`sys`、`subprocess`、`socket`、`pathlib`、`shutil` 等模块。
4. 通过单独进程执行，使用 `resource` 设置 CPU/内存。
5. 文件访问只能通过受控 API。

示例：

```python
import ast
import builtins

FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "socket", "pathlib", "shutil",
    "ctypes", "inspect", "importlib", "multiprocessing", "threading",
}

SAFE_BUILTINS = {
    "abs": builtins.abs,
    "all": builtins.all,
    "any": builtins.any,
    "bool": builtins.bool,
    "dict": builtins.dict,
    "enumerate": builtins.enumerate,
    "float": builtins.float,
    "int": builtins.int,
    "len": builtins.len,
    "list": builtins.list,
    "max": builtins.max,
    "min": builtins.min,
    "range": builtins.range,
    "round": builtins.round,
    "set": builtins.set,
    "str": builtins.str,
    "sum": builtins.sum,
    "tuple": builtins.tuple,
}

class SandboxValidator(ast.NodeVisitor):
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                raise ValueError(f"禁止导入模块: {alias.name}")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".")[0]
        if root in FORBIDDEN_MODULES:
            raise ValueError(f"禁止导入模块: {node.module}")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            raise ValueError("禁止访问双下划线属性")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in {"eval", "exec", "compile", "open", "__import__", "globals", "locals"}:
            raise ValueError(f"禁止使用函数: {node.id}")

def validate_user_code(code: str) -> ast.AST:
    tree = ast.parse(code, mode="exec")
    SandboxValidator().visit(tree)
    return tree

def execute_restricted(code: str) -> dict:
    tree = validate_user_code(code)
    globals_dict = {
        "__builtins__": SAFE_BUILTINS,
        "result": None,
    }
    locals_dict = {}
    exec(compile(tree, "<cron-task>", "exec"), globals_dict, locals_dict)
    return {"success": True, "result": locals_dict.get("result")}
```

资源限制需要在子进程内设置：

```python
import multiprocessing
import resource

def worker(code: str, queue) -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
    try:
        queue.put(execute_restricted(code))
    except Exception as exc:
        queue.put({"success": False, "error": str(exc)})

def run_with_limits(code: str, timeout: int = 3) -> dict:
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=worker, args=(code, queue))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.kill()
        return {"success": False, "error": "执行超时"}
    return queue.get() if not queue.empty() else {"success": False, "error": "无结果"}
```

文件系统访问不要暴露 `open`，而是暴露业务 API：

```python
class TaskFileStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def read_text(self, relative_path: str) -> str:
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root):
            raise PermissionError("非法路径")
        return path.read_text(encoding="utf-8")
```

### 实现复杂度

中。

要改执行器、API 校验、日志、超时、测试。仍需持续维护禁用列表和逃逸测试。

### 安全等级

中到低。

如果仍在当前进程 `exec()`，安全等级低。只有放到子进程并加资源限制后，才能达到中等。

### 性能影响

低到中。

AST 检查成本低；子进程执行会增加启动开销。

### 推荐

只作为过渡方案。不要承诺“安全沙箱”，文案应明确为“受限脚本执行”。生产默认应关闭。

## 七、隔离方案 C：进程级/容器级隔离

### 现状

Shell、Python 脚本已经是子进程执行，但没有做到隔离：

- 没有传 `timeout`。
- 没有限制 CPU/内存。
- 没有限制 cwd。
- 没有最小环境变量。
- 没有只读文件系统。
- 没有 seccomp/AppArmor 策略。

### 问题

子进程不是安全边界。它默认继承后端用户权限、网络能力、文件系统视图和环境变量。

### 影响

攻击者拿到 token 后，可以稳定获得容器内后端用户权限。如果 Docker volume 映射较宽，可能影响宿主数据。

### 方案

#### C1：本机独立进程 + 最小环境

```python
import asyncio
import os
import tempfile

async def run_python_subprocess_safely(code: str, timeout: int = 5) -> dict:
    with tempfile.TemporaryDirectory(prefix="btdeck-task-") as workdir:
        env = {
            "PYTHONPATH": "",
            "PYTHONNOUSERSITE": "1",
            "TZ": "Asia/Shanghai",
        }
        process = await asyncio.create_subprocess_exec(
            "python",
            "-I",
            "-S",
            "-c",
            code,
            cwd=workdir,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {"success": False, "error": "执行超时"}

        return {
            "success": process.returncode == 0,
            "stdout": stdout.decode("utf-8", "replace"),
            "stderr": stderr.decode("utf-8", "replace"),
            "returncode": process.returncode,
        }
```

Linux 下可在子进程 preexec 中设置 resource：

```python
def limit_resources() -> None:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
```

#### C2：Docker 容器隔离

每次任务在短生命周期容器中执行：

```bash
docker run --rm \
  --network none \
  --cpus 0.25 \
  --memory 128m \
  --pids-limit 64 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --security-opt no-new-privileges:true \
  --cap-drop ALL \
  --user 10001:10001 \
  btdeck-task-runner:latest \
  python /runner/task.py
```

后端侧只把任务代码和参数写入临时输入文件或 stdin，不挂载 `/app/config`、数据库、日志、备份目录。需要输出时只挂载单独的任务输出目录。

#### C3：seccomp/AppArmor

Docker 运行时追加：

```bash
--security-opt seccomp=/etc/btdeck/task-seccomp.json
--security-opt apparmor=btdeck-task-runner
```

seccomp/AppArmor 策略原则：

- 禁止 `mount`、`ptrace`、`clone` 高危 flag、`keyctl`、`bpf`。
- 禁止访问宿主敏感路径。
- 默认 deny，按 Python runner 需要逐步放行。

### 实现复杂度

高。

需要构建 task-runner 镜像、定义输入输出协议、处理日志、超时、并发、镜像升级、Docker socket 权限。尤其不能把宿主 Docker socket 直接暴露给 Web 后端，否则风险会扩大。

### 安全等级

高。

前提是容器配置正确，后端不能把敏感目录挂进去，且 runner 使用无网络、只读文件系统、cap drop、no-new-privileges、seccomp/AppArmor。

### 性能影响

中到高。

短任务容器启动成本明显高于当前进程内执行。可以用常驻 worker 池降低延迟，但实现更复杂。

### 推荐

如果业务必须支持用户自定义代码，推荐 C2/C3。否则不要引入这类复杂度，直接采用方案 A。

## 八、总体修复路线

### 第一阶段：止血

1. 禁止新建和更新 Shell/CMD/PowerShell/Python 文本任务，只允许内置任务类型。
2. 隐藏或下线前端自定义脚本入口。
3. 对现有自定义脚本任务默认禁用，要求用户手工确认迁移。
4. 删除旧 `api/router.py`。
5. 将 `app/config.py` 改为 `app/core/config.py` 的兼容转发。

### 第二阶段：统一架构

1. 任务系统改为白名单注册表。
2. `init_db()` 改名并收敛为 seed 初始化。
3. 删除启动流程中的 `create_all()`。
4. Docker、lifespan、Alembic 使用同一迁移入口和同一数据库 URL 来源。
5. 移除 `production_complete_schema.sql` 的自动初始化路径。

### 第三阶段：增强隔离

1. 如仍需用户脚本，先用方案 B 做过渡，但默认关闭。
2. 对高风险部署提供 Docker runner，使用方案 C。
3. 增加审计：谁创建/修改/启动任务、任务参数 hash、执行输出摘要、失败原因。
4. 增加权限：只有明确的系统管理员角色可管理任务，普通登录 token 不可操作。

## 最终推荐

配置系统：保留 `app/core/config.py`，`app/config.py` 先转发后删除。让 `DATABASE_URL` 要么真正生效，要么从 Compose 移除。

数据库迁移：纯 Alembic 管 schema，`init_db()` 只做 seed。启动路径只保留一个迁移入口，删除生产 schema 快照自动初始化和 `create_all()` 兜底。

旧路由：删除 `backend/app/api/router.py`，风险低。

定时任务：默认采用方案 A 白名单任务注册表。方案 B 只作为短期过渡，方案 C 只在确实需要用户代码时投入。
