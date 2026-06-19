# BtDeck 代码审查与质量评估报告

审查日期：2026-06-19  
审查范围：`README.md`、`CLAUDE.md`、`ROADMAP.md`、`docker-compose.yml`、`backend/`、`frontend/`、部署配置与测试配置。  
审查方式：静态阅读、结构统计、关键路径抽样、API 契约交叉检查、有限命令验证。未修改业务代码。

## 1. 项目概览

BtDeck 是一个统一管理 qBittorrent / Transmission 的全栈 BitTorrent 管理平台。后端采用 FastAPI + SQLAlchemy + SQLite，前端采用 Vue 2 + TypeScript + Element UI + Vuex，部署形态包括 Docker Compose、PyInstaller、Windows / Linux 安装包。

路线图显示当前版本为 v1.0.9，重点是全栈仓库整合与一键部署；后续规划包括查询模板、孤儿文件管理、数据库升级到 PostgreSQL、自动化运维。

### 代码规模与结构

| 区域 | 文件数 | 代码行数 |
|---|---:|---:|
| `backend/` | 267 | 90,060 |
| `frontend/` | 173 | 73,396 |
| 合计 | 440 | 163,456 |

关键模块规模：

| 模块 | 文件数 | 行数 |
|---|---:|---:|
| `backend/app/api/endpoints` | 34 | 23,965 |
| `backend/app/services` | 35 | 16,847 |
| `backend/app/models` | 16 | 2,689 |
| `backend/tests` | 57 | 15,315 |
| `frontend/src/views` | 53 | 28,841 |
| `frontend/src/components` | 18 | 9,863 |
| `frontend/src/api` | 14 | 3,383 |
| `frontend/src/store` | 5 | 848 |

### 部署架构

`docker-compose.yml` 定义了双容器架构：

- `backend`：FastAPI 服务，内部端口 5001，SQLite 数据和日志挂载到 `./data/backend/*`。
- `frontend`：Nginx 静态服务，宿主端口 `${BTDECK_PORT:-8080}`，代理 API 到后端。
- 网络：单独 bridge 网络 `btdeck_network`。
- 健康检查：前端 `/health`，后端 `/docs`。

整体部署方案清晰，适合单机运行；但当前配置仍有安全和可维护性短板，详见后文。

## 2. 总体结论

整体质量评分：**6.1 / 10**

项目已经具备较完整的功能面、模块边界和测试意识，后端服务层、适配器层、迁移、审计、通知、回收站等模块较齐全；前端也有 API 层、Vuex 模块、虚拟滚动、懒加载路由和较完整的业务页面。

主要扣分点集中在：

- 🔴 安全边界不足：默认管理员密码、默认 JWT 密钥、配置文件被跟踪、Python 定时任务可执行任意代码、认证逻辑分散。
- 🟡 架构债务明显：后端存在两套配置系统、残留路由文件、部分超大 endpoint / service；前端存在大量 `any`、模板项目残留、类型契约不够严格。
- 🟡 API 契约不统一：部分分页参数使用 `page_size`，部分使用 `pageSize`；部分接口用业务 `code=401` 而非 HTTP 401；部分错误返回格式混杂。
- 🟡 验证环境不完整：后端缺 `pytest`，前端缺 `vue-cli-service`，无法在当前环境跑全量测试 / lint。

## 3. 后端代码审查

### 3.1 代码结构和模块化

优点：

- API、models、schemas、services、repositories、startup、downloader adapters 分层基本明确。
- 下载器能力、标签、审计、通知、回收站、转移、路径维护等业务模块拆分较细。
- `app.state.store` 下载器连接缓存的设计方向正确，多处服务已复用缓存连接。

问题：

#### 🔴 `app/api/router.py` 是残缺且危险的历史文件

位置：`backend/app/api/router.py:1-71`

该文件内容看起来是旧认证路由残片，并非实际路由聚合器。它包含硬编码 JWT 密钥、错误的 cookie 访问、字符串拼接 SQL，以及未完成的 `verify_2fa` 返回逻辑。实际启动使用的是 `app/api/api.py`，但这个同名近似文件非常容易被后续开发误导。

建议：

