# BtDeck 代码路线图

> BtDeck —— 统一管理多种 BitTorrent 客户端（qBittorrent / Transmission）的全栈 Web 应用（FastAPI + Vue 2 + TypeScript）。
> 本路线图是对**源码结构的有证据索引**，按"由粗到细"分三层渐进式披露，用于快速定位模块职责、调用关系与架构约定。

---

## 模块路由

```
BtDeck/
├── backend/          ← FastAPI 后端（Python 3.11+）
│   ├── app-root/        包根入口（main/factory/database/exception_handlers …）
│   ├── api/             HTTP 路由层（35 endpoints + schemas + models + responseVO）
│   ├── services/        业务服务层 + 下载器/标签适配器（含 v1.0.6.25 新增 torrent_ratio_values / sqlite_search_runtime）
│   ├── core/            基础设施（config / path_mapping / file_ops …）+ ⚠ 含 4 个孤儿文件（torrent_operations 已重写为 ratio 工具但仍 0 引用）
│   ├── contracts/ ✨    前后端共享机器可读契约（v1.0.6.27 新增：advanced_search JSON + 加载器）
│   ├── data-models/     ORM 模型 + repositories + schemas + 枚举 + 默认数据
│   ├── tasks/           定时任务 + scheduler + 后台任务
│   ├── domain/          领域目录（downloader / torrents / tracker / auth / user）
│   └── infra/           utils + startup + migrations + alembic（9 个 revision，v1.0.6.25/27 新增 2 个 ratio 迁移）
├── frontend/         ← Vue 2.6 + TypeScript 前端
│   ├── entry/           应用入口（main.ts / router.ts / permission.ts / App.vue）
│   ├── api/             axios API 封装（13 个领域模块）
│   ├── views/           页面视图（13 个 view 模块，Options API + class-component 并存）
│   ├── store/           Vuex（index.ts 空壳 + 5 个 getModule 自注册 module）
│   ├── components-layout/  通用组件（v1.0.6.28 新增 LucideIcon）+ 布局骨架
│   └── utils-types/     工具 / 类型 / 常量 / 指令
├── deploy/           ← 多部署模式（Docker / PyInstaller / Inno Setup / fpm；v1.0.6.28 Dockerfile 镜像源参数化）
├── tests/            ← 测试（backend pytest 101 个 test_*.py + frontend jest unit）
└── perspectives/     ← 跨切专题（调用链 / 约定 / 风险 / 测试覆盖）
```

## 分支说明

| 分支 | 一句话职责 | 链接 |
|------|-----------|------|
| **backend** | FastAPI 后端总览与跨分支依赖骨架 | [backend/README.md](./backend/README.md) |
| ↳ app-root | `backend/app/` 包根 8 文件：应用工厂、DB 引擎、异常处理、配置入口、版本、桌面/WebSocket main | [backend/app-root.md](./backend/app-root.md) |
| ↳ api | HTTP 路由层（34 个 endpoints + schemas + models + responseVO） | [backend/api/README.md](./backend/api/README.md) |
| ↳ services | 业务服务层 + downloader_adapters + tag_adapters | [backend/services/README.md](./backend/services/README.md) |
| ↳ core | 基础设施（config/path_mapping/file_ops/tracker_*），⚠ 含 4 个 0 引用孤儿文件 | [backend/core/README.md](./backend/core/README.md) |
| ↳ contracts ✨v1.0.6.27 | 前后端共享机器可读契约（advanced_search JSON + Python 加载器，单一真相源） | [backend/contracts/README.md](./backend/contracts/README.md) |
| ↳ data-models | ORM 模型 + repositories + schemas + enums + 默认数据种子 | [backend/data-models/README.md](./backend/data-models/README.md) |
| ↳ tasks | 定时任务（cron）+ scheduler + 后台任务管理 | [backend/tasks/README.md](./backend/tasks/README.md) |
| ↳ domain | 领域目录：downloader / torrents / tracker / auth / user | [backend/domain/README.md](./backend/domain/README.md) |
| ↳ infra | utils（audit_logger/encryption/log_sanitizer）+ startup + migrations + alembic | [backend/infra/README.md](./backend/infra/README.md) |
| **frontend** | Vue 2 + TypeScript 前端总览与分支索引 | [frontend/README.md](./frontend/README.md) |
| ↳ entry | 应用入口：Vue 实例化 / 路由 / 路由守卫 / 根组件 | [frontend/entry/README.md](./frontend/entry/README.md) |
| ↳ api | axios 封装的 13 个领域 API 模块 | [frontend/api/README.md](./frontend/api/README.md) |
| ↳ views | 13 个页面视图模块（⚠ class-component 与 Options API 并存） | [frontend/views/README.md](./frontend/views/README.md) |
| ↳ store | Vuex store（空壳 index + 5 个自注册 module） | [frontend/store/README.md](./frontend/store/README.md) |
| ↳ components-layout | 通用组件（Pagination/Breadcrumb/ThemeSwitcher/LucideIcon…）+ layout 骨架 | [frontend/components-layout/README.md](./frontend/components-layout/README.md) |
| ↳ utils-types | utils / types / constants / directive | [frontend/utils-types/README.md](./frontend/utils-types/README.md) |
| **deploy** | 多部署模式分叉：Docker Compose / PyInstaller 单机包 / Inno Setup / fpm | [deploy/README.md](./deploy/README.md) |
| **tests** | 后端 pytest（101 个 test_*.py，按子目录组织）+ 前端 jest unit | [tests/README.md](./tests/README.md) |
| **perspectives** | 跨切专题索引（架构调用链 / 约定 / 风险 / 测试覆盖） | [perspectives/README.md](./perspectives/README.md) |

