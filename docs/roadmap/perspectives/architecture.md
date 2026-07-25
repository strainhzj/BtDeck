# architecture — 关键调用链索引

> 5 条关键业务流程的调用链索引，标注 `文件:行号` 定位。⚠ 完整架构论述（配置双轨、迁移双轨、定时任务隔离三方案）见 [../../backend/docs/architecture-deep-dive.md](../../backend/docs/architecture-deep-dive.md)，本文件不重复。

---

## 链 1：应用启动流程

```
入口（Docker）
  btdeck_startup.sh:62-67
    exec uvicorn app.main:app --host 0.0.0.0 --port 5001 --workers 1
      │
      └─ app/main.py:95  Server.run()
            │
            └─ app/factory.py:116  app = create_app(configure_routes=False)
                  │  app/factory.py:84  create_app()
                  │    ├─ L92  FastAPI(lifespan=lifespan)
                  │    ├─ L94-101  CORSMiddleware
                  │    ├─ L104-106  register_exception_handlers(app)
                  │    └─ L108-109  configure_routes_and_static(app)
                  │         └─ app/startup/routers_initializer.py:6  init_routers(app)
                  │              └─ app/api/api.py:40  api_router (prefix=/api/v1)
                  │
      早期迁移（main.py 内）
        ├─ app/main.py:78  init_config_file()
        ├─ app/main.py:83  yaml.reload()
        └─ app/main.py:92  migrate_database()  → app/core/migration.py

FastAPI lifespan（请求进入前）
  app/startup/lifecycle.py:166  lifespan(app)
    ├─ L54-57   init_db()
    ├─ L66      await init_database_connection()
    ├─ L69      await update_cron_task_status()
    ├─ L75      await cron_executor.start()         # 启动 APScheduler
    │             └─ app/tasks/cron_executor.py  AsyncIOScheduler.add_job (L60/L142/L791)
    ├─ L91-92   asyncio.create_task(startup_event(app))
    │             └─ app/downloader/initialization.py:682  startup_event(app)
    │                  ├─ L709  _async_initialization_tasks
    │                  ├─ L729  _load_initial_downloaders
    │                  └─ L795  _perform_initial_full_sync
    ├─ L94-95   run_dashboard_stats_loop
    ├─ L98-99   check_version_update_task
    └─ L102-103 add_version_update_notification_task
```

## 链 2：种子添加流程（HTTP → SDK → DB → 审计）

```
HTTP POST /api/v1/torrents/add
  └─ app/api/endpoints/torrent_crud.py:122  create_torrent()
       │
       ├─ L155  await app.state.store.get_snapshot()      # 缓存下载器
       ├─ L205  asyncio.to_thread(write_temp_file)        # 临时文件
       ├─ L209  await calculate_info_hash(tmp_file_path)   # → torrent_helpers
       │
       ├─ [Transmission 分支 L221]
       │    ├─ L239  tr_client.add_torrent(BytesIO(file_data), **add_args)
       │    ├─ L249-252  轮询 get_transmission_torrent_info（最多 30s）
       │    └─ L273  create_transmission_torrent_record(...)  → db.add/commit
       │
       ├─ [qBittorrent 分支 L302]
       │    ├─ L315  qb_client.torrents_add(...)
       │    ├─ L332-335  轮询 qb_client.torrents_info（最多 30s）
       │    └─ L359  create_qbittorrent_torrent_record(...)  → db.add/commit
       │
       └─ L426  asyncio.create_task(write_audit_log_async())
                  └─ L398-419  audit_service.log_operation  (异步会话)
```

> 详见第三层样例 [../backend/api/endpoints/torrent_crud.md](../backend/api/endpoints/torrent_crud.md)。

## 链 3：种子删除流程（多等级）

```
HTTP DELETE /api/v1/torrents/...
  └─ app/api/endpoints/torrent_deletion.py  (902 行)
       └─ app/services/torrent_deletion_by_level.py  TorrentDeletionByLevel (1670 行)
            ├─ L1  删任务+数据
            ├─ L2  删任务保数据
            ├─ L3  移回收站  → app/services/recycle_bin_service.py (783 行)
            │                 → app/core/file_operations.py (1474 行, .waiting-delete 标记)
            └─ L4  加"待删除"标签  → app/services/tag_service.py / tag_adapters/
```

> 删除审计：`app/torrents/audit_models.py:21  TorrentAuditLog` + `app/utils/audit_logger.py`

## 链 4：Tracker Reannounce（定时任务）

```
APScheduler job（注册）
  app/tasks/cron_executor.py:60/142/791  add_job(...)
    └─ app/tasks/scheduler/tracker_reannounce_task.py  TrackerReannounceTask (273 行)
         │  继承 scheduler/torrent_sync/base.py:BaseSyncTask
         │
         └─ app/services/reannounce_service.py  (239 行, API 与定时任务共用)
              ├─ 按下载器分批汇报（适配 qB/Transmission）
              ├─ app/core/reannounce_config_operations.py:1-348  CRUD + 域名匹配
              └─ app/models/  tracker_reannounce_config 表（ORM 在 torrents/models.py:432）
```

## 链 5：孤儿文件扫描与清理

```
触发：定时任务 or HTTP /api/v1/orphan-files/scan
  ├─ [定时] app/tasks/scheduler/orphan_scan_task.py  OrphanScanTask (121 行, 每周日凌晨 2 点)
  └─ [HTTP]  app/api/endpoints/orphan_files.py  (153 行)
       └─ app/services/orphan_scanner.py  OrphanScanner (739 行)
            ├─ app/services/orphan_manifest.py  (284 行) 构建实时下载器 manifest
            ├─ 对比 torrent_info 清单 → 找出孤儿文件
            │
            └─ [清理] app/services/orphan_file_service.py  (1088 行)
                 ├─ app/services/orphan_lease.py  (259 行) 跨进程 lease 互斥
                 ├─ app/services/orphan_quarantine.py  (250 行) 隔离区管理
                 └─ app/services/orphan_notification.py  (129 行) 幂等通知
```

---

## 跨层依赖骨架型模块（被高频 import）

| 模块 | 被引用文件数 | 角色 |
|------|------------|------|
| `app.database` | 86 | DB 引擎与会话工厂 |
| `app.services.*` | 50 | 业务服务层 |
| `app.auth.dependencies.require_authenticated_user` | 31 | 认证依赖 |
| `app.core.config` | 28 | 全局配置 |
| `app.api.responseVO.CommonResponse` | — | 统一响应信封 |
| `app.core.database_result` | 11 | DatabaseResult 泛型 |
| `app.core.path_mapping` | 10 | 路径双向映射 |

## 相关文档（完整论述，避免双份真相）

- 配置系统双轨、数据库迁移双轨、残留路由、定时任务代码执行隔离三方案 → [../../backend/docs/architecture-deep-dive.md](../../backend/docs/architecture-deep-dive.md)
- 对上述的独立审查 → [../../backend/docs/architecture-review.md](../../backend/docs/architecture-review.md)