- 删除或归档该文件；如果仍需保留，改名为 `legacy_router_unused.py` 并在文件顶部明确禁止导入。
- 在测试中加入“实际路由只来自 `app/api/api.py`”的约束检查。

#### 🟡 Endpoint 文件过大，服务边界不稳定

位置示例：

- `backend/app/api/endpoints/downloader.py` 约 1,700 行以上。
- `backend/app/api/endpoints/downloader_settings.py` 约 1,500 行以上。
- `backend/app/api/endpoints/torrent_sync.py` 超过 1,200 行。

风险：

- API 层混杂参数校验、业务流程、状态转换、连接访问和错误处理。
- 后续变更容易引入重复逻辑和认证遗漏。

建议：

- 将 endpoint 限制为“参数解析 + 认证 + 调用 service + 响应包装”。
- 按业务命令拆 service，例如 `DownloaderCrudService`、`DownloaderStatusService`、`DownloaderPathMappingService`。
- 对超大文件先做无行为变更拆分，再补契约测试。

### 3.2 API 设计规范性

优点：

- 大多数接口使用统一 `CommonResponse { status, msg, code, data }`。
- 部分分页接口已按约束使用 `list / total / pageSize`。
- 多数 Pydantic / Query 参数有范围限制。

问题：

#### 🟡 REST 风格不一致

位置示例：

- `POST /downloader/getList` 与 `GET /downloader/getList` 同名不同语义。
- `POST /cronTasks/add`、`POST /tracker/addTracker`、`POST /tracker/replaceTracker` 等 RPC 风格接口较多。
- `DELETE /torrents/delete`、`DELETE /torrents/delete-with-level` 混合动词和资源路径。

建议：

- 新接口统一使用资源路径：`GET /downloaders`、`POST /downloaders`、`PATCH /downloaders/{id}`。
- 旧接口保留兼容，但标记 deprecated，并在前端逐步迁移。

#### 🟡 HTTP 状态码和业务错误码混用

位置示例：`backend/app/api/endpoints/torrent_crud.py:804-810`、`backend/app/auth/dependencies.py:52-63`

许多接口认证失败时返回 HTTP 200 + `code="401"`。前端拦截器适配了这个行为，但这会削弱 API 的标准性，也会影响代理、监控、自动化测试和 OpenAPI 客户端。

建议：

- 认证失败统一抛 `HTTPException(status_code=401)`，响应体可仍保持 `CommonResponse`。
- 前端保留业务 `code` 兼容，但优先处理 HTTP 401。

#### 🟡 分页字段仍不完全统一

位置示例：

- `tracker_keywords.py`、`tracker_messages.py`、`setting_templates.py` 使用 `page_size` 参数，但返回 `pageSize`。
- 前端 `src/api/tracker.ts` 同时出现 `pageSize` 与 `page_size`。

建议：

- 后端对外统一 `pageSize`，内部可映射为 `page_size`。
- 用契约测试扫描所有分页响应，强制返回 `list / total / pageSize`。

### 3.3 数据库设计

优点：

- 已引入 Alembic，启动时执行迁移。
- 主业务表有不少索引，例如种子 hash、status、downloader_id、tracker_url、通知 is_read 等。
- SQLite 启用了 WAL，改善单机并发读写。

问题：

#### 🔴 迁移体系存在双轨与绕过风险

位置：

- `backend/app/main.py:73-86`
- `backend/app/startup/lifecycle.py:204-219`
- `backend/app/database.py:112-118`

代码中同时存在“从生产 schema 初始化并跳过 Alembic 链”和“常规 Alembic 迁移”，并且 `init_db()` 仍调用 `Base.metadata.create_all()`。这会导致不同环境的 schema 演化路径不一致，违背项目自身的“所有 Schema 变更必须通过 Alembic”约束。

建议：

- 明确唯一迁移入口：启动时只运行 Alembic。
- 首次初始化也用 Alembic baseline，而不是生产 SQL + 跳过迁移。
- `create_all()` 仅允许测试环境使用，生产启动路径禁用。

#### 🟡 配置系统重复，数据库路径与环境变量语义混乱

位置：

- `backend/app/config.py`
- `backend/app/core/config.py`
- `docker-compose.yml` 中设置 `DATABASE_URL=sqlite:///data/app.db`
- 实际代码使用 `settings.DATABASE_PATH`

