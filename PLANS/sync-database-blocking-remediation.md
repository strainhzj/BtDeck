# 同步任务数据库阻塞与接口超时修复计划

> 状态：报告缺口修复已落地；生产迁移、暂停/恢复演练与发布基线归档待执行
> 创建日期：2026-08-08  
> 最近实施：2026-08-11（按独立验证报告修复 P0/P1/P2 缺口）
> 问题基线：[数据库阻塞与同步问题评估](../backend/docs/operations/database-blocking-and-sync-issues-2026-08.md)  
> 当前主数据库：SQLite  
> 预计总工作量：12～19 个工程日，按发布门分批交付  
> 计划边界：本文定义实施方案与发布门；本次修复未修改 Schema，新增的运行时保护仅为代码配置默认值，生产数据库仍须按 Alembic 流程迁移。

---

## 1. 目标与成功标准

### 1.1 目标

在默认 Tracker 状态同步、种子信息同步及手动同步执行前后，保证普通增删改查接口仍可用，并使同步任务具备可控的资源上限、可恢复进度和可解释的运行状态。

计划完成后需要同时满足：

1. SQLite 写事务短小、分批、可重试，不再由一次全量同步持续持有写锁。
2. 手动同步和定时同步使用同一套协调器、资源准入、下载器运行时和数据库写治理。
3. 异步 API 不直接执行同步下载器网络调用，不因单个慢下载器阻塞事件循环。
4. 后台任务不能占满下载器全部并发容量，交互请求始终保留至少一个执行槽。
5. 大规模同步可在单次运行预算内部分完成，并从持久化检查点继续。
6. 日志、指标、健康检查和任务页能区分成功、部分成功、跳过、无变化、失败和数据新鲜度。
7. 文件型 SQLite 的真实写锁压测证明交互接口 SLO，而不只依赖 Mock 或内存数据库测试。

### 1.2 非目标

- P0/P1 阶段不引入 Redis、Celery、Kafka 或额外分布式基础设施。
- P0/P1 阶段不以切换 PostgreSQL 代替应用层修复。
- 不通过单纯增加前端超时、SQLite busy timeout 或无限重试掩盖阻塞。
- 不新建下载器客户端连接池；所有客户端继续来自 app.state.store。
- P0 阶段不引入 DBWriteQueue。是否需要单写者队列由 P2 数据和 ADR 决定。
- 不在普通请求处理器中套用后台任务的全局资源准入锁；请求端应依靠短事务和交互容量保留。

### 1.3 关键不变量

实施中必须持续满足以下约束：

- 第一次 DML 到 commit 之间禁止下载器网络 I/O、文件备份、长时间 CPU 分类和无关查询。
- 所有大批量写入必须按实际提交边界分块；“循环分块但最后一次提交”不算分批提交。
- 一个批次失败只重试当前批次，已经提交的批次不得回滚或重复制造副作用。
- 下载器客户端只能从 app.state.store 获取，不允许调用 qbClient、trClient 新建连接，也不允许主动 logout。
- Schema 变更必须通过 Alembic，必须验证 upgrade、downgrade、再次 upgrade。
- SQLite 模式强制单后端 Worker；未来 PostgreSQL 多 Worker 仍需单独解决定时任务 Leader。
- 新 API 保持统一响应格式；分页字段固定为 list、total、pageSize。
- 前端继续使用 Vue 2 Options API，新增 TypeScript 类型不得使用 any。

---

## 2. 问题到交付项的完整映射

| 风险编号 | 问题摘要 | 主要交付项 | 验收门 |
|---|---|---|---|
| P0-01 | 手动 sync-single 旁路治理并进入旧全量同步 | W2-1 统一同步协调器 | G2 |
| P0-02 | Tracker 关键词状态全表重写 | W1-2 增量状态写入 | G1 |
| P0-03 | info upsert 单大事务 | W1-1 真分批写入 | G1 |
| P0-04 | async 请求直接调用同步下载器 API、存在漏 await | W2-3 请求端点迁移 | G2 |
| P0-05 | 后台任务占满下载器并发槽 | W2-2 交互容量保留 | G2 |
| P0-06 | SQLite 锁仅进程内生效，旁路写者和多 Worker 未治理 | W2-1、W2-4 | G2 |
| P1-01 | qB 每种子 Tracker 调用和任务爆炸 | W3-1 有界队列与游标 | G3 |
| P1-02 | info 同时处理多个下载器，内存和 CPU 峰值高 | W3-3 有界流水线 | G3 |
| P1-03 | 全量同步状态仅在内存，重启后重复工作 | W3-2 持久化检查点 | G3 |
| P1-04 | 批大小、重试、单轮预算不统一 | W1-1、W3-1、W3-3 | G3 |
| P1-05 | 调度成功、跳过和数据新鲜度语义混乱 | W3-4 任务结果语义 | G3 |
| P1-06 | 缺少阶段级可观测性 | W4-1 结构化观测 | G4 |
| P1-07 | 测试未覆盖真实文件型 SQLite 争用 | W4-3 争用基准 | G4 |
| P2-01 | PostgreSQL 旧计划与当前架构冲突 | W5-3 重写数据库演进计划 | G5 |
| P2-02 | DBWriteQueue 是否需要尚无数据支撑 | W5-2 ADR 决策 | G5 |
| P2-03 | 无专用 readiness 和同步健康视图 | W4-2 健康接口 | G4 |
| P2-04 | Tracker 状态缺少变化指纹 | W5-1 指纹条件优化 | G5 |
| P2-05 | WAL、checkpoint、写放大未量化 | W4-1、W5-2 | G5 |
| P2-06 | 文档和功能状态与真实完成度不一致 | W5-4 状态回填 | G5 |

任何风险编号只有在对应交付项的测试、观测、回滚和 DoD 全部满足后才能关闭。

---

## 3. 当前证据与实施基线

### 3.1 已确认运行基线

- 本地 app.db 约 94 MiB。
- torrents 约 22,277 行，trackers 约 30,475 行，活跃关键词约 189 个。
- 当前有 4 个下载器，其中两个约有 10,000 个种子。
- 历史 Tracker 同步耗时约 152～422 秒，最大记录 1161 秒。
- 种子信息同步存在约 136～190 秒的长运行记录。
- SQLite 使用 WAL、synchronous=NORMAL、busy_timeout=15 秒、NullPool。
- 前端默认请求超时约 20 秒；因此数据库等待和下载器调用阻塞可直接表现为接口超时。
- 现有相关治理测试 75 项通过，但主要验证契约和 Mock；现有 benchmark 没有执行真实文件型 SQLite DML。
- 本地分类探针显示 Tracker 关键词纯 CPU 分类约 0.1 秒，首要问题是无差别写回，不是分类算法本身。
- 文件型 SQLite 探针已经证明：一个未提交 DML 事务足以让竞争写者等待并最终返回 SQLITE_BUSY。

### 3.2 当前源码锚点

下列位置是 2026-08-08 的实测入口；实施前需重新确认行号，源文件和方法名是稳定定位依据：

| 责任 | 当前文件与方法 |
|---|---|
| 通用批量写入 | backend/app/services/sync_db_write.py：bulk_upsert_with_retry |
| 手动同步入口 | backend/app/api/endpoints/torrent_sync.py：sync_single_downloader |
| Tracker 状态更新 | backend/app/api/endpoints/torrent_sync.py：update_tracker_status_from_keywords |
| qB Tracker 展开 | backend/app/api/endpoints/torrents_async.py：_enrich_qb_torrents_with_trackers |
| qB 移除标记 | backend/app/api/endpoints/torrents_async.py：_mark_qb_removed_torrents |
| qB/TR info-only | backend/app/api/endpoints/torrents_async.py：info-only 同步方法 |
| 下载器运行时 | backend/app/services/downloader_api_runtime.py：DownloaderApiRuntime、DownloadLane |
| 后台资源准入 | backend/app/tasks/resource_guard.py |
| 定时执行器 | backend/app/tasks/cron_executor.py |
| info 定时任务 | backend/app/tasks/scheduler/torrent_sync/torrent_info_sync_task.py |
| Tracker 定时任务 | backend/app/tasks/scheduler/torrent_sync/tracker_sync_task.py |
| SQLite 配置 | backend/app/database.py |
| 日志格式 | backend/app/main.py |
| Worker 启动 | backend/btdeck_startup.sh、backend/app/main.py |
| 任务模型与 API | backend/app/tasks/models.py、backend/app/api/endpoints/cron_tasks.py |
| 任务前端 | frontend/src/api/tasks.ts、frontend/src/views/tasks/index.vue |

