# 大批量种子 / Tracker 同步数据库阻塞与接口超时评估

> 评估日期：2026-08-08
>
> 评估性质：只读代码审计、只读本地数据库核对、临时文件型 SQLite 竞争复现
>
> 适用范围：默认任务 `torrent_info_sync_ac608e4d`、`tracker_sync_598b784c`，SQLite 部署，种子/Tracker 同步、定时调度、下载器 API、请求端 CRUD
>
> 当前结论：`sync-resource-governance` 已完成的实现只能视为“部分止血”，在实际默认负载下仍存在 P0 级卡顿和超时路径。

## 1. 执行摘要

实际使用中，Tracker 状态同步任务和种子信息同步任务前后出现明显卡顿，部分增删改查接口超时。该现象与当前代码结构一致，原因不是单一的 SQLite 写锁，而是以下三类资源竞争叠加：

1. Tracker 同步会长时间占用下载器 API，并在完成后对 Tracker 表进行无差异的大范围更新。
2. 种子信息同步的“批量”写入仍可能是一个下载器一次大事务，并在 SQLite 上并发处理多个下载器。
3. 部分请求端点在 `async def` 中直接调用同步下载器 API，绕过 `DownloaderApiRuntime`，导致 FastAPI 事件循环被阻塞；涉及下载器的 CRUD 还会与后台 Tracker 调用争抢同一个下载器。

因此，以下判断应作为当前上线状态：

- 单进程、低变化量、没有手动同步时，主定时路径有一定保护，但不能保证请求延迟。
- 手动同步、首次/重启后的全量同步、qBittorrent 大规模 Tracker 同步、请求端 CRUD 重叠时，仍存在明确的数据库阻塞和接口超时风险。
- `busy_timeout=15s`、WAL 和进程内信号量只是兜底或局部互斥，不能代替短事务、统一写者和交互请求优先级。

## 2. 证据与边界

### 2.1 默认任务时序

默认任务在 `backend/app/data/default_scheduled_tasks.py`（种子信息同步约 L125、Tracker 同步约 L142）中配置为：

| 任务 | 默认计划 | 影响 |
| --- | --- | --- |
| 种子信息同步 | `0,15,30,45 * * * *` | 每 15 分钟启动，info-only 路径最多并发 3 个下载器 |
| Tracker 状态同步 | `10,40 * * * *` | 每 30 分钟启动，Tracker-only 之后还会做关键词状态更新 |

两个任务通常只相隔 5 分钟。若 Tracker 同步超过 5 分钟，种子信息同步会紧随其后进入等待、跳过或连续占用系统资源的窗口。

### 2.2 本地库规模

只读核对 `backend/config/app.db` 得到：

- SQLite journal mode：WAL；page size：4096；默认 `wal_autocheckpoint=1000`
- 有效 `torrent_info`：约 22,000 行
- 有效 `tracker_info`：约 30,000 行
- 有效 Tracker 关键词：189 条
- 下载器：4 个，其中两个约 1 万种子，另两个约 850 种子
- `tracker_info` 有 8 个索引；`torrent_info` 有 16 个索引，写入存在明显索引放大

这不是线上库的完整证明，但规模已经足以复现“默认任务不是小数据任务”的行为。

### 2.3 历史任务日志

本地 `task_logs` 中曾出现：

- Tracker 同步单轮约 152～422 秒，最大 1161 秒
- 种子信息同步单轮约 136～190 秒
- 这些记录大多仍为 `success=1`

日志跨越多个代码版本，不能直接作为当前部署的精确 P95；但它证明“任务成功但持续数分钟”的状态曾真实存在，也说明当前任务成功标志不足以代表服务健康。

### 2.4 验证边界

- 相关治理、调度和 API runtime 测试：75 项通过。
- 现有测试主要验证信号量、调用封装和契约，不制造真实文件型 SQLite 写锁竞争。
- `sync_resource_benchmark.py` 主要使用内存数据库和模拟 HTTP，不能证明真实磁盘、索引和 WAL 压力下请求仍可用。
- 只读复现确认：文件型 SQLite 在一个写事务持有期间，竞争写连接会等待并最终收到 `SQLITE_BUSY`。
- 本文不把本地库时长、大小和历史日志当作生产 SLO，只把它们作为代码风险的佐证。

