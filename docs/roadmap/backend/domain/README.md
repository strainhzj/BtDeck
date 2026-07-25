# backend/domain — 领域目录组

> 按业务领域组织的目录：下载器（downloader）、种子（torrents）、Tracker（tracker）、认证（auth）、用户（user）。各目录含领域 ORM、VO、适配逻辑等。

## downloader/ — 下载器领域（9 个文件，⚠ 无 `__init__.py`）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `initialization.py` | 1999 | 1 class + 31 def | 🔵 下载器初始化与状态轮询总控（连通性检查/全量增量同步/定时任务/qB+Transmission 状态采集） |
| `transmission_settings.py` | 552 | 1 (`TransmissionSettings`) | Transmission 客户端会话设置读写 |
| `qbittorrent_settings.py` | 502 | 1 (`QBitTorrentSettings`) | qBittorrent 应用偏好设置读写 |
| `torrent_fetcher.py` | 271 | 1 (`TorrentFetcher`) | 从下载器拉取种子列表的封装 |
| `torrent_stats_cache.py` | 227 | 2 | `TorrentCacheEntry` / `TorrentStatsCache`：种子统计缓存 |
| `models.py` | 204 | 2 | ORM：`BtDownloaders`（下载器表）+ `DownloaderStatus` 枚举 |
| `exceptions.py` | 202 | 8 | 下载器异常体系（`DownloaderSettingsError` + 7 子类） |
| `responseVO.py` | 202 | 5 | 下载器响应 VO（`DownloaderSimpleVO`/`DownloaderResponse`/`DownloaderVO` 等） |
| `request.py` | 154 | 4 | 请求 VO（`RequestDownloader`/`UpdateDownloader`/`DownloaderCheckVO` 等） |

### initialization.py 核心（最大文件，1999 行）

- **核心类 `DownloaderInitialization`**（L28）：缓冲式增删 + 快照
- **连通性检查**：`check_port_connectivity`(L251)、`check_downloader_connectivity_with_retry`(L305)、qB/Transmission 认证重试 `_check_*_auth_with_retry`(L381/L417)
- **启动流程**：`startup_event(app)`(L682) → `_async_initialization_tasks`(L709) → `_load_initial_downloaders`(L729) → `_perform_initial_full_sync`(L795)
- **同步任务**：`full_database_sync_task`(L915)、自适应间隔 `_calculate_sync_interval`(L1022)
- **后台轮询**：`periodic_check`(L1391)、`downloader_status_polling_task`(L1414)
- **状态更新**：`update_torrent_stats_smart`(L1686)、`_get_qbittorrent_status`(L1898)、`_get_transmission_status`(L1950)

被 `app/startup/lifecycle.py:91` 通过 `asyncio.create_task(startup_event(app))` 启动。

## torrents/ — 种子领域（9 个文件，含 `__init__.py`）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `models.py` | 499 | 5 | ORM：`TorrentInfo`(L12)、`TrackerInfo`(L215)、`TrackerKeywordConfig`(L269)、`TrackerMessageLog`(L349)、`TrackerReannounceConfig`(L432) |
| `audit_enums.py` | 280 | 2 | 审计枚举：`AuditOperationType`(L11, 39 成员) + `AuditOperationResult`(L239) |
| `audit_models.py` | 255 | 1 | ORM：`TorrentAuditLog`(L21) 种子审计日志表 |
| `responseVO.py` | 68 | 2 | `alias_camel`(L8) 驼峰别名 + `TorrentInfoVO`(L14) |
| `trackerVO.py` | 40 | 1 | `TrackerInfoVO`(L5) |
| `request.py` | 15 | 2 | 请求 VO：`Tracker`(L6) / `ModifyTrackerRequest`(L12) |
| `qbittorrent.py` | **0** | 0 | ⚠ **空文件**（0 字节，占位） |
| `transmission.py` | **0** | 0 | ⚠ **空文件**（0 字节，占位） |
| `__init__.py` | 9 | 0 | 导出 `TorrentInfo`/`TrackerInfo`/`TorrentInfoVO`/`TrackerInfoVO` |

## tracker/ — Tracker 领域

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `responseVO.py` | 28 | 1 | `TrackerInfoVO`(L5) Tracker 信息响应 VO |

## auth/ — 认证领域（5 个文件）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `dependencies.py` | 136 | 6 | 🔵 FastAPI 认证依赖：`AuthenticatedUserInfo`(L23) + `require_authenticated_user`(L83) + `get_current_user`(L102) |
| `utils.py` | 152 | 7 | JWT + TOTP：`create_access_token`(L39)、`verify_access_token`(L51)、`generate_totp_secret`(L119)、`verify_totp`(L124) |
| `security.py` | 73 | 5 | 密码 + SM4：`generate_sm4_key`、`sm4_encrypt/decrypt`、`verify_password`、`get_password_hash` |
| `models.py` | 37 | 3 | ORM：`User`(L7)、`LoginLog`(L19)、`Config`(L31) |
| `request.py` | 8 | 1 | 请求 VO：`UserLogin`(L5) |

> `auth/dependencies.require_authenticated_user` 被 **31** 个 endpoint 文件依赖，是认证骨架。

## user/ — 用户领域

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `requestVO.py` | 25 | 3 | 用户请求 VO：`ChangePasswordRequest`(L4)、`TwofactorVerifyRequest`(L12)、`VerifyPasswordFor2FARequest`(L21) |

---

## 关键观察

- **下载器领域是最大复杂度核心**：`downloader/initialization.py`（1999 行）+ `qbittorrent_settings.py` + `transmission_settings.py` 构成下载器管理全链路
- **种子领域 ORM 集中**：`TorrentInfo` / `TrackerInfo` / `TrackerMessageLog` 等核心业务表都在 `torrents/models.py`
- **空文件占位**：`torrents/qbittorrent.py`、`torrents/transmission.py` 为 0 字节空文件
- **`downloader/` 无 `__init__.py`**（实测确认），与其他领域目录不一致

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`downloader/initialization.py` 1999 行）
