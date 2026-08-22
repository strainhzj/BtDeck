# BtDeck Diagnostic Report

- Generated: 2026-06-19T12:09:16+08:00
- Repository: `/home/huangzj/workspace/BtDeck`
- Backend: `/home/huangzj/workspace/BtDeck/backend`

## 1. 配置系统诊断

| Module | Key | Actual value | Source | Static/default value |
| --- | --- | --- | --- | --- |
| app.config | SECRET_KEY | YM4nwx3QBbZ227i5itqf | static fallback | YM4nwx3QBbZ227i5itqf |
| app.config | ACCESS_TOKEN_EXPIRE_MINUTES | 600 | static fallback | 600 |
| app.config | ALGORITHM | HS256 | static fallback | HS256 |
| app.core.config | SECRET_KEY | your-secret-key-for-jwt | static fallback | your-secret-key-for-jwt |
| app.core.config | ACCESS_TOKEN_EXPIRE_MINUTES | 30 | static fallback | 30 |
| app.core.config | ALGORITHM | HS256 | static fallback | HS256 |

| Item | Value |
| --- | --- |
| SECRET_KEY env set | False |
| DATABASE_URL env set | False |
| DATABASE_URL env value | (not set) |
| DATABASE_URL consumed by Python code | False |
| Actual DATABASE_PATH | /home/huangzj/workspace/BtDeck/backend/config/app.db |

### app.config importers
- backend/app/api/endpoints/login.py
- backend/app/api/router.py
- backend/app/auth/dependencies.py
- backend/app/auth/security.py
- backend/app/auth/utils.py
- backend/tests/auth/test_auth_edge_cases.py

### app.core.config importers
- backend/app/api/endpoints/login.py
- backend/app/api/endpoints/torrents_async.py
- backend/app/auth/utils.py
- backend/app/core/migration.py
- backend/app/database.py
- backend/app/downloader/qbittorrent.py
- backend/app/factory.py
- backend/app/main.py
- backend/app/migrations/database_migrator.py
- backend/app/services/seed_transfer_service.py
- backend/app/startup/routers_initializer.py
- backend/app/utils/encryption.py
- backend/app/websocket_main.py
- backend/app/yamlConfig.py

### DATABASE_URL consumers
- (none)

### 配置诊断备注
- app.config import failed: ModuleNotFoundError: No module named 'pydantic'
- app.core.config import failed: ModuleNotFoundError: No module named 'pydantic'
- app.core.config import failed while deriving DB path: ModuleNotFoundError: No module named 'pydantic'

## 2. 数据库诊断

| Item | Value |
| --- | --- |
| Path | /home/huangzj/workspace/BtDeck/backend/config/app.db |
| Exists | False |
| Size | (missing) |
| Open read-only | database file does not exist |

### Tables and Row Counts
| Table | Rows |
| --- | --- |
| (database unavailable) | database file does not exist |

## 3. 定时任务诊断

### All cron_task Records
| Item | Value |
| --- | --- |
| cron_task | database file does not exist |

### Count by task_type
| Item | Value |
| --- | --- |
| cron_task | database file does not exist |

### Script/Internal Class Tasks
| Item | Value |
| --- | --- |
| cron_task | database file does not exist |

### enhanced_python_executor
- (none)

## 4. 认证诊断

| Package | Version | Status |
| --- | --- | --- |
| python-jose | (not installed) | missing |
| jose | (not installed) | missing |
| PyJWT | (not installed) | missing |

### 手动读取 X-Access-Token 的 endpoint 文件
- backend/app/api/endpoints/advanced_search.py
- backend/app/api/endpoints/cron_tasks.py
- backend/app/api/endpoints/cuser.py
- backend/app/api/endpoints/downloader.py
- backend/app/api/endpoints/downloader_capabilities.py
- backend/app/api/endpoints/downloader_capabilities_management.py
- backend/app/api/endpoints/downloader_path_maintenance.py
- backend/app/api/endpoints/downloader_settings.py
- backend/app/api/endpoints/seed_transfer.py
- backend/app/api/endpoints/setting_templates.py
- backend/app/api/endpoints/tag_management.py
- backend/app/api/endpoints/tasks.py
- backend/app/api/endpoints/torrent_backup.py
- backend/app/api/endpoints/torrent_crud.py
- backend/app/api/endpoints/torrent_deletion.py
- backend/app/api/endpoints/torrent_location.py
- backend/app/api/endpoints/torrent_sync.py
- backend/app/api/endpoints/tracker.py
- backend/app/api/endpoints/tracker_keywords.py
- backend/app/api/endpoints/tracker_keywords_pools.py
- backend/app/api/endpoints/tracker_messages.py
- backend/app/api/endpoints/tracker_test.py

### 使用 Depends(get_current_user) 的 endpoint 文件
- backend/app/api/endpoints/audit_logs.py
- backend/app/api/endpoints/dashboard.py
- backend/app/api/endpoints/duplicate_torrents.py
- backend/app/api/endpoints/notifications.py
- backend/app/api/endpoints/recycle_bin.py
- backend/app/api/endpoints/torrent_deletion.py

## 5. 安全检查

### 默认管理员账号
| Check | Value |
| --- | --- |
| users table | database file does not exist |

### CORS 配置
| Source | CORS value/code |
| --- | --- |
| backend/app/factory.py | allow_origins=settings.ALLOWED_HOSTS,<br>allow_credentials=True,<br>allow_methods=["*"],<br>allow_headers=["*"], |
| app.core.config static ALLOWED_HOSTS | ['*'] |

### Git Tracking
| Path | Tracked |
| --- | --- |
| .env | no |
| backend/.env | no |
| backend/config/config.yaml | yes |

## 6. 依赖诊断

| Item | Value | Status |
| --- | --- | --- |
| requirements.txt | backend/requirements.txt | exists |
| JWT packages | python-jose~=3.4.0, pyjwt~=2.8.0, jose~=1.0.0 | conflict |
| Lock files | (none) |  |
