# sync-resource-governance - 同步任务资源治理与下载器 API 调度

> 状态: planned  
> 创建日期: 2026-07-03  
> 执行顺序: 方案二（调度器/资源背压） -> 方案三（下载器 API 调度层）  
> 目标: 解决 tracker 与种子信息同步期间，其它接口请求容易超时的问题。

## 一、问题背景

当前现象是：同步 tracker 或种子信息时，请求其它接口经常超时。前期审查与子代理独立分析后，暂定瓶颈集中在三个层面：

1. 后台同步任务缺少全局资源治理。现有调度主要防止同一任务重复执行，但不同重型任务仍可能并发抢占 DB 写入、下载器 API 与线程池资源。
2. 下载器 API 调用路径存在隔离不足。部分 qBittorrent tracker 路径会批量调用 `torrents_trackers`，并通过默认 executor / `asyncio.to_thread` 放大对 WebUI 与线程池的占用。
3. DB 写入与远程下载器调用边界不够清晰。SQLite 已具备 WAL/busy_timeout 基础，但长事务、批量写入和重型同步叠加时仍可能造成请求侧等待。

已核实修正点：

- `qb_add_torrents_info_only_async` 当前不调用 `_enrich_qb_torrents_with_trackers`，不能把 tracker 富集误归因到 info-only 路径。
- 仍需重点核查 `tracker-only`、`full sync`、`TorrentInfoSyncTask`、`TrackerSyncTask`、`cron_executor` 与下载器连接复用路径。

## 二、范围边界

本任务优先做资源治理与调用隔离，不直接扩大为基础设施重构。

纳入范围：

- 后台任务资源准入控制。
- 重型同步任务互斥、跳过或短等待策略。
- 下载器 API 专用 executor / semaphore / per-downloader 限流。
- qBittorrent tracker 批量调用并发上限、超时与预算控制。
- 关键路径观测日志与最小化压测验证。

暂不纳入：

- 不迁移 SQLite 到 PostgreSQL。
- 不引入 Celery / Redis / 外部队列。
- 不改动前端业务交互契约。
- 不一次性重写所有下载器适配器。
- 暂不实现 `DBWriteQueue`；它只作为后续独立版本候选写入 harness，当前任务不得把它作为完成前置条件。
- 必须纳入硬盘写入频率治理，避免高频小事务、频繁 flush/checkpoint 或日志风暴造成硬盘写入压力与寿命损耗。

## 三、总体架构

### 阶段 0：基线观测与回归保护

目标是在改动前建立可比较数据，防止只凭体感判断。

计划工作：

- 为重型同步任务增加统一日志字段：`task_code`、`downloader_id`、资源准入结果、等待耗时、执行耗时、跳过原因。
- 为下载器 API 调用增加 lane 日志：`lane`、`method`、`downloader_id`、耗时、timeout、异常类型。
- 选择 2-3 个代表接口作为并发同步期间的请求探针，例如 dashboard、torrent list、tracker list。
- 记录当前基线：无同步、tracker 同步中、种子信息同步中三类场景。

验收：

- 能通过日志还原“哪个任务持有了什么资源、其它任务等待了多久”。
- 能区分 DB 等待、下载器 API 等待、线程池饱和和业务查询慢。

### 阶段 1：方案二 - 调度器与资源背压

目标是先限制后台任务并发对系统资源的冲击，让请求侧保留基本响应能力。

建议新增：

- `backend/app/tasks/resource_guard.py`
- `backend/app/tasks/task_profiles.py`

核心设计：

1. `TaskAdmissionController`
   - 维护进程级资源信号量与 per-downloader 锁。
   - 支持 `skip_if_busy`、`wait_timeout`、`max_runtime_hint`。
   - 维护轻量“任务队列/排队登记表”：按 `task_code` 记录 `running` 与 `queued` 数量。
   - 对重型 cron 任务采用同类去重：如果同一个 `task_code` 已在运行或已在队列中等待，则跳过本轮并记录 `skip_reason=duplicate_heavy_task_pending`。
   - 输出结构化准入结果，便于日志和测试断言。

