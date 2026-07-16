# Session Handoff - BtDeck 全栈项目

## 2026-07-16 交接：全栈回归测试质量 P0 整改完成

**当前任务**: `v1.0.6.12`
**分支**: dev
**状态**: 实现与验证完成；本次会话提交并推送。

### 关键结果

- pytest 进程级独立数据库 + 真实 Alembic，禁止访问开发业务库；`OrphanScanner` session factory 可注入。
- 活动种子快照采用五态语义；非权威快照返回 206，权威空快照返回 200；前端保留列表、刷新后受控重试。
- 大活动集合通过 SQLite TEMP 表复合键联接；600 键在变量限制降到 50 时仍通过且无临时表泄漏。
- Jest 组件测试恢复收集，TypeScript 请求契约补齐；根级 GitHub Actions 统一前后端回归门禁。

### 验证

- 后端：2089 passed, 1 skipped；coverage 40.58%；架构检查通过。
- 前端：4 suites / 142 tests；`tsc --noEmit`；生产 build 通过。
- 变更文件 black/flake8 与 `git diff --check` 通过。
- `backend/config/app.db` 测试前后 SHA256 `FBC031EF2CC021D34AE86218A0F6482CC60E917F8EB0A1D3B1627BF93A081A94`、大小与 mtime 均不变。
- 根 `init.sh` 在 Git Bash 下退出 0；Git Bash PATH 的 Node 警告由独立 Node 门禁覆盖。

### 已知技术债

- 全仓 mypy 基线：1534 errors / 123 files。
- 全量测试目录 flake8 仍有既有债务；本次变更文件为 0 错误。
- Vue SFC 历史语义类型债务未纳入本次 P0；`.ts/.tsx` 严格门禁、SFC 编译与组件测试均已启用。

### 未纳入提交

- `.zcode/`、镜像 tar、旧 pytest 输出目录、个人 `tools/`、`.docker_temp_482561487` 等用户未跟踪文件。

---

## 2026-07-12 交接：v1.0.6 孤儿文件安全闭环修复完成

**当前任务**: `v1.0.6.11`
**状态**: 实现与验证完成，尚未提交（用户未要求 commit）。

### 关键结果

- 实时下载器 inventory 是扫描与清理的唯一权威 manifest；不完整即拒绝。
- 手动/自动清理都只做可恢复隔离，不直接删除源文件；到期 purge 采用 tombstone 二次复核。
- scan_id、授权扫描根、完整文件身份、统一维护 lease 和操作 journal 构成清理门禁。
- 扫描最终 DB 写入已事务化；通知失败由每小时补偿任务重试；隔离区由每日任务清除。
- 新迁移：`e6d8a20c41f3_orphan_operation_journal.py`，接在已发布的 `b075727f7182` 后。

### 验证

- 后端相关：152 passed, 1 skipped
- 后端全量：2068 passed, 1 skipped
- flake8 / git diff --check：通过
- 前端目标 eslint / 生产 build：通过（仅既有 warning）
- 根 `init.sh`：当前 Windows 环境缺少 Git Bash/WSL，未执行

### 注意

- 未触碰用户文件：`.zcode/`、`btdeck-backend.latest.tar`、`btdeck-frontend.latest.tar`。
- 工作区内遗留若干 pytest 临时目录因 Windows ACL 无法普通删除；均为未跟踪测试产物，不应提交。

---

## 2026-07-10 交接：v1.0.6 孤儿文件管理与路径维护完成

**当前任务**: `v1.0.6`（合并原 v1.0.6 孤儿文件 + v1.0.7 路径扫描增强 + v1.1.0 自动清理）
**状态**: done。6 阶段全部完成。
**计划文件**: `PLANS/v1.0.6.md`（基于代码现状重写，废弃 2024-04-22 旧计划）
**分支**: dev

### 本轮完成

合并三版本为一个功能集群，实现孤儿文件发现→清理→自动化完整链路：