---

## 4. 目标执行模型

~~~text
手动 API / Cron Executor
          │
          ▼
统一 SyncCoordinator
  ├─ 生成 run_id、任务类型和预算
  ├─ 后台资源准入，仅用于同步作业
  ├─ 读取持久化检查点
  └─ 分阶段执行
          │
          ├───────────────┐
          ▼               ▼
DownloaderApiRuntime    数据读取与差异计算
  ├─ interactive 槽      ├─ 远程 I/O 在事务外
  ├─ background 槽       ├─ CPU 工作在事务外
  └─ 每下载器硬上限      └─ 只生成待写变更集
          │               │
          └───────┬───────┘
                  ▼
          Chunked DB Writer
          ├─ 每批独立 commit
          ├─ 仅当前批重试
          ├─ 记录锁等待和变更数
          └─ 成功后推进 checkpoint
                  │
                  ▼
       结构化日志 / 健康状态 / 任务页
~~~

关键顺序是“远程读取 → 差异计算 → 短事务写入 → 检查点推进”。禁止在已经持有 SQLite 写锁时调用下载器或制作数据库备份。

---

## 5. 发布门与执行顺序

| 阶段 | 目标 | 建议工作量 | 可独立发布 | 发布门 |
|---|---|---:|---|---|
| W0 | 立即止血与基线固化 | 0.5～1 日 | 是，仅运维动作/测试基线 | G0 |
| W1 | 缩短 SQLite 写事务 | 2～3 日 | 是 | G1 |
| W2 | 统一同步路径并恢复请求响应性 | 3～5 日 | 是 | G2 |
| W3 | 有界、可续跑和可解释的同步 | 3～5 日 | 是，含迁移 | G3 |
| W4 | 可观测性、健康检查和真实争用验收 | 2～3 日 | 是 | G4 |
| W5 | P2 决策和文档收口 | 1～2 日 | 是 | G5 |

W1 和 W2 均属于 P0。不得等待 W3/W4 全部完成后才部署 P0 修复。

---

## 6. W0：立即止血与基线固化

### W0-1 生产运行止血手册

**覆盖问题**：P0-01、P0-05、P0-06、P1-05。

**根因**：在代码修复落地前，默认任务可能相邻运行，手动全量同步可能与定时任务重叠，SQLite 无法承受多个长写事务和多 Worker。

**目标文件**：

- backend/docs/operations/database-blocking-and-sync-issues-2026-08.md
- 新建 backend/docs/operations/sync-contention-runbook.md
- 部署说明中实际生效的 Worker 配置文件

**实施步骤**：

1. 记录当前 Tracker 和 info 任务 cron、最近一次成功、最近一次跳过、耗时及实际数据更新时间。
2. 在修复窗口内错开两个任务，至少保留上一次 P95 时长加 50% 的间隔。
3. 高峰期禁止触发手动全量同步；必须执行时，先确认两个默认任务均不在运行。
4. SQLite 部署确认只有一个后端 Worker；发现大于 1 时先回到 1。
5. 保留现有 busy_timeout，不上调前端超时，不把“等待更久”当作止血方案。
6. 给出取消任务和恢复原 cron 的明确操作步骤，不直接修改用户已有任务而不留记录。

**验证**：

- 运维人员能根据手册确认正在运行的同步、Worker 数和最近数据新鲜度。
- 演练暂停、错峰、恢复各一次；不修改数据内容。

**观测**：

- 每 5 分钟记录接口 P95/P99、超时率、SQLITE_BUSY 数、任务阶段和 WAL 大小。
- 记录止血前后同一时间窗口的对比基线。

**回滚**：

- 恢复原 cron 和原任务 enabled 状态。
- 不涉及 Schema，运维动作可即时撤销。

**DoD**：

- 手册包含前置检查、操作、验证、取消和恢复。
- 生产值班人员能在 5 分钟内判断是否存在任务重叠或多 Worker。

### W0-2 可重复基线采集

**覆盖问题**：P1-06、P1-07。

**根因**：当前只有零散日志和一次性探针，后续优化可能无法客观证明收益或发现回退。

**目标文件**：

- backend/scripts/sync_resource_benchmark.py
- 新建 backend/scripts/sync_baseline_report.py，若现有脚本可扩展则不新建
- backend/tests 下相关基准测试说明

**实施步骤**：

1. 固定小、中、大三档数据量；大档至少覆盖当前 2.2 万种子、3 万 Tracker。
2. 固定交互探针：只读列表、单条更新、创建/删除类写请求、任务状态查询。
3. 采集任务总耗时、各阶段耗时、数据库提交次数、每批行数、锁等待、事件循环延迟和 WAL 增量。
4. 输出机器可读 JSON 和简短 Markdown 汇总；报告文件不提交真实业务数据。
5. 保存修复前基线，后续每个发布门使用相同场景复测。

**验证**：

- 同一环境连续运行 3 次，关键指标偏差可解释。
- 报告不包含下载器密码、Cookie、种子敏感字段或完整 Tracker URL。

**观测**：本任务本身建立基线，不新增生产指标。

**回滚**：脚本只读或使用临时数据库；删除临时产物即可。

**DoD**：

- G0 基线报告完成。
- 任何后续“性能改善”均能与该报告作同口径比较。

### G0 发布门

- [ ] 已确认 SQLite 单 Worker。
- [ ] Tracker 与 info 默认任务不存在高峰期重叠。
- [ ] 手动全量同步有明确禁用/审批规则。
- [ ] 基线报告已生成并脱敏。
- [ ] 没有通过增加接口超时掩盖问题。

---

## 7. W1：P0 数据库事务修复

### W1-1 通用写入改为真实分批提交

**覆盖问题**：P0-03、P1-04。

**根因**：bulk_upsert_with_retry 接收大列表并在一个事务内完成，批大小没有形成真实 commit 边界。即使 SQL 执行较快，整个事务仍长时间占有 SQLite 写锁。

**目标文件**：

- backend/app/services/sync_db_write.py
- backend/app/api/endpoints/torrents_async.py
- backend/app/tasks/resource_guard.py
- backend/app/core/config.py
- backend/.env.example 及部署环境变量说明
- backend/tests/services/test_sync_db_write.py
- backend/tests/api/test_torrents_async_db_governance.py
- 新建 backend/tests/integration/test_sqlite_sync_contention.py

**实施步骤**：

1. 在 sync_db_write 中提供统一 chunk 迭代和写入统计结构，至少返回 scanned、changed、committed、batches、retries、elapsed_ms。
2. 将 SYNC_DB_COMMIT_BATCH_SIZE 作为真实提交批大小；默认值先以 200～500 行压测，最终值由 G1 数据确定。
3. 每批采用独立短事务：进入 db_write_scope、执行当前批 DML、commit、退出；下一批不得复用未清理的事务状态。
4. 锁冲突只重试当前批，使用有限指数退避加抖动；设置最大尝试次数和总退避上限。
5. IntegrityError、SQL 逻辑错误不得按锁冲突重试；错误分类需保留原异常链。
6. 批次之间主动让出事件循环；同步 Session 工作通过既有线程边界执行，不在 async 路径直接阻塞。
7. 将 qB/TR info-only 的 bulk 调用迁移到统一实现，删除重复的批处理和 retry 分支。
8. 明确返回部分进度；某批失败时不得把已经提交的批标记为未执行。

**测试**：

- 空输入不创建事务、不 commit。
- 小于、等于、大于 batch size 的边界测试。
- 第 N 批发生一次 SQLITE_BUSY 后仅重试第 N 批。
- 非锁异常立即失败且不重试。
- 文件型 SQLite 两连接并发：交互写在同步批次间获得写锁。
- 22k/30k 规模下单次写事务 P99 小于 250 ms，任何事务不得跨下载器网络调用。
- 既有 test_sync_db_write 和治理架构测试全部通过。

**观测**：

- 结构化字段：run_id、phase、batch_index、batch_rows、changed_rows、commit_ms、lock_wait_ms、retry_count。
- 告警候选：单批 commit 超过 500 ms；一次运行锁重试超过 5 次；连续两批失败。

**回滚**：

- 保留短期配置开关 SYNC_CHUNKED_COMMIT_ENABLED；回滚只切回旧写入实现，不回滚数据。
- 开关最多保留两个稳定版本，避免长期双实现漂移。

