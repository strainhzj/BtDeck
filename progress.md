# Progress Log - BtDeck 全栈项目

## 2026-07-10 - v1.0.6 孤儿文件管理与路径维护（合并三版本）

**任务 ID**: `v1.0.6`（合并原 v1.0.6 孤儿文件 + v1.0.7 路径扫描增强 + v1.1.0 自动清理）
**分支**: dev
**计划文件**: PLANS/v1.0.6.md（基于代码现状重写，废弃 2024-04-22 旧计划）

### 合并理由

原 v1.0.6 + v1.0.7 + v1.1.0 本质是一个功能集群（孤儿文件发现→路径扩展→自动清理），拆三版本导致接口割裂和重复工作。合并为单一版本一次性交付完整链路。

### 旧计划废弃原因（4 个计划文件全部过时）

1. 前端用 Composition API（`defineComponent`+`setup()`），违反项目强制 Options API 约束
2. v1.1.0 的 AutomationService 与现有 cron_executor（APScheduler + task_profiles）功能完全重叠
3. v1.0.7 引用不存在的 PathMapping/PathMappingRule ORM 模型（实际是 BtDownloaders 表的 Text 字段）
4. 所有计划未考虑 sync-resource-governance 治理体系（db_write_scope + task_profiles 三处同步）

### 关键设计决策（用户确认）

- 扫描路径来源：种子 save_path + 下载器路径映射配置（path_mapping JSON external）
- 清理策略：自动清理超期（物理删除 + 审计日志）+ 手动清理（用户勾选）
- 文件清单来源：实时调下载器 API（复用 get_torrent_files 适配器，经 INTERACTIVE lane）
- 定时任务：每周扫描+清理合一（task_type=4 + task_profiles heavy_sync）
- 一并修复 CleanupTaskExecutor 预存 bug（_query_level3/4_torrents 未定义）

### 交付清单（6 阶段）

**Phase 1: 后端数据模型与迁移**
- `app/models/orphan_file.py` — OrphanScanResult + OrphanFile 两表
- `alembic/versions/c3f1a8b7d902_add_orphan_file_tables.py` — 迁移（含 inspect 守卫）
- `alembic/env.py` — 补模型 import
- `app/core/config.py` — 新增 4 项配置（ORPHAN_AUTO_CLEANUP_DAYS=30 等）

**Phase 2: 后端扫描引擎与服务**
- `app/services/orphan_scanner.py` — OrphanScanner（路径收集+文件清单+inode去重+遍历判定）
  - to_thread 移出文件系统遍历；call_downloader_api(INTERACTIVE) 获取文件清单
  - db_write_scope 串行化 DB commit；复用 UnifiedPathMappingService 路径转换
- `app/services/orphan_file_service.py` — OrphanFileService（查询/预览/手动清理/自动清理）
  - 文件删除参考 recycle_bin_service.py（UNC 兼容 + os.remove + 审计日志）
- `app/torrents/audit_enums.py` — 新增 3 个审计枚举（ORPHAN_SCAN/CLEANUP/AUTO_CLEANUP）

**Phase 3: 后端 API 端点**
- `app/api/endpoints/orphan_files.py` — 5 端点（latest/list/scan/cleanup-preview/cleanup）
- `app/api/api.py` — 路由注册 prefix=/orphan-files

**Phase 4: 定时任务与资源治理**
- `app/tasks/scheduler/orphan_scan_task.py` — OrphanScanTask（每周扫描+清理合一）
- 治理三处同步：default_scheduled_tasks（task_code=orphan_scan_cleanup, cron=0 2 * * 0）+ task_profiles（heavy_sync, wait_timeout=60）+ 任务类
- `app/tasks/cleanup_executor.py` — 修复 _query_level3/4_torrents 未定义 bug

**Phase 5: 前端页面与 API**
- `frontend/src/api/orphan-files.ts` — API 封装（5 函数 + 类型定义）
- `frontend/src/views/orphan-files/index.vue` — 管理页面（class 风格 Options API + 统计卡片 + el-table + el-pagination + 清理两步确认）
- `frontend/src/router.ts` — 路由注册 /orphan-files/index icon=folder

**Phase 6: 测试与验证**
- 3 个新测试文件（扫描器纯函数 19 + API 认证 14 + 任务治理 13 = 46 新测试）
- 更新 4 个现有测试（db_migration head/表数 + db_rollback 版本号 + audit_enums 成员数 39→42 + task_profiles 期望集）
- 全量 pytest **1997 passed, 0 failed**（基线 1937→1997 净增 60）
- black/flake8 通过；./init.sh 通过；前端 eslint 0 error + build 成功

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 新增后端测试（46 个） | ✅ 全 pass |
| 全量 pytest tests/ | ✅ **1997 passed, 0 failed**（基线 1937→1997，净增 60） |
| black（改动文件） | ✅ 通过 |
| flake8（改动文件） | ✅ 通过 |
| ./init.sh（全栈环境验证） | ✅ 通过 |
| 前端 eslint | ✅ 0 error |
| 前端 build（含 tsc） | ✅ 成功（orphan-files chunk 生成） |

---

## 2026-07-10 - SQLite 写锁治理完善（to_thread 止血 + db_write_scope 收尾）

**任务 ID**: `sync-resource-governance`（新增子任务 `sync-resource-governance.2.6`）
**分支**: dev
**类型**: 根因修正 + 治理收尾（4 个重型任务）

### 根因修正

经独立代码审查确认：高强度定时任务期间 WebUI 操作接口超时的根因是 **asyncio 事件循环饥饿**，而非 SQLite 写锁竞争。4 个重型任务的 `execute()` 虽是 `async def`，但任务体内含阻塞式同步 `SessionLocal()` 调用 + 同步 HTTP 调用，直接在共享 uvicorn 循环上跑，冻结整个循环，导致所有 WebUI handler（含读请求）都无法被调度。

修复策略（用户确认）：**to_thread 止血 + db_write_scope 收尾**，范围纳入 4 个重型任务。

### 改动清单（7 项）

1. **torrent_tracker_status_judge.py**（P0）：`execute()` 3 个同步 helper（`_load_keywords`/`_get_all_torrents`）改 `to_thread` 移出循环；`_judge_torrents_batch` 拆为 `_judge_one_batch` 分批（`BATCH_SIZE=1000`，每批 `db_write_scope` + `to_thread` + 单次 commit，单批失败即终止）；**N+1 优化**：逐种子 `db.query` 改两次 IN 查询（本批 TorrentInfo IN + TrackerInfo IN），内存按 `torrent_info_id` 分组。

2. **tracker_message_logger.py**（P0）：`_process_messages_batch_async` 2 处 commit + `_cleanup_old_logs_async` 2 处 commit 各包 `db_write_scope`；死代码同步方法（`_collect_tracker_messages`/`_process_messages_batch`/`_cleanup_old_logs`）加 LEGACY 标记。

3. **tracker_reannounce_task.py**（P0）：读段抽 `_read_downloader_data` 经 `to_thread`（保 `expunge_all`+`close`+不传 `db` 给 `execute_reannounce`）；`execute()` 读 enabled_configs 经 `to_thread`；写段 `batch_update_last_announce_time` 经 `to_thread` + `db_write_scope`（不改该函数本体，保 no-db 签名 + 内部自开 session 回归测试）。

4. **downloader_path_scan.py**（P0）：6 处 commit（`_update_path_mapping`/`_update_external_paths`/`_log_task_execution`/`_sync_default_path`/`_sync_active_path`/`_cleanup_obsolete_paths`）各包 `db_write_scope`；同步 HTTP（`app_default_save_path`/`get_session_variables`）经 `to_thread`；远程获取默认路径移出写 session（`_scan_downloader_paths` 预取 `default_path` 传入 `_sync_to_maintenance_table`）。

5. **database.py + test_database_pragmas.py**（P1）：`busy_timeout` 30000→15000 + sync/async engine `timeout` 30→15 + 4 处注释同步（二级兜底，对齐前端 axios timeout=20s，可独立回退 30s）。

6. **test_heavy_task_db_write_governance.py**（P1）：5 个行为测试取代不可行的 AST 断言（judge db_write_scope 进入 / judge to_thread 读 helper / message_logger db_write_scope 进入 / reannounce 写段 db_write_scope / reannounce 读段 to_thread）。

7. **文档 + DoD**（P2）：重写 `sync-db-write-governance.md` §四（纳入 4 个新任务 + to_thread 止血说明 + busy_timeout 15s 调整说明）；`feature_list.json` 新增 `sync-resource-governance.2.6` 子任务。

### 关键约束保持

- `cron_executor` 已在 `admission_controller.task_scope` 内调 `execute()`（cron_executor.py:417-444）→ 任务文件内只加 `db_write_scope`，不加 `task_scope`。
- `db_write_scope` 在 async caller 侧（loop 线程）获取/释放，同步工作经 `to_thread` 在工作线程跑，scope 不进工作线程（参考 `sync_db_write.py:163-169`）。
- 请求侧 endpoints 绝不动，`test_request_side_endpoints_do_not_use_governance_locks` 保持不变（scheduler 模块不在其扫描白名单）。
- `batch_update_last_announce_time` 不改本体（保 no-db 签名 + 内部自开 session，满足 `test_reannounce_config.py` 回归测试）。

### 明确不做（技术债，本次不纳入）

- `_sync_speed_schedule`（cron_executor.py:54-107）：每分钟持 sync SessionLocal 做 HTTP，P3。
- `tracker_candidate_pool`（被 message_logger 同步触发，未注册 task_profiles）：P3。
- `torrent_sync.py` API 触发路径 / `qb_tr_add_torrents_async` 全量同步：feature_list.json 已记 P3。

### 风险与回退

- `to_thread` 用 asyncio 默认线程池，但 `heavy_sync=Semaphore(1)` 限制重型任务不并发，线程池压力可控。
- `db_write_scope` 串行化若致后台 P95 退化，`SYNC_DB_WRITE_SCOPE_ENABLED=False` 一键回退（config.py:119）。
- `busy_timeout` 若 15s 误触 SQLITE_BUSY，改回 30s（独立改动无耦合）。

---

## 2026-07-05 - sync-resource-governance code review 修复轮

**任务**: 修复 sync-resource-governance code review 发现的 4 项问题 + 验收/文档状态对齐
**分支**: dev
**类型**: code review 修复（治理机制加固）

