# backend/api — HTTP 路由层

> FastAPI 路由聚合层，按业务域组织 37 个 endpoint 模块 + 请求/响应模型。所有接口统一返回 `CommonResponse[T]`。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/api/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### api/ 根（2 个文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 路由聚合 api-router | `api.py` | 顶层 `api_router = APIRouter()`，按 prefix 挂载全部子路由（27 次 include_router；prefix→模块映射见下方"路由聚合"） |
| 响应封装 response-vo | `responseVO.py` | 通用响应封装 `CommonResponse[T]`（status / msg / code / data） |

### endpoints/（37 个文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 高级搜索 API advanced-search | `advanced_search.py` | 高级搜索 API（13 字段全字段搜索 + 多选排除）；v1.0.6.27 起接入 `sqlite_search_runtime`（正则执行熔断）与 `app.contracts`（操作符契约校验），防 ReDoS 与前后端漂移 |
| 审计日志 API audit-log | `audit_logs.py` | 审计日志异步 API：查询/导出/归档/统计 |
| 定时任务 API cron | `cron_tasks.py` | 定时任务（cron）配置与日志 CRUD/启停 |
| 用户中心 cuser | `cuser.py` | 用户中心：登出/改信息/改密/2FA（挂 `/user` 与 `/users`） |
| 仪表盘 dashboard | `dashboard.py` | 仪表盘聚合数据，委托 `DashboardService` |
| 健康检查 health | `health.py` | liveness/readiness 与受保护同步业务健康；数据库查询和同步健康均有界超时 |
| 下载器核心 downloader | `downloader.py` | 下载器核心 API（连通性测试/添加管理）；路径映射测试会通过缓存下载器验证内部目录，并在 BtDeck 环境验证外部目录，任一失败即 fail-closed |
| 能力探测 capability | `downloader_capabilities.py` | 下载器能力探测 |
| 能力配置 capability-mgmt | `downloader_capabilities_management.py` | 下载器能力配置管理（更新/重置/删除） |
| 路径维护 path-mgmt | `downloader_path_maintenance.py` | 下载器路径维护 CRUD（默认/活跃路径） |
| 下载器设置 downloader-setting | `downloader_settings.py` | 下载器设置管理（CRUD + 应用；含已废弃 advanced_settings） |
| 重复种子 duplicate | `duplicate_torrents.py` | 重复种子查询；排除 pending/running 删除任务中的种子后再判定重复组 |
| 重复种子快捷删除 duplicate-quick | `duplicate_quick_delete.py` | 重复种子预览与异步删除提交；预览隐藏占用项，提交返回接受/跳过数量且全部占用时不重复派发 |
| 登录 login | `login.py` | 登录（`/login`，校验密码并签发 token） |
| 通知中心 notification | `notifications.py` | 通知中心：列表/未读计数/标记已读 |
| 孤儿文件 API orphan | `orphan_files.py` | 扫描/列表/清理/忽视/隔离恢复；列表文件行返回实时 `hardlink_copy_count`，文件夹行返回合计；清理提交支持原子占用与混合跳过 |
| 回收站 recycle | `recycle_bin.py` | 回收站：列表/还原/清理预览/手动清理 |
| 种子转移 seed-transfer | `seed_transfer.py` | 种子转移，对接 `seed_transfer_service` |
| 配置模板 template | `setting_templates.py` | 配置模板管理：CRUD + 应用 |
| 标签管理 tag | `tag_management.py` | 标签管理：标签 CRUD/种子标签分配/批量操作 |
| 任务日志 task-log | `tasks.py` | 任务日志（`/logs`、`/statistics`） |
| 种子备份 torrent-backup | `torrent_backup.py` | 种子文件备份：备份/还原/列表/管理 |
| 种子 CRUD torrent-crud | `torrent_crud.py` | 种子 CRUD（列表/添加/查询/上传 .torrent）；v1.0.6.33 起异步批量添加已抽取至 `services/torrent_batch_add_service.py` ★ [详情](./endpoints/torrent_crud.md) |
| 种子删除 torrent-delete | `torrent_deletion.py` | 种子多等级删除；异步批量提交原子占用活动 ID，并返回 requested/accepted/skipped 统计 |
| 种子工具 torrent-helper | `torrent_helpers.py` | 种子端点共享工具（哈希/序列化/bencode/DB 辅助）；普通列表与计数排除活动删除任务中的种子 |
| 种子路径 torrent-location | `torrent_location.py` | 修改种子保存路径 |
| 种子速度 torrent-speed | `torrent_speed.py` | 种子级实时速度查询（走 `app.state.store` 缓存） |
| 种子状态 torrent-status | `torrent_status.py` | 种子状态控制（暂停/恢复/重检） |
| 种子同步 torrent-sync | `torrent_sync.py` | 种子同步端点 + 同步辅助函数；手动/兼容路径复用缓存客户端，sync-single 使用 AsyncSession；v1.0.6.25 起同步写入用 `torrent_ratio_values` |
| 种子聚合 torrents | `torrents.py` | 种子聚合路由器（include_router 合并 6 个子路由） |
| 异步种子 DB torrents-async | `torrents_async.py` | 异步版种子 DB 操作（供定时任务用）；info/tracker 受单轮预算与 durable cursor 约束，客户端只接收缓存实例；v1.0.6.25 起写入经 `torrent_ratio_values` |
| Tracker 查询 tracker | `tracker.py` | Tracker 信息查询/同步（异步会话） |
| Tracker 关键词 tracker-keyword | `tracker_keywords.py` | Tracker 关键词 CRUD + 批量 |
| 关键词池 keyword-pool | `tracker_keywords_pools.py` | Tracker 关键词池（candidate/ignored/success/failed 四池） |
| Tracker 消息 tracker-message | `tracker_messages.py` | Tracker 消息记录 CRUD + 加入关键词池 |
| Reannounce 配置 reannounce | `tracker_reannounce.py` | Tracker Reannounce 配置 CRUD + 自动检测域名 |
| 匹配测试 tracker-test | `tracker_test.py` | Tracker 关键词匹配测试 |