**DoD**：

- info-only 不存在覆盖整批数据的一次性 commit。
- 源码审查能清晰标出每个事务的开始和结束。
- 文件型 SQLite 争用测试证明普通写请求可在批次间完成。

### W1-2 Tracker 关键词状态只写变化行

**覆盖问题**：P0-02、P2-04 的前置条件。

**根因**：update_tracker_status_from_keywords 在每次 Tracker 任务末尾扫描并写回全表，即使关键词和判定结果没有变化也制造大量 UPDATE、WAL 和写锁时间。

**目标文件**：

- backend/app/api/endpoints/torrent_sync.py
- 新建或复用 backend/app/services/tracker_status_sync.py
- backend/app/core/tracker_judgment.py 及现有关键词判定服务
- backend/app/tasks/scheduler/torrent_sync/tracker_sync_task.py
- backend/tests/services/test_tracker_status_sync.py
- backend/tests/tasks/test_tracker_sync_task.py
- backend/tests/integration/test_sqlite_sync_contention.py

**实施步骤**：

1. 先完成代码复用审计：复用现有 TrackerJudgmentEngine/关键词判定，不在端点层复制分类规则。
2. 将状态同步从 API 文件抽到服务层，供定时任务、统一协调器和必要的管理入口共同调用。
3. 只查询判定所需最小字段和当前状态；分类在数据库写事务外完成。
4. 生成 old_status 与 new_status 不同的变更集；零变化时不进入 db_write_scope、不执行 UPDATE、不 commit。
5. 对变化集调用 W1-1 的统一分批写入；禁止逐行 commit 和全表无条件 UPDATE。
6. 关键词变化时允许重新计算全量，但仍只写变化行；关键词未变化时的指纹优化留到 W5-1。
7. 返回 scanned、changed、unchanged、batches 和 duration，不再只返回笼统成功。

**测试**：

- 无关键词、无 Tracker、全不变、部分变化、全部变化。
- 规则优先级、大小写、重复关键词和失效关键词沿用既有语义。
- 零变化时断言 DML=0、commit=0。
- 大于 SQLite 绑定变量安全阈值的数据集必须分块。
- 文件型 SQLite 下执行状态重算时，CRUD 写探针不超时。

**观测**：

- tracker_status_scanned、tracker_status_changed、change_ratio、classification_ms、write_ms、commit_batches。
- 当 change_ratio 长期接近 0 但 write_rows 非 0 时告警，防止回归为全表写。

**回滚**：

- 配置开关 SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED 可临时回到旧逻辑。
- 回滚不改变判定规则；若新旧结果不一致，先导出差异再切换。

**DoD**：

- 日常无变化运行的 Tracker 状态阶段不产生写事务。
- 规则变化时仅持久化实际变化行。
- 端点层不再承载 Tracker 全表更新业务逻辑。

### W1-3 qB 移除标记纳入统一写治理

**覆盖问题**：P0-03、P0-06。

**根因**：_mark_qb_removed_torrents 等写路径仍可能在统一 db_write_scope 和真实分批边界之外执行，形成旁路写者。

**目标文件**：

- backend/app/api/endpoints/torrents_async.py
- backend/app/services/sync_db_write.py
- backend/tests/api/test_torrents_async_db_governance.py

**实施步骤**：

1. 对 qB 移除标记先在事务外计算待更新 ID。
2. 使用统一批大小和写入服务更新；空变更不得 commit。
3. 删除路径内自建 retry/commit 逻辑。
4. 全仓扫描同步相关 add、update、delete、bulk_save、execute DML，形成允许清单和旁路清单。
5. 将本轮发现的所有后台同步旁路写者纳入治理；普通短请求写入保持原请求事务，不获取后台准入锁。

**测试**：

- 无移除、少量移除、大量移除和中途锁冲突。
- 架构测试确保同步模块的 DML 只能通过批准的写入口。

**观测**：removed_scanned、removed_changed、commit_batches、lock_retries。

**回滚**：保留旧函数签名，通过内部适配回退，不恢复无界事务。

**DoD**：

- 同步相关的后台 DML 旁路清单归零。
- 普通请求处理器没有误用后台 db_write_scope。

### G1 发布门

- [ ] info-only、Tracker 状态和 qB 移除标记都是真实分批提交。
- [ ] 无变化 Tracker 状态任务 DML=0。
- [ ] 文件型 SQLite 争用测试通过。
- [ ] 单批事务 P99 小于 250 ms，锁重试有上限。
- [ ] 可用开关回退，但没有数据格式变化。

---

## 8. W2：P0 同步路径和请求响应性修复

### W2-1 建立统一 SyncCoordinator，消除手动同步旁路

**覆盖问题**：P0-01、P0-06。

**根因**：手动 sync-single 通过 BackgroundTasks 进入旧版 torrent_sync_db_async，而定时任务走 info-only/tracker-only 新路径。两条路径的准入、分批、错误语义和观测不一致。

**目标文件**：

- 新建 backend/app/services/sync_coordinator.py
- backend/app/api/endpoints/torrent_sync.py
- backend/app/tasks/scheduler/torrent_sync/torrent_info_sync_task.py
- backend/app/tasks/scheduler/torrent_sync/tracker_sync_task.py
- backend/app/tasks/cron_executor.py
- backend/app/tasks/resource_guard.py
- backend/tests/api/test_sync_governance_integration.py
- backend/tests/tasks/test_cron_executor.py
- 新建 backend/tests/services/test_sync_coordinator.py

**实施步骤**：

1. 定义统一请求对象：sync_type、downloader_ids、trigger、run_id、deadline、record_budget、force 和 dry_run。
2. 定义统一结果：outcome、phase、scanned、changed、committed、checkpoint、skip_reason、errors 和 duration。
3. Coordinator 负责阶段编排，具体 qB/TR 读取和转换继续复用现有实现，不复制超过 50% 的业务代码。
4. Cron 和手动入口只调用 Coordinator；手动后台任务也必须在后台执行体内完成资源准入，不在 HTTP 请求线程长持准入锁。
5. 旧 torrent_sync_db_async 先作为 legacy adapter，内部转发至 Coordinator；确认无调用后删除旧全量实现。
6. 数据库备份放在同步写入之前的独立 phase，完成后关闭文件句柄；不得在 DML 事务中复制 app.db/WAL。
7. 对同一 downloader_id 与 sync_type 提供幂等运行键；重复触发返回 already_running/skipped，而不是启动第二个作业。
8. 明确取消语义：在批次和下载器调用边界检查取消；已提交批次保留，结果标记 partial/cancelled。

**测试**：

- 手动和 Cron 触发相同输入时，调用相同 Coordinator 方法及同一写入服务。
- 两个相同任务竞争时只允许一个运行。
- admission 超时、取消、部分完成和下载器离线的结果语义。
- 旧 API 响应兼容；任务实际状态可被查询。
- 架构测试不再允许手动入口调用 legacy 全量实现。

**观测**：

- run_id、trigger、sync_type、downloader_count、admission_wait_ms、phase、outcome。
- 日志可从 HTTP 触发记录关联到每个 phase 和最终 TaskLog。

**回滚**：

- SYNC_CANONICAL_COORDINATOR_ENABLED 短期支持切回 legacy adapter。
- legacy 只能作为应急回退，禁止与新路径同时执行；两个稳定版本后删除。

**DoD**：

- 手动与定时任务只有一个业务执行入口。
- 所有后台同步均经过相同资源准入、写治理和结果记录。
- 无法通过旧端点绕开治理。

### W2-2 为交互下载器 API 保留容量

**覆盖问题**：P0-05、P1-04。

**根因**：DownloaderApiRuntime 虽有 lane 和每下载器总并发上限，但 background Tracker 调用可占满全部槽；priority 参数没有形成可验证的调度保障。

**目标文件**：

- backend/app/services/downloader_api_runtime.py
- backend/app/core/config.py
- backend/.env.example 及部署环境变量说明
- backend/tests/services/test_downloader_api_runtime.py
- backend/tests/integration/test_sync_api_responsiveness.py

**实施步骤**：