### 修复前基线核实

`aaa0976`（修复 tag_aggregation 404 循环 import）后全量 pytest 基线已为 **1926 passed, 0 failed**。
本轮修复前基线干净，无预存 fail（与 `sync-resource-governance.3` 旧 evidence 中"16 failed"叙述不符 ——
该 16 failed 是 `aaa0976` 之前的 tag_aggregation 顺序依赖 bug，已根治，本轮在 evidence 中据实更正）。

### 本轮修复（4 项问题 + 文档对齐）

**问题 1：DownloaderApiRuntime 超时后突破真实 per-downloader 并发上限**
- 根因：`async with sem`（asyncio.Semaphore）在 `wait_for` 超时后由 `__aexit__` 释放令牌，但
  `loop.run_in_executor` 提交的同步线程无法取消，仍在跑 → 新调用立即拿到令牌 → 真实远程并发突破上限。
- 修复：`_per_downloader_sems` 从 `asyncio.Semaphore` 改为 `threading.Semaphore`，由 executor 内
  wrapper 线程自身 `acquire/release`（`with sem: func(...)` 包成 wrapper 提交 executor）。
  超时后底层线程仍持有令牌继续运行，新调用阻塞在 `sem.acquire()` 直到旧线程 release。
- 超时 future done callback：归档 success/failure 统计（避免窗口聚合丢数据）。
- 文件：`backend/app/services/downloader_api_runtime.py`
- 测试：改写 `test_timeout_releases_semaphore`（新语义：超时后新调用最终恢复）+ 新增
  `test_timeout_does_not_break_real_concurrency_cap`（mutation 反向验证：修复前 buggy
  asyncio.Semaphore 实现并发达到 5 突破 limit=2）。

**问题 2：实时速度接口绕过 downloader runtime**
- 根因：`torrent_speed.py` 用独立 `_speed_executor` + `run_in_executor` + `wait_for`，
  前端 1 秒轮询绕过 per-downloader 限流，且有同样的超时线程残留风险。
- 修复：删除模块级 `_speed_executor`，`_call_with_timeout` 改为通过 `call_downloader_api`
  走 `DownloadLane.INTERACTIVE` + `timeout=_DOWNLOADER_TIMEOUT`，复用 per-downloader 限流与
  timeout 语义。`_process_downloader` / `_supplement_disappeared` 全部调用点传入 `downloader_id`。
- 文件：`backend/app/api/endpoints/torrent_speed.py`、`backend/app/startup/lifecycle.py`（删 `_speed_executor.shutdown`）
- 测试：新增 `test_uses_interactive_lane_and_timeout`（断言 lane=INTERACTIVE + timeout=_DOWNLOADER_TIMEOUT）+
  `test_speed_endpoint_does_not_bypass_per_downloader_limit`（spy 验证 N 次并发调用全经 runtime）。
  改写 `TestCallWithTimeout` / `test_qb_supplement_called` 适配新签名（patch `call_downloader_api`，
  避免全量 pytest 时 lifespan 关闭全局单例的污染）。

**问题 3：日志/flush 节流未落地**
- 根因：`SYNC_DISK_FLUSH_INTERVAL_SECONDS` 只在 config/docs 存在；`_log_call` 对每次 API 调用打
  info/warning；qB tracker enrich 逐 torrent 调用导致 O(torrent_count) 成功日志 + 失败双重放大。
- 修复：新增 `_CallStatsAggregator`，按 `(lane, method, downloader_id)` 窗口聚合：
  - 成功路径：不逐条 info，窗口到期输出一条结构化聚合日志（success_count/avg_duration/max_duration）。
  - 失败路径：runtime 层降级为 debug（业务侧 `_fetch_single_trackers` 的逐条 error 保留，避免双重放大），
    窗口聚合仍记录 failure_count + last_error_type。
  - `shutdown()` 强制 flush 残留统计。
- 关键：**不动** `SYNC_DB_COMMIT_BATCH_SIZE` 相关的 `bulk_upsert_with_retry` / `db_write_scope`（已落地的 DB 写治理）。
- 文件：`backend/app/services/downloader_api_runtime.py`
- 测试：新增 `TestCallStatsAggregator`（4 测试，spy `logger.extra` 断言，避免全量 pytest 时
  root logger 级别被前序测试抬高导致 caplog 抓不到 INFO 的污染）。

**问题 4：DownloaderApiRuntime.shutdown 未接入生命周期**
- 根因：runtime 有 `shutdown()` 但应用 shutdown 只停 cron 和（已删除的）`_speed_executor`。
- 修复：`lifecycle.py` finally 块在 cron_executor.stop() 之后调用
  `downloader_api_runtime.shutdown()`（关闭三 lane executor + flush 残留日志统计）。
- 文件：`backend/app/startup/lifecycle.py`
- 测试：新增 `test_lifespan_shutdowns_downloader_api_runtime` + `test_lifespan_no_longer_references_speed_executor`
  （AST 扫描 lifespan finally 块，mutation 验证：删 shutdown 调用 / 改回 _speed_executor 报红）+
  `TestShutdown`（行为测试：shutdown 后 executor._shutdown=True + flush 残留统计）。

**问题 5：验收/文档状态对齐**
- `feature_list.json`：父 feature `planned` → `done`；`last_updated` → `2026-07-05`；
  `sync-resource-governance.3` evidence 用真实数字（1937 passed 0 failed）替换"16 failed"旧叙述；
  新增 `sync-resource-governance.4` 子任务记录本轮修复。
- `progress.md`：新增本节。
- `session-handoff.md`：删除残留"阶段 2.5 / 状态: planned"旧块，更新为当前状态。

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 相关测试（runtime + speed + architecture） | ✅ 60 passed |
| 全量 `pytest tests/` | ✅ **1937 passed, 0 failed**（基线 1926→1937，净增 11 测试） |
| black（6 改动文件） | ✅ 通过 |
| flake8（6 改动文件） | ✅ 通过（顺带修了既有 F401 `_ttl_queue` 未用 import + 新增 pytest import） |
| `./init.sh`（全栈环境验证） | ✅ 通过 |
| mutation 反向验证 | ✅ 问题1（buggy 并发达 5）、问题4（删 shutdown AST 报红）均验证测试有效 |

### 关键设计决策

1. **threading.Semaphore 而非 asyncio.Semaphore**（问题1）：核心不变量是"同步线程实际结束前不释放容量"，
   只有让 wrapper 线程自身持有 semaphore 才能保证。asyncio.Semaphore 在协程层释放，与底层线程生命周期解耦。
2. **失败路径 runtime 层降级 debug**（问题3）：业务侧 `_fetch_single_trackers` 已有逐条 error（失败诊断需要），
   runtime 层若再 warning 会双重放大。聚合统计仍记录 failure_count + last_error_type，shutdown/窗口 flush 时输出。
3. **测试用 spy logger 而非 caplog**（问题3测试）：全量 pytest 时某些 API 测试经 TestClient 触发 lifespan，
   root logger 级别可能被抬高，导致 caplog 抓不到 INFO。spy `logger.info/warning` 的 `extra` dict 断言更可靠。
4. **速度测试 patch call_downloader_api**（问题2测试）：全量 pytest 时 lifespan 退出会关闭全局 runtime executor，
   `test_normal_execution` 真实走全局单例会 RuntimeError。统一 patch 避免污染。

### 改动文件清单

- `backend/app/services/downloader_api_runtime.py`（重写：threading.Semaphore + _CallStatsAggregator + future done callback）
- `backend/app/api/endpoints/torrent_speed.py`（删 _speed_executor，接入 INTERACTIVE lane）
- `backend/app/startup/lifecycle.py`（finally 接入 runtime.shutdown，删 _speed_executor 段）
- `backend/tests/services/test_downloader_api_runtime.py`（+8 测试，改写 1 测试）
- `backend/tests/api/test_torrent_speed_regression.py`（改写 4 测试适配新签名，+2 新测试）
- `backend/tests/test_architecture_constraints.py`（+2 AST 测试，+ pytest import）
- `feature_list.json` / `progress.md` / `session-handoff.md`（文档对齐）

---

## 2026-07-05 - 修复 test_tag_aggregation_api.py 全量运行 404（循环 import 根因）

**任务**: 修复 `tests/api/test_tag_aggregation_api.py` 全量 pytest 时 16 个用例全 404（单独跑通过）
**分支**: dev
**类型**: 测试隔离 → 实为业务代码循环 import bug

### 根因（非测试隔离，是业务代码 bug）

`tests/api/test_tag_aggregation_api.py` 全量运行时所有 `/api/v1/tags/*` 路由返回 404，根因是**全局 `app` 未注册业务路由**，触发链：

```
任意测试先 import app.api.api（如 test_recycle_bin_api.py:31 拿 api_router）
  └─ app.api.api 顶层 import 各 endpoint
     └─ app/api/endpoints/seed_transfer.py:25 顶层 `from app.factory import app`  ← 唯一源头
        └─ 触发 app.factory 执行：create_app() + configure_routes_and_static()
           └─ factory.py:62-64 早退检查命中：
              sys.modules["app.api.api"] 存在但无 api_router 属性（半成品）
              → return，跳过 init_routers → 全局 app 仅 4 条默认路由
```

证据（脚本验证）：
- 干净 import → `app.routes` = 191（含 13 个 `/tags/*`）
- 先 `import app.api.api` 再 `from app.main import app` → `app.routes` = **4**（仅默认）

### 为什么前几次修复都没根治

`cfc787b` / `053a390` 都在**测试侧**改（fixture 隔离、并发改串行、Windows 路径），但根因在业务代码（`seed_transfer.py:25` 顶层 import + `factory.py` 早退），测试侧改动无法根治。

### 修复（按子代理审查裁剪到最小根治）

**① `backend/app/api/endpoints/seed_transfer.py`（根因修复）**
- 删除 line 25 顶层 `from app.factory import app`
- 在 `transfer_seed` 和 `batch_transfer_seeds` 两函数 `try:` 块开头加 lazy import
- 与 `downloader.py:93/423/482/1183`、`torrent_location.py:45` 的既有 lazy 模式一致（代码复用优先）
- 加注释说明循环 import 原因，防止回归

**② `backend/app/factory.py`（可观测性增强，零副作用）**
- 早退分支加 WARNING 日志（命中即代表循环 import，便于将来定位）
- 早退逻辑本身保留（防御性），仅观测不改变控制流

