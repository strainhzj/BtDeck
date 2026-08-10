# SQLite 争用基准与回归门 Runbook（W4-3）

> 对应计划：`PLANS/sync-database-blocking-remediation.md` W4-3（P1-07）
>
> 基准脚本：`backend/scripts/sync_contention_benchmark.py`
> 回归测试：`backend/tests/integration/test_sqlite_sync_contention.py`
> 输出目录：`backend/benchmark_results/sync_contention_<timestamp>.json`
>
> 更新：2026-08-09

## 1. 基准定位

`sync_contention_benchmark.py` 与既有 `sync_resource_benchmark.py` 分工互补：

| 维度 | sync_resource_benchmark.py（阶段 3 产物） | sync_contention_benchmark.py（本脚本） |
| --- | --- | --- |
| 数据库 | 内存 SQLite（StaticPool 单连接） | 真实临时文件 .db（WAL + NullPool 多连接） |
| 数据量 | 无生产近似量 | 三档：小 2k/3k、中 10k/15k、大 22k/30k |
| 后台写入 | 无真实 DML（只模拟下载器慢调用） | 真实 DML：`bulk_upsert_with_retry` / `sync_tracker_status_from_keywords` / 批量 UPDATE dr=1 |
| 故障注入 | 无 | `busy`（持锁 300ms×4）/ `slow-downloader`（2s 延迟 1s 超时）/ `cancel`（中途取消） |
| 用途 | 治理层（admission/lane）响应矩阵 | 文件型 SQLite 争用 + WAL/fsync/锁等待 + 发布门 SLO |

本脚本**只操作临时目录与合成数据，绝不触碰生产 `config/app.db`**；JSON 输出不含任何敏感信息。

## 2. 基准命令

```bash
cd backend

# 本机校准（小档，单次 < 60s）
python scripts/sync_contention_benchmark.py --size small --probe-iterations 10

# 常规档（中档）
python scripts/sync_contention_benchmark.py --size medium --probe-iterations 30

# 发布门档（大档，对应生产 22k torrents / 30k trackers）
python scripts/sync_contention_benchmark.py --size large --probe-iterations 30

# 发布门 SLO 断言（不满足 exit 1）
python scripts/sync_contention_benchmark.py --size large --probe-iterations 30 --assert-slo
```