1. 每下载器保留硬总容量 total_capacity，默认保持 2；新增 background_capacity，SQLite 初始默认 1。
2. background 调用必须同时取得 background 槽和 total 槽；interactive 只取得 total 槽。这样后台最多占 1 个，另 1 个可服务交互。
3. 容量租约由实际线程任务完成时释放，而不是 asyncio 等待超时时释放，避免超时线程仍运行却提前放大真实并发。
4. 分别记录 queue_wait_ms 和 remote_call_ms；请求 timeout 需要明确包含或区分排队预算与远程调用预算。
5. 保留现有线程侧硬信号量作为最终物理上限；不得只依赖 asyncio semaphore。
6. 将未生效的 priority 参数删除或收窄为明确 lane 枚举；P0 不实现复杂优先级队列。
7. 对 total_capacity=1 的配置显式拒绝 background_capacity=1 且要求交互保留的矛盾组合，或自动将后台串行并记录警告。

**测试**：

- 一个后台调用运行时，交互调用可使用保留槽。
- 多个后台调用不能消耗保留槽。
- 调用方超时后，底层线程完成前容量不会释放。
- qB/TR 慢调用、异常、取消、运行时 shutdown 均不泄露租约。
- 每下载器隔离：A 下载器拥堵不影响 B。
- 压测期间交互下载器 API P95 满足 G2 门槛。

**观测**：

- downloader_id、lane、queue_wait_ms、remote_call_ms、active_total、active_background、timeout。
- background 队列持续增长或 interactive queue_wait P95 超过 500 ms 时告警。

**回滚**：

- 配置可将 background_capacity 恢复到原总容量。
- 不改变下载器客户端创建方式或 API 数据结构。

**DoD**：

- 测试能稳定证明后台任务无法占满每下载器全部容量。
- timeout 后不存在并发上限被绕过。

### W2-3 清除 async 请求端同步下载器调用和漏 await

**覆盖问题**：P0-04。

**根因**：torrent_crud.py、tracker.py、torrent_status.py 等 async 处理器仍直接执行同步 qB/TR 客户端调用，慢网络会阻塞事件循环；部分异步 helper 调用缺少 await。

**目标文件**：

- backend/app/api/endpoints/torrent_crud.py
- backend/app/api/endpoints/tracker.py
- backend/app/api/endpoints/torrent_status.py
- backend/app/api/endpoints/torrent_deletion.py
- backend/app/api/endpoints/tag_management.py
- backend/app/api/endpoints/downloader.py
- backend/app/services/downloader_api_runtime.py
- backend/tests/api 下对应端点测试
- 新建 backend/tests/architecture/test_async_downloader_calls.py

**实施步骤**：

1. 先用 AST 建立完整清单：async def 内的客户端同步方法、新建 qbClient/trClient、漏 await coroutine、直接 requests 调用。
2. 按垂直切片迁移：Tracker CRUD → 种子 CRUD/状态 → 删除/标签 → 下载器设置及扫描发现的其他端点。
3. 所有网络调用通过 DownloaderApiRuntime 的 INTERACTIVE lane；客户端只从 app.state.store 获取。
4. 保持当前 API 响应和错误码；将线程中的下载器异常映射回既有业务异常。
5. 修复漏 await 后增加 AsyncMock 断言，防止 coroutine object 被当作结果。
6. 同步 SQLAlchemy Session 的较长查询/写入要么改为同步端点，要么放入明确线程边界；禁止共享同一 Session 跨线程。
7. 架构测试仅允许批准的 adapter 内直接调用同步客户端，端点文件不得调用。

**测试**：

- 每个迁移端点覆盖成功、下载器超时、离线、权限失败和取消。
- 事件循环心跳探针在 2 秒慢下载器调用期间持续运行，最大 lag 满足门槛。
- AST 测试阻止新增直接客户端构造、直接同步调用和已知漏 await 模式。
- 验证同一客户端来自 app.state.store，没有 login/logout 和额外连接。

**观测**：

- endpoint、downloader_id、lane=interactive、queue_wait_ms、remote_call_ms、timeout_stage。
- event_loop_lag_ms 与请求 P95/P99 关联展示。

**回滚**：

- 各垂直切片独立提交和发布，可逐端点回退。
- 不允许以恢复直接同步调用作为长期回滚；紧急回退同时限制该端点并发并登记技术债。

**DoD**：

- 架构测试清单中的 async 端点不再直接执行同步下载器 I/O。
- 交互请求在后台同步运行期间仍能进入保留槽。

### W2-4 SQLite 单 Worker 启动约束

**覆盖问题**：P0-06。

**根因**：resource_guard 和 Python 信号量均为进程内对象；btdeck_startup.sh 可读取 WORKERS 启动多个进程，每个进程还可能各自启动 scheduler，导致锁和准入失效。

**目标文件**：

- backend/btdeck_startup.sh
- backend/app/main.py
- backend/app/database.py
- backend/tests/core/test_sqlite_worker_guard.py
- deploy 和 Docker 运行说明中的 Worker 配置

**实施步骤**：

1. 启动时解析实际 DATABASE_URL；SQLite 且 WORKERS 不等于 1 时 fail-fast，并输出可操作错误。
2. 不依赖 main.py 的直接运行默认值，因为容器脚本和外部 uvicorn 命令都可能绕开。
3. 启动日志记录 database_backend、worker_count、scheduler_enabled 和 process_id。
4. 增加 scheduler 单实例断言；SQLite 当前依靠单 Worker，PostgreSQL 阶段必须另做 Leader 选举或外置 scheduler。
5. 文档明确：不能通过启动多个 SQLite Worker 缓解接口卡顿。

**测试**：

- SQLite + WORKERS=1 启动通过。
- SQLite + WORKERS=2 明确失败。
- PostgreSQL URL 不被 SQLite 检查误杀，但 scheduler 多实例保护仍有显式状态。
- shell 启动参数和直接 Python 启动路径均覆盖。

**观测**：启动日志和 readiness 返回非敏感的 backend 类型、worker 合规状态。

**回滚**：提供临时显式 override 仅用于诊断，不作为生产默认；使用时 readiness 必须 unhealthy。

**DoD**：

- 任何受支持的 SQLite 启动入口都不能静默运行多 Worker。
- 启动配置与实际进程数在日志中可核对。

### G2 发布门

- [ ] 手动和 Cron 同步使用统一 Coordinator。
- [ ] 后台调用最多使用每下载器 1 个默认槽，至少保留 1 个交互槽。
- [ ] async 端点架构扫描无未批准同步下载器调用和漏 await。
- [ ] SQLite 多 Worker fail-fast。
- [ ] 在后台同步持续运行时，代表性 CRUD：只读 P95 小于 1 秒、写 P95 小于 2 秒、超时率低于 0.1%。
- [ ] 事件循环 lag P99 小于 100 ms；单次大于 500 ms 必须有告警和关联日志。

---

## 9. W3：P1 有界、可续跑和可解释的同步

### W3-1 qB Tracker 同步改为有界队列和单轮预算

**覆盖问题**：P1-01、P1-04。

**根因**：_enrich_qb_torrents_with_trackers 可能为全部 hash 一次性创建任务，并对每个种子调用 Tracker API。10k 级下载器会形成任务、网络、内存和总耗时峰值。

**目标文件**：

- backend/app/api/endpoints/torrents_async.py
- backend/app/services/sync_coordinator.py
- backend/app/core/config.py
- backend/.env.example 及部署环境变量说明
- backend/tests/api/test_torrents_async_tracker_budget.py
- backend/tests/services/test_sync_coordinator.py

**实施步骤**：

1. 禁止为全部 hash 一次性 create_task；使用固定大小 worker pool 或有界 producer/consumer 队列。
2. 配置每下载器 tracker_worker_count、max_torrents_per_run、run_budget_seconds 和 per_call_timeout。
3. 首轮按稳定排序读取；后续从持久化 cursor 继续，运行到数量或时间预算即返回 partial。
4. 活跃种子、最近错误种子可配置优先级，但必须保证普通种子最终被轮转，避免永久饥饿。
5. 只有对应数据库批次 durable commit 后才能推进 cursor。
6. 每轮到达末尾时记录 cycle complete 和 last_full_sync_at；下一轮从头开始新周期。
7. qB RID 缓存的确认点与 durable commit 对齐，防止数据库未落盘但缓存已前进。

**测试**：

- 10k hash 时活跃 asyncio 任务数量不超过配置上限加固定控制任务。
- 时间预算、数量预算、取消和重启后续跑。
- 第 N 批失败时 cursor 停在最后 durable 批。
- 活跃优先不破坏最终全覆盖。
- 内存峰值相对基线下降并符合 G3。

**观测**：

