# AGENTS.md - BtDeck 全栈项目

> **项目**: BtDeck - BitTorrent 客户端统一管理平台
> **仓库**: 全栈 monorepo（`backend/` + `frontend/` + `deploy/`）
> **当前开发版本**: v1.0.5（查询模板系统）
> **更新**: 2026-06-18

本文件是全栈代理路由层。端特定技术约束见各端 `AGENTS.md`（**端 AGENTS.md 不再回指本文件**，避免循环跳转）。

---

## 启动工作流

开始任何工作前，按顺序执行：

```text
1. 阅读 AGENTS.md（本文件，全栈工作流与规则）
2. 阅读 feature_list.json（功能状态，current_dev_version 指向当前版本）
3. 阅读 progress.md（会话上下文）
4. 阅读相关端 AGENTS.md + CLAUDE.md + docs/constraints/
   - 后端工作: backend/AGENTS.md → backend/CLAUDE.md → backend/docs/constraints/
   - 前端工作: frontend/AGENTS.md → frontend/CLAUDE.md → frontend/docs/constraints/
5. 阅读 PLANS/<当前版本>.md（如 PLANS/v1.0.5.md）
6. 查阅代码细节时进入 docs/roadmap/（三层渐进式路线图：模块路由 → 分支文件清单 → 源文件方法签名）
7. 运行 ./init.sh（全栈环境验证，默认 --ci 轻量模式）
```

---

## 工作规则

### 1. 全栈统一仓库，Git 操作在根目录执行（强制）

```bash
git add backend/   && git commit -m "feat(backend): xxx"
git add frontend/  && git commit -m "feat(frontend): xxx"
git add deploy/ docker-compose.yml && git commit -m "feat(deploy): xxx"
git add .          && git commit -m "feat: xxx"   # 跨端/全栈变更
```

### 2. API 响应格式统一（强制）

所有 API 必须使用统一响应格式，分页字段名严格固定为 `list`/`total`/`pageSize`。
- 后端详见 `backend/docs/constraints/api-response-format.md`
- 前端详见 `frontend/docs/constraints/api-response-format.md`

### 3. 数据库迁移管理（强制）

所有 Schema 变更必须通过 Alembic 管理，应用启动时自动执行迁移。
详见 `backend/docs/constraints/database-migration.md`

### 4. 下载器连接管理（强制）

必须使用 `app.state.store` 缓存中的客户端连接，严禁重复创建。
详见 `backend/docs/constraints/downloader-connection.md`

### 5. Vue 2 Options API（强制）

前端必须使用 Options API 风格，禁止 Vue 3 Composition API 和 `<script setup>`。
详见 `frontend/docs/constraints/`

### 6. 代码复用优先

检查相似度 >50% 可扩展现有代码，而非新建。
- 后端: `backend/docs/constraints/code-reuse.md`
- 前端: `frontend/docs/constraints/code-reuse.md`

### 7. 交互模式（必读）

🔴 **开始任务前，必须先提出实现假设并获得确认**
❓ **遇到不清楚的细节时，主动提问获取补充信息**

---

## 功能模块索引

### 跨端模块（前后端协同）

| 模块 | 后端 | 前端 |
|------|------|------|
| 种子管理 | `app/api/endpoints/torrent_crud.py` | `views/torrents/index.vue` |
| 种子速度 | `app/api/endpoints/torrent_speed.py` | `api/torrents.ts` getActiveTorrents() |
| 种子删除 | `app/api/endpoints/torrent_deletion.py` | `views/torrents/components/` |
| 下载器管理 | `app/api/endpoints/downloader.py` | `views/downloader/` |
| Tracker | `app/api/endpoints/tracker.py` | `views/tracker/` |
| 回收站 | `app/api/endpoints/recycle_bin.py` | `views/recycle-bin/` |
| 通知中心 | `app/api/endpoints/notifications.py` | `layout/components/NotificationDrawer/` |
| 仪表盘 | `app/api/endpoints/dashboard.py` | `views/dashboard/` |
| 审计日志 | `app/api/endpoints/audit_logs.py` | `views/logs/` |
| 定时任务 | `app/api/endpoints/cron_tasks.py` | `views/tasks/` |
| 标签管理 | `app/api/endpoints/tag_management.py` | `api/tag-management.ts` |
| **查询模板 (v1.0.5)** | `app/api/endpoints/query_templates.py` (待建) | `views/query-templates/` (待建) |

### 端特定模块（详见各端 AGENTS.md 模块索引）

- 后端独有: 种子同步/备份/位置、下载器设置/能力/路径维护、Tracker关键词/重宣告、种子转移、设置模板、速度调度、高级搜索
- 前端独有: 用户设置、传统视图模式

---

## 验证命令

```bash
# 全栈环境验证（轻量，不安装依赖）
./init.sh

# 全栈环境验证（含依赖安装 + lint，首次或 CI 用）
./init.sh --full

# 后端单独验证
cd backend && ./scripts/init.sh

# 前端单独验证
cd frontend && ./scripts/init.sh

# 后端测试
cd backend && pytest

# 前端构建
cd frontend && npm run build
```

---

## 完成定义（Definition of Done）

一个功能/任务完成当且仅当：

- [ ] 实现完成（覆盖 feature_list.json 中该任务声明的所有 file）
- [ ] 后端: mypy + black + flake8 通过；相关 pytest 通过
- [ ] 前端: npm run lint 通过；TypeScript 类型完整（禁止 any）
- [ ] API 文档更新（如有新端点）
- [ ] evidence 记录到 feature_list.json 对应 task
- [ ] progress.md 更新
- [ ] 仓库可重启（./init.sh 通过）

---

## 必需文件（全栈统一，根目录）

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `AGENTS.md` | 全栈路由层（本文件） | 稳定 |
| `feature_list.json` | 全栈功能状态追踪 | 每次会话 |
| `progress.md` | 全栈会话进度日志 | 每次会话 |
| `session-handoff.md` | 全栈会话交接模板 | 每次会话结束 |
| `init.sh` | 全栈环境验证入口 | 稳定 |
| `HARNESS_GUIDE.md` | Harness 实施指南 | 按需 |

各端另有 `AGENTS.md`（端规则指针）、`CLAUDE.md`（端技术约束）、`docs/constraints/`（端详细规范）、`scripts/init.sh`（端环境验证，被根 init.sh 复用）。

---

## 会话结束清单

```text
1. 更新 progress.md（记录完成的工作和决策）
2. 更新 feature_list.json（更新任务 status 与 evidence）
3. 填写 session-handoff.md（交接信息）
4. 验证仓库状态（./init.sh 通过）
5. Git 提交（仅在用户要求时，在仓库根目录执行）
```

---

**最后更新**: 2026-06-18
