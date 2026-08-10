# 同步数据库阻塞修复从头实现验证（W0-W4-2）

> 验证日期：2026-08-10
> 验证范围：`PLANS/sync-database-blocking-remediation.md` 的 W0、W1、W2、W3、W4-1、W4-2
> 验证方式：独立源码审计、架构扫描、全量测试、真实文件型 SQLite 基准；不修改业务代码、不执行数据库迁移。

## 1. 结论先行

当前实现不是“W4-2 已完成即可整体关闭”的状态：

- W1 的短事务、增量 Tracker 状态写入和 qB removed 治理基本有效。
- W2 的资源准入、交互容量保留和单 Worker 防护有效，但仍有 P0 级连接复用/事件循环阻塞缺口。
- W3 的有界队列和检查点框架存在，但 qB Tracker 游标存在可复现的越过未持久化数据的正确性缺陷；info-only 的部分运行没有记录可续跑游标。
- W4-1 的结构化日志、run_id、事件循环 lag、批次提交和 WAL 字节数已接线，但生产运行时 `busy_count`/`checkpoint_busy` 仍为 `None`。
- W4-2 的健康接口和容器探针代码/测试通过；当前本地数据库尚未升级到 Alembic head，真实部署验证仍需先完成迁移。
- W0 需要的生产止血手册和暂停/恢复演练证据未找到；现有 `sync-contention-runbook.md` 是 W4-3 技术基准手册，不是 W0 值班止血手册。

因此，G0、G2、G3、G4 不能仅依据现有 `feature_list.json` 的 `done` 标记视为完全关闭。上线前至少要处理本报告的两个 P0/P1 正确性问题和 W4-1 指标缺口。

## 2. 独立验证证据

### 2.1 测试与基准

| 验证项 | 实际结果 | 判定 |
|---|---:|---|
| 后端全量 `python -m pytest -q` | 3135 passed、7 skipped、3142 collected；pytest 已输出最终摘要，但 Windows 包装命令在 300 秒时退出码为 124 | 测试本身通过；需关注进程收尾超时 |
| 同步治理相关 17 个测试套件 | 323 passed、1 skipped | 通过 |
| 大档真实文件型 SQLite 基准 | 22000 torrents / 30000 trackers / 30 轮；600 次探针无超时，最终 BUSY=0，SLO 4/4 PASS | 通过 |
| `health.py` mypy | `Success: no issues found` | 通过 |
| `health.py` flake8 | 无输出、退出码 0 | 通过 |
| `git diff --check` | 无 whitespace 错误 | 通过 |
| `python -m alembic current` | `f9a1b2c3d4e5` | 低于仓库 head |
| `python -m alembic heads` | `f5e6d7c8b9a0` | 目标 head |
| `python -m alembic check` | `Target database is not up to date` | 部署前必须迁移 |

大档基准主要结果：无同步场景读/写 P95 约 20/21 ms，info 场景约 33/31 ms，Tracker 状态场景约 142/164 ms，qB removed 场景约 28/23 ms；探针总超时为 0。新结果输出在临时目录中，未写入生产数据库。

`./init.sh --ci` 无法在当前 Windows 环境执行：系统 `bash.exe`/WSL 返回 `E_ACCESSDENIED`，不是项目脚本自身失败；因此该项不能记为通过。Black 命令在本环境单文件检查也未在 30 秒内返回，未据此宣称全量格式检查通过。

### 2.2 关键独立复现

用临时 fake qB 客户端复现以下场景：5 个 hash，`QB_TRACKER_MAX_TORRENTS_PER_RUN=2`，`SYNC_DB_COMMIT_BATCH_SIZE=1000`。实际远程调用只有 `h000000`、`h000001`，但 `qb_sync_trackers_only_async()` 返回游标 `{"last_hash":"h000004"}`，`cycle_progress` 为 `5/5`。这证明游标可越过尚未拉取、更未 durable commit 的记录。

## 3. W0-W4-2 门禁矩阵

### W0：立即止血与基线固化 — 部分完成