- queue_depth、workers_active、processed_this_run、budget_reason、cursor_before/after、cycle_progress、remote_error_rate。

**回滚**：

- 可把单轮预算配置为覆盖全量，但仍保留有界 worker，不恢复一次性任务爆炸。

**DoD**：

- qB Tracker 单轮工作量有硬上限。
- 进程重启后不会从头无条件重复整个 10k 周期。

### W3-2 新增持久化同步检查点

**覆盖问题**：P1-03，并支撑 P1-05、P2-03、P2-04。

**根因**：游标、周期开始、最近完整同步和部分结果只存在内存或日志文本中，重启、取消或部署后无法可靠续跑和判断新鲜度。

**目标文件**：

- 新建 backend/app/models/sync_checkpoint.py，或按现有模型组织合并
- backend/app/models/__init__.py
- backend/app/tasks/models.py
- backend/alembic/versions/ 新迁移
- backend/alembic/env.py
- backend/app/services/sync_coordinator.py
- backend/tests/core/test_db_migration.py
- 必要时新建 backend/tests/core/test_sync_checkpoint_migration.py
- backend/tests/services/test_sync_checkpoint.py

**建议 Schema**：

sync_checkpoints：

| 字段 | 用途 |
|---|---|
| id | 主键 |
| downloader_id | 下载器标识 |
| sync_type | info、tracker、tracker_status |
| cursor_value | 透明字符串或 JSON 文本游标 |
| cycle_started_at | 当前周期开始时间 |
| last_full_sync_at | 最近完整覆盖时间 |
| last_success_at | 最近成功提交时间 |
| last_attempt_at | 最近尝试时间 |
| outcome | success、partial、skipped、failed、no_action、cancelled |
| detail_json | 版本化的非敏感统计 |
| version | 乐观更新或格式版本 |
| created_at、updated_at | 审计时间 |

对 downloader_id + sync_type 建唯一约束和查询索引。

task_logs 增补候选字段：

- run_id
- outcome
- skip_reason
- rows_changed
- phase_summary_json

字段可以为空，以兼容历史记录；如现有通用 JSON 字段已满足查询和索引需求，应优先复用，避免重复 Schema。

**实施步骤**：

1. 先确认现有模型是否有可复用的任务状态/键值表；相似度超过 50% 时扩展现有模型。
2. 创建 Alembic 迁移，不使用 create_all。
3. 导入模型到 alembic/env.py，更新 expected head/table count 等迁移防护。
4. Checkpoint 更新与对应数据批次在同一短事务内完成，保证游标不会越过未落盘数据。
5. 使用 version 或受控单运行约束避免两个运行覆盖进度。
6. detail_json 只存聚合统计，不存完整种子、Tracker URL 或下载器凭据。

**测试**：

- 空库 upgrade、downgrade、再次 upgrade。
- 从当前生产近似 Schema 升级，历史 task_logs 可读。
- 批次提交与 checkpoint 原子性。
- 进程重启、取消和失败后正确续跑。
- 并发更新时不会倒退 cursor。

**观测**：

- checkpoint_age_seconds、cycle_age_seconds、last_full_sync_age、cursor_progress、version_conflicts。

**回滚**：

- 先回滚应用到不依赖新字段的版本，再执行 downgrade。
- 部署前备份 SQLite 主库及 WAL/SHM 一致性快照。
- 新表和可空列不影响旧代码；紧急回滚可保留未使用表，待稳定后再清理。

**DoD**：

- 中断和重启后同步从最后 durable checkpoint 继续。
- 迁移往返通过，历史记录兼容。

### W3-3 info-only 改为有界下载器并发和分阶段流水线

**覆盖问题**：P1-02、P1-04。

**根因**：info 任务可同时处理 3 个下载器，并为大下载器构建全量内存对象；远程读取、差异计算和数据库写入的峰值叠加。

**目标文件**：

- backend/app/tasks/scheduler/torrent_sync/torrent_info_sync_task.py
- backend/app/api/endpoints/torrents_async.py
- backend/app/services/sync_coordinator.py
- backend/app/core/config.py
- backend/.env.example 及部署环境变量说明
- backend/tests/tasks/test_torrent_info_sync_task.py
- backend/tests/integration/test_sync_memory_bound.py

**实施步骤**：

1. SQLite 默认 downloader_concurrency=1；配置上限不得超过明确压测值。
2. 将每下载器处理拆为 fetch、normalize、diff、write、checkpoint 五阶段。
3. fetch 完成后释放下载器容量；写事务阶段不持有下载器调用槽。
4. 数据库现有记录按 ID/hash 分页读取，避免一次加载完整 ORM 对象图。
5. normalize/diff 使用受控批次；批次结束后释放临时列表并让出事件循环。
6. 对 qB RID 的增量捷径增加完整性保护；异常时回退到安全对账，但仍受单轮预算限制。
7. 为最大内存、单轮记录数和单轮时长提供硬配置及合理默认。

**测试**：

- 4 下载器、两个 10k 规模下实际并发符合配置。
- fetch 期间数据库写锁未持有；write 期间无下载器调用。
- 内存峰值不随全部下载器总量线性叠加。
- downloader 部分失败不阻止其他下载器完成，结果标记 partial。

**观测**：

- downloader_concurrency、phase_ms、rows_buffered、process_rss_mb、records_per_second、yield_count。

**回滚**：

- 并发配置可降为 1、预算可降小；不得回退为无界全并发。

**DoD**：

- SQLite 默认串行处理下载器。
- 最大内存和单轮工作量有可验证上限。

### W3-4 明确任务 outcome、skip 和数据新鲜度

**覆盖问题**：P1-05。

**根因**：cron_executor 可能把资源冲突跳过记作 success，任务列表只展示执行成功/失败，无法区分“调度器正常但数据没有更新”。

**目标文件**：

- backend/app/tasks/cron_executor.py
- backend/app/tasks/cron_crud.py
- backend/app/tasks/models.py
- backend/app/api/endpoints/cron_tasks.py
- frontend/src/api/tasks.ts
- frontend/src/views/tasks/index.vue
- backend/tests/tasks/test_cron_executor.py
- backend/tests/api/test_cron_tasks.py
- frontend/tests/unit/tasks-sync-freshness.spec.ts

**实施步骤**：

1. 统一 outcome 枚举：success、partial、skipped、failed、no_action、cancelled。
2. 调度器本身成功与业务数据成功分开：skipped 不记为 failed，但也不能更新 last_successful_data_at。
3. skip_reason 使用稳定机器码，如 resource_busy、already_running、outside_budget、downloader_offline。
4. API 返回 lastOutcome、lastSuccessfulDataAt、freshnessSeconds、stale、lastSkipReason 和 lastRunId。
5. stale 阈值由任务类型和 cron 间隔计算，允许配置；连续跳过导致超阈值时显示告警。
6. 前端任务页展示结果标签、最后数据更新时间和陈旧状态；保留现有兼容字段，不新增 any。
7. “无变化”使用 no_action，表示完成检查且数据已是最新，可更新新鲜度；它不同于 skipped。

**测试**：

- 六种 outcome 的后端持久化、API 映射和前端展示。
- skipped 不推进数据成功时间，no_action 会推进。
- 连续跳过后的 stale 判断。
- 旧 task_logs 缺少新字段时兼容展示。

**观测**：

- outcome_total 按 task_type/reason 聚合；freshness_seconds；consecutive_skips。

**回滚**：

- API 新字段均为向后兼容增量；前端回滚后后端字段可保留。
- Schema 回滚遵循 W3-2 顺序。

**DoD**：

- 用户无需阅读原始日志即可判断数据是否新鲜、任务为何未更新。
- skipped 和 success 不再混为同一业务结果。

### G3 发布门

- [ ] qB Tracker 工作队列和单轮预算有硬上限。
- [ ] checkpoint 与数据提交原子推进，重启续跑通过。
- [ ] SQLite info 下载器并发默认 1。
- [ ] 任务 API/UI 区分 success、partial、skipped、failed、no_action、cancelled。
- [ ] 大规模场景进程 RSS 峰值不超过空闲基线加 300 MiB，或给出经批准的环境特定门槛。
- [ ] 每个下载器至少在配置的最大周期内完成一次全覆盖。

---

## 10. W4：P1/P2 可观测性、健康检查与争用验收

### W4-1 阶段级结构化日志与核心指标

**覆盖问题**：P1-06、P2-05。