---

## 阅读层级

- **第一层（本文件）**：模块路由，只看分支职责与导航。
- **第二层（各分支 README.md）**：该分支的文件清单表（文件名 / 行数 / 一句话职责 / 链接）+ 依赖关系。
- **第三层（源文件 .md）**：单个源文件的类/函数索引与方法签名详情（固定四节模板）。
  - 本次已完成样例：[backend/api/endpoints/torrent_crud.md](./backend/api/endpoints/torrent_crud.md)
  - 其余源文件第三层待后续按"模式 B（补充）"增量补齐。

---

## 相关文档（双向链接 ⇄）

| 文档 | 关系 | 路径 |
|------|------|------|
| 项目 README | ⇄ 快速开始 / 技术栈总览 | [../../README.md](../../README.md) |
| 根 CLAUDE.md | ⇄ 全栈协同约束 | [../../CLAUDE.md](../../CLAUDE.md) |
| 根 AGENTS.md | ⇄ 全栈工作流路由层 | [../../AGENTS.md](../../AGENTS.md) |
| 后端 CLAUDE.md | ⇄ 后端技术约束 | [../../backend/CLAUDE.md](../../backend/CLAUDE.md) |
| 前端 CLAUDE.md | ⇄ 前端技术约束 | [../../frontend/CLAUDE.md](../../frontend/CLAUDE.md) |
| 架构深度分析 | 调用链详述来源（配置/迁移双轨、定时任务隔离） | [../../backend/docs/architecture-deep-dive.md](../../backend/docs/architecture-deep-dive.md) |
| 架构独立审查 | 对深度分析的 review | [../../backend/docs/architecture-review.md](../../backend/docs/architecture-review.md) |
| 后端约束集 | API 响应格式 / 数据库迁移 / 下载器连接等 6 条 | [../../backend/docs/constraints/](../../backend/docs/constraints/) |
| 前端约束集 | Options API / 公共变量 / 异步上下文等 6 条 | [../../frontend/docs/constraints/](../../frontend/docs/constraints/) |

> 路线图遵循"单一真相"原则：架构论述、约束条款已在上述文档中存在的，本路线图只放**索引 + 链接**，不复制全文。详见 [perspectives/README.md](./perspectives/README.md)。

---

## 元信息

| 项目 | 值 |
|------|-----|
| 生成日期 | 2026-07-25（首次）/ 2026-07-26（增量更新：v1.0.6.25~28） |
| 来源 | 首次新建（`docs/roadmap/` 此前不存在）；本次为对 v1.0.6.25~28 五次提交（ratio 治本迁移、高级搜索契约化、Lucide 图标基础设施、Dockerfile 镜像源参数化）的增量同步 |
| 分析范围 | backend/app/* + frontend/src/* + deploy + tests（全栈） |
| 行号依据 | 全部由当前源码 grep / Read 实测，禁止沿用历史文档行号 |
| 覆盖深度 | 第一层（全部）+ 第二层（全部 15 个分支，含 v1.0.6.27 新增 contracts）+ 第三层样例（1 个：torrent_crud.py） |
| 模板版本 | 后端 Python 四节；前端 Vue/TS 四节（适配 Options API + class-component 并存） |
| 本次新增 | `backend/contracts/README.md`（新分支）；更新 services/core/api/infra/tests/deploy/risks/architecture 共 11 个文件 |
