# 前端静态展示 Demo 计划（Demo Mode）

> **状态**：待实施（2026-08-23 登记）
> **对应 feature**：`frontend-static-showcase-demo-2026-08-23`
> **目标**：将现有 Vue 2 + TypeScript 前端构建为不依赖真实后端、可独立展示的静态 Demo。

## 1. 产品边界与实现假设

### 1.1 本次目标

- 保留现有路由、布局、页面和主要交互样式，优先复用现有 API 类型、组件、表格、筛选和对话框。
- 新增仅在 Demo 构建中启用的静态数据模式；生产构建继续使用真实后端 API。
- Demo 运行时不连接数据库、下载器、Tracker、文件系统或真实认证服务。
- 支持通过 `dist` 压缩包或独立 Nginx 静态服务展示。
- 所有演示数据使用脱敏 fixture，不携带真实 URL、用户名、密码、Token、路径或种子文件。

### 1.2 明确不承诺的能力

- qBittorrent/Transmission 的真实连接、速度、Tracker 汇报和状态同步。
- 真实文件扫描、种子文件上传/下载、回收站物理删除。
- 真实定时任务执行、脚本执行、密码修改、二因素认证和权限控制。
- 静态 Demo 中的“成功”只代表本地状态模拟成功，不产生后端副作用。

### 1.3 推荐架构

```text
VUE_APP_DEMO_MODE=true
        │
        ├─ 入口/路由：注入演示用户，跳过真实认证守卫
        │
        └─ request.ts：Demo 模式转发到 demoRequest
                         │
                         ├─ typed fixtures（初始数据）
                         ├─ in-memory demo store（本地突变）
                         └─ localStorage（可选，保存演示会话）
```

不建议在每个页面内直接写一套假数据，也不建议复制全部 `api/*.ts`。应保留 API 函数签名和 `{ status, msg, code, data }` 响应信封，在请求层集中模拟，降低真实模式与 Demo 模式的分叉。

## 2. 任务清单

### Task 1：冻结 Demo 范围、数据契约和演示脚本

**目标**：在编码前固定哪些页面可展示、哪些操作可模拟、哪些能力必须标记为“仅演示”。

**工作内容**：

1. 建立路由矩阵：核心展示、扩展展示、只读降级、明确禁用四类。
2. 为仪表盘、下载器、种子、Tracker、通知、任务、日志、回收站、孤儿文件、查询模板准备脱敏 fixture 字段清单。
3. 复核 12 个 API 模块的响应形状，所有分页统一使用 `list` / `total` / `pageSize`。
4. 定义演示数据重置规则、随机速度变化规则、操作成功/失败提示和“Demo Mode”视觉标识。
5. 写出演示脚本：首次进入 → 仪表盘 → 下载器 → 种子筛选/详情 → 暂停/恢复 → 查询模板 → 通知/日志。

**验收标准**：产品或评审可以按脚本在 5 分钟内走完一条完整展示路径；每个未模拟能力都有明确说明，不把模拟结果误认为真实数据。

### Task 2：实现 Demo 构建入口与认证旁路

**目标**：Demo 构建启动后无需真实后端登录即可进入主界面，同时不改变默认生产认证行为。

**预计文件范围**：

- `frontend/.env.demo`
- `frontend/vue.config.js`
- `frontend/src/main.ts`
- `frontend/src/permission.ts`
- `frontend/src/store/modules/user.ts`
- `frontend/src/layout/`（Demo 标识）
- `frontend/tests/unit/`

**工作内容**：

1. 增加 `VUE_APP_DEMO_MODE`，默认值必须为关闭；生产环境不得隐式进入 Demo 模式。
2. Demo 模式初始化固定演示用户、角色和非敏感占位 Token，绕过 `/auth/login`、`/users/info`、refresh token 调用。
3. 保留登录页可选入口，或提供“进入演示”按钮；退出演示后能重新进入，不残留真实账号 Cookie。
4. 在布局或导航区域显示“演示模式 / 数据为本地模拟”标识，避免截图或现场演示造成误解。
5. 对 Demo 模式下的改密、令牌续期、强制改密守卫做显式降级，不触发真实安全流程。

**验收标准**：清空 Cookie/localStorage 后直接访问任意业务路由，不出现网络请求或无限登录重定向；关闭 Demo 模式后原真实认证路径保持不变。