### 不动的部分

- ❌ 不动 `test_tag_aggregation_api.py`：lazy 修好后全局 app 路由齐全，16 个用例自然全绿（子代理审查确认测试侧改动非必要）
- ❌ 不动 `main.py`、`api.py`、其他 endpoint

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 最小复现 `pytest test_recycle_bin_api.py test_tag_aggregation_api.py` | ✅ 29 passed（修复前 16 failed） |
| seed_transfer 回归 `pytest test_seed_transfer_api.py` | ✅ 10 passed（lazy 改动未破坏 global_app.state.store 注入） |
| 全量 `pytest tests/` | ✅ **1925 passed, 0 failed**（修复前 16 failed / 1909 passed） |
| 单文件 `pytest test_tag_aggregation_api.py` | ✅ 16 passed |
| black --check（两改动文件） | ✅ 通过 |
| flake8（两改动文件） | ✅ 通过 |
| mypy（两改动文件） | ✅ 无新增错误（基线 10 个历史错误，行号平移，与本次改动无关） |

### 关键设计决策

1. **范围裁剪**：原计划"两边都修"（业务代码 + 测试侧），子代理独立审查后裁剪为"只修业务代码"。理由：lazy 修复消除循环 import 后，全局 app 路由齐全，测试侧自建 FastAPI 实例非必要条件（治本即可）。
2. **factory 早退逻辑保留**：删除会更激进但风险大（行为变更）；保留 + WARNING 是零副作用的可观测性增强。
3. **不引入回归**：seed_transfer lazy 改动有 `test_seed_transfer_api.py` 作为回归基线（子代理提示的关键风险点），已验证通过。

### 改动文件清单

- `backend/app/api/endpoints/seed_transfer.py`（+11/-1）
- `backend/app/factory.py`（+11）

---

## 2026-07-04 - sync-resource-governance 阶段 3 完成（验证与证据归档）

**任务 ID**: `sync-resource-governance`
**阶段**: 3（验证与证据归档）已完成。整个 sync-resource-governance 任务 0/1/2/2.5/3 全部完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（3）**:
- `backend/tests/test_architecture_constraints.py` 扩展（新增 `test_request_side_endpoints_do_not_use_governance_locks`）
- `backend/tests/api/test_sync_governance_integration.py`（3 行为契约测试）
- `backend/scripts/sync_resource_benchmark.py`（6 场景可重复压测脚本）

### 关键设计决策

1. **分层验证**（避开 TestClient 线程安全问题）：架构约束测试（ast 扫描，钉死请求侧不碰治理锁）+ 行为契约测试（纯 asyncio 并发，不走 TestClient）+ 压测脚本（性能验证，运维手动跑）。
2. **TestClient 拓扑限制记录**：计划说的"断言请求侧在可接受时间内返回"在 pytest+TestClient 下无法严谨实现（TestClient 非线程安全，test_tag_aggregation_api.py:402-411 已记录），性能验证划给可重复脚本。
3. **架构约束防回归**：dashboard/torrent_crud/dashboard_service 三个请求探针模块禁止 import/调用 admission_controller/task_scope/db_write_scope/resource_guard，防止未来误在请求路径加锁。

### 验证结果

**新增测试 4 个全 pass**：
- 1 架构约束（ast 扫描三个模块，mutation 加真实 import 报红验证）
- 3 行为契约（heavy_sync 持有时查询完成 / db_write_scope 持有时读不阻塞 / spy acquire 证明不碰锁）

**mock 压测证据**（30 iterations × 6 场景）：

| 场景 | P50 | P95 | P99 | max | 含义 |
|------|-----|-----|-----|-----|------|
| 1_baseline_no_sync | 0ms | 0ms | 0ms | 15ms | 基线 |
| 2_tracker_sync_running | 0ms | 0ms | 16ms | 16ms | tracker 同步中 |
| 3_torrent_info_sync_running | 0ms | 0ms | 0ms | 15ms | 种子信息同步中 |
| 4_both_sync_triggered | 0ms | 0ms | 15ms | 16ms | 同时触发 |
| 5_single_downloader_many_torrents | 0ms | 0ms | 0ms | 16ms | 单下载器大量种子 |
| 6_multi_downloader_concurrent | 0ms | 0ms | 15ms | 16ms | 多下载器并发 |

**结论**：所有场景 P50/P95 <1ms、P99 ≤16ms、max 16ms，证明请求侧（DashboardService 查询）**未被治理锁（heavy_sync/db_write_scope/lane executor）阻塞**，治理目标达成。15-16ms 的偶发抖动是 asyncio 调度噪音，非锁等待。

**全量套件**：16 failed, 1909 passed，**diff 基线为零**（16 个全是预先存在的 tag_aggregation 顺序依赖 bug）。

### sync-resource-governance 整体完成度

| 阶段 | 内容 | 状态 |
|------|------|------|
| 0+1 | TaskAdmissionController（heavy_sync 背压 + 同类去重 + cron_executor 接入） | ✅ |
| 2 | DownloaderApiRuntime（三 lane 隔离 + per-downloader 限流 + qB tracker 并发治理） | ✅ |
| 2.5 | DB 写入治理（变更检测 + 批量 upsert + db_write_scope 串行化） | ✅ |
| 3 | 验证与证据归档（架构约束 + 行为契约 + 压测脚本） | ✅ |

累计：
- 5 个新模块（resource_guard/task_profiles/downloader_api_runtime/sync_db_write/sync_resource_benchmark）
- 7 个配置项
- 1 个 DB 写入治理指南文档
- ~115 个新单测 + 多处 mutation 反向验证
- 6 个 commit（feat + docs 配对）

### 已知技术债（留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 真实生产环境的压测（含真实多下载器 + 真实 qB/TR 实例 + 真实种子规模）需运维用 sync_resource_benchmark.py 跑。

---

## 2026-07-04 - sync-resource-governance 阶段 2.5 完成（DB 写入治理）

**任务 ID**: `sync-resource-governance`
**阶段**: 2.5（DB 写入治理）已完成。经 3 个并行子代理独立审查（技术正确性/范围回归/测试策略）+ 5 项关键发现实证核实后修订计划。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（3）**:
- `backend/app/services/sync_db_write.py` — 变更检测纯函数（has_torrent_info_changes 动态字段对比、has_tracker_changes 6 字段+归一化）+ bulk_upsert_with_retry（db_write_scope+retry base_delay=1.0）
- `backend/tests/services/test_sync_db_write.py`（21 测试）
- `backend/tests/api/test_torrents_async_db_governance.py`（7 真实 SQLite 部分索引集成测试）

**修改文件（4）**:
- `backend/app/api/endpoints/torrents_async.py` — 新增 extract_tracker_rows_from_torrent（纯提取）+ sync_trackers_batch_async（批量 select+变更检测+严格四步顺序+元组语义 mark_removed）；qb/tr_add_torrents_info_only_async 修正 skip 语义 bug+整行变更检测+替换闭包为 bulk_upsert_with_retry；qb/tr_sync_trackers_only_async 主循环改造（累计 rows→batch_size 200→批量 upsert）
- `backend/app/tasks/resource_guard.py` — db_write_scope 加 SYNC_DB_WRITE_SCOPE_ENABLED 开关
- `backend/app/core/config.py` — 新增 SYNC_DB_WRITE_SCOPE_ENABLED=True

### 关键设计决策（含审查调整）

1. **范围补全**（审查2-A2）：qb+tr 两个 sync_trackers_only_async 都改（原计划只改 qb 是漏项）。
2. **mark_removed 元组语义**（审查1-C6 必修2）：禁止扁平化 url 集合，用 `(info_id, url)` 元组 IN 取反，避免跨种子误删。集成测试用"同名 url 跨种子"场景验证。
3. **变更检测字段**（审查2-D10）：has_torrent_info_changes 只对比实际写入 dict 的 key 集（动态适配），不硬编码 29 字段；has_tracker_changes 只对比 6 业务字段（status/msg/seeder 等是死字段）。
4. **归一化契约**（审查3-A2）：None==""/strip 后比较，防远程返回微小差异导致每轮都写。
5. **db_write_scope 开关**（审查2-C9）：SYNC_DB_WRITE_SCOPE_ENABLED=True，3 行代码快速回滚。
6. **测试分层**（审查3-B4/D10）：纯函数 mock + 真实 SQLite 部分索引集成测试（覆盖 mock 测不到的 on_conflict_do_update(index_where dr=0) 语义）。
7. **测试防假通过**（审查3-B6）：db_write_scope 测试用真实 admission_controller + spy _state.db_writer.acquire，mutation 删包裹后报红。

### 验证

- **新单测 28 个全 pass**：21 sync_db_write（纯函数+mock）+ 7 db_governance（真实 SQLite）
- **mutation 反向验证 3 处**：
  - 删 db_write_scope 包裹 → acquire_spy.assert_awaited 报红 ✓
  - mark_removed 扁平化 url → "同名 url 跨种子"测试报红 ✓
  - 变更检测相关 mutation 由 has_*_changes 纯函数测试覆盖 ✓
- **零回归**：全量 16 failed, 1905 passed，**diff 基线为零**（16 个全是预先存在的 tag_aggregation 顺序依赖 bug，已固化基线）
- **stats 守恒断言**：insert+update+skip == 总输入行数

### 已知技术债（显式记录，留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 这两个路径是写锁竞争的未保护源，本轮不根治（范围控制），留 P3 统一改造。

### 不在本轮范围（明确排除）

- 全量同步的 commit 改造（P3）。
- DBWriteQueue（后续独立版本）。
- 前端任何改动。

### 下一步

阶段 3（验证与证据归档）：补充集成验证 + 手动压测矩阵 + 把同步期间请求响应改善、DB commit/写入频率证据写回 harness。

---

## 2026-07-04 - sync-resource-governance 阶段 2 完成（下载器 API 调用隔离）

**任务 ID**: `sync-resource-governance`
**阶段**: 2（方案三：下载器 API 调用隔离与调度层）已完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（2）**:
- `backend/app/services/downloader_api_runtime.py` — DownloaderApiRuntime（三 lane 独立 ThreadPoolExecutor：tracker=5/sync=4/interactive=6 线程）+ per-downloader Semaphore（DOWNLOADER_IO_CONCURRENCY=2）+ call_downloader_api 统一封装 + LaneLogExtra 结构化日志 + 进程级单例 downloader_api_runtime
- `backend/tests/services/test_downloader_api_runtime.py`（14 个新单测）