**根因**：当前普通日志 formatter 可能丢失 extra 字段，难以把接口超时、事件循环阻塞、下载器排队和 SQLite 写锁关联到同一个同步运行。

**目标文件**：

- backend/app/main.py
- 新建 backend/app/services/sync_observability.py，或扩展现有观测模块
- backend/app/services/sync_coordinator.py
- backend/app/services/downloader_api_runtime.py
- backend/app/services/sync_db_write.py
- backend/app/database.py
- backend/tests/services/test_sync_observability.py

**实施步骤**：

1. 定义稳定事件名和字段字典，不依赖自由文本解析。
2. 使用 run_id 贯穿触发、准入、远程读取、diff、batch commit、checkpoint 和最终 outcome。
3. 采用 JSON formatter 或确保 key=value extra 被 formatter 输出；敏感字段统一脱敏。
4. 启动轻量事件循环 lag 采样器，记录 P95/P99/max。
5. 记录 DownloaderApiRuntime 的 lane 排队与实际调用时间。
6. 记录数据库批次锁等待、commit、retry 和 SQLITE_BUSY。
7. 以只读方式记录 WAL 文件大小、增长率和 checkpoint 统计；高峰期间不主动执行 TRUNCATE checkpoint。
8. 首阶段可用结构化日志加进程内快照，不强制引入 Prometheus；若项目已有指标栈则接入现有方案。

**最小字段集**：

| 类别 | 字段 |
|---|---|
| 关联 | run_id、task_id、sync_type、trigger、downloader_id |
| 阶段 | phase、phase_ms、outcome、skip_reason |
| 下载器 | lane、queue_wait_ms、remote_call_ms、remote_timeout |
| 数据库 | batch_rows、changed_rows、commit_ms、lock_wait_ms、retry_count |
| 运行时 | event_loop_lag_ms、rss_mb、active_jobs |
| SQLite | wal_bytes、wal_growth_bytes、busy_count、checkpoint_busy |

**测试**：

- formatter 输出所有最小字段。
- 密码、passkey、Cookie、Authorization、完整 announce URL 不出现在日志。
- 同一 run_id 可还原完整阶段顺序。
- lag 采样器启动、关闭和异常恢复不泄露 task。

**观测和告警初始阈值**：

- event_loop_lag P99 大于 100 ms 持续 5 分钟：warning。
- 单次 lag 大于 500 ms：critical event。
- interactive queue P95 大于 500 ms：warning。
- SQLite busy 每 5 分钟大于 0：warning；连续增长：critical。
- commit P99 大于 250 ms：warning。
- WAL 持续 30 分钟增长且没有回落：warning。
- Tracker/info freshness 超过两个调度周期：critical。

阈值在两周基线后校准，调整必须留变更记录。

**回滚**：

- formatter 可切回文本模式；指标采样可配置关闭。
- 关闭观测不得关闭同步治理本身。

**DoD**：

- 一次接口超时能关联到当时的任务 phase、下载器排队和 SQLite 写批次。
- 日志不泄露敏感信息。

### W4-2 新增 liveness、readiness 和同步健康接口

**覆盖问题**：P2-03。

**根因**：Docker 当前以 /docs 作为健康检查，不能反映数据库可读、事件循环严重卡顿、Worker 违规或同步数据陈旧。

**目标文件**：

- 新建 backend/app/api/endpoints/health.py，或扩展现有健康端点
- backend/app/api/api.py
- backend/app/main.py 或路由注册文件
- backend/Dockerfile
- docker-compose.yml
- backend/app/api/endpoints/cron_tasks.py 或新建受保护的 sync-health 端点
- backend/tests/api/test_health.py

**实施步骤**：

1. GET /health/live 仅证明进程和事件循环响应，不访问外部下载器。
2. GET /health/ready 执行有严格超时的 SELECT 1，检查 SQLite 单 Worker 合规和 lag 近期状态；不得执行数据库写入。
3. readiness 失败返回 HTTP 503 和统一响应体，只暴露非敏感原因码。
4. Docker/Compose 健康检查从 /docs 改为 /health/ready；start_period 继续覆盖已知启动对账时长。
5. 增加受认证的同步健康接口，返回每类任务最近 outcome、freshness、active run、phase 和 checkpoint age。
6. 下载器离线不应默认让整个应用 readiness 失败；它属于业务健康告警。
7. 数据库“可写”探针不得由高频健康检查执行，可在受控诊断命令中使用临时短事务验证。

**测试**：

- 正常、数据库不可读、查询超时、lag 超阈值、Worker 不合规。
- liveness 在数据库故障时仍可响应。
- 健康接口无认证信息泄漏，Docker 命令只依赖状态码。

**观测**：readiness_failure_total 按原因聚合；同步健康端点访问审计。

**回滚**：

- Compose 可短期回到旧检查，但保留新端点。
- readiness 误报时允许临时放宽 lag 阈值，不跳过数据库检查。

**DoD**：

- /docs 不再承担健康检查职责。
- 运维能通过一个受保护接口判断同步是否活跃、停在哪个 phase、数据是否陈旧。

### W4-3 建立真实文件型 SQLite 争用基准和回归门

**覆盖问题**：P1-07。

**根因**：Mock、内存 SQLite 和不执行真实 DML 的 benchmark 无法暴露 WAL、fsync、索引更新、锁等待和真实并发请求的组合问题。

**目标文件**：

- backend/scripts/sync_resource_benchmark.py
- 新建 backend/scripts/sync_contention_benchmark.py，若可复用则合并
- backend/tests/integration/test_sqlite_sync_contention.py
- backend/tests/integration/test_sync_api_responsiveness.py
- backend/docs/operations/sync-contention-runbook.md

**实施步骤**：

1. 每次测试创建独立临时目录和真实 .db 文件，执行完整 Alembic head。
2. 生成与生产索引和字段分布接近的数据；大档至少 22k torrents、30k trackers。
3. 后台运行 info upsert、Tracker 状态更新和 qB 移除标记的真实 DML。
4. 并发发起代表性只读和写 API；下载器响应使用可控延迟 fake server，而不是跳过网络阶段。
5. 同时采集请求延迟、事件循环 lag、锁等待、提交耗时、WAL、RSS 和线程数。
6. 包含故障注入：SQLITE_BUSY、慢下载器、调用超时、任务取消、进程重启续跑。
7. 基准默认不进入普通单元测试全量，可作为 CI nightly/发布门命令；最小争用回归进入常规 CI。
8. 输出 JSON 供前后版本对比，失败时保留脱敏诊断摘要。

**验收矩阵**：

| 场景 | 只读 P95 | 写 P95 | 超时率 | SQLITE_BUSY | 事件循环 lag P99 |
|---|---:|---:|---:|---:|---:|
| 无同步基线 | 小于 500 ms | 小于 1 s | 0 | 0 | 小于 50 ms |
| info 同步 | 小于 1 s | 小于 2 s | 小于 0.1% | 最终失败 0 | 小于 100 ms |
| Tracker 同步 | 小于 1 s | 小于 2 s | 小于 0.1% | 最终失败 0 | 小于 100 ms |
| info + 交互下载器调用 | 小于 1 s | 小于 2 s | 小于 0.1% | 最终失败 0 | 小于 100 ms |
| 故障注入 | 可解释降级 | 可解释降级 | 无雪崩 | 有界重试 | 单次峰值可关联 |

若测试主机性能不足以满足绝对值，允许先建立环境校准系数，但生产发布门仍必须满足用户可感知 SLO。

**观测**：本任务验证 W4-1 的全部字段，并生成基线差异报告。

**回滚**：测试仅操作临时数据库和 fake downloader；不接触生产 app.db。

**DoD**：

- 基准确实执行文件型 SQLite DML，并能复现修复前阻塞。
- 修复后通过验收矩阵，且结果可在 CI/发布流程重复。

### G4 发布门

- [ ] run_id 能串联所有同步阶段和请求异常。
- [ ] liveness/readiness 与同步业务健康职责分离。
- [ ] Docker/Compose 使用 readiness。
- [ ] 文件型 SQLite 大档争用基准通过。
- [ ] 告警阈值、响应动作和 Runbook 已联动。

---

## 11. W5：P2 决策、演进和文档收口

### W5-1 Tracker 变化指纹条件优化

**覆盖问题**：P2-04。

**根因**：W1-2 已避免无变化写入，但每轮仍可能扫描并分类全部 Tracker。是否值得跳过分类需要真实数据支撑。

**目标文件**：