## 3. P0 问题登记

P0 表示：会直接造成默认场景下接口卡顿/超时、数据写入阻塞或服务级不可用，应优先止损并修复。

### P0-01：手动同步接口绕过统一同步治理

**位置**：`backend/app/api/endpoints/torrent_sync.py` 约 L1172；旧版全量实现位于 `backend/app/api/endpoints/torrents_async.py` 约 L1189、L1749。

**问题**：`/torrents/sync-single` 进入独立后台任务管理器，最多允许 3 个不同下载器并发，未加入定时任务的 `heavy_sync` / `db_writer` 统一协调。它仍会走旧版全量同步，不能与定时 info-only / tracker-only 主路径共享游标、客户端和写入准入。

**阻塞机制**：旧版路径逐种子处理 Tracker，并可能在未提交事务期间等待远端 API 或备份文件 I/O。网络/文件耗时被包含在 SQLite 写事务中，其他写请求等待 `busy_timeout` 后失败。

**影响**：手动同步与定时同步、不同下载器的手动同步之间可以形成写锁竞争；请求端无法判断任务是否已占用数据库。

**修复方向**：将手动接口路由到统一 `SyncCoordinator`；接入同一重任务准入、按下载器去重、缓存客户端和短事务批处理；旧版全量路径先禁用或特性开关隔离。

### P0-02：Tracker 关键词状态更新每轮全表重写

**位置**：调用点 `backend/app/tasks/scheduler/torrent_sync/tracker_sync_task.py` 约 L107-L113；实现 `backend/app/api/endpoints/torrent_sync.py` 约 L1364-L1551。

**问题**：Tracker-only 同步成功后读取全部 Tracker，按 host 计算状态，再按 `normal/error/unknown` 分组执行大范围 `UPDATE`。即使业务字段没有变化，也会更新 `status`、`msg` 和 `update_time`，最后一次性 `commit()`。

**影响**：

- 本地约 3 万条 Tracker 每轮都进入写路径。
- 大型 `IN (...)` 语句增加 SQL 解析和锁持有时间，十万级数据可能触及 SQLite 绑定变量上限。
- 未进入 `db_write_scope`，也没有按批次提交和锁重试。
- 大事务可能触发 WAL 自动 checkpoint，造成额外磁盘 I/O 尾部。

**测量修正**：当前本地 3 万 Tracker、189 关键词的纯分类约 0.1 秒，当前主要瓶颈是无差异全量 UPDATE 和提交，不应只优化关键词匹配。

**修复方向**：仅根据消息变化的 Tracker/host 增量重算；只更新状态真正变化的行；按 200～500 行分批、每批短事务、进入 `db_write_scope`；将分类和写入阶段分别计时。

### P0-03：种子信息批量 upsert 实际仍可能是单个大事务

**位置**：`backend/app/services/sync_db_write.py` 约 L131-L176；调用点 `backend/app/api/endpoints/torrents_async.py` 约 L3010、L3214。

**问题**：`bulk_upsert_with_retry()` 接收一个下载器全部 `to_insert` / `to_update` 后只执行一次 bulk mapping 和一次 commit，没有按 `SYNC_DB_COMMIT_BATCH_SIZE` 分块。变更检测只减少稳态写量，不能保护首次、重启后和强制全量同步。

**影响**：单次事务可能覆盖数万种子和多个索引；写期间增删改接口等待，SQLite WAL 和磁盘写入产生长尾。

**附加问题**：qB/TR 全量同步时间戳主要保存在进程内，重启后可能立即认为需要全量同步；qB removed 标记路径也未完全按批次和写入作用域治理。

**修复方向**：新增和更新均按配置分批，每批独立短事务；持久化全量游标/时间戳；removed 标记按批次处理；每批输出行数、等待、事务和提交耗时。

### P0-04：请求端 `async def` 直接执行同步下载器 API，阻塞事件循环

**位置示例**：

