# backend/tasks — 定时任务与调度

> 基于 APScheduler `AsyncIOScheduler` 的定时任务系统 + 后台执行器 + 任务验证/资源准入控制。

## tasks/ 根（14 个文件）

| 文件 | 行数 | 顶层符号 | 类型 | 一句话职责 |
|------|------|---------|------|-----------|
| `batch_class_validator.py` | 302 | 2 | 工具脚本 | 批量类路径验证（REQ-003，DB 内部类完整性） |
| `class_path_fixer.py` | 403 | 2 | 工具脚本 | 修复 DB 中无效 Python 内部类路径（REQ-003） |
| `class_path_validator.py` | 477 | 4 | 工具脚本 | 类路径验证工具 + `validate_class_paths_batch` |
| `cleanup_executor.py` | 478 | 1 (`CleanupTaskExecutor`) | 后台执行器 | 自动清理执行器：回收站(L3)+待删除标签(L4) |
| `cron_crud.py` | 429 | 2 (`CronTaskCRUD`/`TaskLogsCRUD`) | 数据访问 | 定时任务同步 CRUD（`DatabaseResult`） |
| `cron_crud_async.py` | 218 | 2 | 数据访问 | 定时任务异步 CRUD |
| `cron_executor.py` | 825 | 2 (`CronTaskExecutor`) | 🔵 调度核心 | **APScheduler 调度核心**：`AsyncIOScheduler` + `add_job`（L60/142/791） |
| `cron_models.py` | 76 | 1 (`CronTask`) | ORM | `CronTask` 定时任务表 |
| `enhanced_python_executor.py` | 593 | 5 | 执行器 | 增强沙箱化 Python 代码执行器（REQ-002，智能异步检测） |
| `logger.py` | 161 | 4 | 日志 | 任务执行日志写入与统计 |
| `models.py` | 69 | 1 (`TaskLogs`) | ORM | `TaskLogs` 任务日志表 |
| `resource_guard.py` | 311 | 6 (`TaskAdmissionController`) | 准入控制 | 同步任务资源准入控制器（背压，防 DB/下载器/线程池抢占） |
| `task_profiles.py` | 122 | 4 (`TaskProfile`) | 配置 | 重型任务资源 profile 注册表 |
| `validation_service.py` | 593 | 9 | 验证 | 任务验证（脚本语法/Cron 表达式/Python 类三套校验） |

## tasks/scheduler/ — APScheduler job 实现（14 个文件）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `audit_log_exporter.py` | 105 | 2 | 审计日志归档到文件 |
| `dashboard_stats.py` | 90 | 1 | 看板统计聚合任务 |
| `downloader_cache_sync.py` | 330 | 1 | 下载器实例缓存同步 |
| `downloader_path_scan.py` | 840 | 1 | 扫描 torrent_info 路径写入 downloader_path_maintenance |
| `orphan_notification_retry_task.py` | 56 | 1 | 补发未成功的幂等通知 |
| `orphan_quarantine_purge_task.py` | 25 | 1 | 每日清理超期孤儿隔离区 |
| `orphan_scan_task.py` | 121 | 1 | 每周日凌晨 2 点全量扫描孤儿文件 |
| `tag_sync.py` | 244 | 4 | 定期从下载器同步标签到 DB |
| `torrent_sync.py` | 202 | 1 | ⚠ **已废弃**：拆分为下方两个任务 |
| `torrent_tracker_status_judge.py` | 498 | 1 | 遍历种子检查 tracker 状态 |
| `tracker_candidate_pool.py` | 473 | 1 | 从 tracker_message_log 读未处理消息填候选池 |
| `tracker_message_logger.py` | 899 | 1 | 定期扫描所有 tracker 返回消息入库 |
| `tracker_reannounce_task.py` | 273 | 5 | 按站点间隔定时对种子执行 tracker 汇报 |
| `tracker_status_judge.py` | 422 | 1 | 扫描未处理消息做状态判断 |

## tasks/scheduler/torrent_sync/ — 同步子模块（4 个文件）

`torrent_sync.py` 废弃后拆分而来。

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `__init__.py` | 11 | 0 | 包 docstring |
| `base.py` | 238 | 1 (`BaseSyncTask`) | 种子同步公共基础类 |
| `torrent_info_sync_task.py` | 204 | 1 | 高频同步种子基础信息（名称/大小/进度/状态） |
| `tracker_sync_task.py` | 214 | 1 | 高频同步 tracker 状态（announce/scrape/错误） |

---

## 调度链路

```
app/startup/lifecycle.py:lifespan
  └─→ await cron_executor.start()          # 启动 AsyncIOScheduler
        └─→ AsyncIOScheduler.add_job(...)   # cron_executor.py L60/L142/L791
              ├─→ scheduler/*_task.py        # 各 job 实现
              ├─→ scheduler/torrent_sync/*   # 拆分后的同步子任务
              └─→ cleanup_executor.py        # 后台清理执行器（非 APScheduler）
```

## 任务分类

- **APScheduler 注册入口**（唯一）：`tasks/cron_executor.py`
- **APScheduler job 实现**（被调度）：`scheduler/` 下 14 个 .py（含 1 个已废弃 `torrent_sync.py`）+ `scheduler/torrent_sync/` 子包 4 个
- **后台执行器**（非 APScheduler）：`cleanup_executor.py`、`enhanced_python_executor.py`
- **REQ-002/003 工具脚本**（一次性）：`batch_class_validator.py`、`class_path_fixer.py`、`class_path_validator.py`、`validation_service.py`
- **资源治理**：`resource_guard.py`（准入控制器）、`task_profiles.py`（任务 profile）、`sync_db_write.py`（在 services 分支）

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`cron_executor.py` 825 行调度核心）
