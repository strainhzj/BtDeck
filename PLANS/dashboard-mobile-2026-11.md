# 仪表盘移动版二期（dashboard-mobile-2026-11）

> **状态**: 已确认执行（2026-11-13 用户拍板：D1–D3 按默认建议；D4 覆盖——**方案文件入库**，随功能提交入仓）
> **日期**: 2026-11-13
> **前置**: 一期 `dashboard-redesign-2026-11` 已交付部署（dev@8db992a 合入），桌面 12 卡全部 props 驱动可移植

## 1. 背景与目标

- 一期改造 desktop-only（PLANS/dashboard-redesign-2026-11.md W1–W5 无移动条目）；移动端 `/m/dashboard` 仍是 Phase 4 时代旧简化页（views/mobile/dashboard.vue，384 行），未消费一期任何新字段（statusBuckets/siteBuckets/tasks.enabled/24h 流量/热门种子）。
- 伴侣 APK 强制 mobile 模式 → APK 用户与一期成果完全绝缘。
- **目标**: 重写 `views/mobile/dashboard.vue` 为纵向卡片流，消费一期同一数据源，**后端零改动**。

## 2. 架构决策（复用优先）

1. **直接复用桌面卡片族**：12 张卡全部 props 驱动纯渲染（调研证实），mobile 页直接 import；卡壳复用 `DashWidget.vue`（编辑态 UI 仅 editing 时渲染，移动端恒 false 天然隐藏）。
2. **样式复用**：页面根节点挂 `dashboard-page` class → 复用 `styles/dashboard-theme.scss` 全部卡片样式；移动专属覆盖（单列流/卡片间距/触控目标）写页面 scoped style。
3. **数据源与桌面一致**：`getDashboardData()`（30s 轮询）+ `getActiveTorrents()`（热门种子/hero 速度）+ `/reports/speed/history?range=24h`（120s）+ `getTaskList`（60s）+ 下拉刷新全量触发。
4. **移动壳约定沿用**：`PullToRefresh` mixin + `m-pull-indicator`；根选择器保持 `.m-dashboard`（e2e mobile-routes/login 断言依赖）。

## 3. 卡片清单（12 裁 9）

| 卡 | 组件 | 数据 | 备注 |
|---|---|---|---|
| KPI 2×2 | KpiCard×4 | dashboard 响应 | 网格外恒显，同桌面语义 |
| 实时脉搏 hero | HeroPulseCard | system 总速度 + active-torrents | 含波浪 canvas（ResizeObserver 自适应） |
| 状态分布环 | StatusDonutCard | torrents.statusBuckets | echarts（共享 chunk，不新增体积） |
| 近 24h 流量 | DailyTrafficCard | /reports/speed/history 分桶 | echarts |
| 站点分布 | SiteBarsCard | torrents.siteBuckets | 纯 CSS hbar |
| 热门种子 Top5 | HotTorrentsCard | active-torrents 速度排序 | 行点击跳 /m/torrents |
| 下载器健康 | InstanceHealthCard | downloader_list | 保留现页"去添加下载器"空态引导 |
| 最近活动 | ActivityTimelineCard | dashboard.activities | 纯 CSS |
| 定时任务 | CronTaskCard | cron 列表 + enabled | "已启用"口径同桌面 |
| ~~速度火花~~ | SpeedSparkCard | — | hero 已覆盖实时速度，裁 |
| ~~吞吐管道~~ | ThroughputTubesCard | — | 装饰性，裁 |
| ~~链路雷达~~ | RadarCard | — | 装饰性，裁 |
| ~~快捷操作~~ | QuickActionsCard | — | tabbar/抽屉已覆盖导航，裁 |

**明确不做**：预设切换/编辑模式/拖拽排序/列宽循环/布局持久化（移动端固定单列流，无这些交互）。

## 4. 轮询与生命周期

- 间隔：dashboard 30s / active 3s / tasks 60s / traffic 120s（照搬桌面常量；**待确认**是否移动端放宽 active 至 5s 省电）
- 下拉刷新：并发触发全部 fetch
- `beforeDestroy` 全量清理定时器 + hero 卡自带 ResizeObserver 自清理（组件内已处理）

## 5. i18n

- 卡片内部文案：桌面已有键直接复用（DashWidget title 走 `$t('dashboard.widgets.*.title')`）
- 页面级新键（如空态引导文案调整）：zh/en 双语同步新增，过 i18n-leftover-guard

## 6. 验证与交付

- 新增 `tests/unit/mobile-dashboard.spec.ts`：挂载渲染/props 映射/下拉刷新/定时器清理/热门种子跳转
- e2e 根选择器 `.m-dashboard` 不变，mobile-routes.spec 兼容
- 门禁：typecheck + `npm run lint` 净增 0（基线 280 口径）+ 全量 Jest 不回退 + `npm run build` 成功且 echarts 体积预算复核
- 分支 `feature/dashboard-mobile-2026-11`（基于 origin/dev）；feature_list.json 登记 + progress.md 记录 + roadmap 同步（views/mobile 行）
- 方案文件按一期先例**仅本地留存不入库**（待用户确认）

## 7. 待确认决策点

| # | 决策点 | 默认建议 |
|---|---|---|
| D1 | active 轮询间隔 | 照搬 3s（与桌面一致，数据实时性优先） |
| D2 | 下载器卡复用 InstanceHealthCard（桌面一致视觉）+ 保留移动空态引导 | 是 |
| D3 | 卡片清单裁剪方案（上表） | 按表执行 |
| D4 | 方案文件本地留存不入库 | 是（一期先例） |