风险：

- Docker 配置中的 `DATABASE_URL` 可能没有被实际消费。
- `app.config.settings.SECRET_KEY` 与 `app.core.config.settings.SECRET_KEY` 默认值不同。

建议：

- 合并为单一配置入口，例如只保留 `app/core/config.py`。
- 明确支持 `DATABASE_URL` 或删除 compose 中无效变量。
- 为配置加载写单元测试，覆盖 Docker、开发、本地打包三种场景。

### 3.4 安全性

#### 🔴 默认管理员账号密码为 `admin/admin`

位置：`backend/app/database.py:149-162`

首次初始化自动创建默认管理员，且控制台打印默认密码。这是生产部署的高危入口。

建议：

- 首次启动强制要求环境变量提供初始管理员密码，或生成一次性随机密码并只打印一次。
- 首次登录强制修改密码。
- 提供 `BTDECK_INIT_ADMIN_PASSWORD` / `BTDECK_INIT_ADMIN_USER`。

#### 🔴 默认 JWT 密钥和配置文件跟踪风险

位置：

- `backend/app/config.py:26`
- `backend/app/core/config.py:69`
- `backend/.env.example`
- `backend/config/config.yaml` 已被 Git 跟踪

`.gitignore` 已声明忽略 `config/config.yaml`，但当前仓库仍跟踪该文件。报告中不展开具体密钥值，但这属于敏感配置泄露风险。

建议：

- 从版本库移除 `backend/config/config.yaml`，仅保留 `config.yaml.example`。
- 生产启动时若检测到默认 `SECRET_KEY`，直接拒绝启动。
- 统一密钥来源，避免 YAML secret、JWT secret、SM4 secret 各自分散。

#### 🔴 定时任务可执行任意 Python 代码

位置：

- `backend/app/tasks/cron_executor.py:451-522`
- `backend/app/tasks/enhanced_python_executor.py:181-285`
- `backend/app/api/endpoints/cron_tasks.py:321-364`

定时任务支持 `exec()` 执行用户提供代码，且部分路径使用完整 `__builtins__`。这相当于拥有后端进程权限的远程代码执行能力。如果认证被绕过或管理员账号泄露，攻击者可读取配置、访问文件系统、连接内网。

建议：

- 生产环境默认禁用任意代码执行型任务。
- 改为白名单任务注册表：用户只能选择预定义任务类和参数。
- 如必须支持脚本，放入隔离进程 / 容器，限制文件系统、网络、CPU、内存和超时。
- 定时任务创建、更新、执行必须有独立权限、审计日志和二次确认。

#### 🟡 密码“加密”不是密码哈希

位置：`backend/app/auth/security.py:20-45`

当前密码用 AES ECB 模式可逆加密，函数命名为 `get_password_hash` 但不是哈希。数据库泄露时，攻击者拿到密钥即可还原所有密码。

建议：

- 用户密码使用 Argon2id / bcrypt / PBKDF2，不可逆哈希。
- 下载器密码等必须可还原的凭据再使用 KMS / Fernet / AES-GCM 等认证加密。
- 禁止 ECB，改用带随机 nonce/iv 的 AEAD 模式。

#### 🟡 认证逻辑分散且校验结果有遗漏

位置示例：

- `backend/app/auth/dependencies.py`
- `backend/app/api/endpoints/cuser.py:115-123`
- 多个 endpoint 手动读取 `x-access-token`

部分接口调用 `utils.verify_access_token(token)` 后未检查返回值是否为 `None`，只依赖异常。但该函数设计上验证失败返回 `None`，不一定抛异常。

建议：

- 所有受保护接口统一使用 `Depends(get_current_user)`。
- 删除每个 endpoint 内手写 token 解析。
- 增加测试：无 token、过期 token、verify_secret 不匹配时所有写接口必须拒绝。

#### 🟡 CORS 默认 `*`

位置：`backend/app/core/config.py:65`、`backend/app/factory.py:41-48`

建议：

- 生产环境只允许配置中的可信域名。
- 如果 `allow_credentials=True`，不要使用通配来源。

### 3.5 性能考虑

优点：