### models/（请求/响应 Pydantic 模型）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 高级搜索模型 search-model | `advanced_search.py` | 高级搜索 13 字段请求/响应模型 + 排除字段模型；v1.0.6.25 起新增 ratio 4 操作符（`eq`/`ne`/`gt`/`lt`）+ `is_null`/`is_not_null`；v1.0.6.27 起 Pydantic 校验器引用 `app.contracts.advanced_search`（`SUPPORTED_SEARCH_OPERATORS` / `allowed_operators_for_field`），请求期即拒绝非法操作符 |

### schemas/（领域 Pydantic 模型）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 路径映射 schema path-mapping | `path_mapping.py` | 路径映射 Pydantic 模型（前后端协同验证，含逐条内外目录检查结果） |
| 关键词 schema tracker-keyword | `tracker_keywords.py` | Tracker 关键词 CRUD 请求/响应 |
| 消息 schema tracker-message | `tracker_messages.py` | Tracker 消息记录请求/响应 |

---

## 路由聚合

> 注：`api/` 目录有 `__init__.py`（空），但 `api/endpoints/` 目录**无 `__init__.py`**（实测确认）。

`api.py` 中 prefix → 模块映射（部分复用）：

| prefix | 模块 |
|--------|------|
| `/auth` | login |
| `/downloader` | downloader |
| `/user`、`/users` | cuser（同一 router 两个 prefix） |
| `/torrents` | torrents（聚合 crud/status/deletion/sync/location/speed） |
| `/tracker` | tracker |
| `/tasks`、`/cronTasks` | tasks、cron_tasks |
| `/dashboard` | dashboard |
| `/advanced-search` | advanced_search |
| `/tracker-keywords`（×2）、`/tracker-messages`、`/tracker-test`、`/tracker-reannounce` | tracker_* |
| `/torrent-status` | torrent_status |
| `/audit-logs` | audit_logs |
| `/recycle` | recycle_bin |
| `/downloaders`（×4：settings/capabilities/capabilities_management/path_maintenance）、`/setting-templates` | downloader_* / setting_templates |
| `/tags` | tag_management |
| `/notifications` | notifications |
| `/orphan-files` | orphan_files |
| `/torrents` 附加 | duplicate_torrents、torrent_backup、seed_transfer |

最终在 `app/startup/routers_initializer.py:16` 注入顶层前缀 `API_V1_STR`（默认 `/api/v1`）。

---

## 调用约定

- **认证**：业务端点统一 `Depends(require_authenticated_user)`（来自 `app.auth.dependencies`，被 31 个文件使用）
- **DB 会话**：`Depends(get_db)` / `AsyncSessionLocal`（来自 `app.database`，被 86 个文件使用）
- **响应**：所有成功响应 `return CommonResponse(data=...)`；异常由 `app.exception_handlers` 统一归一化
- **横向复用**：endpoint 之间通过 `*_helpers.py`（如 `torrent_helpers.py`）共享工具函数，避免重复实现

## 第三层详情

- 本次已完成：[endpoints/torrent_crud.md](./endpoints/torrent_crud.md)（种子 CRUD 端点）
- 其余 endpoint 第三层待后续会话按模式 B 补齐
