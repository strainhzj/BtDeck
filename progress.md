# Progress Log - BtDeck 全栈项目

> **项目**: BtDeck 全栈（backend + frontend）
> **当前分支**: dev
> **当前开发版本**: v1.0.5（查询模板系统）
> **更新**: 2026-06-18

> 本文件由 backend/progress.md 与 frontend/PROGRESS.md 合并而来（2026-06-18）。按"版本分节 + 每节内前后端子段"组织，技术决策表合并为一表并新增"端"列。

---

## 进行中功能

### v1.0.5 查询模板系统 (in-progress) — dev 分支

**计划文件**: `PLANS/v1.0.5.md`

**目标**: 实现查询模板功能，用户可保存常用查询条件并一键应用，含系统预设模板。

**任务拆解**: 15 个任务（见 feature_list.json v1.0.5），覆盖后端模型/迁移/服务/API/路由/预设、前端 API/页面/路由/组件、全栈测试。

**关键依赖**: QueryTemplate 用 `back_populates="query_templates"`，需在 `app/auth/models.py` 的 User 类添加对应 relationship。

**结论**: 计划中，待启动。

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

---

## 当前会话

> **2026-06-18**: 完成 harness 体系合并（前后端 → 根目录），v1.0.5 任务拆解落地。下一步：启动 v1.0.5 查询模板系统开发。

---

**最后更新**: 2026-06-18