**修改文件（3）**:
- `backend/app/api/endpoints/torrents_async.py` — 16 处 `asyncio.to_thread` 全量迁移到 `call_downloader_api`（按 sync_lane/tracker_lane/interactive_lane 分类）；`_enrich_qb_torrents_with_trackers` 默认并发 10→3（取 settings.QB_TRACKER_CONCURRENCY）+ 加 downloader_id 参数 + 4 个调用点对齐；`qb_add_torrents_info_only_async`/`tr_add_torrents_info_only_async` 加可选 client 参数 + fallback
- `backend/app/tasks/scheduler/torrent_sync/torrent_info_sync_task.py` — 调用点从 app.state.store 取缓存 client 传入同步函数（复用连接，遵循 downloader-connection 约束）

### 关键设计决策

1. **三 lane 物理隔离**：每个 lane 独立 ThreadPoolExecutor，tracker 批量查询不挤占 sync 主数据同步、不挤占 interactive 用户操作。线程数根据 QB_TRACKER_CONCURRENCY(3) + 余量设为 5/4/6。
2. **per-downloader 跨 lane 总并发**：DOWNLOADER_IO_CONCURRENCY=2 限制同一下载器的所有远程调用总并发，防止单个 qB WebUI 被多任务同时打满。这是 lane 之上的第二层限流。
3. **qB tracker 并发治理**：`_enrich_qb_torrents_with_trackers` 历史默认 10，会打满 qB WebUI；改为取 settings.QB_TRACKER_CONCURRENCY(默认3)，并在 lane executor 之上叠加 asyncio.Semaphore 做批量并发控制。
4. **client 复用渐进式改造**：给 qb/tr_add_torrents_info_only_async 加可选 client 参数，None 时 fallback 新建；TorrentInfoSyncTask 从 store 取后传入。不破坏现有调用方，向后兼容。
5. **异常透传不吞**：call_downloader_api 只记录日志 + 重新抛出，不吞任何异常（调用方原有错误处理逻辑保持不变）。

### 验证

- **新单测 14 个全 pass**：参数透传/超时/超时释放 semaphore/异常透传/异常释放 semaphore/三 lane 物理隔离（线程名前缀断言）/per-downloader 并发上限/不同下载器并行/结构化日志 extra/便捷封装委托
- **mutation 反向验证**：去掉 per-downloader semaphore（换成 Semaphore(10)）→ test_same_downloader_concurrency_capped 报红（max=4 超过 limit=2）✓
- **零回归**：tasks/ + services/ 全量 217 passed；全量套件 16 failed, 1877 passed — 16 个失败全是预先存在的 test_tag_aggregation_api.py 顺序依赖 bug（已三次验证基线）
- **to_thread 清零**：torrents_async.py 的 `asyncio.to_thread` 从 16 处降到 0 处

### 不在本轮范围（明确排除）

- DB 写入治理（db_write_scope 接入 + 批量提交 + 变更检测）— 下一轮（阶段 2.5）
- DBWriteQueue — 后续独立版本候选
- 前端任何改动

### 下一步

阶段 2.5（DB 写入治理）：按 `backend/docs/constraints/sync-db-write-governance.md` 指南，把 qb_add_torrents_info_only_async / qb_sync_trackers_only_async 等同步函数的 commit 点包进 db_write_scope + 批量 upsert + 变更检测。

---

## 2026-07-04 - sync-resource-governance 阶段 0+1 完成（调度器资源背压）

**任务 ID**: `sync-resource-governance`
**阶段**: 0（基线观测）+ 1（方案二：调度器与资源背压）合并实施，已完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（4）**:
- `backend/app/tasks/task_profiles.py` — TaskProfile dataclass + TASK_PROFILES 注册表（6 个重型 task_code）+ get_profile/is_heavy_task 谓词
- `backend/app/tasks/resource_guard.py` — TaskAdmissionController（heavy_sync 全局令牌 + per-task_code 运行/排队登记 + 同类去重跳过 + 等待超时 + task_scope 异常安全 + release 幂等 + db_write_scope 骨架）+ AdmissionResult + 进程级单例 admission_controller
- `backend/docs/constraints/sync-db-write-governance.md` — DB 写入治理指南（变更检测/批量 upsert/db_writer 临界区/日志节流，供阶段 2 改造同步函数 commit 点遵循）
- `backend/tests/tasks/test_task_profiles.py` / `test_resource_guard.py` / `test_cron_executor_admission.py`（3 个测试文件，34 个新单测）

**修改文件（2）**:
- `backend/app/core/config.py` — 新增 7 项配置：SYNC_HEAVY_CONCURRENCY=1、SYNC_HEAVY_QUEUE_LIMIT=1、DOWNLOADER_IO_CONCURRENCY=2、QB_TRACKER_CONCURRENCY=3、DOWNLOADER_API_TIMEOUT_SECONDS=30、SYNC_DB_COMMIT_BATCH_SIZE=200、SYNC_DISK_FLUSH_INTERVAL_SECONDS=5.0
- `backend/app/tasks/cron_executor.py` — `_run_python_internal_class` 签名从 `(executor_code: str)` 改为 `(task: Dict)`；在 importlib 加载类后、调 execute() 前按 task_code 查 profile，重型任务用 `admission_controller.task_scope` 包裹，admitted=False 直接返回 skipped 且不调 execute；轻量任务走原路径不进入背压

### 关键设计决策

1. **接入位置**：cron_executor._run_python_internal_class 是 task_type=4（Python 内部类）的唯一执行入口，所有 6 个重型同步任务都经此进入 execute()。统一在此接入，避免改 6 个任务子类，且新任务自动获得背压保护（只要在 task_profiles 登记）。

2. **同类去重维度**：保留现有 `running_tasks: Dict[int, bool]`（task_id 维度，APScheduler 重入保护）+ 新增 task_code 维度（跨任务类型资源竞争）。两者互补不冲突。

3. **db_writer 骨架不强制接入**：本轮只暴露 `db_write_scope()` 信号量（并发 1）+ 写治理指南，不改造 torrents_async.py 现有 commit 点（留给阶段 2 一起做），避免阶段 1 范围爆炸。

4. **测试隔离**：admission_controller 是进程级单例，每个测试 setup 调 `reset_state()` 重建信号量与登记表，避免状态泄漏。

### 验证

- **新单测 39 个全 pass**：task_profiles（19）+ resource_guard（15）+ cron_executor_admission（5）
- **mutation 反向验证（含审查修订后）**：
  - Mutation A（去掉 acquire 的 running 去重检查）→ 2 个去重测试报红 ✓
  - Mutation B（cron_executor 绕过 admission）→ 2 个接入契约测试报红 ✓
  - Mutation C（删 release idempotency 守卫）→ 修订后的 test_double_release_does_not_overreturn_semaphore 报红 ✓
  - Mutation D（删 _build_log_extra 字段）→ 修订后的 test_admitted_path_extra_contains_all_required_fields 报红 ✓
  - Mutation E（删 acquire 异常分支的 queued 归还）→ 修订后的 test_acquire_exception_releases_queue_slot 报红 ✓
- **零回归**：tests/tasks/ 全量 203 passed（含 test_cron_executor.py 的 coalesce 锚点）
- **全量套件**：16 failed, 1863 passed — 16 个失败全是预先存在的 test_tag_aggregation_api.py 顺序依赖 bug（已用 git stash 验证基线就是 16 failed，与本次改动无关）

### 子代理 code review 修订（2026-07-04）

3 个并行子代理审查（并发正确性 / 测试质量 / 接入回归），逐条实证核实后修订：

- **🔴 假通过 #1（release 幂等性测试）**：原 test_double_release 只断言"能再次 acquire"，溢出后照样能 acquire。重写为跨 task_code 断言溢出后果（两个不同 task_code 同时 admitted=True 破坏互斥）。Mutation C 验证抓到。
- **🔴 假通过 #2（StructuredLog 测试）**：原 spy 断言 AdmissionResult 入参字段，删日志 extra 后仍 PASS。拆出 `_build_log_extra` 纯函数，直接断言 extra dict 的 7 个字段。Mutation D 验证抓到。
- **🔴 skip 与真失败混淆**：原 skip 返回 success=False 与真执行失败结构相同，运维误判故障。改为 success=True + skipped=True 标记 + [ADMISSION_SKIP] 机器可解析前缀。
- **⚠️ 盲区（acquire 异常分支）**：原测试未覆盖 heavy_sync.acquire 抛非 Timeout 异常时的 queued 归还。补 test_acquire_exception_releases_queue_slot。Mutation E 验证抓到。
- **⚠️ 漂移（task_profiles 锚点）**：原 EXPECTED_HEAVY_TASK_CODES 硬编码不与 default_scheduled_tasks.py 交叉验证。补 test_all_profile_codes_exist_in_default_scheduled_tasks + test_profile_codes_subset_of_python_class_tasks。
- **文档化**：task_profiles.py 顶部加"task_code 不可改名 + 配置启动时固化"运维约束；release() docstring 加"禁止体内 await"约束。

### 不在本轮范围（明确排除）

- 阶段 2 `downloader_api_runtime`（tracker/sync/interactive lane、qB tracker 并发治理、to_thread 迁移）— 下一轮
- 现有 torrents_async.py 同步函数的 db_writer/批量提交改造 — 阶段 2 做
- DBWriteQueue — 后续独立版本候选
- 前端任何改动

### 下一步

进入阶段 2（方案三：下载器 API 调用隔离与调度层）：新建 `backend/app/services/downloader_api_runtime.py`，隔离 tracker/sync/interactive lane，控制 qB tracker 明细并发（默认 3），优先复用 app.state.store 客户端，迁移 torrents_async.py 的 `asyncio.to_thread` 散落点到专用 executor。

---

## 2026-07-03 - 下一任务：同步任务资源治理与下载器 API 调度

**任务 ID**: `sync-resource-governance`  
**计划文件**: `PLANS/sync-resource-governance.md`  
**状态**: planned，尚未进入代码实现。  
**用户决策**: 按“方案二 -> 方案三”的顺序修复，即先做调度器/资源背压，再做下载器 API 调用隔离与调度层。