- `backend/app/api/endpoints/torrent_crud.py` 约 L130：异步添加种子接口直接调用 `qb_client` / `tr_client`。
- `backend/app/api/endpoints/tracker.py` 约 L32、L459、L572：Tracker 增删改路径直接调用同步客户端。
- `backend/app/api/endpoints/torrent_status.py`：暂停、恢复、重检和汇报接口存在同类直接调用。

**问题**：这些请求没有统一通过 `call_downloader_api(..., INTERACTIVE)`，部分接口还混用同步 `Session` 和 `AsyncSession`。qB/TR 的同步 HTTP 调用会占用 FastAPI 事件循环；Tracker 任务运行期间远端响应变慢时，所有同 Worker 请求都可能排队。

**附加正确性问题**：Tracker CRUD 中存在异步辅助函数未 `await` 的调用路径；部分旧 helper 仍自行创建下载器客户端，违反连接复用约束。

**影响**：解释了“查询接口也卡”的现象：即使查询本身不抢 SQLite 写锁，只要事件循环没有机会调度，它也会超时。

**修复方向**：所有同步远端调用统一进入 interactive lane 或 `asyncio.to_thread`；请求端使用缓存客户端；统一会话边界；补齐缺失的 `await`；禁止在异步 handler 中直接调用阻塞客户端。

### P0-05：后台 Tracker API 没有为交互请求保留容量

**位置**：`backend/app/services/downloader_api_runtime.py` 约 L193-L300。

**问题**：虽然有 tracker/sync/interactive 三个线程池，但同一下载器仍由一个总 `threading.Semaphore`（默认 2）限流。Tracker 同步可以持续占满这两个令牌；`priority` 参数目前只是预留参数，没有实际优先级调度或公平队列。

**影响**：涉及下载器的 CRUD 即使接入 runtime，也可能长期等待后台 Tracker 请求；直接绕过 runtime 的旧接口还会进一步放大 qB/TR WebUI 压力。

**修复方向**：采用后台/交互分层配额或公平优先队列，例如总容量 2 时后台最多占 1，至少为 interactive 保留 1；Tracker 任务采用有界队列、时间预算和持久化游标，不再把所有种子一次性提交。

### P0-06：SQLite 的锁和调度保护只在进程内且不是所有写者都接入

**位置**：`backend/app/tasks/resource_guard.py` 约 L71-L78、L241-L254；`backend/app/startup/lifecycle.py` 约 L267；`backend/btdeck_startup.sh` 默认 `WORKERS=1`。

**问题**：`heavy_sync`、`db_write_scope` 和任务登记都是进程内信号量。手动/旧版同步、Tracker 状态后处理、部分 CRUD 和辅助写入不一定进入同一作用域。若设置多个 Worker，每个 Worker 会有自己的信号量并可能启动自己的调度器。

**影响**：SQLite 下多 Worker 会产生跨进程写竞争；单 Worker 下未接入作用域的写者仍可绕过串行化，形成 `SQLITE_BUSY`。

**修复方向**：SQLite 启动时强制 `WORKERS=1` 并在启动日志中明确拒绝多 Worker；统一所有后台写入入口；若产品必须多 Worker，迁移 PostgreSQL 或增加可靠的跨进程 Leader/写者机制。

## 4. P1 问题登记

P1 表示：会显著放大 P0，造成任务饥饿、数据新鲜度下降、重启放大或无法稳定验收，应在 P0 止损后处理。

### P1-01：qB Tracker 同步按种子逐个请求，十万级不可控

**位置**：`backend/app/api/endpoints/torrents_async.py` 约 L2591-L2680。

**问题**：每个种子调用一次 `torrents_trackers`，一次创建全部 task；默认 Tracker 并发和 per-downloader 总并发很低，任务没有总时长、数量预算、游标或断点续跑。

**影响**：十万种子即使远端单次 10ms，也需要约 500 秒理论下限；实际可能数十分钟。`heavy_sync` 长时间被占用，其他任务被跳过或滞后。

**修复方向**：有界生产者/消费者、活跃/变化/错误优先、每轮时间预算、持久化游标、下一轮续跑和失败熔断。

### P1-02：种子信息同步同时处理多个下载器，事件循环和内存压力不可见

