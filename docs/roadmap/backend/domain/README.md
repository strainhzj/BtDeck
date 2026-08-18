# backend/domain — 领域目录组

> 按业务领域组织的目录：下载器（downloader）、种子（torrents）、Tracker（tracker）、认证（auth）、用户（user）。各目录含领域 ORM、VO、适配逻辑等。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/domain/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### downloader/ — 下载器领域（9 个文件，⚠ 无 `__init__.py`）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 初始化总控 downloader-init | `initialization.py` | 🔵 下载器初始化与状态轮询总控（连通性检查/全量增量同步/定时任务/qB+Transmission 状态采集；核心类 `DownloaderInitialization` L28；`_set_online_status` 维护 is_online/offline_since 供缓存剔除与速度接口跳过，L1525） |
| Transmission 设置 tr-settings | `transmission_settings.py` | `TransmissionSettings`：Transmission 客户端会话设置读写 |
| qB 设置 qb-settings | `qbittorrent_settings.py` | `QBitTorrentSettings`：qBittorrent 应用偏好设置读写 |
| 种子拉取 torrent-fetcher | `torrent_fetcher.py` | `TorrentFetcher`：从下载器拉取种子列表的封装 |
| 统计缓存 stats-cache | `torrent_stats_cache.py` | `TorrentCacheEntry` / `TorrentStatsCache`：种子统计缓存 |
| 下载器 ORM downloader-model | `models.py` | ORM：`BtDownloaders`（下载器表）+ `DownloaderStatus` 枚举 |
| 异常体系 downloader-exception | `exceptions.py` | 下载器异常体系（`DownloaderSettingsError` + 7 子类） |
| 下载器 VO downloader-vo | `responseVO.py` | 下载器响应 VO（`DownloaderSimpleVO`/`DownloaderResponse`/`DownloaderVO` 等） |
| 下载器请求 downloader-request | `request.py` | 请求 VO（`RequestDownloader`/`UpdateDownloader`/`DownloaderCheckVO` 等） |

### initialization.py 核心（最大文件，1999 行）

- **核心类 `DownloaderInitialization`**（L28）：缓冲式增删 + 快照
- **连通性检查**：`check_port_connectivity`(L251)、`check_downloader_connectivity_with_retry`(L305)、qB/Transmission 认证重试 `_check_*_auth_with_retry`(L381/L417)
- **启动流程**：`startup_event(app)`(L682) → `_async_initialization_tasks`(L709) → `_load_initial_downloaders`(L729) → `_perform_initial_full_sync`(L795)
- **同步任务**：`full_database_sync_task`(L915)、自适应间隔 `_calculate_sync_interval`(L1022)
- **后台轮询**：`periodic_check`(L1391)、`downloader_status_polling_task`(L1414)
- **状态更新**：`update_torrent_stats_smart`(L1686)、`_get_qbittorrent_status`(L1898)、`_get_transmission_status`(L1950)

被 `app/startup/lifecycle.py:91` 通过 `asyncio.create_task(startup_event(app))` 启动。

### torrents/ — 种子领域（9 个文件，含 `__init__.py`）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 种子 ORM torrent-model | `models.py` | ORM：`TorrentInfo`(L12，`error_reason` Text L24)、`TrackerInfo`(L240)、`TrackerKeywordConfig`(L294)、`TrackerMessageLog`(L374)、`TrackerReannounceConfig`(L457) |
| 审计枚举 audit-enum | `audit_enums.py` | 审计枚举：`AuditOperationType`(L11, 39 成员) + `AuditOperationResult`(L239) |
| 审计 ORM audit-model | `audit_models.py` | ORM：`TorrentAuditLog`(L21) 种子审计日志表 |
| 种子 VO torrent-vo | `responseVO.py` | `alias_camel`(L8) 驼峰别名 + `TorrentInfoVO`(L14)，`error_reason` L37 自动输出为 `errorReason` |
| Tracker VO tracker-vo | `trackerVO.py` | `TrackerInfoVO`(L5) |
| 请求 VO torrent-request | `request.py` | 请求 VO：`Tracker`(L6) / `ModifyTrackerRequest`(L12) |
| 空占位 qb | `qbittorrent.py` | ⚠ **空文件**（0 字节，占位） |
| 空占位 tr | `transmission.py` | ⚠ **空文件**（0 字节，占位） |
| 导出种子模型 torrent-export | `__init__.py` | 导出 `TorrentInfo`/`TrackerInfo`/`TorrentInfoVO`/`TrackerInfoVO` |

### tracker/ — Tracker 领域

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Tracker 响应 VO tracker-info-vo | `responseVO.py` | `TrackerInfoVO`(L5) Tracker 信息响应 VO |

### auth/ — 认证领域（6 个文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 认证依赖 auth-dependency | `dependencies.py` | 🔵 FastAPI 认证依赖：`AuthenticatedUserInfo`(L23) + `require_authenticated_user`(L83) + `get_current_user`(L102) |
| JWT/TOTP auth-utils | `utils.py` | JWT + TOTP：`create_access_token`(L39)、`verify_access_token`(L51)、`generate_totp_secret`(L119)、`verify_totp`(L124) |
| 密码/SM4 auth-security | `security.py` | 密码 + SM4：`generate_sm4_key`、`sm4_encrypt/decrypt`、`verify_password`、`get_password_hash` |
| 用户 ORM auth-model | `models.py` | ORM：`User`(L7)、`LoginLog`(L19)、`Config`(L31) |
| 登录请求 auth-request | `request.py` | 请求 VO：`UserLogin`(L5) |
| 令牌清理 auth-token-cleanup ✨2026-08-18 | `token_cleanup.py` | refresh_tokens 过期记录清理：`CLEANUP_SQL`（过期/撤销超保留期 DELETE）+ 同步函数，供每日 04:30 定时任务调用 |

> `auth/dependencies.require_authenticated_user` 被 **31** 个 endpoint 文件依赖，是认证骨架。

### user/ — 用户领域

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 用户请求 VO user-request | `requestVO.py` | 用户请求 VO：`ChangePasswordRequest`(L4)、`TwofactorVerifyRequest`(L12)、`VerifyPasswordFor2FARequest`(L21) |

---

## 关键观察

- **下载器领域是最大复杂度核心**：`downloader/initialization.py`（1999 行）+ `qbittorrent_settings.py` + `transmission_settings.py` 构成下载器管理全链路
- **种子领域 ORM 集中**：`TorrentInfo` / `TrackerInfo` / `TrackerMessageLog` 等核心业务表都在 `torrents/models.py`
- **空文件占位**：`torrents/qbittorrent.py`、`torrents/transmission.py` 为 0 字节空文件
- **`downloader/` 无 `__init__.py`**（实测确认），与其他领域目录不一致

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`downloader/initialization.py` 1999 行）
