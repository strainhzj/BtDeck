# 同步数据库阻塞止血 Runbook（W0）

> 适用任务：`torrent_info_sync_ac608e4d`（种子信息）和
> `tracker_sync_598b784c`（Tracker 状态/信息）。
>
> 关联报告：[`database-blocking-and-sync-issues-2026-08.md`](database-blocking-and-sync-issues-2026-08.md)
> 和 [`database-blocking-and-sync-verification-2026-08.md`](database-blocking-and-sync-verification-2026-08.md)。
>
> 本手册用于出现接口卡顿、CRUD 超时、SQLite busy 或事件循环 lag 时的值班操作。
> 目标是先停止新增压力、保留已提交批次，再恢复到可观测的错峰运行；不在事故中直接删除
> 数据库、执行迁移或手工清空 WAL。

## 1. 触发条件与值班原则

满足任一条件即可进入止血流程：

- `/health/ready` 返回 503，或 `/api/v1/health/sync` 报告同步任务 stale/offline/active 超时；
- 交互接口连续出现超时，或只读/写请求 P95 超过发布门（1s/2s）；
- 日志出现 `SQLITE_BUSY`、`checkpoint_busy=true`、事件循环 lag 告警，且与同步运行窗口重合；
- 同一下载器的 info 与 tracker 同时运行，或单轮处理量明显超过配置预算。

事故期间遵循：先暂停调度，再确认活动运行已退出；只保留已提交批次；所有命令、时间、
run_id 和观测结果写入值班记录。不要通过重启/删除 `app.db-wal` 规避锁问题。

## 2. 止血步骤（不改业务数据）

1. 记录当前时间、实例/Worker、请求超时样例和最近一次 `run_id`。
2. 读取健康端点（需要认证的同步端点使用值班账号）：

   ```text
   GET /health/live
   GET /health/ready
   GET /api/v1/health/sync
   ```

   保存响应中的 `reasonCodes`、任务 `outcome`/`freshness`、`activePhase`、checkpoint age、
   downloader offline 告警以及 WAL/busy 事件。

3. 在定时任务页面或 API 中定位上述两个 `task_code`，记录 task id、enabled、下一次执行时间，
   然后分别调用暂停动作（路由形如 `POST /api/v1/cron-tasks/{task_id}/pause`）。暂停只阻止
   新一轮调度，不假定当前协程已经停止。
4. 暂停人工“立即执行/重试”入口，通知相关操作人不要再次触发同步。若部署有多个 Worker，
   确认所有 Worker 的调度器均已暂停；临时将同步 Worker/并发降至 1，只作为止血措施。
5. 每 10 秒检查一次 `/api/v1/health/sync` 和日志，直到 `activePhase` 清空、没有新增
   `sync_batch_commit`，且 CRUD 探针恢复。若活动运行持续超过单轮 deadline，使用任务取消能力，
   记录“已提交批次保留、未提交批次丢弃”的结果。
6. 只读记录 WAL 文件大小和 busy 状态；不执行 `PRAGMA wal_checkpoint(TRUNCATE)`，不手工复制/删除
   `app.db`、`app.db-wal` 或 `app.db-shm`。

## 3. 恢复与错峰顺序

恢复前必须满足：`/health/ready` 为 200、数据库探针成功、事件循环 lag 回落、最近一次活动
   run 已终止，且没有未处理的版本迁移。恢复顺序如下：

1. 先只恢复 **info** 任务，使用默认单轮预算，观察一个完整周期；确认 checkpoint cursor
   前进且没有 busy/CRUD 超时后，再恢复 **tracker** 任务。
2. 两个任务至少错开一个调度周期；不要在恢复后立即手工触发全量同步。若必须补偿，按下载器
   分批、单下载器串行执行，并保留每轮 `cursor`。
3. 恢复 Tracker 后观察 Tracker 状态更新是否与 info 写入重叠；若重叠，再次暂停 tracker，
   将频率移到低峰期，或降低 `record_budget`/deadline，而不是提高数据库 busy timeout。
4. 使用任务页面或 API 调用 `POST /api/v1/cron-tasks/{task_id}/resume`，记录恢复时间和
   操作人。恢复后 30 分钟内每 5 分钟采样一次健康端点、WAL、busy、loop lag、CRUD P95。

## 4. 观察与升级门槛

| 指标 | 正常目标 | 升级/再次止血 |
| --- | --- | --- |
| 只读 CRUD P95 | < 1s | 连续 3 个窗口 ≥ 1s |
| 写 CRUD P95 | < 2s | 连续 3 个窗口 ≥ 2s 或出现超时 |
| `busy_count`/`checkpoint_busy` | 0 / false | 任一窗口 busy>0 且持续 2 次 |
| 事件循环 lag P99 | < 100ms | ≥ 100ms；单次 > 500ms 立即记录 |
| checkpoint cursor | 每轮成功后单调前进 | 倒退、跨过未提交 hash 或连续 2 轮不变 |
| freshness/stale | 在任务 SLA 内 | 超过 SLA 1 个周期，或 downloader offline |

触发升级时保留：应用日志（含 `run_id`）、`/health/ready` 与 `/api/v1/health/sync` 响应、
WAL 快照、最近 30 轮基准 JSON、任务配置和数据库文件大小；交给后端值班人员分析，不在生产
直接改表或迁移。

## 5. 演练与记录模板

每次发布前至少完成一次“暂停—确认无活动—恢复”的无数据变更演练。演练只暂停 cron，不执行
同步、不改数据库，结果归档到运维目录。

```text
时间（Asia/Shanghai）：
环境/实例/Worker：
操作人：
触发原因或演练：
info task_id / tracker task_id：
暂停时间 / activePhase 清空时间：
最近 run_id：
暂停前 health/ready 与 sync health：
WAL bytes / busy_count / checkpoint_busy：
恢复时间 / 恢复顺序：
恢复后 30 分钟 CRUD P95、超时数、loop lag P99：
checkpoint cursor（前→后）与 freshness：
结论（PASS/ROLLBACK/ESCALATE）：
附件路径：
```

技术争用基准和发布门请使用 [`sync-contention-runbook.md`](sync-contention-runbook.md)；本手册
只定义事故中的暂停、恢复和升级动作。