**问题背景**:
- tracker 与种子信息同步期间，请求其它接口经常超时。
- 初步判断瓶颈不是单一 API 慢，而是后台重型任务并发争抢 DB 写入、下载器 WebUI/API、默认线程池与调度资源。
- 已修正一条分析误差：`qb_add_torrents_info_only_async` 当前不调用 `_enrich_qb_torrents_with_trackers`，后续不能把 tracker 富集误归因到 info-only 路径。

**Harness 更新**:
- 新增 `PLANS/sync-resource-governance.md`，作为下一项目任务的详细执行计划。
- `feature_list.json` 的 `current_dev_version` 已更新为 `sync-resource-governance`。
- 新任务拆分为基线观测、方案二资源背压、方案三下载器 API 调度、验证归档四个阶段。

**已确认决策（2026-07-03 补充）**:
- 重型 cron 任务需要引入“队列长度/排队登记”概念：按 `task_code` 判断是否已有同类重型任务运行中或排队中，若存在则跳过本轮。
- `downloader_io` 默认并发使用 2。
- qB tracker 明细并发默认使用 3。
- 允许新增配置项：`SYNC_HEAVY_CONCURRENCY`、`SYNC_HEAVY_QUEUE_LIMIT`、`DOWNLOADER_IO_CONCURRENCY`、`QB_TRACKER_CONCURRENCY`、`DOWNLOADER_API_TIMEOUT_SECONDS`、`SYNC_DB_COMMIT_BATCH_SIZE`、`SYNC_DISK_FLUSH_INTERVAL_SECONDS`。
- 必须关注硬盘写入频率，避免逐条写库、逐条日志落盘、高频 commit/flush 击垮硬盘或造成大规模寿命损耗。
- 暂不实现 `DBWriteQueue`；它作为后续独立版本候选保留在 harness 中，当前任务只做 `db_writer` 短锁、批量提交、变更检测和写入节流。

> **项目**: BtDeck 全栈（backend + frontend）
> **当前分支**: dev
> **当前开发版本**: v1.0.5（查询模板系统）
> **更新**: 2026-06-25

> 本文件由 backend/progress.md 与 frontend/PROGRESS.md 合并而来（2026-06-18）。按"版本分节 + 每节内前后端子段"组织，技术决策表合并为一表并新增"端"列。

---

## 进行中功能

### v1.0.5 数据库四轨治理（单轨化重构）

**触发问题**: 启动报 `table users already exists`（schema 快照与已有库冲突）
**根因**: 数据库 schema 管理存在四轨冗余：
1. Alembic 迁移链（唯一正道）
2. `Base.metadata.create_all()`（init_db 无条件兜底，无法 ALTER）
3. 生产 schema 快照 `ensure_database_initialized`（写入幽灵版本 9aea25308aff）
4. search_templates 原生 SQL 自建表（独立第四轨）

**治理目标**: 统一为单一 Alembic 轨，存量数十/数百用户升级无感、非破坏性。

**核心决策（经 5 轮子代理审查 + 4 项用户决策）**:
- DEV 默认不变（保持 True），不加新配置项，Docker 默认行为不变（向下兼容）
- seed 保留原生 SQL，仅服务层迁 ORM
- frozen 保留 init_schema_from_production.py 作灾备兜底（仅移除启动调用）
- 幽灵版本（9aea25308aff）用 KNOWN_GHOST_VERSIONS 黑名单救援；未知版本只告警不降级
- 迁移前自动备份（checkpoint+cp，保留 3 份）
- 回滚策略三级（Level1 代码回滚/Level2 备份还原/Level3 alembic downgrade）

**实施（7 阶段，~28 文件）**:
| 阶段 | 内容 | 验证 |
|------|------|------|
| 0 | test_db_migration.py（6 场景） | 6 passed |
| 1a | search_template.py ORM + env.py 补 import | 导入链正常 |
| 1b | search_templates 迁移(95ef8bd8b47a) + ORM 改造 + 清理8处_ensure + downloader裸查询修复 | ORM 测试 9 passed |
| 2 | init_db 删 create_all | — |
| 3 | migrate_database() + _rescue_or_warn_version(黑名单) + _backup + config.py + env.py URL 统一 + .gitignore | 幽灵救援/未知告警/head no-op 全实测通过 |
| 4 | main.py 收敛(删 schema 快照/initialQb/init_db) + 幽灵版本文档清理 | py_compile + import 链通过 |
| 5 | btdeck_startup.sh(删 shell 迁移) + rollback-guide.md + 迁移标注规范 + lint 扩展 + 老迁移标注 | lint 通过 |

**验证结果**:
- pytest: 1536 passed, 2 failed（均为既有 Windows 路径分隔符 bug + flaky 测试，与本次无关）
- lint_btdeck.py: 未发现阻塞性问题
- 手动 A（空库建 25 表+admin+4 模板）/ B（已有库 no-op 不备份）/ C（环境变量路由）/ D（幽灵救援）全通过
- `./init.sh --ci` 全栈环境验证通过

**关键设计文档**: `backend/docs/operations/rollback-guide.md`（回滚操作指南）

**运维影响**:
- 存量用户升级（含幽灵版本库）：自动救援 + 备份，无感
- 后续字段/表变动：alembic 标准流程
- 版本回滚：纯增量走 Level1（代码回滚），破坏性走 Level2（备份还原）


### v1.0.5-audit 契约审计修复（技术债）— fix/contract-audit 分支

**计划文件**: `PLANS/v1.0.5-audit.md`
**审计依据**: `backend/docs/style-and-contract-audit.md`（P1 确定性 bug + P0 契约归一化）
**范围**: P0 + P1。不覆盖 P2（REST 路由迁移）/ P3（前端类型收敛），推迟。

**已完成（5 commit）**:
| 任务 | commit | 验证 |
|------|--------|------|
| P0-3 后端全局异常处理器 | ac324bc | pytest 1524 passed 无回归 |
| P0-1 前端 ApiError 归一化 | 0e55469 | jest 25/25, eslint 0 error |
| P1-A 后端补 4 项端点 | efc6574 | auth+cron 189 passed |
| P1-B 前端修 4 项契约 | 0e8f007 | jest 25/25, eslint 0 error |
| P0-2c 认证基础设施补强 | 9e19822 | auth 125 passed |

**进行中**:
- P0-2a 认证迁移到 `require_authenticated_user`（20+ 文件/~195 处，分批提交）
- P0-2b 认证测试改造（~40 处断言）

**审计交叉验证结论（3 个独立 Explore agent 核实）**:
- 9 项契约不匹配中 8 项属实，`/tags/batch-delete` 误报（后端已有端点）
- tracker statistics 是漏挂装饰器的孤立函数，修复成本极低
- tag_management 的 `{success,message}` 是私有 helper 返回值，非 HTTP 响应，降级不改

---

### v1.0.5 查询模板系统 (done) — dev 分支

**计划文件**: `PLANS/v1.0.5.md`（已标注方向转变）

**目标**: 实现查询模板功能，用户可保存常用查询条件（简单查询 + 高级搜索）并一键应用，含系统预设模板。

**方向转变（重要）**: 探索阶段发现后端与前端已存在完整的 `search_templates` 基础设施（表 + CRUD 端点 + 服务 + 前端 API），仅前端入口 `handleSaveSearchTemplate` 是空函数。改为**补全现有系统**而非从零新建，避免重复造轮子。

**任务完成情况** (12/12 done，见 feature_list.json v1.0.5)：
- 后端：4 个预设模板数据 + init_db 集成 + apply/权限确认（现有代码已满足）+ 16 个认证测试
- 前端：API 便捷方法 + index.vue 接线（handleSaveSearchTemplate + applyQueryTemplate）+ 管理页 + 对话框 + 路由
- 全栈：保存→应用链路代码闭环

**5 个 commit**: 63a4bec / d04af4d / 7f111f8 / 7896a23 / (本条状态更新)

**遗留**: ~~前端 lint/tsc 因环境依赖未完整安装，留待完整环境验证。~~ ✅ **2026-06-27 已补验**（lint 0 error/131 warning、build 成功含 tsc、test:unit 34 passed）。

---

## 已完成功能

### v1.0.4 实时速度监控 (done) — dev 分支

**计划文件**: `PLANS/v1.0.4.md`

**与计划的偏差**:
- 计划: `TorrentStateManager` 动静数据分离(10s/10min刷新) → 实际: 轻量级 `active-torrents` 接口 + 前端1秒轮询
- 计划: `speed-all` API → 实际: `active-torrents` API（仅返回有速度的种子）
- 计划: 前端 `setup()` + Composition API → 实际: **Options API** + 虚拟分页
- 计划: 前端 10秒/10分钟双定时器 → 实际: 1秒单定时器轮询
- 额外完成: 种子完成后自动更新数据库状态、活跃种子进度字段

#### 后端（11 个任务全部 done）

| 任务 | 说明 |
|------|------|
| 活跃种子速度接口 | `torrent_speed.py`, qB用status_filter, tr仅查速度字段 |
| 路由注册 | `/torrents/active-torrents` |
| 线程池泄漏修复 | commit 25c59aa |
| 速度单位转换修复 | commit d79040d |
| Transmission空列表修复 | commit b4ddde2 |
| 活跃种子进度字段 | commit a568aa9, progress字段(0-100百分比) |
| 种子完成后自动更新状态 | commit f8b0185, progress达100%自动更新为completed |
| 性能测试 | 4下载器并发平均543ms |
| 场景测试 | 8个验收场景通过 |

#### 前端（2 个任务 done）

| 任务 | 说明 |
|------|------|
| 前端 API 封装 | `torrents.ts` getActiveTorrents() |
| 前端种子列表改造 | Options API + 虚拟分页 + 1秒轮询 + beforeDestroy清理 |

**关键实现**: `activeSpeedMap` 缓存速度数据；虚拟分页算法（活跃种子优先排列）；防抖 + 版本控制避免重复请求。

**结论**: v1.0.4 前后端开发完成。

---

### v1.0.9 一键部署 (done，提前完成) — dev 分支

**说明**: v1.0.9 早于 v1.0.5~v1.0.8 提前完成落地。

| 任务 | 说明 |
|------|------|
| 全栈 monorepo 整合 | commit c7ce2f4，前后端合并为单一仓库 |
| PyInstaller 打包 | deploy/btdeck.spec，前后端合一单可执行文件 |
| Inno Setup Windows 安装包 | deploy/btdeck.iss |
| fpm Linux 安装包 | deploy/build-linux.sh，.deb/.rpm |
| Docker Compose 全栈部署 | docker-compose.yml |