可选参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--scenarios` | `0,A,B,C` | `0`=无同步基线、`A`=info upsert、`B`=tracker 状态增量写、`C`=qB removed 标记 |
| `--probe-iterations` | 30 | 每场景请求探针轮数（每轮 5 类探针） |
| `--downloader-delay-ms` | 0 | fake 下载器可控延迟（ms），经 `call_downloader_api` 真实调用（executor + semaphore + wait_for），0 关闭 |
| `--fault` | `none` | `busy` / `slow-downloader` / `cancel`（见第 4 节） |
| `--assert-slo` | 关 | 启用发布门 SLO（大档），不满足 exit 1 并输出失败诊断 |
| `--out-dir` | `backend/benchmark_results` | JSON 输出目录（自动创建） |

## 3. 三档数据与场景说明

| 档位 | torrents | trackers | 用途 |
| --- | ---: | ---: | --- |
| small | 2,000 | 3,000 | 本机校准 / CI 冒烟（单次 < 60s） |
| medium | 10,000 | 15,000 | 常规回归 |
| large | 22,000 | 30,000 | 发布门（生产近似量，来自本地库只读核对） |

数据全部为合成数据（`bench-t-*` / `bench-r-*` / `tracker-bench-*.example` 域名），
tracker 消息按 host 分组覆盖 failed/unknown/success 三态，使关键词状态判定
同时命中 `error` / `unknown` / `normal` 三种结果。种子表带 `dr` / `downloader_id`
索引，模拟生产索引更新放大。

场景（后台真实 DML 与请求探针并发）：

- **0_baseline**：仅探针，无后台 DML（验收矩阵"无同步基线"行）。
- **A_info_upsert**：40% 种子更新 + 10% 新增（下限 2000 行），真实调用
  `bulk_upsert_with_retry`（batch_size=200，`db_write_scope` + 每批独立 commit）。
- **B_tracker_status**：真实调用 `sync_tracker_status_from_keywords` 两遍——
  第 1 遍全量判定写回（大档 150 批），第 2 遍验证零变化零 DML（W1-2 语义）。
- **C_qb_removed_mark**：最后 30% 种子批量 `UPDATE dr=1`，逐批 commit + 有界重试
  （等价 qB removed 标记路径；实现为脚本内逐批 UPDATE 循环，报告中说明：
   未调用生产端点层，但 DML 形状一致）。

请求探针（每探针独立连接，等价交互 API 操作）：只读 `count` / 分页 /
任务状态查询 + 单条 `INSERT` / `UPDATE dr=1`；单探针预算 15s，超限计为探针超时。

## 4. 故障注入

| 故障 | 注入方式 | 预期（断言） |
| --- | --- | --- |
| `busy` | 后台持写锁不提交 300ms × 4 次（间隔 50ms），同时后台 DML 连接 busy_timeout 收紧到 100ms 制造真实 SQLITE_BUSY 错误码 | 观察到 BUSY > 0；重试有界（单批 ≤ 6 次）；最终失败 = 0；探针写 P95 可解释升高（排队等待） |
| `slow-downloader` | 探针中 fake 下载器调用延迟 2s、`wait_for` 超时 1s（每轮独立 downloader_id 避免 semaphore 排队积压） | 下载器调用按 `asyncio.TimeoutError` 返回；探针 DB 操作零超时；事件循环 max lag < 1s；事后检查探针正常 |
| `cancel` | 场景 A 后台 DML 提交满 3 批（600 行）后取消协程任务 | 已提交批次保留（行数 = 整批倍数、< 总量、取消后不再增长）→ 与 W2-1 `SyncRequest.is_cancelled` "已提交批次保留、结果 partial" 语义一致 |

故障断言全部写入 JSON 的 `fault.assertions`；任一 FAIL 不影响其他场景数据，
但应视为"雪崩"信号。`--assert-slo` 仅在 `--fault none` 时评估（故障运行是诊断模式）。

实现注意：

- 故障 busy 下统一写入器退避参数在**进程内**临时收紧（`SYNC_DB_LOCK_RETRY_COUNT`
  3→6、`SYNC_DB_RETRY_MAX_BACKOFF_SECONDS` 2→3s，结束即恢复）：300ms 持锁 +
  100ms busy_timeout 组合下，生产默认 3 次尝试可能耗尽导致 `ChunkedWriteError`；
  基准要验证的是"有界重试 + 最终一致"，而非"耗尽重试"。生产参数下的吸收行为
  由集成测试（`tests/integration/test_sqlite_sync_contention.py`）覆盖。
- 场景内持有"WAL 见证连接"，防止最后一个连接关闭时 SQLite 自动 checkpoint
  截断 WAL，使 `wal.growth_bytes` 真实反映场景写入量。

## 5. 验收矩阵（大档）

| 场景 | 只读 P95 | 写 P95 | 超时率 | SQLITE_BUSY | 事件循环 lag P99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 无同步基线（0_baseline） | < 500ms | < 1s | 0 | 0 | < 50ms |
| info 同步（A） | < 1s | < 2s | < 0.1% | 最终失败 0 | < 100ms |
| Tracker 同步（B） | < 1s | < 2s | < 0.1% | 最终失败 0 | < 100ms |
| info + 交互下载器调用（A + `--downloader-delay-ms`） | < 1s | < 2s | < 0.1% | 最终失败 0 | < 100ms |
| 故障注入 | 可解释降级 | 可解释降级 | 无雪崩 | 有界重试 | 单次峰值可关联 |

`--assert-slo` 机器断言四要素（大档）：只读 P95 < 1s、写 P95 < 2s、
探针超时率 < 0.1%、最终 SQLITE_BUSY 失败 = 0；不满足 exit 1 并输出失败诊断。
lag/RSS/WAL 作为观测指标随 JSON 输出，不进入硬门禁（阈值见 W4-1 观测告警）。

## 6. 前后版本 JSON 对比

每次运行生成 `backend/benchmark_results/sync_contention_<ts>.json`：

```json
{
  "meta": { "python": "...", "sqlite_version": "...", "size": "large", "fault": "none", ... },
  "seed": { "gen_s": 3.2, ... },
  "scenarios": [
    { "name": "A", "bg": { "commit_ms_stats": {...}, "retries": 0, ... },
      "probes": { "read_count": {"samples_ms": [...], "p95": ...}, ... },
      "wal": { "growth_bytes": ... }, "loop_lag_ms": {...}, "busy_count": 0, ... }
  ],
  "fault": { "applied": false, ... },
  "slo": { "passed": true, "checks": [...] }
}
```

对比步骤（发布/变更前基线 vs 变更后）：

1. 同一台机器、同一档位（建议 large + `--assert-slo`）各跑一次。
2. 比较各场景 `probes.*.p95/p99`、`bg.commit_ms_stats.p95`、`wal.growth_bytes`、
   `loop_lag_ms.p99`、`busy_count`、`fault.assertions`。
3. 关注相对变化而非绝对值（本机磁盘/杀软/节能策略都会影响 commit_ms）。
4. 阈值判定：读 P95 / 写 P95 退化 > 30%、busy_count 从 0 转正、
   任何 fault.assertion 由 PASS 转 FAIL，均应阻断发布并排查。

## 7. CI / 发布门接入建议

- **常规 CI**：`pytest tests/integration/test_sqlite_sync_contention.py -q`
  （最小争用回归，约 10s；22k 性能用例默认 skip）。
- **Nightly**：`python scripts/sync_contention_benchmark.py --size medium --probe-iterations 30`
- **发布门（发布前手动/流水线）**：
  `python scripts/sync_contention_benchmark.py --size large --probe-iterations 30 --assert-slo`
  退出码 0 才放行；同时将 JSON 归档到发布产物，留作回滚对比。
- 故障注入可作每周诊断：`--fault busy / slow-downloader / cancel`（小档即可）。
- 注意：Windows 下 `python` 不在 PATH 时用完整解释器路径，例如
  `C:\software\python\python.exe scripts\sync_contention_benchmark.py ...`；
  CI 建议固定 Python 3.11+ 与 SQLite ≥ 3.35（WAL 并发语义）。

## 8. 环境校准系数

发布门绝对阈值基于"用户可感知 SLO"设定（读 1s / 写 2s / 超时率 0.1%）。
若测试主机明显弱于生产（如无 SSD、杀软实时扫描、虚拟机），允许先建立校准系数：

- 校准系数 = 生产基准读数 / 本机基线读数（以 0_baseline 场景读/写 P95 为基准）。
- 校准仅用于本机持续回归的趋势判定；**生产发布门仍按第 5 节绝对阈值**。
- 任何校准调整必须在 JSON 或对比报告中注明（meta 中可附注），不静默放宽。

本机首次实测（2026-08-09，Windows 10，Python 3.12.4 / SQLite 3.45.3，小档校准）：
无故障下各场景读/写 P95 约 15-30ms，`--fault busy` 下写 P95 升至约 320ms
（300ms 持锁排队，可解释降级），远低于发布门阈值；如大档实测超出阈值，
先排查磁盘/杀软等环境因素再调整参数，不得直接放宽断言。

## 9. 已知限制

- 场景 B 调用真实 `sync_tracker_status_from_keywords`，但其读写作用于基准专用
  最小表（表名/列名与生产 `tracker_info` / `tracker_keyword_config` 对齐），
  未建生产全部 8+16 个索引——索引放大效应弱于生产，属保守方向（低估争用）。
- 场景 C 为脚本内等价逐批 UPDATE 循环（qB removed 生产端点未直接调用）。
- `slow-downloader` 故障下，`call_downloader_api` 超时路径会触发生产代码
  `_attach_done_stats._on_done` 对 cancelled future 调 `fut.exception()` 的
  `CancelledError` 噪音（`except Exception` 捕获不到 BaseException）；
  基准与对应集成测试在事件循环异常处理器中过滤该固定模式。这是既有生产代码
  的观测缺口，建议在 W4-1 观测收口时修复（`_on_done` 先判 `fut.cancelled()`）。
- RSS 依赖 psutil，未安装时自动跳过（JSON 中为 null）。
- 进程内临时收紧写入器退避参数（故障 busy）仅在基准进程内生效，结束即恢复。