**位置**：`backend/app/tasks/scheduler/torrent_sync/torrent_info_sync_task.py` 约 L80-L87；`backend/app/api/endpoints/torrents_async.py` 约 L2834-L3012、L3112-L3216。

**问题**：默认最多 3 个下载器并发；每个下载器会读取全量业务字段、构造内存 cache、遍历远端记录、再集中 bulk upsert。CPU 计算、对象转换和列表构造没有按批让出事件循环。

**影响**：即使最终只有一个 SQLite 写者，多个同步协程仍会同时占用 CPU、内存和磁盘；首次/全量同步时更明显。

**修复方向**：SQLite 默认先按下载器串行或设置有界并发；读取、diff、写入都按批次处理；必要时将纯 CPU diff 放入线程；批次之间记录事件循环延迟。

### P1-03：全量同步状态未持久化，重启会放大压力

**位置**：`backend/app/api/endpoints/torrents_async.py` 约 L2532-L2535、L2757-L2760、L3070-L3073。

**问题**：qB/TR 全量同步时间戳和部分首次同步标志保存在进程内字典；进程重启、Worker 重启或部署后可能立即触发全量同步。qB RID 虽有持久化，但不能替代全量游标。

**影响**：部署、崩溃恢复和健康检查失败后的重启都可能瞬间制造大批量读写。

**修复方向**：持久化 `last_full_sync_at`、游标、状态和失败重试信息；重启后按增量恢复，只有明确过期或人工要求才全量。

### P1-04：Tracker 状态更新和若干删除/恢复路径缺少统一重试与批量上限

**问题**：Tracker 状态后处理、qB removed 标记以及部分旧版 Tracker CRUD 写入没有统一的批次大小、锁重试、失败隔离和 rollback 语义。

**影响**：单个大批次失败会放大重试成本；大 `IN` 语句可能超过 SQLite 参数上限；无法定位是第几批造成阻塞。

**修复方向**：统一 `DbWriteBatch` 工具，限制 ID 数量、每批独立 retry/rollback，日志带 `batch_no` 和行数。

### P1-05：默认排程与跳过语义无法反映服务新鲜度

**问题**：Tracker 与 info 任务只有 5 分钟间隔；资源准入超时会将任务记为成功但带 `skipped`，任务列表未直接展示“本轮未执行/数据未刷新”。

**影响**：用户看到任务成功，实际数据可能连续多轮未同步；下一个周期又遇到同一压力。

**修复方向**：调整低峰排程；记录 `admitted/skipped/wait` 和 `last_successful_data_at`；以数据新鲜度而不是 task success 触发告警。

### P1-06：当前观测不能定位卡顿阶段

**问题**：任务日志主要有 start/end/duration/success，缺少远端等待、数据库等待、事务持有、批次、WAL、checkpoint、事件循环和请求关联信息。`resource_guard` 的 `extra` 字段没有被当前普通 formatter 完整输出，见 `backend/app/main.py` 约 L40。

**影响**：无法区分“SQLite 写锁”“qB WebUI 慢”“事件循环冻结”“磁盘 checkpoint 慢”。

**修复方向**：JSON 日志和指标至少包含：

```text
run_id, task_code, downloader_id, phase, batch_no
rows_scanned, inserted, updated, skipped
api_queue_ms, api_call_ms, db_wait_ms, tx_ms, checkpoint_ms
sqlite_code, retry_count, event_loop_lag_ms, outcome
```

### P1-07：测试和 benchmark 没有覆盖真实文件库并发

**问题**：现有 75 项相关测试通过，但主要是内存 SQLite、StaticPool、mock HTTP 或单纯信号量测试；没有覆盖手动同步与 cron 重叠、真实索引、真实 WAL、慢下载器和请求端并发。

**影响**：治理测试可能全部通过，但生产仍然出现超时；当前 `sync-resource-governance` 的“done”证据不足以证明请求 SLO。

**修复方向**：增加文件型临时 SQLite + 真实 schema/index 的压力脚本，持续探测 `/docs`、只读接口、写接口和下载器交互接口。

## 5. P2 问题登记

