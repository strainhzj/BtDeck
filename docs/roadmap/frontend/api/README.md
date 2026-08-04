# frontend/api — axios API 封装

> 12 个领域 API 模块，统一通过 `@/utils/request`（axios 封装）调用后端 `/api/v1/*`。

## 文件清单（12 个 .ts，跳过 torrents_patch.txt）

| 文件 | 行数 | 导出符号数 | request import | 一句话职责 |
|------|------|-----------|---------------|-----------|
| `torrents.ts` | 1219 | 37 func / 45 iface | L2 | 🔵 种子管理核心：列表/添加/批量/删除（多级别+异步）/暂停恢复/校验/tracker 操作/高级搜索/搜索模板/重复检测/辅种迁移/路径/备份/reannounce/活跃种子 |
| `tracker.ts` | 598 | 26 func / 29 iface | L2 | Tracker：关键词 CRUD+批量/消息日志 CRUD+批量/统计/测试匹配/关键词池/汇报配置 CRUD+自动检测域名+批量更新 |
| `tasks.ts` | 499 | 18 func / 24 iface | L2 | 定时任务：CRUD/执行/日志/统计/清理 + 脚本/cron/Python 类校验 |
| `downloader.ts` | 317 | 24 const | L1 | 下载器 CRUD、状态/连接测试、设置/模板、路径映射；路径验证请求/响应使用完整类型并承载逐条内外目录检查结果 |
| `recycle-bin.ts` | 196 | 5 func / 11 iface | L2 | 回收站：列表/恢复（含 .torrent 文件恢复）/清理预览/清理 |
| `audit-logs.ts` | 187 | 6 func / 10 iface | L1 | 审计日志：查询/统计/操作类型/导出/归档/下载 |
| `tag-management.ts` | 175 | 9 func / 5 iface / 1 enum | L6 | 标签管理：分类/标签 CRUD/批量删除/分类支持检查 |
| `orphan-files.ts` | 427 | 11 func / 25 iface / 8 type | L2 | 孤儿文件：扫描/筛选/清理/忽视/隔离恢复；忽视结果保留逐项失败原因，彻底删除为立即返回的持久化任务并提供状态查询 |
| `torrents-backup.ts` | 148 | 7 func / 6 iface | L1 | 种子备份：列表/删除/去重/导入 + 导出/下载/上传 URL 构造 |
| `notification.ts` | 104 | 6 func / 3 iface | L2 | 通知列表/未读数/标记已读未读/全部已读/删除 |
| `users.ts` | 51 | 4 const | L1 | 用户：getUserInfo / changePassword / login / logout |
| `dashboard.ts` | 8 | 1 const | L1 | 仪表盘聚合数据（仅 `getDashboardData`） |

> 所有文件均 `import request from '@/utils/request'`（行号见上表）。`torrents.ts` 是最大且最核心的 API 模块。

## 调用约定

- **统一信封**：所有 API 返回 `ApiEnvelope<T>`（status/msg/code/data），与后端 `CommonResponse` 对齐
- **分页字段**：固定 `list/total/pageSize`（见 [约束](../../../frontend/docs/constraints/api-response-format.md)）
- **类型定义**：请求/响应 interface 多数定义在 API 文件内（如 `torrents.ts` 45 个 iface），部分共享类型在 `src/types/`

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`torrents.ts` 1219 行核心 API）