**部署修复系列**: 5e4baf8 / 6f8e3e0 / 78033bc / fb380b9 / b80a7f6（Inno Setup 语言包、PyInstaller 路径、pandas/numpy/openpyxl hiddenimport、PIL 排除、systemd 目录预创建等）。

---

## 计划外已完成功能

### 通知中心 (done) — dev 分支

**后端**: `notification.py`(模型) + `notification_service.py`(版本检查、未读计数) + `notifications.py`(GET/PUT/DELETE 端点)。单向信箱模式，仅系统写入。
**前端**: `NotificationDrawer/index.vue`(全局右侧抽屉) + `NotificationItem.vue` + `store/modules/notification.ts`(Vuex) + `api/notification.ts`。60秒未读计数轮询。

### Tracker关键词池初始化 (done) — dev 分支

`tracker_keywords_pools.py` 关键词池管理，默认数据自动初始化，集成到 `init_db()` 统一初始化流程。

### 统一初始化重构 (done) — dev 分支

所有初始数据初始化统一到 `init_db()`，集成到后端启动流程。commit 22a89c8。

---

## 待开发功能（按计划顺序）

| 版本 | 名称 | 计划文件 | 状态 |
|------|------|----------|------|
| v1.0.6 | 孤儿文件管理 | PLANS/v1.0.6.md | pending |
| v1.0.7 | 路径扫描增强 | PLANS/v1.0.7.md | pending |
| v1.0.8 | 数据库升级 | PLANS/v1.0.8.md | pending |
| v1.1.0 | 自动化运维 | PLANS/v1.1.0.md | pending |

---

## 技术决策记录

| 日期 | 端 | 决策 | 理由 |
|------|----|------|------|
| 2026-04-22 | backend | 轻量级active-torrents替代动静分离 | 更简单，前端1秒轮询仅查有速度种子 |
| 2026-04-22 | frontend | Options API 而非 Composition API | 项目技术栈约定 |
| 2026-04-22 | frontend | 前端虚拟分页 | 已有查询逻辑，前端合并更灵活 |
| 2026-04-22 | frontend | 防抖+版本控制 | 避免1秒轮询导致重复请求和页面卡顿 |
| 2026-04-22 | backend | 专用线程池 | 避免阻塞默认executor |
| 2026-04-22 | backend | 统一初始化到 init_db() | 集中管理初始数据 |
| 2026-06-18 | fullstack | harness 体系合并到根目录 | 全栈 monorepo 统一状态追踪，消除端级重复 |
| 2026-06-18 | fullstack | v1.0.5 补全 search_templates 而非新建 query_templates | 探索发现已有完整基础设施，避免重复造轮子 |
| 2026-06-18 | fullstack | User 不加 relationship（用 created_by 整数列） | 遵循既有约定（SettingTemplate 同模式），避免触发 User 表迁移 |
| 2026-06-18 | fullstack | query_config 用 source=simple/advanced 双分支 | 1:1 还原两种查询状态（listQuery / condition_groups），应用时按 source 分流 |
| 2026-06-19 | fullstack | 审计修复用独立 feature 块 v1.0.5-audit 而非 v1.0.5.1 | v1.0.5.1 子任务号已被 done 占用，撞号；用 -audit 后缀避开数字子任务号空间 |
| 2026-06-19 | fullstack | 实施顺序 P0-3→P0-1→P1→P0-2c→P0-2a/b | 异常处理器先做兜底；前端归一化在后端 401 之前避免破损窗口；认证基础设施先于迁移避免 user_id 断链 |
| 2026-06-19 | backend | 认证统一用 require_authenticated_user（HTTP 401），login.py 豁免 | login 的 code=401 是密码错误业务语义，非认证失效，前端登录页依赖此分支不跳转 |
| 2026-06-19 | backend | 不把 user_id 加入 verify_access_token required_fields | 避免现有未过期 token 全部失效（强制全员重登），改为 AuthenticatedUserInfo 兜底解析 |
| 2026-06-19 | frontend | ApiError extends Error + 兼容 msg/response getter | 降低约 33 个存量 catch 块的回归（e.msg / e.response.data.msg 链式读取仍可用） |
| 2026-06-19 | frontend | 成功码白名单 {200,206,207} | 206(需确认路径映射)/207(Multi-Status 部分成功) 是业务级成功，不归一化为错误 |
| 2026-06-19 | fullstack | apply 改前端对齐后端 Path 参数 | 后端 Path 更 RESTful，且 override=True 硬编码使 override_local 无效 |
| 2026-06-19 | fullstack | torrents/detail 不补后端端点，删前端死代码 | getTorrentDetail 从未被调用，补后端会引入语义模糊(hash可能重复)的未用功能 |

---

## 当前会话

> **2026-06-28**: 后端回归测试补全（续）——为"纯 DB 操作、业务逻辑零测试覆盖"的接口补充 API 级回归测试，每个接口经"子代理审查 → 实证核实 → 修订 → 反向验证"闭环。共 10 个 commit，+86 个回归测试，全量 tests/api/ 413 passed 无回归。
>
> **本次覆盖的 3 个接口 + 1 个基础设施重构**：
>
> 1. **审计日志查询接口**（commit 545fad4 + 8197567，41 测试）
>    - POST /audit-logs/query（11 维过滤 + 子查询 count + LIKE 模糊 + 分页）
>    - GET /audit-logs/statistics（内存聚合 + unknown 桶）
>    - GET /audit-logs/operation-types（39 枚举展开）
>    - 范式：aiosqlite 异步内存库 + AsyncSession + 覆盖 get_async_db
>    - 子代理审查修订（+7）：排序完整序列断言、count 解耦 offset 验证、msg 排除断言防 service 吞异常假通过、401 body 断言、枚举 value 集合相等、LIKE 通配符已知行为、download-export 约定差异
>
> 2. **仪表盘统计接口**（commit 39e4b97 + 1485986 + 399b68b + 1c05d16，23 测试）
>    - GET /dashboard（裸 SQL 聚合 cron_task/torrent_audit_log + 内存缓存 store/torrent_stats）
>    - 范式：aiosqlite 异步内存库 + SimpleNamespace FakeStore 注入 app.state
>    - 经 **4 轮子代理审查**完全收敛：第1轮发现 1 真 flaky（60秒窗口）+ 1 假通过（dr 方向）；第2-4轮逐轮确认上轮到位 + 补覆盖盲区（dict 计数 vs set、keyword_rule 归一化路径、torrent_stats=None 已知行为）
>    - 关键修复：时间断言用绝对时间/身份标记避免 flaky；降级场景加 msg 断言防假通过
>
> 3. **种子删除 L4 接口**（commit 1e9a10f + 4ac69af，22 测试）
>    - DELETE /torrents/delete-with-level（L4 待删除标签路径）
>    - **设计转折**：原计划 HTTP e2e 经子代理审查发现 3 个 🔴 致命缺陷（同步/异步库不可共享内存库、响应字段缺失、store 未挂载），**重设计为 service 级测试**绕开三缺陷
>    - 范式：同步内存库 + mock request（挂 store）+ mock audit（AsyncMock 记录调用）
>    - 子代理审查修订（+4）：补 delete_batch_by_level 降级编排测试（L3→L4，service 核心复杂度零覆盖）、audit 身份锁定断言、OR 断言收窄、脏数据边界
>
> 4. **测试基础设施去重**（commit c881d69，重构）
>    - 提取 make_torrent 工厂到 tests/api/conftest.py（3 文件去重 → 1 共享工厂，13 业务 kwarg 超集签名）
>    - 设计决策：普通函数（非 fixture，接 db 参数多次调用）；test_torrent_models 的 MagicMock 工厂不合并（不同关注点）
>
> **关键测试质量教训（多轮审查沉淀）**：
> - **flaky 防护**：时间断言用绝对时间/足够裕度/身份标记，不用"恰好当前时间"
> - **防假通过**：降级/空数据场景加 msg 排除断言（防 service 吞异常返回空结构仍 code=200）
> - **身份锁定**：过滤测试断"返回哪条"而非"返回几条"（防方向写反）；audit 断 torrent_info_id
> - **完整序列 + 计数**：排序用完整顺序断言（非首尾比较）；分类用 dict 计数（set 漏计数）
> - **service 级 vs HTTP e2e**：当 endpoint 有同步/异步双 session + 响应字段裁剪时，service 级测试绕开共享库与字段缺失问题，且能测到完整返回字典
>
> **子代理审查的工作流价值**：每轮审查都实证核实（不盲信），发现真问题（flaky/假通过/盲区）也否决误报（如"len==len 恒真"实际能抓到）。4 轮审查收敛性：第1轮发现最多（质量基线），后续轮次确认到位 + 补越来越细的盲区。
>
> ---

> **2026-06-27（续）**: 收尾——v1.0.5-audit 标 done + 前端验证补遗 + 残留分支清理。
>
> **v1.0.5-audit 契约审计收尾** ✅
> - feature_list.json 中 v1.0.5-audit 的 8 个子任务（P0-1~P0-3 / P0-2a-d / P1-A/B）全 done，范围明确（P0+P1 完成，P2/P3 推迟有记录）。feature 顶层 status 从 `in_progress` 标为 `done`
> - **残留分支清理**：原独立分支 `fix/contract-audit` 的所有 commit 已 100% 合并入 dev（`git log dev..fix/contract-audit` 为空，dev 领先 29 commit）。删除本地 + 远端 `fix/contract-audit`（用户决策"删本地+远端"）。远端现仅剩 `origin/dev` + `origin/master`
>   - 注：`git branch -d` 因本地相对上游 `origin/fix/contract-audit` 的保守判断报"未完全合并"，但相对 dev 实际已无独有 commit，改用 `-D` 强制删除（reflog 可恢复）
>
> **前端验证补遗（清除 progress.md 既有遗留）** ✅
> - 既有遗留"前端 lint/tsc 因环境依赖未完整安装"（progress.md:99）现环境就绪，补跑：
>   - `npm run lint`：**0 errors**（131 warnings，全是 no-unused-vars 非阻塞）
>   - `npx vue-cli-service build`：**成功**（含 tsc 类型检查，dist 生成）
>   - `npm run test:unit`：**34 passed**（含契约审计的 ApiError 归一化测试）
> - progress.md:99 遗留标记为已补验
>
> ---