P2 表示：不会单独造成当前最急迫的超时，但会影响长期扩展、维护、回归和容量规划。

### P2-01：PostgreSQL 迁移条件和旧计划需要重新定义

当前 v1.0.8 PostgreSQL 计划不能直接照搬。代码存在 SQLite 专用 `ON CONFLICT`、partial index、PRAGMA、硬编码连接和 SQLite 变量限制假设。

建议以指标触发迁移：目标负载下任何 `SQLITE_BUSY`、写等待 P95 >250ms、事务持有 P99 >500ms、必须多 Worker/HA，或同步无法在周期内完成。迁移前先清理短事务和请求阻塞问题，避免把应用层饥饿原样搬到 PostgreSQL。

### P2-02：是否引入统一 DBWriteQueue 尚未决策

单一后台写队列可合并同 key 更新、限制 commit 频率并提供恢复/flush，但不能自动控制请求端直接写入，也不能替代短事务。应在 P0/P1 修复并有真实指标后再决定，避免新增复杂度掩盖边界问题。

### P2-03：缺少轻量 readiness 与同步健康状态

当前健康检查偏向 `/docs`，没有同时返回数据库可读写、WAL 大小、最近成功同步时间、当前重任务和跳过次数。

建议新增只读 readiness/diagnostic 信息，至少区分：

- 事件循环是否可调度
- SQLite 是否可读、可写
- 当前是否有写事务
- Tracker/info 最近一次真实成功时间
- 最近 5 分钟 `SQLITE_BUSY`、超时和跳过数

### P2-04：Tracker 状态计算缺少可复用的变化指纹

当前每轮都读取消息并重复分类。可为 `(tracker_id, announce_msg, scrape_msg)` 保存 hash/version，只有变化记录重新分类；关键词表变化时再按关键词版本增量失效。

### P2-05：WAL、checkpoint 和写放大缺少容量管理

`wal_autocheckpoint` 使用默认值，未观测 WAL 峰值、checkpoint busy/log/checkpointed、数据库增长和磁盘余量。状态全量 UPDATE 还会产生无效页面写入。

建议增加 WAL/数据库文件指标和低峰 checkpoint 策略；不要在高峰期频繁强制 `TRUNCATE`，备份流程需与写入窗口隔离。

### P2-06：实现状态、约束文档和风险登记不一致

`feature_list.json` 将 `sync-resource-governance` 标记为 `done`，而 `backend/docs/constraints/sync-db-write-governance.md` 仍把若干相关路径作为低优先级技术债。本报告发现这些路径已影响实际接口可用性，后续应把它们升级到明确的 P0/P1 backlog，并更新完成定义、测试证据和生产压测证据。

## 6. 立即止损方案（不改代码）

在 P0 修复上线前，建议运维按以下顺序处理：

1. 暂停 `tracker_sync_598b784c`，或将其移到低峰期并降低频率。
2. 不让 Tracker 同步与种子信息同步只相隔 5 分钟；间隔应覆盖观测到的最大任务时长，不能依赖固定时间猜测。
3. SQLite 保持 `WORKERS=1`。
4. 临时将 `QB_TRACKER_CONCURRENCY=1`，减少 qB WebUI 背景压力。
5. 避免同步窗口执行批量手动同步和批量 CRUD。
6. 不要单纯增大前端超时或 `busy_timeout`；这会把失败变成更长的等待，并不能恢复事件循环或释放远端容量。

## 7. 修复路线

### 阶段 A：P0 止血

- 统一手动同步、定时同步和下载器客户端入口。
- Tracker 状态只更新变化行，按 200～500 行分批、短事务、锁重试。
- `bulk_upsert_with_retry` 真实按批次提交；新增、更新、removed 都分批。
- 所有请求端同步下载器调用迁移到 interactive lane / `to_thread`，修复缺失 `await`。
- 为每个下载器保留交互 API 容量；SQLite 强制单 Worker。

### 阶段 B：P1 稳定性

- qB Tracker 使用有界队列、预算和持久化游标。
- info-only 按下载器有界并发，避免一次读取/构造/提交整库。
- 持久化全量同步状态，重启后优先增量恢复。
- 统一批次写工具和错误隔离。
- 增加真实文件型 SQLite 压测与请求探针。

