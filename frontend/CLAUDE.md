# CLAUDE.md - BTDeck前端项目

为Claude Code提供前端开发指导，专注于Vue 2 + TypeScript技术栈。

## 技术栈

- **Node.js**: 18.20.1 | **Vue**: 2.6.12 | **TypeScript**: 4.x
- **UI**: Element UI 2.15.13 | **状态**: Vuex 3.6.2

## 核心约束

### 1. API响应格式规范（强制）

所有API调用必须使用统一响应格式，分页数据字段名严格固定。

→ [详细规范](./docs/constraints/api-response-format.md)

### 2. 代码复用优先

优先复用现有组件和函数，检查>50%相似度可扩展。

→ [详细规范](./docs/constraints/code-reuse.md)

### 3. 公共变量先行

创建新页面/组件前，先检查`styles/variables.scss`是否已有所需变量。

→ [详细规范](./docs/constraints/common-variables.md)

### 4. Vue异步操作中this上下文

在第一个`await`前保存所有需要的`this`属性快照。

→ [详细规范](./docs/constraints/vue-async-context.md)

### 5. 环境变量配置一致性（强制）

开发环境和生产环境的环境变量配置必须保持语义一致性，特别是API版本号。

→ [详细规范](./docs/constraints/environment-consistency.md)

### 6. 列表排序逻辑约束

关键排序逻辑（如活跃种子优先）必须始终生效，不得因用户筛选而禁用。

→ [详细规范](./docs/constraints/list-sorting.md)

## 功能模块

### 通知中心

- **组件**: `src/layout/components/NotificationDrawer/` — 全局右侧抽屉（el-drawer）
- **Vuex**: `src/store/modules/notification.ts` — `NotificationModule`
- **API**: `src/api/notification.ts`
- **触发入口**: Navbar 闹钟图标 → `NotificationModule.ToggleDrawer(true)`
- **轮询**: 60秒轮询 `/notifications/unread-count` 更新徽章数字
- **约束**: 通知中心是全局组件，位于 Layout 层级，不属于任何路由页面。使用 `el-drawer` 从右侧滑出，自带遮罩层。

## 项目结构

```
BtDeck_fronted/
├── src/
│   ├── api/          # API接口定义
│   ├── components/   # 通用组件
│   ├── router/       # 路由配置
│   ├── store/        # Vuex状态管理
│   ├── styles/       # 全局样式
│   ├── utils/        # 工具函数
│   └── views/        # 页面组件
├── package.json
└── vue.config.js
```

## 开发命令

```bash
# 安装依赖
npm install

# 启动开发服务
npm run serve

# 代码检查
npm run lint

# 生产构建
npm run build
```

## 服务端口

- 开发: http://localhost:8080
- 生产: http://localhost:3000
