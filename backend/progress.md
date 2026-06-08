# Progress Log - BTDeck 后端

> **项目**: BTDeck 后端服务
> **当前分支**: dev
> **更新**: 2026-05-27

---

## 进行中功能

### v1.0.4 实时速度监控 (in-progress) — dev 分支

**计划文件**: `PLANS/v1.0.4.md`

**与计划的偏差**:
- 计划: `TorrentStateManager` 动静数据分离(10s/10min刷新) → 实际: 轻量级 `active-torrents` 接口 + 前端1秒轮询
- 计划: `speed-all` API → 实际: `active-torrents` API（仅返回有速度的种子）
- 额外完成: 种子完成后自动更新数据库状态、活跃种子进度字段

**已完成任务** (11/11):

| 任务 | 状态 | 说明 |
|------|------|------|
| 后端活跃种子速度接口 | done | `torrent_speed.py`, qB用status_filter, tr仅查速度字段 |
| 后端路由注册 | done | `/torrents/active-torrents` |
| 线程池泄漏修复 | done | commit 25c59aa |
| 速度单位转换修复 | done | commit d79040d |
| Transmission空列表修复 | done | commit b4ddde2 |
| 活跃种子进度字段 | done | commit a568aa9, progress字段(0-100百分比) |
| 种子完成后自动更新状态 | done | commit f8b0185, progress达100%自动更新为completed |
| 性能测试 | done | 4下载器并发平均543ms |
| 场景测试 | done | 8个验收场景通过 |

**结论**: v1.0.4 后端开发完成，待合并 master。

---

## 计划外已完成功能

### 通知中心 (done) — dev 分支

- `notification.py` - Notification 模型
- `notification_service.py` - 通知服务（版本检查、未读计数）
- `notifications.py` - API 端点 (GET/PUT/DELETE)
- 版本更新通知内容优化
- 标记未读功能

### Tracker关键词池初始化 (done) — dev 分支

- `tracker_keywords_pools.py` - 关键词池管理
- 默认数据自动初始化
- 集成到 `init_db()` 统一初始化流程

### 统一初始化重构 (done) — dev 分支

- 所有初始数据初始化统一到 `init_db()`
- 集成到后端启动流程

---

## 待开发功能（按计划顺序）

| 版本 | 名称 | 计划文件 | 状态 |
|------|------|----------|------|
| v1.0.5 | 查询模板系统 | PLANS/v1.0.5.md | pending |
| v1.0.6 | 孤儿文件管理 | PLANS/v1.0.6.md | pending |
| v1.0.7 | 路径扫描增强 | PLANS/v1.0.7.md | pending |
| v1.0.8 | 数据库升级 | PLANS/v1.0.8.md | pending |
| v1.0.9 | 一键部署 | PLANS/v1.0.9.md | pending |
| v1.1.0 | 自动化运维 | PLANS/v1.1.0.md | pending |

---

## 技术决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-04-22 | 轻量级active-torrents替代动静分离 | 更简单，前端1秒轮询仅查有速度种子 |
| 2026-04-22 | 前端虚拟分页 | 已有查询逻辑，前端合并更灵活 |
| 2026-04-22 | 专用线程池 | 避免阻塞默认executor |
| 2026-04-22 | 统一初始化到 init_db() | 集中管理初始数据 |

---

## 当前会话

> 无活跃开发任务

---

**最后更新**: 2026-05-27