- backend/app/services/tracker_status_sync.py
- backend/app/models/sync_checkpoint.py
- 必要时新增 Alembic 迁移
- backend/tests/services/test_tracker_status_sync.py

**实施前门槛**：

- W4 数据显示 classification_ms 或读取成本占 Tracker 状态阶段 P95 的 20% 以上；否则不实现，只保留增量写。

**实施步骤**：

1. 指纹至少包含启用关键词规则版本、相关 Tracker 行的稳定版本信息和判定算法版本。
2. 不对完整敏感 URL 直接落盘；使用稳定摘要。
3. 指纹相同且上次周期完整成功时，可返回 no_action。
4. 任何规则版本变化、数据不完整、上次 partial/failed 都必须重新计算。

**测试**：

- 同指纹跳过、关键词变化、Tracker 增删改、算法版本变化、上轮失败。
- 不允许哈希碰撞或缺失元数据导致错误跳过；使用强摘要和版本字段。

**观测**：fingerprint_hit_rate、classification_saved_ms、false_skip_guard。

**回滚**：关闭指纹开关即恢复 W1-2 的全量比较、增量写，不影响正确性。

**DoD**：

- 只有数据证明收益后才实施。
- 指纹只优化计算，不改变 Tracker 判定正确性。

### W5-2 基于指标决定 DBWriteQueue 和 WAL 策略

**覆盖问题**：P2-02、P2-05。

**根因**：当前没有证据说明在真实分批、统一入口和单 Worker 后仍需要进程内单写者队列；过早引入会增加公平性、取消、崩溃恢复和请求优先级复杂度。

**目标文件**：

- 新建 backend/docs/adr/ADR-sync-db-write-queue.md
- backend/docs/operations/sync-contention-runbook.md
- 若决定实施，再单独创建实现计划

**决策指标**：

- G4 后 SQLITE_BUSY 是否仍发生。
- 写请求 P95/P99 是否仍超 SLO。
- 同时活跃写者数量和 lock_wait 分布。
- WAL 增长、checkpoint_busy 和单批 commit 分布。
- 是否存在无法通过错峰、分批和容量治理解决的公平性问题。

**决策规则**：

1. 若最终 SQLITE_BUSY=0 且写请求 SLO 达标：不引入 DBWriteQueue。
2. 若冲突集中于少数后台写者：继续收口旁路或降低批次/并发。
3. 只有多个合法写者在短事务下仍持续冲突，才设计单写者队列。
4. 队列若实施，交互写优先级、超时后的任务生命周期、崩溃恢复和可观测性必须先写入 ADR。
5. WAL 采用被动 checkpoint 观测；高峰期禁止定时 TRUNCATE。只有持续增长且 reader 阻碍明确时再调 checkpoint 参数。

**测试**：ADR 必须引用至少 7 天生产/准生产数据和 G4 基准结果。

**观测**：沿用 W4-1，不另造无法关联的指标。

**回滚**：本项默认是决策文档；若结论为不实施，无代码回滚。

**DoD**：

- DBWriteQueue 有明确“做/不做/何时复审”结论。
- WAL 参数变更有前后数据、风险和恢复步骤。

### W5-3 重写 PostgreSQL 演进计划

**覆盖问题**：P2-01。

**根因**：现有 PLANS/v1.0.8.md 包含与当前 app.state.store 客户端复用约束冲突的下载器连接池设想，且数据库切换不能自动解决事件循环阻塞和下载器容量争用。

**目标文件**：

- PLANS/v1.0.8.md
- backend/docs/constraints/database-migration.md
- backend/docs/constraints/downloader-connection.md
- 必要时新增数据库演进 ADR

**触发条件**：

满足任一项才进入 PostgreSQL 实施：

- SQLite 单 Worker 吞吐成为经 G4 证明的主要瓶颈。
- 产品需要可靠多 Worker/高可用写入。
- 数据规模或运维要求超出单文件备份和恢复能力。
- 长期指标表明分批治理后写请求 SLO 仍无法达到。

**重写要求**：

1. 明确 SQLite 和 PostgreSQL 双路径或一次性迁移策略。
2. 所有 Schema 仍由 Alembic 管理。
3. 移除新建下载器连接池方案；客户端继续由 app.state.store 管理。
4. PostgreSQL 多 Worker 必须解决 scheduler Leader、跨进程任务互斥和 checkpoint 并发。
5. 评估 SQL 方言、upsert、锁语义、备份恢复、连接池、数据迁移校验和回滚窗口。
6. 保留 W1～W4 的有界同步和观测，不因数据库升级删除。

**测试**：

- 迁移前后行数、关键聚合和随机样本校验。
- 回滚演练、双写或停机窗口演练。
- PostgreSQL 下同一套争用和 API SLO 基准。

**观测**：连接池等待、事务时长、死锁、慢 SQL、scheduler Leader 和数据新鲜度。

**回滚**：必须在实施计划中定义数据冻结点和回迁策略；没有演练不得上线。

**DoD**：

- v1.0.8 不再把数据库升级描述为当前 P0 的前置解决方案。
- 计划与 app.state.store、Alembic 和 scheduler 约束一致。

### W5-4 修正文档、功能状态与路线图

**覆盖问题**：P2-06。

**根因**：sync-resource-governance 的完成证据和约束文档把部分路径描述为已治理，但源码仍有 P0 旁路和真实争用测试缺口。

**目标文件**：

- feature_list.json
- progress.md
- session-handoff.md
- PLANS/sync-resource-governance.md
- backend/docs/constraints/sync-db-write-governance.md
- backend/docs/operations/database-blocking-and-sync-issues-2026-08.md
- docs/roadmap/ 相关三层路线图

**实施步骤**：

1. 实施启动时，在 feature_list.json 新增本修复计划的可追踪任务，或将旧“完成”状态降级并增加 follow-up，禁止继续使用误导性完成证据。
2. 每个发布门记录测试命令、结果和性能报告路径。
3. 源码方法或调用链变化后使用 roadmap-maintain 规则更新路线图并实测行号。
4. 约束文档列出唯一允许的同步写入口、手动/定时统一路径和真实文件型测试要求。
5. G5 后将原评估文档的问题状态更新为 closed、mitigated 或 deferred，并附证据。

**测试**：

- 路线图漂移检查。
- feature_list.json 格式和 evidence 路径有效。
- 文档中的方法名、配置名和命令可在仓库定位。

**观测**：不新增运行指标；以发布门证据完整率作为项目指标。

**回滚**：文档变更可独立回退，但不得把未通过发布门的事项恢复为完成。

**DoD**：

- P0/P1/P2 每项都有最终状态和证据链接。
- 约束、计划、路线图和源码一致。

### G5 发布门

- [ ] Tracker 指纹按数据决定实施或明确不实施。
- [ ] DBWriteQueue ADR 已作结论。
- [ ] WAL 策略有至少 7 天数据支撑。
- [ ] PostgreSQL 计划与当前架构一致，并保持为条件演进。
- [ ] feature_list、progress、handoff、constraints、roadmap 全部收口。

---

## 12. 配置设计与默认值原则

最终配置名应服从现有配置模型命名规范；下表是计划语义，不要求逐字采用：

| 配置语义 | SQLite 初始值 | 说明 |
|---|---:|---|
| DB commit batch size | 200～500，压测确定 | 必须形成真实 commit |
| DB lock retry count | 3 | 只重试当前批 |
| DB retry total backoff | 不超过 2 秒 | 防止排队雪崩 |
| 每下载器总调用容量 | 2 | 保持当前硬上限 |
| 每下载器后台容量 | 1 | 留 1 个交互槽 |
| info 下载器并发 | 1 | SQLite 默认 |
| qB Tracker workers | 1～2 | 不超过后台容量 |
| qB Tracker 单轮记录预算 | 500～1000 | 由远程耗时校准 |
| qB Tracker 单轮时间预算 | 60～120 秒 | 到期返回 partial |
| event loop lag warning | 100 ms P99 | 5 分钟窗口 |
| stale threshold | 2 个调度周期 | 按任务类型计算 |

所有新配置必须：

- 有类型、范围校验和启动日志。
- 有示例配置与默认行为测试。
- 不允许配置组合破坏交互保留槽或形成无界重试。
- 在任务结果中记录本次实际采用的关键预算，便于复盘。

---

## 13. 测试与验证总矩阵

### 13.1 单元测试

