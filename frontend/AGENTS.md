# AGENTS.md - BtDeck 前端（端规则指针）

> **技术栈**: Vue 2.6.12 | TypeScript 4.x | Element UI 2.15.13 | Vuex 3.6.2
> **更新**: 2026-06-18

本文件是前端规则指针。**全栈工作流、Git 规范、功能状态、进度日志统一在根目录**（`../AGENTS.md`、`../feature_list.json`、`../progress.md`），本文件不再重复，亦不回指根目录工作流。

---

## 前端工作流入口

前端开发时，按顺序：

```text
1. 先读 ../AGENTS.md（全栈工作流与跨端规则）
2. 读本文件（前端模块索引 + 约束入口）
3. 读 CLAUDE.md（前端技术约束）
4. 读 docs/constraints/（前端详细规范）
5. 读 ../feature_list.json（全栈功能状态，前端任务 file 前缀 src/）
6. 读 ../progress.md（全栈进度日志）
7. 运行 ../init.sh 或 ./scripts/init.sh（环境验证）
```

> 注：全栈启动工作流的权威定义在 `../AGENTS.md`，本处仅给出前端视角的入口指引。

---

## 前端工作规则（强制）

### 1. Vue 2 Options API

必须使用 Options API 风格，禁止 Vue 3 Composition API 和 `<script setup>`。

### 2. API 响应格式处理

统一响应格式：`{ status, msg, code, data }`，分页字段名固定：`list`/`total`/`pageSize`。详见 `docs/constraints/api-response-format.md`

### 3. TypeScript 类型定义

禁止使用 `any`，所有 Props/Data/Computed 必须有完整类型定义。

### 4. 异步操作中的 this 上下文

在第一个 `await` 前保存所有需要的 `this` 属性快照。详见 `docs/constraints/vue-async-context.md`

### 5. 定时器清理

必须在 `beforeDestroy` 中清理所有 `setInterval`/`setTimeout`。

### 6. 代码复用优先

检查 `src/components/` 和 `src/utils/` 是否有现成组件/函数，相似度 >50% 可扩展。详见 `docs/constraints/code-reuse.md`

### 7. 公共变量优先

创建组件前先检查 `styles/variables.scss` 是否已有所需变量。详见 `docs/constraints/common-variables.md`

### 8. 列表排序逻辑约束

关键排序逻辑（如活跃种子优先）必须始终生效，不得因用户筛选而禁用。详见 `docs/constraints/list-sorting.md`

### 9. 环境变量配置一致性

开发环境和生产环境的环境变量配置必须保持语义一致性。详见 `docs/constraints/environment-consistency.md`

---

## 前端功能模块索引

| 模块 | 页面 | 组件目录 | API 文件 | Vuex 模块 |
|------|------|----------|----------|-----------|
| 种子管理 | `views/torrents/` | `components/torrents/` (9个组件) | `api/torrents.ts` | - |
| 种子操作 | `views/torrents/components/` (10个对话框) | - | - | - |
| 下载器管理 | `views/downloader/` | - | `api/downloader.ts` | - |
| 仪表盘 | `views/dashboard/` | - | `api/dashboard.ts` | - |
| 回收站 | `views/recycle-bin/` | - | `api/recycle-bin.ts` | - |
| Tracker | `views/tracker/` | - | `api/tracker.ts` | - |
| 定时任务 | `views/tasks/` | `components/tasks/` (3个组件) | `api/tasks.ts` | - |
| 通知中心 | Layout层 `NotificationDrawer/` | `NotificationItem.vue` | `api/notification.ts` | `store/modules/notification.ts` |
| 标签管理 | - | - | `api/tag-management.ts` | - |
| 用户设置 | - | - | `api/users.ts` | `store/modules/user.ts` |
| 审计日志 | `views/logs/` | - | `api/audit-logs.ts` | - |
| **查询模板 (v1.0.5)** | `views/query-templates/` (待建) | `views/query-templates/components/` (待建) | `api/query-templates.ts` (待建) | - |

> 跨端模块（前后端协同）的总览见 `../AGENTS.md` 功能模块索引。

---

## 前端项目结构

```text
frontend/
├── src/
│   ├── api/                       # API接口定义 (13个模块)
│   ├── components/                # 通用组件
│   ├── layout/components/         # 布局组件（Navbar/Sidebar/NotificationDrawer）
│   ├── views/                     # 页面组件 (11个模块)
│   ├── store/modules/             # Vuex模块 (app/user/notification/downloaderSettings)
│   ├── router.ts                  # 路由配置（单文件，集中式 routes 数组）
│   ├── styles/                    # 全局样式（variables.scss / mixins.scss）
│   ├── utils/                     # 工具函数（request.ts API 基础地址）
│   └── main.js                    # 应用入口
├── scripts/
│   ├── init.sh                    # 端环境验证（支持 --ci）
│   └── lint-vuex-action.js        # Vuex action 检查
├── docs/constraints/              # 约束文档 (6个)
├── package.json
├── tsconfig.json
└── vue.config.js
```

---

## 前端验证命令

```bash
# 端环境验证（默认：安装依赖 + 验证）
./scripts/init.sh

# 端环境验证（轻量，不安装依赖，被根 init.sh 调用）
./scripts/init.sh --ci

# 代码检查
npm run lint

# 生产构建验证
npm run build

# 运行测试
npm run test:unit

# Vuex action 规范检查
npm run lint:vuex-action
```

---

## 前端约束文档（`docs/constraints/`）

| 文件 | 适用场景 |
|------|----------|
| `api-response-format.md` | 调用/解析任何 API 时 |
| `code-reuse.md` | 创建新组件/函数前 |
| `common-variables.md` | 编写样式时 |
| `vue-async-context.md` | 编写 async 方法时 |
| `environment-consistency.md` | 修改环境配置时 |
| `list-sorting.md` | 修改列表排序时 |

---

**最后更新**: 2026-06-18