- SQLite WAL 模式已开启。
- 下载器状态使用 `app.state.store` 缓存。
- 有 `torrent_speed` 线程池、实时速度缓存、dashboard 后台任务等优化。
- 前端有虚拟滚动组件和懒加载路由。

问题：

#### 🟡 SQLite + NullPool 在写多场景下扩展有限

位置：`backend/app/database.py:15-45`

项目路线图规划 v1.0.8 升级 PostgreSQL，这一方向合理。当前功能包含同步种子、审计日志、通知、定时任务、tracker 消息等写入场景，SQLite 锁竞争仍是风险。

建议：

- 短期：统一事务边界，批量写入分批提交，避免长事务。
- 中期：引入 PostgreSQL，使用连接池和索引迁移验证。
- 对种子列表、tracker 状态列表建立查询 explain 基准。

#### 🟡 后台任务与 API 进程耦合

位置：`backend/app/startup/lifecycle.py:235-265`

定时任务、下载器加载、dashboard 刷新、版本检查都在 API 进程生命周期内启动。单进程部署可运行，但重启、阻塞和任务异常会影响 API。

建议：

- 中长期拆出 worker 进程。
- 对后台任务加健康状态、错误计数和熔断。

### 3.6 错误处理与日志

优点：

- 多数模块已使用 `logger`。
- 有日志脱敏工具测试。

问题：

#### 🟡 错误消息直接暴露异常细节

位置示例：`backend/app/api/endpoints/login.py:83-88`、多处 `msg=f"...{str(e)}"`

风险：

- 可能泄露路径、SQL、内部状态或第三方客户端错误。

建议：

- 对外返回通用错误码和用户可理解信息。
- 详细异常只写服务端日志，并附 request_id。

#### 🟢 日志风格不统一

位置：`backend/app/startup/lifecycle.py` 多处 `print`

建议：

- 统一使用结构化 logger。
- 启动阶段也输出到同一日志系统，便于 Docker / systemd 收集。

### 3.7 测试覆盖情况

优点：

- 后端测试文件 57 个，覆盖 auth、API、core、models、services、repositories、tasks、utils。
- 有认证保护扩展测试和若干回归测试，质量意识较好。

问题：

#### 🟡 当前环境无法运行后端测试

执行 `python3 -m pytest -q` 失败：`No module named pytest`。`python` 命令也不存在。

建议：

- 提供可复现测试环境：`make test` 或 `uv run pytest` / `pip install -r requirements.txt`。
- CI 中固定跑 `pytest`、`mypy`、`black --check`、`flake8`。

## 4. 前端代码审查

### 4.1 Vue 组件设计和复用性

优点：

- 业务页面按 `views` 拆分，通用组件放在 `components`。
- 有 `BatchButton`、`Pagination`、`VirtualScrollList`、任务编辑器等复用组件。
- 路由使用动态 import，具备懒加载。

问题：

#### 🟡 项目混合使用 Class Component 与 Options API 约束不一致

位置示例：

- `frontend/src/App.vue`
- `frontend/src/router.ts`
- 多个 `.vue` 使用 `vue-property-decorator`

前端 AGENTS 约束要求 Vue 2 Options API，禁止 Vue 3 Composition API 和 `<script setup>`。当前虽然不是 Vue 3，但大量使用 class-style component，与“Options API”约束不完全一致。

建议：

- 明确项目规范：要么接受 Vue 2 class-style，要么逐步迁移回 Options API。
- 新代码统一风格，避免同时出现 class component、Options API、装饰器 Vuex 三种风格。

#### 🟢 模板项目残留

位置：

- `frontend/package.json` name 仍为 `vue-typescript-admin-template`
- `src/views/table`、`src/views/tree`、`src/views/nested` 等模板残留目录
- `src/api/articles.ts`

建议：

- 删除未使用模板页面和 API。
- 修改 package name / author 等元数据，降低维护误导。

### 4.2 TypeScript 类型完整性

问题：

#### 🟡 `any` 使用广泛

统计：`frontend/src` 中 `any` 约 441 次，包含 API 响应、组件 props、表单 refs、列表项、错误对象等。

位置示例：

- `frontend/src/api/torrents.ts:164`
- `frontend/src/api/downloader.ts:3`
- `frontend/src/store/modules/downloaderSettings.ts:43`
- `frontend/src/components/torrents/VirtualScrollList.vue:38-49`