### Task 3：实现集中式静态请求层和本地状态仓库

**目标**：以最少页面改动承接现有 API 调用，并覆盖可展示交互的本地状态变化。

**预计文件范围**：

- `frontend/src/utils/request.ts`
- `frontend/src/demo/fixtures/`
- `frontend/src/demo/demo-request.ts`
- `frontend/src/demo/demo-store.ts`
- `frontend/src/demo/types.ts`
- `frontend/tests/unit/demo-*.spec.ts`

**工作内容**：

1. 在 `request.ts` 的 Axios 调用前按 Demo 开关分流；关闭开关时不得改变现有拦截器、错误归一化和 401 续期行为。
2. 按 `method + URL pattern` 路由到本地 handler，覆盖核心 GET 和必要的 POST/PUT/DELETE，不以字符串散落在页面中。
3. 返回完整 API 信封，分页、列表为空、部分成功、业务错误和 Blob 响应均保持调用方预期。
4. 用 typed fixture 和本地 store 实现增删改、暂停/恢复、已读/未读、模板保存/应用、任务状态变化等有限状态机。
5. Demo 模式禁止真实网络兜底；未实现的接口返回可读的 Demo 降级响应并显示一次性提示。
6. 本地存储只保存演示偏好和可选的 Demo 状态，提供“重置演示数据”能力；不保存真实凭据。

**验收标准**：核心页面 Network 面板无 `/api/v1` 请求；API 单测覆盖成功、分页、空数据、模拟错误、Blob 和未支持接口；真实模式 API 契约测试不回归。

### Task 4：完成核心展示页面和主要本地交互

**目标**：优先交付一条完整、稳定、视觉上可展示的产品主流程。

**预计文件范围**：

- `frontend/src/views/dashboard/`
- `frontend/src/views/downloader/`
- `frontend/src/views/torrents/`
- `frontend/src/components/torrents/`
- `frontend/src/views/query-templates/`
- `frontend/src/layout/components/NotificationDrawer/`
- `frontend/tests/unit/`

**工作内容**：

1. 仪表盘展示固定下载器、种子、任务和系统统计，刷新时使用同一本地数据源。
2. 下载器页面展示在线/离线节点、速度、任务数和设置摘要；连接测试、同步、暂停轮询等改为本地反馈。
3. 种子列表支持分页、状态/下载器/标签筛选、排序、列表/传统视图切换、详情弹窗和 Tracker 详情。
4. 种子暂停、恢复、重新检查、删除等操作更新本地 store，并模拟短暂 loading/成功提示；删除流程不得等待真实任务接口。
5. 查询模板支持新增、编辑、应用、删除，应用后回填筛选条件。
6. 通知中心提供未读角标、查看详情、标记已读和清空等本地操作。

**验收标准**：演示脚本全程不依赖后端；页面切换、筛选、分页、弹窗、操作反馈和刷新均可重复操作；至少覆盖桌面宽度和窄窗口布局。

### Task 5：处理扩展页面、轮询、文件和 Blob 特殊路径

**目标**：让非核心页面不会因遗留请求而报错、卡死或触发真实网络。

**预计文件范围**：

- `frontend/src/views/tracker/`
- `frontend/src/views/tasks/`
- `frontend/src/views/logs/`
- `frontend/src/views/recycle-bin/`
- `frontend/src/views/orphan-files/`
- `frontend/src/views/settings/`
- `frontend/src/components/tasks/`
- `frontend/src/views/torrents/FileManagement.vue`
- `frontend/src/api/`
- `frontend/tests/unit/`

**工作内容**：

1. Tracker 关键词、汇报配置和测试工具使用脱敏数据；真实网络测试按钮改为本地结果或明确禁用。
2. 任务/日志页面提供静态任务状态和日志分页；脚本、Python 类、Cron 校验返回固定演示结果。
3. 回收站和孤儿文件支持查看、筛选、确认弹窗和本地状态变化；扫描轮询使用有限的 queued/running/success 状态机。
4. 统一处理 `setInterval` / `setTimeout`，Demo 模式下保持页面销毁清理，避免切换路由后重复轮询。
5. 文件上传改为本地文件选择后的模拟结果；导入、物理删除等动作显示“Demo 不执行”。
6. 审计/任务/种子备份导出返回本地 Blob 或提供预览，不访问真实导出接口。
7. 设置页的密码、二因素和下载器高级配置仅展示当前 Demo 状态，禁止暗示已写入后端。

