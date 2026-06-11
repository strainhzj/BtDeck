# BTDeck 前端项目

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Node Version](https://img.shields.io/badge/node-18.20.1-brightgreen)](https://nodejs.org/)
[![Vue Version](https://img.shields.io/badge/vue-2.6.12-brightgreen)](https://vuejs.org/)

基于 Vue 2 + TypeScript + Element UI 的 BitTorrent 管理器前端应用。

## 📋 项目简介

BTDeck 是一个全栈 Web 应用，为用户提供多种 BitTorrent 客户端（qBittorrent、Transmission）的统一管理界面。

### 核心特性

- 🎯 **多下载器统一管理** - 支持 qBittorrent 和 Transmission
- 📊 **实时状态监控** - WebSocket 实时推送下载器状态
- 🔄 **后台任务调度** - 自动化下载管理
- 🔐 **安全认证** - JWT + TOTP 二次验证
- 📱 **响应式设计** - 支持移动设备访问
- 🎨 **Element UI** - 完整的管理后台组件库

### 技术栈

- **框架**: Vue 2.6.12 + TypeScript
- **UI组件**: Element UI 2.15.13
- **状态管理**: Vuex 3.6.2 (使用 vuex-module-decorators)
- **路由管理**: Vue Router 3.5.3
- **HTTP客户端**: Axios 0.27.2
- **代码编辑器**: Monaco Editor 0.34.1
- **构建工具**: Vue CLI 4.5.12
- **Node.js**: 18.20.1 (开发环境)

## 🚀 快速开始

### 环境要求

- Node.js 18.20.1
- npm 或 yarn

### 安装依赖

```bash
npm install
```

### 开发环境运行

```bash
npm run serve
```

访问 http://localhost:8080

### 生产环境构建

```bash
npm run build
```

构建产物在 `dist/` 目录，可部署到 nginx 等 Web 服务器。

### 代码检查

```bash
# ESLint 检查
npm run lint

# ESLint 自动修复
npm run lint:fix
```

### 运行测试

```bash
# 单元测试
npm run test:unit

# 集成测试
npm run test:integration

# 端到端测试 (Playwright)
npm run test:playwright

# 运行所有测试
npm run test:all
```

## 📁 项目结构

```
BtDeck_frontend/
├── public/              # 静态资源
├── src/
│   ├── api/            # API 接口定义
│   ├── components/     # 通用组件
│   ├── router/         # 路由配置
│   ├── store/          # Vuex 状态管理
│   ├── styles/         # 全局样式
│   ├── utils/          # 工具函数
│   ├── views/          # 页面组件
│   ├── App.vue         # 根组件
│   ├── main.ts         # 入口文件
│   └── permission.ts   # 路由守卫
├── package.json        # 依赖配置
├── tsconfig.json       # TypeScript 配置
├── vue.config.js       # Vue CLI 配置
└── CLAUDE.md          # 开发指导文档
```

## 📜 更新日志

### v1.0.3 (2026-04-21)

#### 📝 项目更新

- 统一项目命名为 BTDeck，移除 btpManager 相关字眼
- 优化项目文档结构
- 更新依赖项版本

---

## 🔧 开发配置

### 环境变量

```bash
# 开发环境 (.env.development)
VUE_APP_BASE_API=http://localhost:5001
VUE_APP_TITLE=BitTorrent管理器

# 生产环境 (.env.production)
VUE_APP_BASE_API=/api
VUE_APP_TITLE=BitTorrent管理器
```

### 服务端口

- **开发服务**: http://localhost:8080
- **生产服务**: http://localhost:3000

### API 代理

开发环境自动代理 API 请求到后端服务器 http://localhost:5001

## 📖 开发文档

详细的开发指南请参考 [CLAUDE.md](./CLAUDE.md)

### 核心文档

- **项目认知框架** - 了解项目定位和核心价值
- **开发工作约束** - 代码简洁性原则、交互模式、代码复用
- **前端常见陷阱** - Vue 异步操作、组件复用、设计债务
- **前端架构** - 技术栈、项目结构、认证系统
- **开发工作流** - 启动、构建、部署流程

### API 响应格式规范

所有后端 API 接口遵循统一响应格式：

```typescript
interface APIResponse<T = any> {
  code: string;      // 状态码 (200, 401, 403, 422, 500)
  msg: string;       // 接口返回信息
  data: T;           // 接口返回数据
  status: string;    // 接口返回状态描述
}
```

**分页响应格式**（强制规范）：

```typescript
export interface PaginatedResponse<T> {
  total: number      // 总记录数
  page: number       // 当前页码
  pageSize: number   // 每页记录数 (必须使用 pageSize)
  list: T[]          // 数据列表 (必须使用 list)
}
```

## 🎨 核心功能模块

### 认证和权限系统

- **Token 认证**: 使用 `X-Access-Token` 请求头进行 JWT 认证
- **权限控制**: 路由守卫和权限验证
- **用户状态**: Vuex 管理用户信息和登录状态
- **重定向机制**: 未登录用户自动跳转到登录页面

### HTTP 请求架构

- **统一实例**: axios 实例和拦截器配置
- **拦截器**: 自动处理 token、错误响应和加载状态
- **错误处理**: 统一处理 API 响应格式

### 状态管理

- **装饰器模式**: 使用 vuex-module-decorators
- **动态注册**: 支持模块的动态加载
- **类型安全**: TypeScript 接口定义

### 路由系统

- **布局路由**: 基于布局的嵌套路由结构
- **懒加载**: 组件按需加载
- **权限守卫**: 基于用户权限的访问控制

## 🔐 安全机制

- JWT Token 认证
- TOTP 二次验证
- XSS 防护
- CSRF 防护
- 输入验证

## 🧪 测试策略

- **单元测试**: 组件逻辑、工具函数
- **集成测试**: 完整的前后端交互链路
- **端到端测试**: 使用 Playwright 进行 E2E 测试

## 📦 部署

### 构建生产版本

```bash
npm run build
```

### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /path/to/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 🤝 协作开发

### Git 工作流

```bash
# 1. 查看当前状态
git status

# 2. 添加修改的文件
git add .

# 3. 提交代码（使用约定式提交格式）
git commit -m "feat: 添加XX功能"

# 4. 推送到远程仓库
git push origin feature-branch
```

### 提交信息格式

```
feat: 新增功能
fix: 修复bug
docs: 文档更新
style: 代码格式调整
refactor: 重构代码
test: 测试相关
chore: 构建/工具链更新
```

## 📝 开发规范

- 遵循 [CLAUDE.md](./CLAUDE.md) 中的开发指导
- 代码提交前确保通过 ESLint 检查
- 优先复用现有组件和工具函数
- 遵循 KISS、DRY、YAGNI 原则

## 🔗 相关项目

- **后端项目**: [BtDeck](../BtDeck/)
- **主项目**: [BtDeck_full_stack](../)

## 📄 许可证

本项目采用 **GNU General Public License v3.0** 许可证。

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)

### 核心要点

- ✅ **自由使用** - 可以自由使用、研究、修改软件
- ✅ **自由分享** - 可以自由分发原始版本和修改版本
- ⚠️ **开源义务** - 修改和衍生作品必须同样使用 GPL v3 开源
- ⚠️ **提供源码** - 分发时必须提供完整的源代码
- ❌ **禁止闭源** - 不得将软件闭源后分发

完整许可证文本请参阅 [LICENSE](./LICENSE) 文件。

---

**开发协作**: 前端开发人员应共同维护文档，及时更新架构变更和最佳实践。
**问题反馈**: 遇到文档未覆盖的场景，请记录并更新，确保团队知识积累。