1. **后端数据模型**：OrphanScanResult + OrphanFile 两表 + Alembic 迁移 c3f1a8b7d902（含 inspect 守卫）+ 4 项配置
2. **扫描引擎**：OrphanScanner（路径收集 to_thread + 文件清单 call_downloader_api INTERACTIVE + inode 去重 + 遍历判定 + db_write_scope 批量写入）
3. **清理服务**：OrphanFileService（分页查询/预览/手动清理/自动清理超期，文件删除参考 recycle_bin_service UNC 兼容 + 审计日志）
4. **API 端点**：5 端点（latest/list/scan/cleanup-preview/cleanup），require_authenticated_user 认证 + CommonResponse 响应
5. **定时任务**：OrphanScanTask 每周日 2 点扫描+清理合一，task_profiles 三处同步（orphan_scan_cleanup heavy_sync wait_timeout=60）
6. **bug 修复**：CleanupTaskExecutor _query_level3/4_torrents 未定义方法补全（task_type=5 触发路径原会 AttributeError）
7. **前端**：orphan-files.ts API + index.vue 管理页（class 风格 Options API + 统计卡片 + el-table + el-pagination + 清理两步确认）+ 路由注册

### 验证结果

- 新增 46 测试全 pass（扫描器 19 + API 认证 14 + 任务治理 13）
- 全量 pytest **1997 passed, 0 failed**（基线 1937→1997 净增 60，零回归）
- black/flake8 通过；./init.sh 通过
- 前端 eslint 0 error + build 成功（tsc 通过，orphan-files chunk 生成）

### 关键设计决策

1. **合并三版本**：v1.0.6+v1.0.7+v1.1.0 本质一个功能集群，拆三版本导致接口割裂
2. **复用 cron_executor**：不新建 AutomationService（与现有调度框架重复）
3. **实时调下载器 API**：复用 QBittorrentDeleteAdapter/TransmissionDeleteAdapter 的 get_torrent_files，经 INTERACTIVE lane 受 per-downloader 限流
4. **治理合规**：to_thread 移出同步操作 + db_write_scope 串行化 + task_profiles 三处同步
5. **迁移 inspect 守卫**：orphan_file_tables 迁移加 inspect 守卫（表已存在时 no-op），与 search_templates 迁移风格一致

### 快速恢复

```bash
cd backend
# 跑本轮新测试
python -m pytest tests/services/test_orphan_scanner.py tests/api/test_orphan_files_api.py tests/tasks/test_orphan_scan_task.py -v
# 全量回归
python -m pytest tests/ -q
# 前端验证
cd ../frontend && npx eslint src/api/orphan-files.ts src/views/orphan-files/index.vue && npx vue-cli-service build
```

### 下一步可选方向

1. **v1.0.8 数据库升级（PostgreSQL）**：推迟中，先验证 sync-resource-governance 治理效果。若治理后无 DB 瓶颈可无限期推迟
2. **真实环境压测**：孤儿文件扫描在真实多下载器 + 大量种子场景的性能验证（文件清单获取是瓶颈，受 per-downloader 并发限制）
3. **P3 已知技术债**：全量同步 + API 触发路径接入 db_write_scope（sync-resource-governance 遗留）
4. **前端 index.vue 4 等级删除迁移**（traditional-view-align 遗留技术债）

---

## 历史交接（按时间倒序，精简归档）

### 2026-07-10 - SQLite 写锁治理完善（to_thread 止血 + db_write_scope 收尾）

- 4 个重型任务（judge/message_logger/reannounce/path_scan）的 execute() 体内阻塞式 SessionLocal/HTTP 调用改 to_thread 移出循环 + db_write_scope 串行化。
- busy_timeout 30000→15000 + sync/async engine timeout 30→15。

### 2026-07-05 - sync-resource-governance code review 修复轮完成

- 4 项治理机制缺陷修复（threading.Semaphore + 速度接口接入 INTERACTIVE lane + 日志聚合 + lifecycle shutdown）。
- 全量 1937 passed 0 failed。

修复 sync-resource-governance code review 发现的 4 项治理机制缺陷：

1. **DownloaderApiRuntime 超时突破真实 per-downloader 并发上限**
   - `asyncio.Semaphore` → `threading.Semaphore`（由 executor 内 wrapper 线程自身 acquire/release），
     确保"同步线程实际结束前不释放容量"。超时后底层线程仍持有令牌，新调用阻塞直到 release。
   - 新增 `test_timeout_does_not_break_real_concurrency_cap`（mutation 反向验证：buggy 实现并发达 5 突破 limit=2）。
2. **实时速度接口绕过 runtime 旁路限流**
   - `torrent_speed.py` 删除独立 `_speed_executor`，`_call_with_timeout` 接入 `DownloadLane.INTERACTIVE` +
     `timeout=_DOWNLOADER_TIMEOUT`，复用 per-downloader 限流避免前端 1s 轮询成为旁路压力源。