已确认：SQLite 单 Worker 启动防护、默认任务错峰配置、assessment 文档中的临时停用建议、可重复基准脚本和真实大档基准均存在。

未确认：计划要求的专用生产 Runbook（前置检查、暂停 Tracker/info、手动同步禁用、Worker/新鲜度检查、取消和恢复 cron）及一次不改数据的暂停/恢复演练证据。现有 [`sync-contention-runbook.md`](sync-contention-runbook.md) 只描述 W4-3 基准命令和 SLO。

另外，仓库内已提交的大档 JSON 使用 10 轮探针；计划/runbook 的发布门命令要求 30 轮。本次 30 轮结果只保存在临时输出目录，尚未形成可归档的发布基线报告。

### W1：SQLite 写事务短事务化 — 基本通过

`sync_db_write.bulk_upsert_with_retry()` 已按批次独立 commit、只重试当前锁冲突批、保留部分进度并在批间让出事件循环；Tracker 关键词状态服务支持零变化零 DML；qB removed 标记走统一批量写入器。相关单测、文件型争用测试和大档基准均通过。

残留风险位于旧 full/兼容路径的直接 commit 和客户端构造，归入 W2 的 P0 闭环，而不是将 W1 的治理结果扩大解释为所有写者已统一。

### W2：统一同步路径与请求响应性 — 未完全通过（P0）

通过项：`SyncCoordinator`、heavy-sync 准入、按下载器顺序执行、interactive 容量保留、SQLite 单 Worker guard，以及已登记垂直切片的 async 下载器调用架构测试。

发现的两个 P0 缺口：

1. `SyncCoordinator._get_cached_client()` 返回 `None` 时，info-only 仍会在 [`torrents_async.py`](../../app/api/endpoints/torrents_async.py) 的 `qb_add_torrents_info_only_async`（约 2986 行）和 `tr_add_torrents_info_only_async`（约 3349 行）中构造 `qbClient`/`trClient`；full 路径在约 1213、1727 行无条件构造客户端。该路径违反 [`downloader-connection.md`](../constraints/downloader-connection.md) 的“只能使用 `app.state.store`”约束，也会重新引入重复连接和远端争用。
2. [`torrent_sync.py`](../../app/api/endpoints/torrent_sync.py) 的 `sync_single_downloader()` 是 `async def`，在约 1263 行直接执行同步 `db.query(...).first()`。SQLite 写锁存在时，这个查询会在事件循环线程内等待 busy timeout，HTTP 请求可能在后台任务尚未启动前就卡住。现有 AST 测试规则没有覆盖 `torrents_async.py` 和 `torrent_sync.py`，所以全量测试不会发现该缺口。

修复验收：canonical info/full 必须强制传入缓存客户端；缺失缓存应明确返回 offline/failed，不得 fallback 自建；full 函数签名接收 `client`；`sync-single` 的下载器查询改为 AsyncSession 或明确线程边界；架构测试扩展到两个同步文件。

### W3：有界、可续跑和可解释同步 — 部分完成

通过项：qB 有界 producer/worker、单轮数量/时间预算、稳定排序、checkpoint 表及乐观锁、W3-3 分页读取/缓冲上限、W3-4 六态 outcome/freshness。相关测试通过。

必须修复的 P1-01/P1-03 缺口：`qb_sync_trackers_only_async()` 在 enrich 只处理预算前缀后，仍遍历完整 `existing_torrents`，并把没有 tracker rows 的未处理对象写入 `batch_last_hash`。当最后一次 flush 未达到批大小时，最终 durable cursor 会跳到未处理 hash（已在本次验证独立复现），重启后会永久跳过这些 hash。游标只能从“成功写入批次中最后一个实际处理 hash”计算；应增加批大小大于预算的回归测试。

另一个 P1-03 注意点：`SyncCoordinator._sync_one_downloader()` 对 info/full 返回 `meta=None`，info-only 的数量/时间预算结束后没有 per-record cursor；checkpoint 只能记录 outcome/时间，下一轮仍可能从远端列表开头重复处理。若产品要求“部分运行重启后续跑”覆盖 info，应增加 info 游标或明确把 info 预算语义改为可重做且有去重成本预算。