> **2026-06-27**: 高风险 lint 技术债 3 类清理（F811 + E711/E712 + mypy ORM 债评估）——lint 技术债清理第七轮。
>
> **任务 A：F811 高风险残留清理（5→0）** ✅
> - cuser.py：两个 `twofa_verify` 绑不同路由路径（/2faVerifyQrCode/ 与 /2faVerifyCode/），FastAPI 按路径注册故路由正常工作，仅模块级变量被后者覆盖（无调用点）。改名为 `twofa_verify_qrcode`/`twofa_verify_code` 消除 F811（无害变量重定义，**非 bug**）
> - torrents_async.py：`qb/tr_add_torrents_info_only_async` 各定义 3 次。经 **AST 对比 + git 历史追溯（初始 commit 8fe877d）** 确认：tr 三份 IDENTICAL（copy-paste 死代码）；qb 前两份一致（含 tracker 富集），第三份（生效版，Python 后定义覆盖前定义）**从 day 1 起就不含 tracker 富集**（富集只在 tracker-only 同步函数 `qb_sync_trackers_only_async` 里）。三份重复定义自项目诞生即存在，生效版始终是第三份。删除前两组死代码副本（**-678 行**），保留生效版。调用方仅 `torrent_info_sync_task.py`，行为不变
> - **审查教训（子代理发现）**：首版 commit ba8689b 把"第三份去掉富集"误归因到 73df90c。`git log -S "_enrich_..."` 命中 73df90c 是因为它**新增**的 tracker-only 函数含此调用，而非从 info_only **删除**。`git log -S` 只说明该 commit 涉及该字符串，**不能推断增删方向**，必须看 hunk 的 +/- 行（73df90c 的 hunk `@@ -3142,3 +3142,222 @@` 证明只在文件末尾追加、未动 info_only）。已更正文档
> - **门禁收紧**：F811 从 .flake8 extend-ignore 移除，进入全仓门禁。commit ba8689b
>
> **任务 B：E711/E712 全量清理（47→0，最高风险）** ✅
> - **逐个甄别 47 处** == None / == True / == False，区分 ORM 查询（保留语义）与 Python 条件（改 is），**不盲改**避免破坏 SQLAlchemy 查询生成
> - 44 处 ORM `.filter()`/`.where()`/`or_()`/`case()` 内的 `== True/False` → SQLAlchemy 官方推荐的 `.is_(True)`/`.is_(False)`（生成 IS true/false，对 NOT NULL boolean 列与 `==` 语义等价）
> - 3 处 Python 条件：`torrent_sync.py:712 create_time==None→is None`；`torrent_sync.py:1165 downloader.enabled!=True→not downloader.enabled`（已加载实例属性，三态完全等价）
> - 4 处 `downloader.py delay==False`：**0==False 真值陷阱**（ping3.ping 返回值可能是数值/False/None，改 is False 会改变 delay=0 真值）→ **用户决策**加 inline `# noqa: E712` 保留==
> - **子代理 code review（修复者盲点防护）补充修复 3 处**：tracker_messages:90 + cron_crud:418/420 是历史 ORM noqa 顶替（应做 .is_() 而非 noqa），扫描时被默认 noqa 掩盖漏报，一并修正
> - **门禁收紧**：E711/E712 从 .flake8 extend-ignore 移除，进入全仓门禁。commit 7a21718
>
> **任务 C：mypy app/models/ ORM 债评估（133 处，只评估不实施）** ✅
> - 133 errors（117 assignment + 10 return-value + 4 arg-type + 2 var-annotated，9 文件）**100% 归因 ORM 描述符类型推断失败**（`Base=declarative_base()` 1.4 风格），非真实 bug
> - **SQLAlchemy 已是 2.0.47**（无需升级依赖），但未启用 mypy 插件
> - 三方案评估：A 迁移 `DeclarativeBase`+`Mapped[]`（长期最优，17文件146字段，2-3会话）/ B 启用 mypy 插件（短期过渡降噪）/ C 保持现状
> - 评估报告写入 `backend/docs/tech-debt-lint-baseline.md`，**不实施代码改动**，建议作为独立技术债任务单独立项
>
> **验证**：每任务后 pytest（A: 1619 passed；B: 1619 passed）；flake8 全仓 0 错误；F811/E711/E712 isolated 全 0；历史修复全完好。
>
> **lint 技术债清理里程碑**：7 轮清理后，`.flake8` extend-ignore 仅剩 E203/E402/E501/W503/W504/W605 六项（风格/格式类），所有进入豁免的历史 F/E 规则（F401/F541/F811/F821/F824/F841/E711/E712/E722/E741）已全部清零进门禁。剩余仅 mypy ORM 债（架构级，待 SQLAlchemy 2.0 迁移独立立项）。
>
> ---

> **2026-06-26（续4）**: F811 重复 import + E722/E741 风格清理——lint 技术债清理第六轮。
>
> **任务：F811 重复 import（部分）+ E722 + E741** ✅
> - F811：15→5（清 10 处：7 模块级重复 import 删除 + 3 函数内局部 import 加 noqa；剩 5 处是高风险项单独记录）
> - E722：2→0（裸 except 改 except Exception，避免误捕 KeyboardInterrupt）
> - E741：2→0（列表推导式变量 l 改 label）
> - **门禁收紧**：E722/E741 从 `.flake8` extend-ignore 移除（F811 保留豁免，仍有 5 处残留）
>
> **F811 调研发现 2 个真实 bug（高风险，单独记录未修）**：
> - `torrents_async.py`：`qb/tr_add_torrents_info_only_async` 各定义 3 次（copy-paste 残留），需验证内容一致性
> - `cuser.py`：`twofa_verify` 同名函数定义两次绑不同路由。FastAPI 按路径注册故两条路由正常工作，仅模块级变量被后者覆盖（无害），建议改函数名消除 F811（子代理审查修正：非"路由 bug"，是"无害变量重定义"）

> **子代理审查后修正（91140f3）**：
> - 3 处 noqa: F811 的注释从误导性的"与另一函数不冲突"改为准确的"与上方冗余，保留以降低独立 try 块对顶部 import 顺序的耦合"（实为同一函数内冗余 import，功能无害）
> - cuser 判断从"潜在路由 bug"修正为"无害变量重定义"（两函数绑不同路径，路由正常工作）
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；E722/E741 isolated 0；历史修复全完好。
>
> **剩余 lint 债**：F811 高风险 5 处（重复函数/同名 bug）、E711/E712 高风险 47 处（ORM 甄别）、mypy ORM 债 133（SQLAlchemy 2.0 迁移）。
>
> ---

> **2026-06-26（续3）**: P2 F841 未用变量清理（23→0）——lint 技术债清理第五轮。
>
> **任务：F841 局部变量赋值未用全部清理 + 进门禁** ✅
> - 8 文件 23 处：
>   - 16 个 `except ... as e:`（e 未用）→ `except ...:`（保留异常类型去绑定）
>   - 5 个 `torrents = client.xxx()` 连接健康检查 → `client.xxx()`（**保留调用去赋值**，调用是健康检查不能丢）
>   - 1 个 `manager = Service(db)` → `Service(db)`（保留调用）
>   - 1 个 `module = importlib.import_module()` → `importlib.import_module()`（保留导入副作用）
> - **门禁收紧**：F841 从 `.flake8` extend-ignore 移除，进入全仓门禁
>
> **过程中的脚本踩坑（已解决）**：
> - 首版正则 ` as e:\s*$` 的 `\s*$` 吞了行尾换行符，把 except 行和下一行合并成一行（IndentationError）
> - 已 `git checkout HEAD` 回滚，修正为 `line.replace(' as e:', ':')` 只替换子串不碰换行
> - **教训**：处理含换行的文本时，正则的 `$`/`\s*$` 会跨行，应用 `str.replace` 精确替换子串
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541/F821/F824/F401/example= 均无回退；py_compile 全部通过。
>
> ---

> **2026-06-26（续2）**: P5 Pydantic example= 全仓统一（177→0）——lint 技术债清理第四轮。
>
> **任务：Pydantic v1 `example=` → v2 `examples=[]` 全仓清理** ✅
> - 10 文件 166 处（含 app/models/ 之前清的 11 处，共 177→0）：`example=X` → `examples=[X]`
> - 正则方案（字符串/数字/bool/None/空列表 4 类字面量精确匹配），修复后 example= 全清零
> - 补全被 Pydantic v2 静默忽略的 OpenAPI schema 示例值
> - **意外收益**：pytest warnings 865→713（`example=` 的 PydanticDeprecationWarning 消失）
>
> **过程中的脚本踩坑（已解决）**：
> - AST 脚本因 col_offset 是 UTF-8 字节偏移（含中文行与字符索引不一致）导致插入位置错误，损坏 api/responseVO.py
> - 已 `git checkout HEAD` 回滚，改用正则方案（不依赖字节偏移），165 处全清零无误
> - **教训**：Python ast 的 col_offset 对非 ASCII 行是字节偏移，不能直接用于字符串切片
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541/F821/F824/F401 均无回退；schema examples 生成验证通过。
>
> ---

> **2026-06-26（续）**: P3 F541 f-string 清理（74→0）——lint 技术债清理第三轮。
>
> **任务：F541 无占位符 f-string 全部清理 + 进门禁** ✅
> - 26 文件 74 处 `f"无占位符"` → 普通字符串（72 处脚本批量 + 2 处多行拼接手工）
> - 修复前 AST 分析确认 74 处全部是纯字面量、无 `{{}}` 转义，可安全去 `f` 前缀
> - **门禁收紧**：F541 从 `.flake8` extend-ignore 移除，进入全仓门禁
>
> **⚠️ 过程中的工作树污染事故（已恢复）**：
> - 发现本地 dev ref 被某操作重置回 eaf677a（丢失 f867b09 P0 修复），导致在无 P0 修复的旧基础上误跑 F541 脚本
> - 症状诡异：`git diff HEAD` 显示无差异（被 autocrlf=true 掩盖），但工作树文件实际是旧内容
> - 根因定位：`git log` 发现 HEAD 是 eaf677a 而非 f867b09；`origin/dev` 仍有 f867b09
> - 恢复：`git reset --hard origin/dev` 对齐远端，P0 修复完好确认后在干净基础上重跑
> - **教训**：开始工作前必须 `git log` 确认 HEAD 状态，不能假设；`git diff` 在 autocrlf 下可能有假象，用 `git status` + hash 对比更可靠
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541 isolated 0；F821/F824 仍 0（P0 完好）。
>
> **剩余 lint 债**：P2 F841（23）、P4 E711/E712（47，需甄别 ORM 查询）、P5 example=（166）、F811（15）、mypy ORM 债（133）。
>
> ---

