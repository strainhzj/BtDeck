# BtDeck 版本计划

> **维护约定**: PLANS/ 只保留有后续开发价值的活跃计划；已完成或整体过时的计划移入 [archive/](./archive/)，最终状态与遗留事项见 [archive/README.md](./archive/README.md)。
> **最后更新**: 2026-09-08

## 活跃计划

| 计划 | 范围 | 状态 |
|------|------|------|
| [MCP 服务与可选能力开放](./mcp-service-capabilities.md) | 同进程 MCP、全局/逐能力开关、统一认证、Tracker/路径脱敏、六项首批工具与 G0～G11 实现门禁 | 🚧 实施中（2026-09-08 W0 契约/选型 + W1 配置控制面（fail-closed/CAS/kill switch/设置 UI）落地；下一步 W2 挂载与认证接线；工具 0/6、Gate 0/12 PASS）；feature `mcp-service-capabilities-2026-08-28` |
| [双模式客户端](./dual-mode-client.md) | 服务端模式/伴侣客户端模式、安卓壳工程、移动 UI 与发布验收 | 🔶 进行中；feature `v1.0.6-dual-mode-client`（9 task 完成 8，剩 Play/侧载/跨模式发布验收） |
| [前端静态展示 Demo](./frontend-static-showcase-demo.md) | 不依赖真实后端的静态 Demo 构建与独立交付 | 🔶 进行中；feature `frontend-static-showcase-demo-2026-08-23`（7 阶段完成 6，剩 Docker demo 镜像构建与浏览器人工验收） |
| [v1.0.8 数据库升级](./v1.0.8.md) | PostgreSQL 数据源支持（条件演进路线）+ SQLite→PG 迁移 | ⏸️ 暂缓（2026-09-08 决策：数据库源变动暂不处理）。注意：原计划中下载器连接池部分已被 `app.state.store` 缓存 + DownloaderApiRuntime 容量治理覆盖；重启前须先按归档 sync 计划 W5-3 重写对齐当前架构 |

## 说明

- v1.0.x 为内部里程碑编号，与产品发布号相互独立（见根 README「版本说明」）。
- 2026-09-08 计划盘点：v1.0.4～v1.0.7、v1.1.0 版本计划与 8 份专项修复计划共 14 份已归档；其中 v1.0.7（路径扫描增强）因引用的基础设施不存在而整体过时，v1.1.0（自动化运维）已被现有定时任务基建事实性覆盖。盘点结论与遗留事项详见 [archive/README.md](./archive/README.md)。
