# backend/tasks — 定时任务与调度

> 基于 APScheduler `AsyncIOScheduler` 的定时任务系统 + 后台执行器 + 任务验证/资源准入控制。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/tasks/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### tasks/ 根（14 个文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 批量类路径验证 class-batch-validator | `batch_class_validator.py` | 批量类路径验证（REQ-003，DB 内部类完整性） |
| 类路径修复 class-fixer | `class_path_fixer.py` | 修复 DB 中无效 Python 内部类路径（REQ-003） |
| 类路径验证 class-validator | `class_path_validator.py` | 类路径验证工具 + `validate_class_paths_batch` |
| 清理执行器 cleanup | `cleanup_executor.py` | 后台执行器 `CleanupTaskExecutor`：自动清理执行器（回收站(L3)+待删除标签(L4)） |
| 定时任务同步 CRUD cron-crud | `cron_crud.py` | `CronTaskCRUD`/`TaskLogsCRUD`：定时任务同步 CRUD（`DatabaseResult`） |
| 定时任务异步 CRUD cron-crud-async | `cron_crud_async.py` | 定时任务异步 CRUD |
| 调度核心 cron-executor | `cron_executor.py` | 🔵 APScheduler 调度核心 `CronTaskExecutor`：`AsyncIOScheduler` + `add_job`（L60/142/791） |
| 定时任务表 cron-model | `cron_models.py` | ORM `CronTask`：定时任务表 |
| Python 沙箱执行 python-executor | `enhanced_python_executor.py` | 增强沙箱化 Python 代码执行器（REQ-002，智能异步检测） |
| 任务日志 logger | `logger.py` | 任务执行日志写入与统计 |
| 任务日志表 task-log-model | `models.py` | ORM `TaskLogs`：任务日志表 |
| 资源准入 resource-guard | `resource_guard.py` | 同步任务资源准入控制器 `TaskAdmissionController`（背压，防 DB/下载器/线程池抢占） |
| 任务 profile task-profile | `task_profiles.py` | 重型任务资源 profile 注册表 `TaskProfile` |
| 任务验证 validation | `validation_service.py` | 任务验证（脚本语法/Cron 表达式/Python 类三套校验） |

### scheduler/ — APScheduler job 实现（14 个文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 审计日志导出 audit-export | `audit_log_exporter.py` | 审计日志归档到文件 |
| 看板统计 dashboard-stats | `dashboard_stats.py` | 看板统计聚合任务 |
| 下载器缓存同步 downloader-cache | `downloader_cache_sync.py` | 下载器实例缓存同步 |
| 路径扫描 path-scan | `downloader_path_scan.py` | 扫描 torrent_info 路径写入 downloader_path_maintenance |
| 孤儿通知重试 orphan-notify-retry | `orphan_notification_retry_task.py` | 补发未成功的幂等通知（隔离区彻底删除完成通知） |
| 隔离区清理 orphan-purge | `orphan_quarantine_purge_task.py` | 每日清理超期孤儿隔离区 |
| 孤儿全量扫描 orphan-scan | `orphan_scan_task.py` | 每周日凌晨 2 点只持久化提交后台 scan_id/task_id；扫描成功后由调度器串接自动清理，超量门禁会拒绝清理 |
| 标签同步 tag-sync | `tag_sync.py` | 定期从下载器同步标签到 DB |
| 种子同步废弃 torrent-sync-old | `torrent_sync.py` | ⚠ **已废弃**：拆分为下方两个任务 |
| tracker 状态判断 torrent-tracker-judge | `torrent_tracker_status_judge.py` | 遍历种子检查 tracker 状态；`evaluate_tracker_error_state()` L69 复用共享策略联合下载器状态码与关键词，Working 且 announce/scrape 消息为空时明确正常，有消息仍按关键词分类；独立 Cron 为 `20,50 * * * *`，在 Tracker 同步后 10 分钟运行 |
| 候选池填充 candidate-pool | `tracker_candidate_pool.py` | 从 tracker_message_log 读未处理消息填候选池 |
| tracker 消息入库 tracker-logger | `tracker_message_logger.py` | 定期扫描所有 tracker 返回消息入库 |
| reannounce 任务 reannounce | `tracker_reannounce_task.py` | 按站点间隔定时对种子执行 tracker 汇报 |
| 状态判断 status-judge | `tracker_status_judge.py` | 扫描未处理消息做状态判断 |

### scheduler/torrent_sync/ — 同步子模块（4 个文件）

`torrent_sync.py` 废弃后拆分而来。

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 同步基础类 sync-base | `base.py` | `BaseSyncTask`：种子同步公共基础类 |
| 基础信息同步 info-sync | `torrent_info_sync_task.py` | 高频同步种子基础信息（名称/大小/进度/状态） |
| tracker 同步 tracker-sync | `tracker_sync_task.py` | 高频同步 tracker 状态（announce/scrape/错误） |

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