2. 资源类型
   - `heavy_sync`: 全局重型同步令牌，默认并发 1。
   - `db_writer`: DB 写入令牌，默认并发 1，只包裹实际写入/commit 阶段。
   - `downloader_io`: 下载器 API 总令牌，默认并发 2。
   - `per_downloader`: 同一下载器的重型同步互斥，避免同一个 qB WebUI 被多任务同时打满。
   - `read_heavy`: 重型读查询令牌，给后续统计类接口预留扩展点。
   - `disk_write_budget`: 写入节流概念，不一定第一轮做成独立类，但必须在任务中落实批量写入、合并提交和最小写入间隔。

3. 调度器接入
   - 在 `cron_executor` 或任务统一入口根据 `task_code` 查找 profile。
   - 对 tracker 同步、种子信息同步、tracker 状态判定、重宣告、下载器路径扫描等重型任务配置 `heavy_sync` / `per_downloader`。
   - 忙时策略优先采用“同类任务已运行/已排队则跳过本轮并记录原因”，避免 cron 堆积。
   - 队列长度第一轮不做无限队列，只保留每类重型任务最多 1 个等待名额；超过即跳过。

4. 任务内部接入
   - 远程下载器调用不持有 `db_writer`。
   - DB 写入/commit 才进入 `db_writer`。
   - 大批量写入按批次释放控制权，避免长时间占用写令牌。
   - 避免逐条 torrent/tracker commit；优先内存聚合、批量 upsert、批量 audit/log 写入。
   - 对状态无变化的数据不写库，减少无效写入。
   - 对高频日志或进度类数据设置合并窗口，默认不因每个 tracker/torrent 事件立即落盘。

首批候选任务：

- `TorrentInfoSyncTask`
- `TrackerSyncTask`
- `TrackerMessageLogger`
- `TorrentTrackerStatusJudge`
- `TrackerReannounceTask`
- `DownloaderPathScanTask`

验收：

- 任意两个重型同步任务同时触发时，最多一个进入 `heavy_sync`。
- 同一 `task_code` 的重型任务如果已运行或排队，本轮新触发任务被跳过，日志记录可追踪。
- 请求接口在重型同步期间不再被后台任务无限制挤占。
- 单元测试覆盖准入成功、忙时跳过、等待超时、异常释放资源。
- 批量同步期间 DB 写入次数、commit 次数和日志落盘次数有可观测数据，且不存在逐条高频写入放大。

### 阶段 2：方案三 - 下载器 API 调用隔离与调度层

目标是把 qBittorrent / Transmission 远程调用从默认线程池和无差别并发中隔离出来，避免 tracker N+1 或批量同步拖垮其它接口。

建议新增：

- `backend/app/services/downloader_api_runtime.py`

核心设计：

1. 专用 executor / lane
   - `tracker_lane`: tracker 明细、tracker 状态、重宣告等。
   - `sync_lane`: 种子列表、文件列表、下载器状态同步等。
   - `interactive_lane`: 用户触发的轻量操作，预留较高优先级。

2. 统一调用封装
   - `call_downloader_api(downloader_id, lane, func, timeout, *, operation, priority)`
   - 内部处理 executor、per-downloader semaphore、timeout、日志、异常归一。
   - 替换散落的 `asyncio.to_thread` / 直接同步调用。

3. qB tracker 并发治理
   - tracker 明细查询默认并发从 10 降到 3。
   - 增加单轮预算，例如最大 torrent 数、最大耗时、失败熔断阈值。
   - 超出预算时记录“部分同步”，下轮继续，而不是阻塞整轮。

4. 下载器连接复用
   - 优先使用 `app.state.store` 中缓存客户端。
   - 对当前无法直接传入 store 的路径，先增加可选 client 参数或适配层，不重复创建连接。

验收：

- 重型 tracker 查询不再占用默认 executor。
- qB tracker 明细并发可配置，默认不超过用户确认值。
- 用户请求触发的轻量下载器操作拥有独立 lane，不被后台 tracker 批量查询完全阻塞。
- `TorrentInfoSyncTask` happy path 使用缓存客户端，避免重复创建连接。

### 阶段 3：后续增强 - 每下载器队列与合并

此阶段作为方案三的增强，不建议第一轮就做满。

候选能力：

- 每个下载器一个轻量队列，按优先级执行。
- 合并同一下载器短时间内重复的 tracker 状态查询。
- 对后台任务设置 rate limit 与冷却时间。
- 为失败下载器做短期熔断，保护其它下载器和请求接口。