建议：

- 定义统一 `ApiResponse<T>`、`PaginatedData<T>`。
- 为下载器、任务、通知、审计日志、tracker 关键词补齐 DTO。
- 对 Element UI ref 可集中定义辅助类型，减少局部 `as any`。

#### 🟡 API 层大量 `as unknown as Promise<T>`

位置：`frontend/src/api/torrents.ts` 多处。

这说明 axios wrapper 的类型没有正确表达返回值，导致调用方用类型断言绕过编译器。

建议：

- 将 `request` 封装为泛型：`request<T>(config): Promise<ApiResponse<T>>`。
- API 函数直接返回 `request<T>()`，删除双重断言。

### 4.3 状态管理（Vuex）

优点：

- `user`、`notification` 使用 `vuex-module-decorators` 并配置 `rawError: true`。
- `lint:vuex-action` 自定义脚本可运行且通过。
- 通知模块有轮询启停逻辑。

问题：

#### 🟡 Vuex 风格不一致

位置：

- `frontend/src/store/modules/user.ts` 使用 `vuex-module-decorators`
- `frontend/src/store/modules/downloaderSettings.ts` 使用传统 `Module`

建议：

- 统一 Vuex 模块风格。
- 将 `downloaderSettings` 加入 `IRootState`，避免类型遗漏。

#### 🟢 全局轮询生命周期依赖调用方

位置：`frontend/src/store/modules/notification.ts:162-179`

轮询可停止，但需要确保 App 或 Layout 销毁 / 登出时必定调用。

建议：

- 登出时统一调用 `NotificationModule.StopUnreadPolling()`。
- 在 Layout 根组件生命周期中集中启动和停止。

### 4.4 API 调用和错误处理

优点：

- `src/utils/request.ts` 统一添加 `x-access-token` 和 `Authorization`。
- 处理了业务 `code=401` 和 HTTP 401 的跳转去重。
- 调试日志对 token 做脱敏。

问题：

#### 🟡 前端强依赖后端业务 `code` 字符串

位置：`frontend/src/utils/request.ts:75-115`

如果后端某接口返回 HTTP 401 或非 `CommonResponse` 错误体，调用方处理会不一致。

建议：

- 后端统一 HTTP 状态码后，前端改为 HTTP 优先、业务 code 兼容。
- 定义错误类型，避免全部转为 `Error(res.msg)` 后丢失 code、data、details。

#### 🟢 业务错误有“静默失败”倾向

位置示例：`frontend/src/store/modules/notification.ts:79-81`、`131-133` 等。

通知轮询静默是合理的，但用户主动操作如删除、标记已读也静默失败会造成无反馈。

建议：

- 后台轮询静默。
- 用户操作失败显示消息，并保留重试入口。

### 4.5 用户体验和交互设计

优点：

- 页面功能覆盖面完整：下载器、种子、回收站、Tracker、任务、审计日志、通知中心。
- 种子列表有批量操作、列设置、高级搜索、活动种子筛选。
- 大列表有虚拟滚动组件。

问题：

#### 🟡 高风险操作交互需要更强保护

删除、批量删除、定时任务脚本执行、批量转移等都是高风险操作。当前已有分级删除概念，但安全确认和审计呈现仍应加强。

建议：

- 高风险操作展示影响范围：下载器、种子数量、是否删除文件、可恢复性。
- 对“完全删除”和“执行脚本任务”增加二次确认或输入确认短语。
- 操作完成后链接到审计日志详情。

#### 🟢 调试输出残留较多

位置示例：

- `frontend/src/views/torrents/components/TrackerOperationDialog.vue`
- `frontend/src/views/tracker/reannounce-config.vue`
- `frontend/src/views/torrents/FileManagement.vue`

建议：

- 统一使用 debug flag 包装。
- 生产构建移除 `console.log`，保留必要 `console.warn/error` 或接入前端日志。

### 4.6 前端性能优化

优点：

- 路由动态 import，页面懒加载。
- 静态资源 Nginx 长缓存，SPA HTML 不缓存。
- 种子相关组件有虚拟滚动。

问题：

#### 🟡 TypeScript 检查被关闭

