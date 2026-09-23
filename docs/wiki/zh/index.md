# BtDeck Wiki

[English](../en/index.md)

BtDeck 是一个统一管理 qBittorrent 与 Transmission 的全栈 BitTorrent 管理平台。它提供 Web 管理界面、实时状态监控、搜索与查询模板、Tracker 管理、回收站、孤儿文件治理，以及移动 Web 和 Android 双模式客户端。

当前 Wiki 以 **v1.0.6** 为内容基线。功能是否可用仍取决于运行平台、下载器能力矩阵和部署配置。

## 从这里开始

- [快速开始](./quick-start.md)：第一次启动 BtDeck。
- [Docker 部署](./deployment/docker.md)：推荐的生产与家庭服务器部署方式。
- [源码部署](./deployment/source.md)：本地开发和调试。
- [核心功能](./guide/core-features.md)：了解常用页面和数据安全边界。
- [移动端与 Android](./guide/mobile-and-android.md)：移动 Web、伴侣模式和本机服务端模式。
- [安全配置](./operations/security.md)：公网部署前必须完成的配置。
- [故障排查](./troubleshooting.md)：从健康检查和日志开始定位问题。

## 你可以用 BtDeck 做什么

| 目标 | 入口 |
| --- | --- |
| 管理多个下载器 | 下载器管理、连接测试、能力检查、设置模板 |
| 管理种子 | 添加、搜索、批量操作、标签、转移、备份、分级删除 |
| 观察运行状态 | 仪表盘、实时速度、Tracker 状态、通知中心 |
| 整理磁盘 | 孤儿文件扫描、忽视名单、隔离区和回收站 |
| 自动化工作 | 定时任务、查询模板、MCP 服务能力 |
| 手机访问 | 移动 Web PWA 或 Android 双模式客户端 |

## 部署方式

| 方式 | 适合场景 | 主要入口 |
| --- | --- | --- |
| Docker Compose | 长期运行、家庭服务器、NAS 或云主机 | [Docker 部署](./deployment/docker.md) |
| 源码运行 | 开发、调试、贡献代码 | [源码部署](./deployment/source.md) |
| Windows/Linux 制品 | 不想维护 Python/Node 环境 | 参见仓库 `deploy/` 和发布说明 |
| Android | 移动伴侣或手机本机服务 | [移动端与 Android](./guide/mobile-and-android.md) |

## 版本提示

产品版本由仓库的 `release/release-config.json` 提供。Wiki 页面中的“已支持”描述以 v1.0.6 发布内容为准；路线图中的计划不会自动代表已发布功能。

