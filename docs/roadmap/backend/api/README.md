# backend/api — HTTP 路由层

> FastAPI 路由聚合层，按业务域组织 35 个 endpoint 模块 + 请求/响应模型。所有接口统一返回 `CommonResponse[T]`。

## 路由聚合

| 文件 | 行数 | 职责 |
|------|------|------|
| `api.py` | 86 | 顶层 `api_router = APIRouter()`，按 prefix 挂载全部子路由（27 次 include_router） |
| `responseVO.py` | 13 | 通用响应封装 `CommonResponse[T]`（status / msg / code / data） |

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

## endpoints/ 文件清单（35 个）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `advanced_search.py` | 436 | 0 class, 10 def | 高级搜索 API（13 字段全字段搜索 + 多选排除）；v1.0.6.27 起接入 `sqlite_search_runtime`（正则执行熔断）与 `app.contracts`（操作符契约校验），防 ReDoS 与前后端漂移 |
| `audit_logs.py` | 324 | 3 class, 6 def | 审计日志异步 API：查询/导出/归档/统计 |
| `cron_tasks.py` | 1073 | 19 class, 29 def | 定时任务（cron）配置与日志 CRUD/启停 |
| `cuser.py` | 309 | 0 class, 7 def | 用户中心：登出/改信息/改密/2FA（挂 `/user` 与 `/users`） |
| `dashboard.py` | 40 | 0 class, 1 def | 仪表盘聚合数据，委托 `DashboardService` |
| `downloader.py` | 1530 | 2 class, 22 def | 下载器核心 API（连通性测试/添加管理；路径映射测试会通过缓存下载器验证内部目录，并在 BtDeck 环境验证外部目录，任一失败即 fail-closed） |
| `downloader_capabilities.py` | 243 | 0 class, 3 def | 下载器能力探测 |
| `downloader_capabilities_management.py` | 267 | 1 class, 4 def | 下载器能力配置管理（更新/重置/删除） |
| `downloader_path_maintenance.py` | 317 | 2 class, 6 def | 下载器路径维护 CRUD（默认/活跃路径） |
| `downloader_settings.py` | 1303 | 0 class, 11 def | 下载器设置管理（CRUD + 应用；含已废弃 advanced_settings） |
| `duplicate_torrents.py` | 416 | 1 class, 3 def | 重复种子查询 |
| `login.py` | 88 | 0 class, 2 def | 登录（`/login`，校验密码并签发 token） |
| `notifications.py` | 116 | 0 class, 6 def | 通知中心：列表/未读计数/标记已读 |
| `orphan_files.py` | 146 | 1 class, 5 def | 孤儿文件管理：扫描/列表（含统一扫描上下文与剩余量统计）/清理预览/手动清理 |
| `recycle_bin.py` | 311 | 4 class, 5 def | 回收站：列表/还原/清理预览/手动清理 |
| `seed_transfer.py` | 268 | 0 class, 2 def | 种子转移，对接 `seed_transfer_service` |
| `setting_templates.py` | 338 | 0 class, 6 def | 配置模板管理：CRUD + 应用 |
| `tag_management.py` | 1459 | 0 class, 19 def | 标签管理：标签 CRUD/种子标签分配/批量操作 |
| `tasks.py` | 40 | 0 class, 2 def | 任务日志（`/logs`、`/statistics`） |
| `torrent_backup.py` | 824 | 0 class, 12 def | 种子文件备份：备份/还原/列表/管理 |
| `torrent_crud.py` | 828 | 1 class, 5 def | 种子 CRUD（列表/添加/查询/上传 .torrent）★ [详情](./endpoints/torrent_crud.md) |
| `torrent_deletion.py` | 902 | 7 class, 9 def | 种子删除（多等级删除） |
| `torrent_helpers.py` | 866 | 0 class, 16 def | 种子端点共享工具（哈希/序列化/bencode/DB 辅助）；v1.0.6.25 起写入路径经 `torrent_ratio_values` 规范化 ratio |
| `torrent_location.py` | 93 | 0 class, 1 def | 修改种子保存路径 |
| `torrent_speed.py` | 604 | 6 class, 12 def | 种子级实时速度查询（走 `app.state.store` 缓存） |
| `torrent_status.py` | 959 | 6 class, 6 def | 种子状态控制（暂停/恢复/重检） |
| `torrent_sync.py` | 1526 | 2 class, 16 def | 种子同步端点 + 同步辅助函数；v1.0.6.25 起同步写入用 `torrent_ratio_values` |
| `torrents.py` | 30 | 0 class, 0 def | 种子聚合路由器（include_router 合并 6 个子路由） |
| `torrents_async.py` | 3604 | 0 class, 38 def | 异步版种子 DB 操作（供定时任务用）；v1.0.6.25 起写入经 `torrent_ratio_values` |
| `tracker.py` | 920 | 0 class, 11 def | Tracker 信息查询/同步（异步会话） |
| `tracker_keywords.py` | 612 | 0 class, 10 def | Tracker 关键词 CRUD + 批量 |
| `tracker_keywords_pools.py` | 377 | 1 class, 5 def | Tracker 关键词池（candidate/ignored/success/failed 四池） |
| `tracker_messages.py` | 524 | 0 class, 9 def | Tracker 消息记录 CRUD + 加入关键词池 |
| `tracker_reannounce.py` | 216 | 3 class, 6 def | Tracker Reannounce 配置 CRUD + 自动检测域名 |
| `tracker_test.py` | 76 | 0 class, 1 def | Tracker 关键词匹配测试 |

> `endpoints/` 目录无 `__init__.py`（Python 3 namespace package，实测确认）。

## models/ 子目录（请求/响应 Pydantic 模型）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `advanced_search.py` | 692 | 12 class, 2 def | 高级搜索 13 字段请求/响应模型 + 排除字段模型；v1.0.6.25 起新增 ratio 4 操作符（`eq`/`ne`/`gt`/`lt`）+ `is_null`/`is_not_null`；v1.0.6.27 起 Pydantic 校验器引用 `app.contracts.advanced_search`（`SUPPORTED_SEARCH_OPERATORS` / `allowed_operators_for_field`），请求期即拒绝非法操作符 |

## schemas/ 子目录（领域 Pydantic 模型）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `path_mapping.py` | 127 | 7 class | 路径映射 Pydantic 模型（前后端协同验证，含逐条内外目录检查结果） |
| `tracker_keywords.py` | 73 | 4 class | Tracker 关键词 CRUD 请求/响应 |
| `tracker_messages.py` | 92 | 7 class | Tracker 消息记录请求/响应 |

---

## 调用约定

- **认证**：业务端点统一 `Depends(require_authenticated_user)`（来自 `app.auth.dependencies`，被 31 个文件使用）
- **DB 会话**：`Depends(get_db)` / `AsyncSessionLocal`（来自 `app.database`，被 86 个文件使用）
- **响应**：所有成功响应 `return CommonResponse(data=...)`；异常由 `app.exception_handlers` 统一归一化
- **横向复用**：endpoint 之间通过 `*_helpers.py`（如 `torrent_helpers.py`）共享工具函数，避免重复实现

## 第三层详情

- 本次已完成：[endpoints/torrent_crud.md](./endpoints/torrent_crud.md)（种子 CRUD 端点）
- 其余 endpoint 第三层待后续会话按模式 B 补齐