位置：`frontend/vue.config.js:43-45`

配置删除 `fork-ts-checker`，`lintOnSave=false`。这会让大量类型问题进入构建产物。

建议：

- 恢复 `fork-ts-checker` 或新增 `npm run type-check`。
- CI 强制执行 `vue-cli-service lint` 和类型检查。

#### 🟡 Monaco Editor 全局打包可能增加首屏体积

位置：`frontend/vue.config.js:17-21`

Monaco 语言包包含多种语言，若不是首屏必需，应确认其 chunk 拆分效果。

建议：

- 只在任务编辑页懒加载 Monaco。
- 用 bundle analyzer 检查首屏 JS 体积。

### 4.7 前端测试

问题：

#### 🟡 前端测试覆盖明显不足

仅发现 2 个测试文件，集中在 `AdvancedMultiSelect`。

建议：

- 优先补：登录流程、路由守卫、request 拦截器、种子列表筛选、删除确认、任务编辑器。
- 对 API 契约使用 mock response 做组件集成测试。

#### 🟡 当前环境无法运行 lint

执行 `npm run lint -- --no-fix` 失败：`vue-cli-service: not found`。说明当前未安装前端依赖或环境未初始化。

已通过的有限验证：

- `npm run lint:vuex-action -- --help` 通过，输出所有 `@Action` 装饰器均正确配置 `rawError: true`。

## 5. 全栈集成审查

### 5.1 前后端 API 契约一致性

优点：

- 基础响应结构一致：`status / msg / code / data`。
- 前端 baseURL `/api/v1` 与后端 API 前缀 `/api/v1` 基本一致。
- 通知中心契约较清晰：`/notifications`、`/unread-count`、`pageSize`、`list/total`。

问题：

#### 🔴 Nginx API 代理路径存在重复 `/api/v1` 风险

位置：

- `frontend/.env.production`: `VUE_APP_BASE_API=/api/v1`
- `frontend/nginx.conf:78-80`: `location /api/ { proxy_pass http://btdeck-backend:5001/api/v1/; }`

当浏览器请求 `/api/v1/torrents/getList` 时，Nginx `location /api/` 匹配后可能转发为 `/api/v1/v1/torrents/getList`，具体取决于 `proxy_pass` URI 替换规则。这是部署后 API 404 的高风险点。

建议：

- 方案 A：前端生产 base API 改为 `/api`，Nginx 代理到后端 `/api/v1/`。
- 方案 B：前端保持 `/api/v1`，Nginx `proxy_pass http://btdeck-backend:5001;` 不追加 `/api/v1/`。
- 加一条 Docker 集成测试：前端容器请求 `/api/v1/dashboard` 必须命中后端。

#### 🟡 WebSocket 架构未在 compose 中暴露后端 5002

README 声称 WebSocket 地址为 `ws://localhost:5002`，Nginx 配置代理 `/ws/` 到 `btdeck-backend:5002`，但后端 compose 只暴露容器内 API，且主服务 Dockerfile 只启动 `btdeck_startup.sh`，需要确认是否同时启动 WebSocket 服务。

建议：

- 明确后端容器内是否启动 5002。
- 若使用 Nginx `/ws/`，前端只暴露 8080 即可；README 改为 `ws://localhost:8080/ws/`。
- 加健康检查或集成测试验证 WebSocket 握手。

### 5.2 部署配置合理性

优点：

- 后端容器使用非 root 用户。
- 前端容器使用非 root Nginx 用户。
- 资源限制、健康检查、日志卷、缓存卷配置完整。

问题：

#### 🟡 后端健康检查依赖 `/docs`

位置：`docker-compose.yml`

生产环境通常会关闭 docs，健康检查应使用专门 `/health`。

建议：

- 后端实现 `/health`，检查数据库连接、迁移状态、关键后台任务状态。
- compose 健康检查改为 `/health`。

#### 🟢 Compose version 字段已不推荐

位置：`docker-compose.yml:5`

新版 Docker Compose 已不需要 `version`，轻微问题。

### 5.3 环境变量管理

问题：

#### 🔴 敏感配置与默认配置管理不合格

位置：

- `backend/config/config.yaml` 被 Git 跟踪。
- `frontend/.env` 被 Git 跟踪。
- `backend/.env.example` 给出固定默认 JWT secret。

