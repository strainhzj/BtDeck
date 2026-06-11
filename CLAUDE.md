# CLAUDE.md - BTDeck全栈项目

为Claude Code提供项目整体认知和开发指导，专注于前后端协同和系统集成。

## 项目定位

**BTDeck**是统一管理多种BitTorrent客户端(qBittorrent、Transmission)的全栈Web应用。

- **前端**: Vue 2 + TypeScript + Element UI
- **后端**: FastAPI + Python + SQLAlchemy
- **目录**: 前端(`frontend/`) 后端(`backend/`)

## 核心工作约束

### 1. 代码简洁性原则

追求代码简洁、模块化、可复用，遵循KISS/DRY/YAGNI原则。

### 2. 交互模式（必读）

🔴 **开始任务前，必须先提出实现假设并获得确认**

- 分析需求，提出实现假设（框架、架构、文件）
- 检查假设间的矛盾关系
- **等待用户确认后再开始编码**

### 3. 问题澄清机制

❓ **遇到不清楚的细节时，主动提问获取补充信息**

- 需求模糊或存在歧义时提问
- 多种实现方案时，列出优劣并推荐
- 涉及架构变更时必须确认

### 4. Git操作规范

🔧 **全栈统一仓库管理，Git操作在根目录执行**

```bash
# 前端相关变更
git add frontend/ && git commit -m "feat(frontend): xxx"

# 后端相关变更
git add backend/ && git commit -m "feat(backend): xxx"

# 全栈/部署相关变更
git add deploy/ docker-compose.yml && git commit -m "feat(deploy): xxx"
```

## 功能模块索引

### 通知中心

- **性质**: 系统单向信箱（非实时消息），系统写入通知记录，用户在通知中心查看
- **触发入口**: 右上角闹钟图标（`el-icon-alarm-clock`）→ 右侧 `el-drawer` 抽屉
- **通知类型**: `version_update`（版本更新）、`system`（系统通知）
- **版本检查**: 启动时查询 GitHub Release API，发现新版本自动插入通知记录
- **未读轮询**: 前端 60 秒轮询 `/api/v1/notifications/unread-count`
- **后端路由前缀**: `/api/v1/notifications`
- **前端 Vuex 模块**: `notification`（`src/store/modules/notification.ts`）

## 项目级文档

- [后端开发规范](./backend/CLAUDE.md) - FastAPI + Python技术栈约束
- [前端开发规范](./frontend/CLAUDE.md) - Vue 2 + TypeScript技术栈约束

## 快速启动

### 后端
```bash
cd backend
conda activate btpManager
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001
```

### 前端
```bash
cd frontend
npm run serve
```

### Docker
```bash
docker compose up -d --build
```

访问: http://localhost:8080 | API文档: http://localhost:5001/docs
