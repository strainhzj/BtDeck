# Session Handoff - BtDeck 全栈项目

## 2026-07-10 交接：质量门禁可信化（进行中）

**当前任务**：`quality-gate-hardening`

- 已完成：严格入口接入、Black/Flake8/Ruff 基线修复、后端 AST lint 与前端 Vuex lint 的正反例测试。
- 已验证：`pytest backend/tests/test_architecture_constraints.py -q` 为 19 passed；Black、Flake8、Ruff 均通过；Vuex lint 的 Jest 正反例测试通过。
- 未完成且必须保持阻断：全仓 Mypy 存在历史类型错误；前端 `npm run lint` 报 129 条 warning，现因 `--max-warnings 0` 正确返回非零。
- 下一步：按 ESLint 输出逐项删除未使用符号、收敛非空断言，再规划 Mypy 类型债专项；不要恢复 `|| echo`、降低 warning 阈值或将规则整体关闭。

---

## 2026-07-05 交接：sync-resource-governance code review 修复轮完成

**当前任务**: `sync-resource-governance`
**状态**: code review 修复轮（阶段 4）完成。父 feature 已从 `planned` 标为 `done`。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮完成（code review 4 项问题修复 + 验收文档对齐）

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
---

## 2026-07-10 交接：质量门禁可信化（前端 warning 已清零）
**当前任务**：`quality-gate-hardening`

- 已完成：根/后端/前端 init 的 lint 吞错修复；后端 Black/Flake8/Ruff/custom lint 接入；自定义架构 lint 全规则负向样例；前端 Vuex action lint 可测试化；前端 129 条 ESLint warning 清零。
- 已验证：`backend/tests/test_architecture_constraints.py` 21 passed；后端 Black/Flake8/Ruff 通过；`frontend npm run lint` 通过且执行 `lint-vuex-action`；`npm run test:unit -- lint-vuex-action.spec.ts` 2 passed。
- 仍需独立处理：`python -m mypy app` 暴露历史类型债务，当前严格入口会真实失败；不要恢复 `|| echo`、不要降低 warning 阈值、不要关闭自定义规则。
- 下一步建议：把 Mypy 债务拆成独立 SQLAlchemy/Pydantic 类型治理任务，避免混进 lint 可信化修复。