建议：

- `.env`、`config.yaml` 只保留 example，不提交真实或生成配置。
- 启动时检测默认密钥并失败退出。
- 提供 `docker-compose.example.yml` 或 `.env.example` 描述必须配置项。

### 5.4 依赖管理

问题：

#### 🟡 后端依赖存在混乱和潜在冲突

位置：`backend/requirements.txt`

同时存在 `python-jose`、`jose`、`pyjwt`；`common~=0.1.2` 语义不清；安全库、加密库混用。依赖注释显示曾做安全升级，但未见 lock 文件。

建议：

- 移除未使用或冲突依赖，统一 JWT 库。
- 使用 `pip-tools` / `uv lock` 生成锁定依赖。
- CI 加依赖漏洞扫描。

#### 🟡 前端依赖偏旧且未安装验证

位置：`frontend/package.json`

Vue 2、axios 0.21.1、Element UI 都是较老生态；当前环境缺 `node_modules`，lint 无法运行。

建议：

- 短期锁定依赖并确保 CI 可安装。
- 中期评估 Vue 2 EOL 后的升级路线，至少升级 axios 到安全版本并跑回归。

## 6. 优先级整改建议

### P0：上线前必须处理

1. 🔴 移除默认 `admin/admin`，强制初始化密码。
2. 🔴 移除版本库中的真实 / 生成配置文件，生产默认密钥拒绝启动。
3. 🔴 禁用或隔离任意 Python 代码执行型定时任务。
4. 🔴 修复前端 Nginx API 代理路径重复风险。
5. 🔴 清理 `backend/app/api/router.py` 残缺文件，避免误导和潜在导入风险。

### P1：近期质量提升

1. 🟡 合并后端配置系统，明确 `DATABASE_URL` 是否生效。
2. 🟡 认证统一改为依赖注入，所有受保护接口使用同一鉴权路径。
3. 🟡 统一 HTTP 状态码与业务响应格式。
4. 🟡 统一分页参数与响应字段。
5. 🟡 恢复后端 pytest / 前端 lint / type-check 的可运行环境。
6. 🟡 拆分超大 endpoint 和 service 文件。

### P2：中长期演进

1. 🟢 PostgreSQL 迁移和查询性能基准。
2. 🟢 后台任务拆成 worker。
3. 🟢 前端类型收敛，逐步消除 `any`。
4. 🟢 删除模板残留页面和未使用 API。
5. 🟢 增加端到端测试和 Docker 集成测试。

## 7. 验证记录

已执行：

- 代码规模统计：成功。
- 文件结构枚举：成功。
- `npm run lint:vuex-action -- --help`：成功。
- `git status --short`：审查前工作树无输出。

未能执行：

- `python -m pytest -q`：失败，系统无 `python` 命令。
- `python3 -m pytest -q`：失败，`No module named pytest`。
- `npm run lint -- --no-fix`：失败，`vue-cli-service: not found`，前端依赖未安装。

## 8. 评分明细

| 维度 | 分数 | 说明 |
|---|---:|---|
| 功能完整度 | 7.5 | 功能面完整，业务模块丰富 |
| 后端架构 | 6.2 | 分层存在，但超大文件、配置双轨、迁移双轨明显 |
| API 契约 | 6.0 | 有统一响应意识，但 REST、状态码、分页命名不统一 |
| 数据库设计 | 6.3 | 索引和迁移有基础，但 Alembic 约束未完全落实 |
| 安全性 | 4.2 | 默认凭据、默认密钥、任意代码执行是主要风险 |
| 前端架构 | 6.4 | 结构清晰但类型和风格不统一 |
| 测试质量 | 5.8 | 后端测试较多，前端测试不足，当前环境不可复现 |
| 部署运维 | 6.5 | Docker 结构完整，但代理、健康检查、环境变量有风险 |

综合评分：**6.1 / 10**

结论：BtDeck 已经从原型进入“功能较完整但工程治理不足”的阶段。最需要优先处理的不是继续加功能，而是收敛安全边界、统一契约、恢复可验证的 CI，并拆除历史残留与配置双轨。处理完 P0 / P1 后，项目质量可提升到 7.5 分以上。
