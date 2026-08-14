# architecture — 关键调用链索引

> 5 条关键业务流程的调用链索引，标注 `文件:行号` 定位。⚠ 完整架构论述（配置双轨、迁移双轨、定时任务隔离三方案）见 [../../backend/docs/architecture-deep-dive.md](../../backend/docs/architecture-deep-dive.md)，本文件不重复。

---

## 链 1：应用启动流程

```
入口（Docker）
  btdeck_startup.sh:102
    exec uvicorn app.main:app ...
      │
      └─ app/main.py:26  from app.factory import app
            └─ app/factory.py:116  app = create_app(configure_routes=False)
                  │  app/factory.py:84  create_app()
                  │    ├─ L92  FastAPI(lifespan=lifespan)
                  │    ├─ L94-101  CORSMiddleware
                  │    ├─ L104-106  register_exception_handlers(app)
                  │    └─ L108-109  configure_routes_and_static(app)
                  │         └─ app/startup/routers_initializer.py:6  init_routers(app)
                  │              └─ app/api/api.py:40  api_router (prefix=/api/v1)
                  │
直接运行（非 Docker import 路径）
  app/main.py:140-163
    init_config_file() → yaml.reload() → migrate_database()
      └─ 失败时拒绝进入 Server.run()

FastAPI lifespan（请求进入前）
  app/startup/lifecycle.py:262  lifespan(app)
    ├─ L302 migrate_database()（失败时 fail-fast，后续均不执行）
    ├─ L318 init_db()
    ├─ L327 await init_database_connection()
    ├─ L332 await reconcile_orphan_file_state() # 分批对账历史隔离候选
    ├─ L350 recover_interrupted_orphan_scans()  # running → failed
    ├─ L364 await update_cron_task_status()
    ├─ L375 await cron_executor.start()         # 启动 APScheduler
    │             └─ app/tasks/cron_executor.py  AsyncIOScheduler.add_job (L60/L142/L791)
    ├─ L391 asyncio.create_task(startup_event(app))
    │             └─ app/downloader/initialization.py:682  startup_event(app)
    │                  ├─ L709  _async_initialization_tasks
    │                  ├─ L729  _load_initial_downloaders
    │                  └─ L795  _perform_initial_full_sync
    ├─ L397 持久化孤儿清理任务恢复
    ├─ L404 queued 孤儿扫描恢复
    ├─ L408 run_dashboard_stats_loop
    ├─ L412 check_version_update_task
    └─ L416 add_version_update_notification_task
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
  ├─ [定时] app/tasks/scheduler/orphan_scan_task.py  OrphanScanTask (242 行, 提交并等待 dispatcher 终态，阶段摘要进入 Cron task_logs)
  └─ [HTTP]  app/api/endpoints/orphan_files.py  POST /scan (L317，handler L318)
       └─ app/services/orphan_scan_job_service.py (477 行)
            ├─ 持久化 queued scan_id/task_id 并立即返回
            ├─ GET /scans/{scan_id} 只读单行轮询状态
            └─ OrphanScanDispatcher 串行调度/重启恢复/定时等待终态
                 └─ app/services/orphan_scanner.py  OrphanScanner (927 行)
                      ├─ orphan_manifest.py 严格映射 + 实时 manifest
                      ├─ 文件系统核查 → 稳定 current detail
                      └─ orphan_lifecycle_service.py (454 行)
                           └─ 每 200 条短事务查询/更新/resolved + db_write_scope

列表：orphan_file_service.py (3438 行)
  ├─ 文件夹父行只做 SQL 聚合
  └─ /folders/children 展开后独立分页，仅当前可见文件 stat 硬链接

清理：预览/手动/前缀/定时公用最新批次门禁；>50000 条在路径映射+样本复核前全部拒绝，未复核状态向仍有活跃候选的后续小扫描传递
```

## 链 6：高级搜索（HTTP → 契约校验 → 有界正则 → ORM 执行）✨v1.0.6.25~28

```
HTTP POST /api/v1/advanced-search
  └─ app/api/endpoints/advanced_search.py  (436 行)
       │
       ├─ [请求期契约校验]
       │    app/api/models/advanced_search.py  (706 行, Pydantic)
       │      └─ import app/contracts/advanced_search.py
       │            └─ ADVANCED_SEARCH_CONTRACT ← advanced_search_contract.json
       │                 （SUPPORTED_SEARCH_OPERATORS / allowed_operators_for_field / FRONTEND_TO_BACKEND_OPERATOR）
       │      → 字段级白名单；include/exclude 模式独立；旧模板值兼容归一
       │
       ├─ [正则执行熔断]（仅 regex 类条件）
       │    app/services/sqlite_search_runtime.py  (100 行)
       │      ├─ validate_regex_pattern  (请求期编译 + lru_cache 256)
       │      └─ _sqlite_bt_regexp       (单次 match 10ms 超时 + 查询总预算 2s 双重熔断，防 ReDoS)
       │
       └─ [ORM 查询执行]
            app/services/advanced_search.py  AdvancedSearchService (1397 行)
              ├─ 20 字段查询引擎；字段级空值操作符 + include/exclude 严格补集
              ├─ Tracker 否定以 NOT EXISTS 覆盖多 Tracker；文本通配符按字面、标签按完整 token
              ├─ 下载器 UI 提交稳定 ID，并兼容当前/历史 nickname；超级做种是/否/不支持三态
              └─ 基础查询排除 dr/deleted_at/活动删除，避免回收站泄漏
```

> **前后端契约守卫**：`advanced_search_contract.json` 是单一源，前端生成 `advancedSearch.generated.ts`；`npm run contract:check` 检测生成漂移，`operator-contract.spec.ts` 再执行运行时值/模式兼容守卫。

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