W3-3 的分页只限制一次 ORM 查询峰值，`existing_torrents_cache` 仍保存全部 hash→dict，远端列表也整体驻留内存；这属于 P1-02 的“缓解而非硬上限”，需要用生产 RSS/CPU 数据决定是否继续拆流水线。

### W4-1：阶段级观测 — 部分完成（P2-05 未闭环）

稳定事件名、字段白名单、脱敏、run_id ContextVar、event-loop lag、下载器 lane 排队、批 commit/重试、WAL bytes/growth 均已接线，相关测试通过。

但 [`snapshot_wal_stats()`](../../app/services/sync_observability.py) 明确返回 `busy_count=None`、`checkpoint_busy=None`；lifecycle 的 WAL 事件也只转发这两个空值，测试还明确断言它们为 `None`。计划 W4-1 的最小 SQLite 字段要求这两个指标可观测，因此 P2-05 仍只能算部分完成。后续应以受控、只读的 PASSIVE checkpoint 观测或等价 SQLite 连接指标补齐，不能以频繁 TRUNCATE checkpoint 代替。

### W4-2：健康检查 — 代码通过，部署验证待迁移

`/health/live` 不访问 DB/下载器；`/health/ready` 对 `SELECT 1` 有严格超时，并检查 Worker 和 lag；`/api/v1/health/sync` 受认证，返回 outcome/freshness/active phase/checkpoint age/下载器离线告警；Dockerfile 和 Compose 已使用 `/health/ready`。9 个 health 专项测试和全量回归通过。

业务健康查询本身没有与 readiness 同等级的数据库超时边界，锁极端情况下可能等待到连接层超时；建议作为硬化项补充。当前本地 `app.db` 尚未到 `f5e6d7c8b9a0`，所以真实实例验证必须在发布启动自动迁移或受控 `alembic upgrade head` 后复测。

## 4. P0/P1/P2 状态回填

| 风险 | 本次验证状态 | 说明 |
|---|---|---|
| P0-01 手动同步旁路 | 部分修复 | 已接 Coordinator，但 sync-single 仍有事件循环内同步 DB 查询，full 仍可自建客户端 |
| P0-02 Tracker 全表重写 | 基本修复 | 增量状态服务和零变化零 DML 测试通过 |
| P0-03 info 单大事务 | 基本修复 | 通用写入器真实分批 commit；旧 full 备份/兼容写者仍需路径收口 |
| P0-04 async 同步下载器调用 | 部分修复 | 已登记垂直切片通过；同步专用文件仍有 4 个直接构造点，架构测试未覆盖 |
| P0-05 后台占满交互容量 | 基本修复 | background/total lane 及交互保留槽测试通过 |
| P0-06 SQLite 锁旁路/多 Worker | 部分修复 | 单 Worker guard 和主要写者已治理；客户端 fallback、旧 full/同步端点仍是旁路风险 |
| P1-01 qB Tracker 任务爆炸/续跑 | 部分修复 | 有界队列有效，但游标可越过未处理 hash |
| P1-02 info 并发/内存峰值 | 部分修复 | 默认串行、分页、缓冲上限有效；全量 cache 仍驻留内存 |
| P1-03 重启后重复全量 | 部分修复 | tracker cursor 有框架但有 bug；info-only 没有记录级 cursor |
| P1-04 批大小/重试/预算不统一 | 部分修复 | 通用写者统一；qB tracker/旧 full 仍有不同写入边界和 fallback |
| P1-05 outcome/freshness 语义 | 通过 | 六态、skip_reason、freshness 和任务页测试通过 |
| P1-06 阶段观测 | 基本通过 | 结构化事件/run_id/lag/lane/commit 已有；SQLite busy/checkpoint 字段缺值 |
| P1-07 真实文件型争用测试 | 通过（当前机器） | 22k/30k、30 轮、600 探针 SLO 通过；RSS 未采集（psutil 不可用） |
| P2-03 readiness/同步健康 | 代码通过 | 真实数据库需先迁移到 head |
| P2-05 WAL/checkpoint/写放大量化 | 部分完成 | WAL bytes/growth 有；busy/checkpoint 运行时为空 |
| P2-01/P2-02/P2-04/P2-06 | 不在本次范围/未关闭 | 需按 W5 计划单独决策和文档收口 |