### 阶段 C：P2 扩展性

- 建立 readiness、同步新鲜度和 WAL 运维指标。
- 评估 Tracker 状态指纹、低峰 checkpoint 和索引写放大。
- 用真实 SLO 决定是否迁移 PostgreSQL 或引入 DBWriteQueue。

## 8. 观测与告警方案

### 8.1 指标

| 指标 | 目的 |
| --- | --- |
| `sync_duration_seconds{task,phase}` | 区分远端、读取、diff、写入、后处理耗时 |
| `sync_freshness_seconds{downloader,type}` | 判断数据是否真实更新 |
| `sync_skipped_total{reason}` | 识别准入超时和重复任务 |
| `db_writer_wait_seconds` | 判断写者排队 |
| `db_transaction_hold_seconds` | 判断事务是否过长 |
| `sqlite_busy_total{code}` / `db_retry_total` | 直接观察锁冲突 |
| `sqlite_wal_bytes` / `db_bytes` | 观察 WAL 和数据库增长 |
| `checkpoint_seconds` | 识别提交后的 I/O 尾部 |
| `downloader_api_queue_seconds{lane}` | 识别后台调用挤占交互容量 |
| `downloader_api_call_seconds{lane,operation}` | 区分排队和远端慢 |
| `event_loop_lag_seconds` | 识别 async handler 被同步调用冻结 |
| `http_request_seconds{route}` | 直接关联用户接口超时 |

### 8.2 日志字段

任务、批次和请求日志都应关联 `run_id`，至少输出：

```text
run_id task_code downloader_id phase batch_no
rows_scanned rows_inserted rows_updated rows_skipped rows_removed
api_queue_ms api_call_ms db_wait_ms tx_ms checkpoint_ms
sqlite_error_code retry_count event_loop_lag_ms outcome
```

禁止逐条输出 Tracker/torrent 成功日志；使用窗口聚合，保留失败样本。

### 8.3 初始告警阈值

- 5 分钟内出现 1 次 `SQLITE_BUSY`：告警；出现 3 次：严重告警。
- 写等待 P95 >250ms 持续 10 分钟。
- 事务持有 P99 >500ms 或单次 >2 秒。
- 任意请求 P95 >1 秒，或超时率 >1%。
- 事件循环延迟 P99 >100ms。
- 同步新鲜度超过计划周期 2 倍，或连续两轮跳过。
- WAL 持续超过 512 MiB 或磁盘可用空间低于 25%。

## 9. 压测验收

必须使用文件型 SQLite、生产级 WAL/索引/连接参数，不能用 `:memory:` 作为数据库阻塞验收依据。

测试矩阵：

- 1 万、5 万、10 万种子；每种子 1/3/10 个 Tracker。
- 无变化、10% 变化、首次全量、重启后首次同步。
- 单下载器、4 下载器、慢 qB/TR、API 超时和取消。
- 定时 Tracker、定时 info、手动同步和 CRUD 同时运行。
- 持续访问 `/docs`、纯读接口、写接口和下载器交互接口。

首轮验收目标：

- `SQLITE_BUSY = 0`。
- 纯读接口 P95 <500ms。
- 写接口 P95 <1s、P99 <2s。
- 写事务持有 P99 <200ms，最大值 <1s。
- 事件循环延迟 P99 <100ms。
- 同步在下一调度周期前完成或有明确的可观测续跑状态。
- WAL 峰值、checkpoint 时长和磁盘增长在容量预算内。

这些是初始验收目标，应在真实部署基线后校准，不应替代业务方最终 SLO。

## 10. 本文与现有治理文档的关系

- `backend/docs/constraints/sync-db-write-governance.md` 仍是新增同步写路径的约束基线。
- 本文是面向实际运行卡顿的风险登记和整改优先级，覆盖该约束未闭环的旧路径、请求端路径和真实验证缺口。
- P3 技术债未纳入本文；只有已经影响默认任务期间接口可用性或会阻止 P0/P1 验收的项才列入。
