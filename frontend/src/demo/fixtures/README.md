# Demo fixtures

这里存放 Demo Mode 的初始脱敏数据。`index.ts` 是唯一初始数据入口，后续请求层和内存 store 都应从该入口读取，页面内不得再复制一套假数据。

## 字段分组

| 分组 | 主要字段 | 语义 |
|------|----------|------|
| `user` | `userId`、`name`、`roles` | 固定演示身份，不代表真实账号 |
| `downloaders` | 节点 ID、昵称、类型、在线状态、速度、计数 | 使用 `.example.invalid` 主机占位 |
| `torrents` | 种子身份、状态、进度、速度、Tracker 摘要 | `hash`、保存目录和文件名均为演示占位 |
| `notifications` | 类型、标题、内容、优先级、已读状态 | 不携带 release URL、凭据或真实故障信息 |
| `queryTemplates` | 来源、条件、公开状态、使用次数 | 与查询模板页面的 `conditions` 结构保持一致 |
| `tasks` / `taskLogs` | 任务状态、结果、新鲜度、日志详情 | 只表达本地模拟结果 |
| `auditLogs` | 操作、旧值、新值、结果、时间 | IP、UA、request/session ID 固定为空 |
| `recycleBin` / `orphanFiles` | 名称/路径、大小、状态、置信度 | 路径只使用 `/demo/*` |
| `tracker*` | 关键词、消息、池统计、汇报配置 | Tracker 域名使用 `.example.invalid` |
| `backups` / `categories` / `tags` | 备份摘要和筛选选项 | 不生成或读取真实 torrent 文件 |

## 使用规则

- API 响应由请求层补齐 `{ status, msg, code, data }` 信封；列表响应统一使用 `list`、`total`、`pageSize`。
- store 可以在会话内复制并变更 fixture，但不能直接修改导出的初始对象。
- 新增字段时先更新 `src/demo/types.ts`，再更新这里的字段说明和对应 fixture。
- Demo 构建不得以 fixture 缺失为理由回退到 Axios、Fetch 或真实 API。