## 5. 修复优先级与再次验收

1. **P0：连接生命周期和 sync-single DB 边界**。移除 canonical info/full fallback，自建客户端只保留缓存初始化层；扩展 AST 架构规则并增加缺缓存失败用例。
2. **P1：qB Tracker durable cursor**。按实际 enrich/写入前缀构造批次，游标只在对应批 commit 成功后推进；加入“batch size > 单轮预算、未处理对象无 rows”的回归。
3. **P1：info-only 续跑语义**。增加 info cursor/分页 checkpoint，或在计划中明确 info partial 的可重复成本与上限，并在健康端点区分“重复扫描”和“可续跑”。
4. **P2：W4-1 SQLite 指标**。补齐 `busy_count`、`checkpoint_busy` 的只读观测，保留 WAL growth；为阈值告警增加真实字段断言。
5. **W0/G4：运维闭环**。新增生产止血 Runbook，完成一次暂停/错峰/恢复演练，归档同口径 30 轮基线 JSON/Markdown；在迁移到 `f5e6d7c8b9a0` 后重新调用 `/health/ready` 和 `/api/v1/health/sync`。

在以上项目完成前，本报告建议把 W2、W3、W4-1 相关 `done` 视为“实现已提交但发布门待复核”，不要以当前健康接口或大档 SLO 单独宣称数据库阻塞问题已全部解决。

## 6. 2026-08-11 修复后复核

已按本报告第 5 节实施：

- P0：`torrents_async.py` 与 `torrent_sync.py` 已移除 qB/TR 业务路径的直接客户端构造；
  canonical info/full、legacy adapter 和 `sync-single` 均复用 `app.state.store` 客户端，
  缺失缓存时失败；`sync-single` 改用 `AsyncSession` 异步查询。
- P1：qB Tracker 游标改为只消费 enrich 成功的连续前缀，抽取/批提交失败停在最后
  durable hash；新增“远程失败不跨游标”和批大小大于预算回归。qB/TR info 增加稳定 hash
  cursor、durable progress callback，并在有 cursor 时强制完整快照续跑。
- P2：WAL 快照用 `wal_checkpoint(PASSIVE)` 提供 `busy_count`、`checkpoint_busy`；
  `/api/v1/health/sync` 增加 `HEALTH_SYNC_DB_TIMEOUT_SECONDS` 有界查询超时与 503 reason code。
- W0：新增 [`sync-stopgap-runbook.md`](sync-stopgap-runbook.md)，包含暂停/恢复、错峰、升级
  门槛和演练记录模板。

修复后定向验证：

```text
83 passed（info cursor / Tracker cursor / WAL / architecture / health）
70 passed、5 skipped（coordinator / checkpoint / governance / torrent metadata / legacy review）
18 passed、1 skipped（memory bound + file SQLite contention）
```

`python -m ruff check` 对本次修改文件通过，`git diff --check` 无 whitespace 错误。Black
全文件检查仍受仓库既有格式债与 Windows 环境超时影响，未进行自动重排。生产数据库仍保持
未迁移状态，W0 暂停/恢复演练及 30 轮基线归档需要在受控部署窗口执行；因此报告中的部署
发布门不能仅凭本地测试视为关闭。

追加验证：后端全量 `python -m pytest -q` 为 `3142 passed, 7 skipped`（3149 collected）。
修复后真实文件型 SQLite 大档重新执行 30 轮/600 探针，0 超时、最终 BUSY=0、SLO 4/4 PASS；
JSON 仅写入临时目录 `C:\Users\huangzj\AppData\Local\Temp\btdeck-sync-fix-20260811`。
