# Progress Log - BTDeck 前端

> **项目**: BTDeck 前端应用
> **当前分支**: dev
> **更新**: 2026-05-27

---

## 进行中功能

### v1.0.4 实时速度监控 (in-progress) — dev 分支

**计划文件**: `PLANS/v1.0.4.md`

**与计划的偏差**:
- 计划: `setup()` + Composition API → 实际: **Options API** + 虚拟分页
- 计划: 10秒/10分钟双定时器 → 实际: 1秒单定时器轮询

**已完成任务** (2/2):

| 任务 | 状态 | 说明 |
|------|------|------|
| 前端 API 封装 | done | `torrents.ts` getActiveTorrents() |
| 前端种子列表改造 | done | Options API + 虚拟分页 + 1秒轮询 + beforeDestroy清理 |

**关键实现**:
- `activeSpeedMap` 缓存速度数据
- 虚拟分页算法：活跃种子优先排列
- 防抖 + 版本控制避免重复请求

**结论**: v1.0.4 前端开发完成，待合并 master。

---

## 计划外已完成功能

### 通知中心 (done) — dev 分支

- `NotificationDrawer/index.vue` - 全局右侧抽屉
- `NotificationDrawer/NotificationItem.vue` - 通知项组件
- `store/modules/notification.ts` - Vuex 通知模块
- `api/notification.ts` - 通知 API
- 60秒未读计数轮询

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
| 2026-04-22 | Options API 而非 Composition API | 项目技术栈约定 |
| 2026-04-22 | 前端虚拟分页 | 已有查询逻辑，前端合并更灵活 |
| 2026-04-22 | 防抖+版本控制 | 避免1秒轮询导致重复请求和页面卡顿 |

---

## 当前会话

> 无活跃开发任务

---

**最后更新**: 2026-05-27