**验收标准**：所有注册路由均可打开；未支持动作不会产生 404、401、网络错误洪泛或无限轮询；文件与导出按钮的行为符合 Demo 说明。

### Task 6：独立静态构建、服务和交付包

**目标**：生成不需要后端容器的可展示产物。

**预计文件范围**：

- `frontend/package.json`
- `frontend/.env.demo`
- `frontend/Dockerfile.demo`
- `frontend/nginx.demo.conf`
- `frontend/README.md`
- `deploy/`（如确有必要）

**工作内容**：

1. 增加明确的 Demo 构建命令，使用 Node 18.20.1 与锁文件安装依赖，避免依赖本机 Node 版本漂移。
2. 构建结果只依赖前端 `dist`，不复制后端、数据库、迁移或下载器配置。
3. 提供 zip/dist 交付方式和独立 Nginx 容器方式；独立 Nginx 不配置 `btdeck-backend` upstream，不依赖 Compose 服务名。
4. 保留 SPA fallback、静态资源缓存和健康检查；说明应通过 HTTP 服务访问，不承诺直接双击 `file://` 可用。
5. 记录构建产物大小、首屏/异步 chunk、浏览器支持范围和启动命令。

**验收标准**：在无后端、无数据库、无 API 代理的干净环境中启动后可完成核心演示流程；zip 和容器两种方式至少一种可复现，最好两种均可复现。

### Task 7：测试、回归和人工验收

**目标**：确认 Demo 模式隔离、真实模式不回归、交互可重复和发布包可启动。

**预计文件范围**：

- `frontend/tests/unit/demo-*.spec.ts`
- `frontend/tests/unit/` 相关路由/页面契约测试
- `frontend/scripts/`（如需增加 Demo 检查）
- `frontend/README.md`
- `feature_list.json`
- `progress.md`
- `session-handoff.md`

**工作内容**：

1. 单测覆盖 Demo 开关、认证旁路、请求分流、分页、状态突变、错误和 Blob。
2. 增加“Demo 模式不得调用 Axios/Fetch 外部地址”的测试或构建后静态检查。
3. 回归现有 `typecheck`、contract check、ESLint、Jest；修复或单独记录现有契约漂移，不把无关生成文件混入 Demo 变更。
4. 用干净浏览器验证首次进入、刷新、前进/后退、退出、重置数据、窄屏和重复点击。
5. 在无后端环境启动交付包，记录每条演示路径的结果和已知限制。
6. 完成后只将有证据的任务改为 `done`，并把构建、测试、包体和人工验收证据回填到 `feature_list.json`。

**验收标准**：核心演示路径全部通过；Demo 构建无真实网络依赖；生产模式不受影响；所有限制、启动方式和数据语义写入交付说明。

## 3. 建议实施顺序与交付节奏

1. 先完成 Task 1–3，形成能启动、能进主界面、能返回静态数据的最小骨架。
2. 再完成 Task 4，优先产出可对外展示的核心流程。
3. Task 5 作为扩展覆盖，不能阻塞核心 Demo 首次交付。
4. Task 6 与 Task 7 在核心流程稳定后并行推进。

建议首个可展示版本只承诺仪表盘、下载器、种子管理、查询模板和通知中心；任务、孤儿文件、回收站、备份和设置页按“静态展示/降级提示”交付，不承诺完整业务等价。

## 4. 完成定义

- [ ] Demo 模式与生产模式有明确构建开关，默认生产模式不变。
- [ ] 核心页面在无后端环境可打开并可重复操作。
- [ ] 无真实凭据、真实下载器地址、真实文件路径和真实外部网络依赖。
- [ ] API 响应信封和分页字段保持项目约定。
- [ ] Demo 请求层、状态仓库、特殊路径和路由守卫有测试。
- [ ] `typecheck`、contract check、ESLint、Jest 和 Demo production build 有记录。
- [ ] 静态交付包可从 README 复现启动，限制清单完整。
- [ ] `feature_list.json`、`progress.md`、`session-handoff.md` 的证据已同步。

**登记说明**：本计划只登记实现方案，不代表已经修改前端代码、完成静态化或验证 Demo 构建。
