# Progress Log - BtDeck 全栈项目

> **项目**: BtDeck 全栈（backend + frontend）
> **当前分支**: dev
> **当前开发版本**: v1.0.5（查询模板系统）
> **更新**: 2026-06-18

> 本文件由 backend/progress.md 与 frontend/PROGRESS.md 合并而来（2026-06-18）。按"版本分节 + 每节内前后端子段"组织，技术决策表合并为一表并新增"端"列。

---

## 进行中功能

### v1.0.5-audit 契约审计修复（技术债）— fix/contract-audit 分支

**计划文件**: `PLANS/v1.0.5-audit.md`
**审计依据**: `backend/docs/style-and-contract-audit.md`（P1 确定性 bug + P0 契约归一化）
**范围**: P0 + P1。不覆盖 P2（REST 路由迁移）/ P3（前端类型收敛），推迟。

**已完成（5 commit）**:
| 任务 | commit | 验证 |
|------|--------|------|
| P0-3 后端全局异常处理器 | ac324bc | pytest 1524 passed 无回归 |
| P0-1 前端 ApiError 归一化 | 0e55469 | jest 25/25, eslint 0 error |
| P1-A 后端补 4 项端点 | efc6574 | auth+cron 189 passed |
| P1-B 前端修 4 项契约 | 0e8f007 | jest 25/25, eslint 0 error |
| P0-2c 认证基础设施补强 | 9e19822 | auth 125 passed |

**进行中**:
- P0-2a 认证迁移到 `require_authenticated_user`（20+ 文件/~195 处，分批提交）
- P0-2b 认证测试改造（~40 处断言）

**审计交叉验证结论（3 个独立 Explore agent 核实）**:
- 9 项契约不匹配中 8 项属实，`/tags/batch-delete` 误报（后端已有端点）
- tracker statistics 是漏挂装饰器的孤立函数，修复成本极低
- tag_management 的 `{success,message}` 是私有 helper 返回值，非 HTTP 响应，降级不改

---

### v1.0.5 查询模板系统 (done) — dev 分支

**计划文件**: `PLANS/v1.0.5.md`（已标注方向转变）

**目标**: 实现查询模板功能，用户可保存常用查询条件（简单查询 + 高级搜索）并一键应用，含系统预设模板。

**方向转变（重要）**: 探索阶段发现后端与前端已存在完整的 `search_templates` 基础设施（表 + CRUD 端点 + 服务 + 前端 API），仅前端入口 `handleSaveSearchTemplate` 是空函数。改为**补全现有系统**而非从零新建，避免重复造轮子。

**任务完成情况** (12/12 done，见 feature_list.json v1.0.5)：
- 后端：4 个预设模板数据 + init_db 集成 + apply/权限确认（现有代码已满足）+ 16 个认证测试
- 前端：API 便捷方法 + index.vue 接线（handleSaveSearchTemplate + applyQueryTemplate）+ 管理页 + 对话框 + 路由
- 全栈：保存→应用链路代码闭环

**5 个 commit**: 63a4bec / d04af4d / 7f111f8 / 7896a23 / (本条状态更新)

**遗留**: 前端 lint/tsc 因环境依赖未完整安装，留待完整环境验证。

---

## 已完成功能

### v1.0.4 实时速度监控 (done) — dev 分支

**计划文件**: `PLANS/v1.0.4.md`

**与计划的偏差**:
- 计划: `TorrentStateManager` 动静数据分离(10s/10min刷新) → 实际: 轻量级 `active-torrents` 接口 + 前端1秒轮询
- 计划: `speed-all` API → 实际: `active-torrents` API（仅返回有速度的种子）
- 计划: 前端 `setup()` + Composition API → 实际: **Options API** + 虚拟分页
- 计划: 前端 10秒/10分钟双定时器 → 实际: 1秒单定时器轮询
- 额外完成: 种子完成后自动更新数据库状态、活跃种子进度字段

#### 后端（11 个任务全部 done）

