# AGENTS.md - BTDeck 前端项目

> **项目**: BTDeck 前端应用
> **技术栈**: Vue 2.6.12 | TypeScript 4.x | Element UI 2.15.13 | Vuex 3.6.2
> **更新**: 2026-05-27

---

## 项目定位

BTDeck 前端提供统一的 BitTorrent 客户端管理界面，支持种子管理、下载器配置、实时监控等功能。

---

## 启动工作流

开始任何工作前，按顺序执行：

```text
1. 阅读 AGENTS.md（本文件）
2. 阅读 CLAUDE.md（前端技术约束）
3. 阅读 docs/constraints/（详细规范）
4. 阅读 feature_list.json（功能状态）
5. 阅读 PROGRESS.md（会话上下文）
6. 运行 ./scripts/init.sh（验证环境）
```

---

## 工作规则

### 1. Vue 2 Options API（强制）

必须使用 Options API 风格，禁止 Vue 3 Composition API 和 `<script setup>`。

### 2. API 响应格式处理（强制）

统一响应格式：`{ status, msg, code, data }`
分页字段名固定：`list`/`total`/`pageSize`

详见 `docs/constraints/api-response-format.md`

### 3. TypeScript 类型定义（强制）

禁止使用 `any`，所有 Props/Data/Computed 必须有完整类型定义。

### 4. 异步操作中的 this 上下文（强制）

在第一个 `await` 前保存所有需要的 `this` 属性快照。

详见 `docs/constraints/vue-async-context.md`

### 5. 定时器清理（强制）

必须在 `beforeDestroy` 中清理所有 `setInterval`/`setTimeout`。

### 6. 代码复用优先

检查 `src/components/` 和 `src/utils/` 是否有现成组件/函数，相似度 >50% 可扩展。

详见 `docs/constraints/code-reuse.md`

### 7. 公共变量优先

创建组件前先检查 `styles/variables.scss` 是否已有所需变量。

详见 `docs/constraints/common-variables.md`

### 8. 列表排序逻辑约束

关键排序逻辑（如活跃种子优先）必须始终生效，不得因用户筛选而禁用。

详见 `docs/constraints/list-sorting.md`

### 9. 环境变量配置一致性（强制）

开发环境和生产环境的环境变量配置必须保持语义一致性。

详见 `docs/constraints/environment-consistency.md`

---

## 功能模块索引

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

---

## 项目结构

```text
BtDeck_fronted/
├── src/
│   ├── api/                       # API接口定义 (13个模块)
│   │   ├── torrents.ts            # 种子相关 API
│   │   ├── downloader.ts          # 下载器 API
│   │   ├── notification.ts        # 通知 API
│   │   └── types.d.ts             # 公共类型定义
│   ├── components/                # 通用组件
│   │   ├── torrents/              # 种子相关组件 (9个)
│   │   ├── tasks/                 # 任务相关组件 (3个)
│   │   ├── BatchButton.vue        # 批量操作按钮
│   │   ├── Pagination/            # 分页组件
│   │   └── MonacoEditor.vue       # 代码编辑器
│   ├── layout/components/         # 布局组件
│   │   ├── Navbar/                # 导航栏
│   │   ├── NotificationDrawer/    # 通知抽屉
│   │   └── Sidebar/               # 侧边栏
│   ├── views/                     # 页面组件 (11个模块)
│   │   ├── torrents/              # 种子管理
│   │   │   ├── index.vue          # 种子列表主组件
│   │   │   └── components/        # 10个操作对话框
│   │   ├── downloader/            # 下载器管理
│   │   ├── dashboard/             # 仪表盘
│   │   ├── tracker/               # Tracker管理
│   │   ├── recycle-bin/           # 回收站
│   │   ├── tasks/                 # 定时任务
│   │   └── logs/                  # 审计日志
│   ├── store/modules/             # Vuex模块 (4个)
│   │   ├── app.ts                 # 应用状态
│   │   ├── user.ts                # 用户状态
│   │   ├── notification.ts        # 通知状态
│   │   └── downloaderSettings.ts  # 下载器设置
│   ├── router/                    # 路由配置
│   ├── styles/                    # 全局样式
│   │   ├── variables.scss         # 公共变量
│   │   └── mixins.scss            # 公共 mixin
│   ├── utils/                     # 工具函数
│   └── main.js                    # 应用入口
├── scripts/
│   ├── init.sh                    # 初始化脚本
│   └── lint-vuex-action.js        # Vuex action 检查
├── docs/constraints/              # 约束文档 (6个)
├── package.json
├── tsconfig.json
└── vue.config.js
```

---

## 验证命令

```bash
# 环境验证
./scripts/init.sh

# 代码检查
npm run lint

# TypeScript 检查
# npm run check (如已配置)

# 生产构建验证
npm run build

# 运行测试
npm run test:unit

# Vuex action 规范检查
npm run lint:vuex-action
```

---

## 必需文件

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `AGENTS.md` | 前端工作流（本文件） | 稳定 |
| `CLAUDE.md` | 前端技术约束 | 稳定 |
| `feature_list.json` | 功能状态追踪 | 每次会话 |
| `PROGRESS.md` | 会话进度日志 | 每次会话 |
| `session-handoff.md` | 会话交接模板 | 每次会话结束 |
| `scripts/init.sh` | 环境验证脚本 | 稳定 |

### 约束文档（`docs/constraints/`）

| 文件 | 约束内容 | 适用场景 |
|------|----------|----------|
| `api-response-format.md` | API 统一响应格式、分页字段名 | 调用/解析任何 API 时 |
| `code-reuse.md` | 代码复用优先原则、>50% 相似度扩展 | 创建新组件/函数前 |
| `common-variables.md` | 公共 CSS 变量先行、禁止硬编码颜色值 | 编写样式时 |
| `vue-async-context.md` | Vue 2 异步操作 this 上下文丢失问题 | 编写 async 方法时 |
| `environment-consistency.md` | 开发/生产环境变量一致性 | 修改环境配置时 |
| `list-sorting.md` | 列表排序逻辑约束 | 修改列表排序时 |

---

## 会话结束清单

```text
1. 更新 PROGRESS.md（记录完成的工作和决策）
2. 更新 feature_list.json（更新功能状态）
3. 填写 session-handoff.md（交接信息）
4. 验证仓库状态（./scripts/init.sh 通过）
5. Git 提交（仅在用户要求时，在 BtDeck_fronted/ 目录内执行）
```

---

**最后更新**: 2026-05-27