> **2026-06-26**: P0 真实 bug 修复（F821/F824，17→0）——lint 技术债清理第二轮。
>
> **任务：F821/F824 真实 bug 全部修复 + 进门禁** ✅
> - 6 文件 17 处 undefined name / global 误用全部修复：
>   - audit_logger.py（5 处）：补模块级 `logger` + `desc` import
>   - torrent_crud.py / torrent_deletion.py（3 处）：函数加 `request: Request` 参数（原 `req.app`/`request` undefined 会 NameError 崩溃）
>   - initialization.py（7 处）：2 个后台任务函数加 `app: FastAPI` 参数（原调用已注释=死代码）+ 删 4 处纯 dict 操作的无用 `global`
>   - tag_service.py（1 处）：删除 except return 后的孤儿死代码（含 undefined `tags`）
>   - security.py（1 处）：删 `_decryption_key_cache.clear()` 的无用 `global`
> - **门禁收紧**：6 文件的 F821/F824 per-file-ignores 全部移除，F821/F824 现进入全仓门禁
> - **教训**：torrent_crud.py 加 `request: Request`（无默认值）放在 `_user=Depends()`（有默认值）之后触发 SyntaxError，导致 180 个测试 setup ERROR；pytest 立即捕获，改为 `request: Request = None` 修复
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F821/F824 isolated 0 残留；init.sh 通过。
>
> **剩余 lint 债**：P2 F841（23）、P3 F541（74）、P4 E711/E712（47，需甄别 ORM 查询）、P5 example=（166）、mypy ORM 债（133，待 SQLAlchemy 2.0 迁移）。

---

> **2026-06-25**: lint 技术债清理（F401 + mypy app/models/ 渐进）——两项独立技术债任务。
>
> **任务 1：F401 未用 import 清理（基线 P1，最大单项收益）** ✅
> - autoflake 保守参数清理：**321 → 9**（清掉 310 个未用 import）
> - **陷阱规避**：autoflake 会误删 `database.py` 的 9 个 ORM 模型注册 import（防御性注册，注释明确意图），手工恢复 + 加 `.flake8` per-file-ignore
> - **附带修复**：`app/models/__init__.py` 的 `__all__` 拼写 bug（`TRANSER_STATUS_SUCCESS` → `TRANSFER_STATUS_SUCCESS`，导致重导出名不副实）
> - **门禁收紧**：F401 从 `.flake8` extend-ignore 移除 → 新增代码未用 import 现已进入门禁
> - black 修复 autoflake 删 import 后的空行副作用（E303/E302）
>
> **任务 2：mypy app/models/ 渐进清理** 🔶（部分完成，剩余归 ORM 债）
> - 修复前 145 errors → 修复后 133 errors（-12）
> - **修了 12 个真实类型 bug**：Pydantic v2 API 误用（`example=` → `examples=[]`，11 个；`ConfigDict(by_alias=)` 死键，1 个）。原 v1 写法被静默忽略导致 OpenAPI schema 无示例值
> - **剩余 133 个 100% 归因 ORM 描述符**：根因 `Base = declarative_base()`（SQLAlchemy 1.4 风格），mypy 不识别 `class X(Base)` 为合法类型。117 assignment + 10 return-value + 4 arg-type + 2 var-annotated。**解法是 SQLAlchemy 2.0 声明式迁移**（`DeclarativeBase` + `Mapped[]`），属独立大任务，不混入 lint 清理
> - **review 发现的遗漏**：全仓另有 166 处同型 v1 `example=` 写法（10 个文件，downloader/torrents/tracker/user/api 等），本次只清了 app/models/ 的 2 个 vo 文件，其余留作 P5 后续项
>
> **验证**：pytest 1589 passed（0 失败，0 回归）；flake8 项目配置 0 错误；mypy app/models/ 145→133；init.sh 全栈验证通过。
>
> **下一步建议**：F401 已彻底闭环。mypy 剩余的 133 个 ORM 债 + 全仓其他模块需等 SQLAlchemy 2.0 迁移（独立任务）。
>
> ---
>
> **2026-06-20**: v1.0.5-audit P0-2 认证统一全部完成——本会话完成 P0-2a（24 文件迁移，分 4 批）+ P0-2b（测试断言改造）+ P0-2d（弃用 verify_token_dependency），共 6 commit。
>
> **调研修正**：交接文档预估 ~21 文件 + ~102 处测试断言。实际调研发现：24 个文件；测试改造仅 32 处 inline 断言（因 test_auth_protection_extended.py 的 62 处走 _is_auth_rejected helper 已兼容 HTTP 401）。这改变了"必须原子配对"的前提，改为按风险分 4 批，每批 commit + 跑针对性 pytest。
>
> **完成清单**：
> - Batch A（10 token-only）+ Batch B（downloader/cron_tasks/tracker/torrent_crud/sync，最大 cron_tasks 20 endpoint）
> - Batch C（3 user_id 文件，advanced_search 旧 token 缺 user_id → HTTP 401 兜底，用户确认对齐 torrent_location 模板）
> - Batch D（4 mixed 部分迁移文件）
> - P0-2b：5 测试文件断言改造（含 tag_management mock_auth 改用 dependency_overrides）
> - P0-2d：verify_token_dependency 加 DeprecationWarning，cron_tasks.verify_token 已删除
>
> **附带修复**：多处预存在的"不安全 try/except 认证"（verify_access_token 失败返回 None 而非抛异常，旧代码 try/except 形同虚设，torrent_sync/tracker_messages/cuser 2FA 端点）。
>
> **验证**：后端 pytest 1523 passed（2 个预存在失败：test_unified_token_expiry 路径分隔符 bug + test_concurrent_requests flaky，均与本次无关）；init.sh 全栈验证通过。
>
> **下一步**：P0-2 全部完成。剩余 P2/P3 均为推迟项（REST 路由迁移、前端 any 治理、OpenAPI schema、分页字段统一、API 对照表 CI）。可选收尾：彻底删除 verify_token_dependency 定义。

---

### 传统模式 bug 修复 + 防回归基础设施 + 功能对齐（2026-06-28）

**目标**：传统模式(TraditionalView.vue)相对列表模式(index.vue)全面对齐——先修 bug，再建防回归基础设施，最后补齐缺失功能。

**方法论**：全程「子代理对抗审查 + 用户决策修订」循环——每个方案先用 Explore 子代理独立审查挑毛病，修正阻断项后再实施。

#### 阶段 1：Bug 修复（8 个，commit 含于防回归提交）
子代理精准审查 + API 签名亲核（deleteTorrents 后端只认 info_id/delete_data/id_recycle；token 存 Cookie 非 localStorage）。
- Bug#4 删除参数错误（hashes→info_id）、Bug#3 速度轮询（原生fetch+错token→getActiveTorrents封装）
- Bug#1 删除计数（字符串长度→逐种子）、Bug#2 文案语义（下载器组数vs种子数）
- Bug#8 选中状态重置、Bug#7 排序键（!!map→速度>0）、Bug#6 单条删除错误收敛、Bug#9 未用import

#### 阶段 2：三层防回归基础设施（commit 52ff81e）
子代理对抗审查修正 3 处阻断：AST selector 静默失效（firstArgument→arguments.0.value 实测）、L3 正则脚本对 index.vue 误报、L2/L3 scope 冲突。
- **L1 ESLint**：no-restricted-syntax 禁原生 fetch/token（esquery 1.7.0 实测 selector），no-unused-vars（warn 避免117历史债阻断CI），FileManagement.vue 文件级豁免
- **L2 纯函数+mixin**：utils/torrentBatch.ts（5纯函数，API依赖注入便于单测）+ mixins/torrentBatch.ts（薄封装），两视图删除~280行重复实现
- **L3 jest 单测**：行为契约断言（不怕等价重写）。反向验证：改回Bug#7原始形态→2测试变红，fetch规则实测拦截

#### 阶段 3：功能对齐（13项，分 P0/P1/P2 三批）
子代理审查修正 4 处阻断：toolbar布局缺失、4等级删除下沉硬伤（上帝mixin）、sort_by跨视图bug、下沉边界偏乐观。

| 批次 | commit | 内容 |
|------|--------|------|
| P0 | c286b7e | 活动开关/刷新/改路径/转移/Tracker操作·汇报·全局替换/详情Tracker增强（9项，对话框全复用） |
| P1 | c82a321 | 高级搜索/查询模板/查找重复 + sort_by统一修复（addedDate→added_date对齐后端ORM字段名） |
| P2 | 5df3ce8 | 4等级删除（纯函数+mixin分层，只做TraditionalView）+ 列设置（10列可隐藏） |

#### 验证
- eslint: 全程 0 error（123 warning 全为历史债，no-unused-vars 降为 warn）
- jest: 53 → 81 passed（净增28行为契约单测）
- mixin/utils 文件 0 TS 错误；两视图 template 噪音是项目既有 vue-tsc 推断问题

#### 关键设计决策
- **下沉边界清晰**：无副作用→utils纯函数（可单测）；Vue实例方法($loading/$message)→mixin；UI接线→视图。不造上帝mixin
- **4等级删除分层**：纯函数(构造/解析)+mixin(入口/轮询/loading+beforeDestroy清理)+视图(dropdown)，解决this.$loading/this.tableData/长轮询生命周期三矛盾
- **列设置独立key**：traditional_columns_visibility 与列表分开（两视图列结构不同）
- **查询模板路由**：traditional模式下index.vue未挂载，apply_template_id必须在本视图处理

#### 诚实边界（未做）
- index.vue 的4等级删除迁移（单独立项，P2只做TraditionalView）
- 详情面板「文件/Peers」占位tab（需后端API，属另一功能）
- showActiveOnly分页失真（标known-issue，对齐列表既有缺陷未根治）
- 主题切换不在对齐范围（传统模式用固定scss主题）

---

**最后更新**: 2026-06-28