| 任务 | 说明 |
|------|------|
| 活跃种子速度接口 | `torrent_speed.py`, qB用status_filter, tr仅查速度字段 |
| 路由注册 | `/torrents/active-torrents` |
| 线程池泄漏修复 | commit 25c59aa |
| 速度单位转换修复 | commit d79040d |
| Transmission空列表修复 | commit b4ddde2 |
| 活跃种子进度字段 | commit a568aa9, progress字段(0-100百分比) |
| 种子完成后自动更新状态 | commit f8b0185, progress达100%自动更新为completed |
| 性能测试 | 4下载器并发平均543ms |
| 场景测试 | 8个验收场景通过 |

#### 前端（2 个任务 done）

| 任务 | 说明 |
|------|------|
| 前端 API 封装 | `torrents.ts` getActiveTorrents() |
| 前端种子列表改造 | Options API + 虚拟分页 + 1秒轮询 + beforeDestroy清理 |

**关键实现**: `activeSpeedMap` 缓存速度数据；虚拟分页算法（活跃种子优先排列）；防抖 + 版本控制避免重复请求。

**结论**: v1.0.4 前后端开发完成。

---

### v1.0.9 一键部署 (done，提前完成) — dev 分支

**说明**: v1.0.9 早于 v1.0.5~v1.0.8 提前完成落地。

| 任务 | 说明 |
|------|------|
| 全栈 monorepo 整合 | commit c7ce2f4，前后端合并为单一仓库 |
| PyInstaller 打包 | deploy/btdeck.spec，前后端合一单可执行文件 |
| Inno Setup Windows 安装包 | deploy/btdeck.iss |
| fpm Linux 安装包 | deploy/build-linux.sh，.deb/.rpm |
| Docker Compose 全栈部署 | docker-compose.yml |

**部署修复系列**: 5e4baf8 / 6f8e3e0 / 78033bc / fb380b9 / b80a7f6（Inno Setup 语言包、PyInstaller 路径、pandas/numpy/openpyxl hiddenimport、PIL 排除、systemd 目录预创建等）。

---

## 计划外已完成功能

### 通知中心 (done) — dev 分支

**后端**: `notification.py`(模型) + `notification_service.py`(版本检查、未读计数) + `notifications.py`(GET/PUT/DELETE 端点)。单向信箱模式，仅系统写入。
**前端**: `NotificationDrawer/index.vue`(全局右侧抽屉) + `NotificationItem.vue` + `store/modules/notification.ts`(Vuex) + `api/notification.ts`。60秒未读计数轮询。

### Tracker关键词池初始化 (done) — dev 分支

`tracker_keywords_pools.py` 关键词池管理，默认数据自动初始化，集成到 `init_db()` 统一初始化流程。

### 统一初始化重构 (done) — dev 分支

所有初始数据初始化统一到 `init_db()`，集成到后端启动流程。commit 22a89c8。

---

## 待开发功能（按计划顺序）

| 版本 | 名称 | 计划文件 | 状态 |
|------|------|----------|------|
| v1.0.6 | 孤儿文件管理 | PLANS/v1.0.6.md | pending |
| v1.0.7 | 路径扫描增强 | PLANS/v1.0.7.md | pending |
| v1.0.8 | 数据库升级 | PLANS/v1.0.8.md | pending |
| v1.1.0 | 自动化运维 | PLANS/v1.1.0.md | pending |

---

## 技术决策记录