3. **日志/flush 节流落地**
   - 新增 `_CallStatsAggregator` 按 `(lane, method, downloader_id)` 窗口聚合（落地
     `SYNC_DISK_FLUSH_INTERVAL_SECONDS`）。成功路径不逐条 info；失败路径 runtime 层降级 debug
     （避免与业务侧 error 双重放大）；shutdown 强制 flush。**不动** DB 写治理（`SYNC_DB_COMMIT_BATCH_SIZE`）。
4. **runtime.shutdown 接入生命周期**
   - `lifecycle.py` finally 块调用 `downloader_api_runtime.shutdown()`（关闭三 lane executor + flush 统计），
     删除已废弃的 `_speed_executor.shutdown` 引用。

### 验证结果

- 相关测试（runtime + speed + architecture）：60 passed
- 全量 `pytest tests/`：**1937 passed, 0 failed**（基线 1926→1937，净增 11 测试，零回归）
- black / flake8：通过
- `./init.sh`：通过
- mutation 反向验证：问题1（buggy 并发达 5）、问题4（删 shutdown AST 报红）均验证测试有效

### sync-resource-governance 整体完成度

| 阶段 | 内容 | 状态 |
|------|------|------|
| 0+1 | TaskAdmissionController（heavy_sync 背压 + 同类去重） | ✅ |
| 2 | DownloaderApiRuntime（三 lane 隔离 + per-downloader 限流 + qB tracker 并发治理） | ✅ |
| 2.5 | DB 写入治理（变更检测 + 批量 upsert + db_write_scope 串行化） | ✅ |
| 3 | 验证与证据归档（架构约束 + 行为契约 + 压测脚本） | ✅ |
| 4 | code review 修复轮（超时并发 + 速度旁路 + 日志节流 + 生命周期） | ✅ |

### 已知技术债（留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 真实生产环境的压测（含真实多下载器 + 真实 qB/TR 实例 + 真实种子规模）需运维用 sync_resource_benchmark.py 跑。

### 快速恢复

```bash
cd backend
# 跑本轮新测试
python -m pytest tests/services/test_downloader_api_runtime.py tests/api/test_torrent_speed_regression.py tests/test_architecture_constraints.py -v
# 全量回归
python -m pytest tests/ -q
```

### 下一步可选方向

sync-resource-governance 任务已全部完成（含 code review 修复）。剩余可选方向：
1. **P3 已知技术债**：全量同步 + API 触发路径接入 db_write_scope
2. **真实环境压测**：运维在 staging/生产用 sync_resource_benchmark.py 跑，对比部署前后
3. **DBWriteQueue**（后续独立版本）：当前任务完成后若仍显示 DB 写锁等待，作为独立版本重新设计
4. 切换到其它任务

---

## 历史交接（按时间倒序，精简归档）

### 2026-07-04 - sync-resource-governance 阶段 3 完成（验证与证据归档）

- 架构约束测试（请求探针模块不碰治理锁）+ 3 行为契约测试 + 压测脚本（6 场景，P50/P95<1ms）。
- 阶段 0/1/2/2.5/3 全部完成（code review 修复前的状态）。

### 2026-07-04 - sync-resource-governance 阶段 2.5 完成（DB 写入治理）

- sync_db_write.py 公共工具（变更检测 + 批量 upsert + db_write_scope）。
- 28 个新单测（21 纯函数+mock + 7 真实 SQLite 部分索引集成测试）。

### 2026-07-04 - sync-resource-governance 阶段 2 完成（下载器 API 调用隔离）

- DownloaderApiRuntime 三 lane 独立 ThreadPoolExecutor + per-downloader Semaphore + call_downloader_api 统一封装。
- torrents_async.py 16 处 asyncio.to_thread 全量迁移。

### 2026-07-04 - sync-resource-governance 阶段 0+1 完成（调度器资源背压）

- TaskAdmissionController（heavy_sync 全局令牌 + per-task_code 运行/排队登记 + 同类去重跳过）。
- 39 个新单测 + 5 处 mutation 反向验证。

### 2026-06-28 - 后端回归测试补全专项

- 为 6 个零覆盖接口补 API 级回归测试（审计日志/仪表盘/种子删除/cron安全/种子转移/下载器设置）。
- 14 commit，+135 测试，全量 tests/api/ 462 passed。

---

## 会话信息

**当前分支**: dev
**当前开发版本**: sync-resource-governance（已 done）
**最后更新**: 2026-07-05
