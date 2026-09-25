# BtDeck 版本计划

> **维护约定**: PLANS/ 只保留有后续开发价值的活跃计划；已完成或整体过时的计划移入 [archive/](./archive/)，最终状态与遗留事项见 [archive/README.md](./archive/)。
> **最后更新**: 2026-09-18

## 活跃计划

| 计划 | 范围 | 状态 |
|------|------|------|
| [桌面 Web 中英双语](./desktop-bilingual.md) | M1 核心桌面英文闭环 → M2 全部桌面双语；语言基础、错误标识、系统预设、危险操作及视觉验收 | 🚧 P1～P6-5 已完成（2026-09-18~09-20 dev 主线交付，P6-5 收口含审计门禁翻转），P7 收口与验收准备中；feature `desktop-bilingual-20260918`；2026-09-22 合并注：MCP/MoviePilot 新面双语另立项（见 PLANS/merge-dev107-into-dev.md §8） |
| [MoviePilot 整理联动](./moviepilot-integration.md) | BtDeckBridge 插件（V2）、整理历史只读镜像同步、下载器映射与任务关联查询、设置页/种子详情媒体库页签 | 🚧 第一版闭环落地（2026-09-09 后端/前端/插件代码+自动化测试全绿，66+38 项）；真实宿主联调待部署信息；feature `moviepilot-integration-2026-09-09`；2026-09-22 随 dev1.0.7 合入 dev |
| [MCP 服务与可选能力开放](./mcp-service-capabilities.md) | 同进程 MCP、全局/逐能力开关、统一认证、Tracker/路径脱敏、六项首批工具与 G0～G11 实现门禁 | ✅ 已完成（W0～W4-d 全量交付，四制品黑盒全矩阵 + 12/12 门禁 READY，feature 终态 done）；2026-09-22 随 dev1.0.7 合入 dev |
| [统计数据与报表](./statistics-reports.md) | 统计数据顶级菜单（总览/趋势/做种/Tracker 四页签 13 项正式报表）+ 独立沉浸式趣味报告（火种/勋章/年度报告/白嫖慈善榜）+ 速度时间采样双表与常驻任务 + tracker 计数字段激活 + TR added_date 时区归一 | 🚧 W1 采样数据层 + W2 数据激活与口径修复 + W3 报表服务与端点已完成（2026-09-24 全绿：5342 passed，迁移链尾 c9e0f1a2b3c4）；W4-W7 待实施；feature `statistics-reports-2026-09`，分支 `feature/reports` |
| [双模式客户端](./dual-mode-client.md) | 服务端模式/伴侣客户端模式、安卓壳工程、移动 UI 与发布验收 | 🔶 进行中；feature `v1.0.6-dual-mode-client`（9 task 完成 8，剩 Play/侧载/跨模式发布验收） |
| [前端静态展示 Demo](./frontend-static-showcase-demo.md) | 不依赖真实后端的静态 Demo 构建与独立交付 | 🔶 进行中；feature `frontend-static-showcase-demo-2026-08-23`（7 阶段完成 6，剩 Docker demo 镜像构建与浏览器人工验收） |
| [v1.0.8 数据库升级](./v1.0.8.md) | PostgreSQL 数据源支持（条件演进路线）+ SQLite→PG 迁移 | ⏸️ 暂缓（2026-09-08 决策：数据库源变动暂不处理）。注意：原计划中下载器连接池部分已被 `app.state.store` 缓存 + DownloaderApiRuntime 容量治理覆盖；重启前须先按归档 sync 计划 W5-3 重写对齐当前架构 |
| [dev1.0.7 → dev 分支合并](./merge-dev107-into-dev.md) | 两线（双语完成态 × MCP+MoviePilot）语义合并、迁移链重挂、门禁适配与全量验证 | ✅ 已完成（2026-09-22；含独立审查核验与附录 A） |

## 说明

- v1.0.x 为内部里程碑编号，与产品发布号相互独立（见根 README「版本说明」）。
- 2026-09-08 计划盘点：v1.0.4～v1.0.7、v1.1.0 版本计划与 8 份专项修复计划共 14 份已归档；其中 v1.0.7（路径扫描增强）因引用的基础设施不存在而整体过时，v1.1.0（自动化运维）已被现有定时任务基建事实性覆盖。盘点结论与遗留事项详见 [archive/README.md](./archive/README.md)。