| 日期 | 端 | 决策 | 理由 |
|------|----|------|------|
| 2026-04-22 | backend | 轻量级active-torrents替代动静分离 | 更简单，前端1秒轮询仅查有速度种子 |
| 2026-04-22 | frontend | Options API 而非 Composition API | 项目技术栈约定 |
| 2026-04-22 | frontend | 前端虚拟分页 | 已有查询逻辑，前端合并更灵活 |
| 2026-04-22 | frontend | 防抖+版本控制 | 避免1秒轮询导致重复请求和页面卡顿 |
| 2026-04-22 | backend | 专用线程池 | 避免阻塞默认executor |
| 2026-04-22 | backend | 统一初始化到 init_db() | 集中管理初始数据 |
| 2026-06-18 | fullstack | harness 体系合并到根目录 | 全栈 monorepo 统一状态追踪，消除端级重复 |
| 2026-06-18 | fullstack | v1.0.5 补全 search_templates 而非新建 query_templates | 探索发现已有完整基础设施，避免重复造轮子 |
| 2026-06-18 | fullstack | User 不加 relationship（用 created_by 整数列） | 遵循既有约定（SettingTemplate 同模式），避免触发 User 表迁移 |
| 2026-06-18 | fullstack | query_config 用 source=simple/advanced 双分支 | 1:1 还原两种查询状态（listQuery / condition_groups），应用时按 source 分流 |
| 2026-06-19 | fullstack | 审计修复用独立 feature 块 v1.0.5-audit 而非 v1.0.5.1 | v1.0.5.1 子任务号已被 done 占用，撞号；用 -audit 后缀避开数字子任务号空间 |
| 2026-06-19 | fullstack | 实施顺序 P0-3→P0-1→P1→P0-2c→P0-2a/b | 异常处理器先做兜底；前端归一化在后端 401 之前避免破损窗口；认证基础设施先于迁移避免 user_id 断链 |
| 2026-06-19 | backend | 认证统一用 require_authenticated_user（HTTP 401），login.py 豁免 | login 的 code=401 是密码错误业务语义，非认证失效，前端登录页依赖此分支不跳转 |
| 2026-06-19 | backend | 不把 user_id 加入 verify_access_token required_fields | 避免现有未过期 token 全部失效（强制全员重登），改为 AuthenticatedUserInfo 兜底解析 |
| 2026-06-19 | frontend | ApiError extends Error + 兼容 msg/response getter | 降低约 33 个存量 catch 块的回归（e.msg / e.response.data.msg 链式读取仍可用） |
| 2026-06-19 | frontend | 成功码白名单 {200,206,207} | 206(需确认路径映射)/207(Multi-Status 部分成功) 是业务级成功，不归一化为错误 |
| 2026-06-19 | fullstack | apply 改前端对齐后端 Path 参数 | 后端 Path 更 RESTful，且 override=True 硬编码使 override_local 无效 |
| 2026-06-19 | fullstack | torrents/detail 不补后端端点，删前端死代码 | getTorrentDetail 从未被调用，补后端会引入语义模糊(hash可能重复)的未用功能 |

---

## 当前会话

> **2026-06-20**: v1.0.5-audit P0-2 认证统一全部完成——本会话完成 P0-2a（24 文件迁移，分 4 批）+ P0-2b（测试断言改造）+ P0-2d（弃用 verify_token_dependency），共 6 commit。
>
> **调研修正**：交接文档预估 ~21 文件 + ~102 处测试断言。实际调研发现：24 个文件；测试改造仅 32 处 inline 断言（因 test_auth_protection_extended.py 的 62 处走 _is_auth_rejected helper 已兼容 HTTP 401）。这改变了"必须原子配对"的前提，改为按风险分 4 批，每批 commit + 跑针对性 pytest。
>
> **完成清单**：
> - Batch A（10 token-only）+ Batch B（downloader/cron_tasks/tracker/torrent_crud/sync，最大 cron_tasks 20 endpoint）
> - Batch C（3 user_id 文件，advanced_search 旧 token 缺 user_id → HTTP 401 兜底，用户确认对齐 torrent_location 模板）
> - Batch D（4 mixed 部分迁移文件）
> - P0-2b：5 测试文件断言改造（含 tag_management mock_auth 改用 dependency_overrides）
> - P0-2d：verify_token_dependency 加 DeprecationWarning，cron_tasks.verify_token 已删除
>
> **附带修复**：多处预存在的"不安全 try/except 认证"（verify_access_token 失败返回 None 而非抛异常，旧代码 try/except 形同虚设，torrent_sync/tracker_messages/cuser 2FA 端点）。
>
> **验证**：后端 pytest 1523 passed（2 个预存在失败：test_unified_token_expiry 路径分隔符 bug + test_concurrent_requests flaky，均与本次无关）；init.sh 全栈验证通过。
>
> **下一步**：P0-2 全部完成。剩余 P2/P3 均为推迟项（REST 路由迁移、前端 any 治理、OpenAPI schema、分页字段统一、API 对照表 CI）。可选收尾：彻底删除 verify_token_dependency 定义。

---

**最后更新**: 2026-06-20