### 后续独立版本候选：DBWriteQueue

`DBWriteQueue` 不在当前 `sync-resource-governance` 任务中实现，只保留为后续独立版本尝试。

候选目标：

- 把后台同步任务的数据库写入统一投递到专用写入队列。
- 由单独 worker 批量写入、合并写入、节流 commit。
- 进一步降低 SQLite 写锁竞争和硬盘小写入放大。
- 支持短时间内同一 torrent/tracker 状态多次变化时只写最终状态。

启动条件：

- 当前任务完成后，验证仍显示 DB 写锁等待或磁盘写入放大是主要瓶颈。
- 已有清晰的写入一致性要求、退出前 flush 策略、失败重试策略和可接受的数据延迟范围。
- 作为独立版本重新设计计划、验收标准与回滚策略。

触发条件：

- 阶段 1 + 阶段 2 后仍出现 qB WebUI 被后台任务打满。
- 日志显示同一下载器存在大量重复同类 API 调用。

## 四、验证方案

### 单元测试

建议新增或扩展：

- `backend/tests/tasks/test_resource_guard.py`
- `backend/tests/tasks/test_task_profiles.py`
- `backend/tests/services/test_downloader_api_runtime.py`
- 相关同步任务的 mock client 回归测试。

覆盖点：

- 资源正常获取和释放。
- 异常时资源释放。
- 忙时跳过策略。
- 等待超时策略。
- per-downloader 互斥。
- lane executor 不使用默认 executor 的行为契约。

### 集成验证

建议构造一个可重复脚本或 pytest 场景：

1. 启动 tracker 同步 mock 任务，模拟大量远程 API 慢响应。
2. 同时请求 dashboard / torrent list / tracker list。
3. 断言请求侧在可接受时间内返回。
4. 断言第二个重型同步任务被跳过或等待超时，而不是堆积并发。

### 手动压测矩阵

至少覆盖：

- 无同步时接口响应。
- tracker 同步中接口响应。
- 种子信息同步中接口响应。
- tracker 同步 + 种子信息同步同时触发。
- 单下载器大量种子。
- 多下载器并发。

## 五、待用户确认决策

这些点不在计划中强行定死，进入实现前需要你决策：

1. 重型任务忙时策略：已确认采用“同类任务运行中/排队中则跳过本轮”。
   - 实现要求：按 `task_code` 检查运行中和等待中任务；同一重型 cron 任务最多允许 1 个实例运行或等待。

2. `downloader_io` 默认并发：已确认使用 2。

3. qB tracker 明细并发默认值：已确认使用 3。

4. 是否允许新增配置项：已确认允许。
   - 候选：`SYNC_HEAVY_CONCURRENCY`、`SYNC_HEAVY_QUEUE_LIMIT`、`DOWNLOADER_IO_CONCURRENCY`、`QB_TRACKER_CONCURRENCY`、`DOWNLOADER_API_TIMEOUT_SECONDS`、`SYNC_DB_COMMIT_BATCH_SIZE`、`SYNC_DISK_FLUSH_INTERVAL_SECONDS`。

5. 是否把 `DBWriteQueue` 纳入本任务：已确认暂不纳入。
   - 处理方式：作为后续独立版本候选保留在 harness 中；当前任务只做 `db_writer` 短锁、批量写入、写入合并和硬盘写入频率治理。

6. 硬盘写入频率治理：已确认必须纳入。
   - 实现要求：避免逐条写库、逐条日志落盘和过高 commit 频率；优先批量提交、变更检测、合并写入、节流日志。

## 六、完成定义

- 方案二完成：调度器资源背压可用，关键重型任务接入，日志和单元测试齐备。
- 方案三第一轮完成：下载器 API runtime 可用，qB tracker 并发受控，关键 `to_thread` 路径迁移。
- 同步期间请求接口超时问题有可复现验证与改善证据。
- `DBWriteQueue` 不作为当前任务完成条件，仅需在 harness 中保留后续独立版本候选说明。
- `feature_list.json` 记录任务状态与 evidence。
- `progress.md` 与 `session-handoff.md` 更新下一步工作和待决策项。
- 后端相关测试通过；如未能运行完整测试，需记录原因与替代验证。