- sync_db_write：分批、重试、异常分类、统计。
- tracker_status_sync：变化检测、零写入、规则兼容。
- DownloaderApiRuntime：容量保留、timeout 后租约、shutdown。
- SyncCoordinator：阶段、幂等、取消、partial、skip。
- checkpoint：原子推进、版本冲突、续跑。
- outcome/freshness：六种结果和陈旧判断。
- observability：字段完整、脱敏、run_id 关联。

### 13.2 架构测试

- async endpoint 不得直接调用同步下载器 I/O。
- 不得创建 qbClient/trClient；客户端必须来自 app.state.store。
- 同步后台 DML 不得绕开统一 writer。
- 请求处理器不得获取后台资源准入锁。
- SQLite 启动不得多 Worker。

### 13.3 集成测试

- 真实临时文件型 SQLite，不使用内存数据库替代争用场景。
- 运行 Alembic head 和生产同等索引。
- 同步 DML 与 CRUD 并发。
- fake qB/TR 提供延迟、错误、超时和断连。
- 取消和进程重启后的 checkpoint 恢复。

### 13.4 前端测试

- 任务 outcome、skip reason、freshness、stale 展示。
- 历史记录缺少新字段时兼容。
- 不新增 any；typecheck、lint、unit、build 通过。

### 13.5 必跑命令

实施阶段按改动范围运行：

~~~text
cd backend && pytest tests/services/test_sync_db_write.py
cd backend && pytest tests/services/test_downloader_api_runtime.py
cd backend && pytest tests/api/test_sync_governance_integration.py
cd backend && pytest tests/integration/test_sqlite_sync_contention.py
cd backend && pytest
cd frontend && npm run test:unit
cd frontend && npm run lint
cd frontend && npm run build
./init.sh --ci
git diff --check
~~~

若仓库脚本名与实际不同，实施时以现有测试目录和 package scripts 为准，并在 evidence 中记录真实命令。

---

## 14. 分批上线、观测和回滚

### 14.1 上线顺序

1. G0：先错峰、单 Worker、采集基线。
2. G1：只上线短事务和增量写，观察至少一个完整 info/Tracker 周期。
3. G2：上线 Coordinator、容量保留和端点迁移，先单个下载器 canary。
4. G3：先执行 Alembic，再启用 checkpoint 和预算；验证历史任务兼容。
5. G4：切换健康检查前先在旁路探测 24 小时，确认无误报。
6. G5：在至少 7 天指标后完成 P2 决策。

### 14.2 每个发布门的观察窗口

- 至少覆盖 3 次 info 任务和 3 次 Tracker 任务。
- 至少包含一次手动单下载器同步。
- 至少包含一个高峰交互时段。
- 检查接口 SLO、lag、SQLITE_BUSY、commit、WAL、RSS、outcome 和 freshness。

### 14.3 自动暂停条件

满足任一项，停止扩大 rollout：

- CRUD 超时率超过 0.5% 或高于基线两倍。
- 出现数据行数异常下降、checkpoint 倒退或重复副作用。
- SQLITE_BUSY 最终失败连续出现。
- event loop lag 大于 500 ms 且与新路径相关。
- WAL 持续异常增长、磁盘剩余空间低于运维阈值。
- 同步周期无法在配置最大周期内完成。

### 14.4 回滚顺序

1. 停止新同步任务并等待当前短批次结束，不强杀正在 commit 的进程。
2. 通过发布门级开关回到上一条已验证路径。
3. 若涉及 W3 Schema：先回滚应用，再按迁移手册 downgrade；紧急情况下可保留向后兼容的新表/可空列。
4. 核对行数、最近 checkpoint、task outcome 和 CRUD 健康。
5. 恢复任务时先单下载器、单轮小预算。

禁止直接删除 app.db、WAL 或 SHM 来解除锁。数据库恢复必须使用一致性备份和既有恢复流程。

---

## 15. 风险与待确认决策

| 决策 | 建议默认 | 决策时点 |
|---|---|---|
| SQLite commit batch 最终值 | 先 200～500 压测 | G1 前 |
| qB Tracker 游标排序键 | 稳定 hash + 周期版本 | W3 设计评审 |
| info 内存上限 | 基线加 300 MiB | G3 前按部署内存校准 |
| task_logs 是否加列 | 优先复用现有结构；查询需求不足才加 | W3 迁移评审 |
| 指标后端 | 先结构化日志/现有栈 | W4 设计评审 |
| Tracker 指纹 | 有收益证据才做 | G4 后 |
| DBWriteQueue | 默认不做 | 7 天指标后 ADR |
| PostgreSQL | 条件演进，不是 P0 前置 | G5 |

任何待确认项都不得阻塞 W1 的短事务和增量写修复。

---

## 16. 完成定义

本计划整体完成需要同时满足：

- [ ] P0-01～P0-06 全部通过 G1/G2，并有真实 SQLite 争用证据。
- [ ] P1-01～P1-07 全部通过 G3/G4。
- [ ] P2-01～P2-06 已实施或由数据支持的 ADR 明确延期。
- [ ] 默认 Tracker/info 任务运行期间，代表性 CRUD 达到既定 SLO。
- [ ] 无最终 SQLITE_BUSY，事件循环 lag 和下载器排队在阈值内。
- [ ] 无变化 Tracker 状态同步不执行 DML。
- [ ] qB Tracker 和 info 的单轮任务、并发、内存和重试均有硬上限。
- [ ] 重启、取消、部分失败后能从 durable checkpoint 恢复。
- [ ] 用户能在任务页看到 outcome、skip reason 和数据新鲜度。
- [ ] liveness、readiness、同步业务健康和 Docker 健康检查完成分工。
- [ ] Alembic 往返、后端测试、前端测试、构建、init 和 diff check 通过。
- [ ] feature_list、progress、session-handoff、constraints 和 roadmap 与源码一致。
- [ ] 所有临时 legacy/feature flag 有删除版本，不形成永久双路径。

---

## 17. 首个实施批次建议

第一批只做 W1，控制改动面并最快消除数据库长锁：

1. 为 bulk_upsert_with_retry 增加真实分批提交和每批有限重试。
2. Tracker 状态更新改为变化检测后分批写，零变化零 DML。
3. qB removed 标记纳入同一 writer。
4. 增加最小文件型 SQLite 争用回归。
5. 通过 G1 后立即发布观察，不等待 Coordinator 和 checkpoint。

第二批实施 W2，直接处理用户感知的接口卡顿；第三批再引入 W3 的迁移和续跑能力。这样的拆分能把 P0 修复与较大的状态模型变更隔离，便于验证和回滚。

---

## 18. 2026-08-11 报告缺口修复记录

本节记录依据 `database-blocking-and-sync-verification-2026-08.md` 落地的修复，
不替代上面的发布门。生产发布前仍需在受控实例完成迁移、暂停/恢复演练和 30 轮基线归档。

- **P0 连接生命周期**：`torrents_async.py` 的 qB/TR info/full 方法改为强制接收缓存
  client；`torrent_sync.py` legacy adapter 和同步端点不再构造 `qbClient`/`trClient`，
  缺缓存直接 failed/raise；`sync-single` 查询改为 `AsyncSession` + `select`。
- **P1 Tracker 游标**：qB enrich 写入成功/失败标记；写入阶段只消费连续成功前缀，
  批提交/空 tracker 结果也只推进到实际处理 hash，抽取失败停止当前前缀，避免跨过未落盘记录。
- **P1 info 续跑**：qB/TR info 按稳定 hash 排序，支持 `{last_hash}` cursor、数量/时间预算、
  durable 写入后的 progress callback；存在 cursor 时强制完整快照，避免增量列表跳过 cursor 前的变更。
- **P2/W4-1 观测**：`snapshot_wal_stats()` 使用 `PRAGMA wal_checkpoint(PASSIVE)` 只读探测
  `busy_count`/`checkpoint_busy`；同步健康端点新增有界超时 `HEALTH_SYNC_DB_TIMEOUT_SECONDS`。
- **W0 运维闭环**：新增 [`backend/docs/operations/sync-stopgap-runbook.md`](../backend/docs/operations/sync-stopgap-runbook.md)，
  覆盖暂停、活动运行确认、错峰恢复、升级阈值和记录模板。

本次代码回归门：同步/观测/架构/健康定向套件通过；真实文件型 SQLite 争用回归通过；
生产 `app.db` 未迁移、未执行生产任务暂停/恢复，故 G0/G4 的部署项保持待执行。
