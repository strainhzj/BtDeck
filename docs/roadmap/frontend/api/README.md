# frontend/api — axios API 封装

> 12 个领域 API 模块，统一通过 `@/utils/request`（axios 封装）调用后端 `/api/v1/*`。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/api/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查（12 个 .ts，跳过 torrents_patch.txt）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 种子管理核心 torrent | `torrents.ts` | 🔵 种子管理核心：列表/添加/批量/异步删除/重复检测/文件备份等；`Torrent` 暴露 `auxiliarySeedCount` 与 downloadComplete 兼容字段；`TorrentListParams.tracker_domain` L201 支持 Tracker 主机域名多选，`single_error_only` L205 支持错误单种全局唯一排查，`getTrackerDomains()` L260 读取定时同步已采集的域名；`getActiveTorrents()` L1379 获取 200/206 实时快照，`reconcileRuntimeTorrentStates()` L1390 低频核验复合键终态；均复用 `getTorrentList()` 的筛选、排序与分页契约 |
| Tracker tracker | `tracker.ts` | Tracker：关键词 CRUD+批量/消息日志 CRUD+批量/统计/测试匹配/关键词池/汇报配置 CRUD+自动检测域名+批量更新 |
| 定时任务 tasks | `tasks.ts` | 定时任务：CRUD/执行/日志/统计/清理 + 脚本/cron/Python 类校验 |
| 下载器 downloader | `downloader.ts` | 下载器 CRUD、状态/连接测试、设置/模板、路径映射；`syncDownloader()` L105 以 `SyncTaskSubmission` 接收异步任务，`getSyncTaskStatus()` L113 对 task_id 编码后查询真实后台终态；路径验证请求/响应使用完整类型并承载逐条内外目录检查结果 |
| 回收站 recycle-bin | `recycle-bin.ts` | 回收站：列表/恢复（含 .torrent 文件恢复）/清理预览/清理 |
| 审计日志 audit-logs | `audit-logs.ts` | 审计日志：查询/统计/操作类型/导出/归档/下载（下载走 axios blob 携带认证头，文件名 encodeURIComponent；替代历史 window.open 直开 URL 的前缀/凭证/拦截器三重损坏） |
| 标签管理 tag | `tag-management.ts` | 标签管理：分类/标签 CRUD/批量删除/分类支持检查 |
| 孤儿文件 orphan | `orphan-files.ts` | `triggerScan` 提交后台 scan_id/task_id，`getScanStatus` 轮询；`getOrphanFolderChildren` 展开后独立分页；`reviewScanGuardrail` 双确认复核；保留硬链接定位、清理/忽视/隔离恢复 |
| 种子备份 torrents-backup | `torrents-backup.ts` | 种子备份：列表/删除/去重/导入 + 导出/下载/上传 URL 构造 |
| 通知 notification | `notification.ts` | 通知列表/未读数/标记已读未读/全部已读/删除 |
| 用户 users | `users.ts` | 用户：getUserInfo / changePassword / login / logout |
| 仪表盘 dashboard | `dashboard.ts` | 仪表盘聚合数据（仅 `getDashboardData`） |

> 所有文件均 `import request from '@/utils/request'`（行号见上表）。`torrents.ts` 是最大且最核心的 API 模块。

## 调用约定

- **统一信封**：所有 API 返回 `ApiEnvelope<T>`（status/msg/code/data），与后端 `CommonResponse` 对齐
- **分页字段**：固定 `list/total/pageSize`（见 [约束](../../../frontend/docs/constraints/api-response-format.md)）
- **类型定义**：请求/响应 interface 多数定义在 API 文件内（如 `torrents.ts` 54 个 interface），部分共享类型在 `src/types/`

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`torrents.ts` 1398 行核心 API）
