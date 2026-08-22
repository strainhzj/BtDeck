# 同步任务 DB 写入治理（sync-db-write-governance）

> 适用范围：`backend/app/tasks/scheduler/` 重型同步任务与 `torrents_async.py` 内的同步函数
> 已接入治理的任务文件：
> - `app/api/endpoints/torrents_async.py`（info_only / tracker_only 同步函数，经 `bulk_upsert_with_retry`）
> - `app/tasks/scheduler/torrent_tracker_status_judge.py`（种子 Tracker 状态判断：分批 + `db_write_scope` + `to_thread`）
> - `app/tasks/scheduler/tracker_message_logger.py`（Tracker 消息记录：4 处 commit 包 `db_write_scope`）
> - `app/tasks/scheduler/tracker_reannounce_task.py`（Tracker 汇报：读段 `to_thread` + 写段 `to_thread` + `db_write_scope`）
> - `app/tasks/scheduler/downloader_path_scan.py`（路径扫描：6 处 commit 包 `db_write_scope` + 同步 HTTP `to_thread` + 远程调用移出写 session）
> 关联计划：`PLANS/sync-resource-governance.md` 阶段 1（DB 写入治理）/ 阶段 2.6（to_thread 止血 + db_write_scope 收尾）
> 强制级别：改造同步函数 commit 点时**必须**遵循本文档；新建同步函数**必须**遵循本文档

---

## 一、目标

防止后台同步任务通过高频小事务、逐条 commit、逐条日志落盘击垮 SQLite 写锁与硬盘寿命。本指南与 `TaskAdmissionController` 的 `heavy_sync` 全局互斥配合，共同保证同步期间请求侧接口的响应能力。

## 二、强制规范

### 2.1 变更检测：状态无变化不写库

同步函数在写入前必须对比新旧状态，**仅在字段实际变化时**才进入写路径。

```python
# ✅ 正确：先比对，再决定是否写
new_state = {"name": ..., "progress": ..., "status": ...}
if _has_changes(existing_row, new_state):
    async with admission_controller.db_write_scope():
        _apply_changes(existing_row, new_state)
        await db.commit()
```

```python
# ❌ 错误：无条件全量更新（逐条 commit 的主要来源）
for torrent in remote_torrents:
    await _upsert_torrent(db, torrent)  # 每条都写，即使无变化
    await db.commit()
```

### 2.2 批量 upsert：禁止逐条 commit

大批量同步必须使用批量 upsert（SQLAlchemy `bulk_insert_mappings` / `bulk_update_mappings` 或 SQLite `INSERT ... ON CONFLICT`），并按 `settings.SYNC_DB_COMMIT_BATCH_SIZE`（默认 200）分批提交。

```python
# ✅ 正确：内存聚合 + 批量提交
buffer = []
for idx, change in enumerate(changes):
    buffer.append(change)
    if len(buffer) >= settings.SYNC_DB_COMMIT_BATCH_SIZE:
        async with admission_controller.db_write_scope():
            await _bulk_upsert(db, buffer)
            await db.commit()
        buffer.clear()
if buffer:  # flush 残余
    async with admission_controller.db_write_scope():
        await _bulk_upsert(db, buffer)
        await db.commit()
```

### 2.3 db_writer 临界区：只包裹 commit 阶段

`db_write_scope()` 的并发为 1（串行化写者）。**只包裹实际写入 + commit**，不要把远程下载器调用放进临界区，否则下载器 IO 等待会放大写锁占用时间。

```python
# ✅ 正确：远程调用在临界区外，commit 在临界区内
remote_data = await call_downloader_api(...)  # 不持有 db_writer
parsed = _parse_changes(existing, remote_data)  # 内存计算
if parsed:
    async with admission_controller.db_write_scope():
        await _apply_parsed(db, parsed)
        await db.commit()
```

```python
# ❌ 错误：远程调用包在 db_write_scope 内，放大写锁占用
async with admission_controller.db_write_scope():
    remote_data = await call_downloader_api(...)  # 阻塞其它写者
    await _apply(db, remote_data)
    await db.commit()
```

### 2.4 日志/进度类数据节流

高频日志（如逐 tracker 状态、逐 torrent 事件）不得立即落盘，必须按 `settings.SYNC_DISK_FLUSH_INTERVAL_SECONDS`（默认 5s）合并窗口聚合后输出。

```python
# 进度类数据用内存累加，按窗口 flush
if now - last_flush >= settings.SYNC_DISK_FLUSH_INTERVAL_SECONDS:
    logger.info("[sync] progress: %s", aggregated_progress)
    last_flush = now
```

`logger.info/warning` 也属"落盘"：单轮同步内同类信息合并为一条结构化日志，避免逐条 tracker/torrent 输出。

## 三、接入检查清单

改造或新建同步函数时核对：

- [ ] 写入前有变更检测（diff / hash 比对），无变化走 no-op 分支。
- [ ] 批量 upsert，未出现 `for ... await db.commit()` 逐条提交。
- [ ] `db_write_scope()` 只包裹 commit 阶段，不包含远程下载器调用。
- [ ] 同步函数内单轮 commit 次数 ≤ `ceil(total_changes / SYNC_DB_COMMIT_BATCH_SIZE) + 1`。
- [ ] 进度/状态类日志按节流窗口合并，未逐条输出。

## 四、接入现状

### 4.1 已接入 `db_write_scope` 的写路径

- `torrents_async.py`：`qb/tr_add_torrents_info_only_async`、`qb/tr_sync_trackers_only_async` 经 `bulk_upsert_with_retry`（内含 `db_write_scope` + retry + 变更检测）。
- `torrent_tracker_status_judge.py`：分批判断（`BATCH_SIZE=1000`），每批 `db_write_scope` + `to_thread` 调 `_judge_one_batch`，单批 commit 毫秒级。
- `tracker_message_logger.py`：`_process_messages_batch_async` / `_cleanup_old_logs_async` 的 4 处 commit 包 `db_write_scope`。
- `tracker_reannounce_task.py`：读段抽 `_read_downloader_data` 经 `to_thread`；写段 `batch_update_last_announce_time` 经 `to_thread` + `db_write_scope`。
- `downloader_path_scan.py`：6 处 commit 包 `db_write_scope`；同步 HTTP 调用（`app_default_save_path` / `get_session_variables`）经 `to_thread`；远程获取默认路径移出写 session。

### 4.2 to_thread 止血（事件循环饥饿根因）

重型任务 `execute()` 虽为 `async def`，但任务体内含阻塞式同步 `SessionLocal()` / 同步 HTTP 调用，会冻结共享 uvicorn 事件循环，导致所有 WebUI handler（含读请求）无法调度。**所有阻塞式同步调用必须经 `asyncio.to_thread` 移出事件循环**：

```python
# ✅ 正确：同步 SessionLocal 读 / 同步 HTTP 经 to_thread 移出循环
keyword_map = await asyncio.to_thread(self._load_keywords)
default_path = await asyncio.to_thread(client.app_default_save_path)

# ✅ 正确：同步写经 to_thread，db_write_scope 在 async caller 侧获取/释放
async with admission_controller.db_write_scope():
    await asyncio.to_thread(ops.batch_update_last_announce_time, ids)
```

⚠️ **`db_write_scope` 必须在 async caller 侧（loop 线程）获取/释放，同步工作经 `to_thread` 在工作线程跑，scope 不进工作线程。** 参考已验证模式 `sync_db_write.py:163-169`（`run_sync + await db.commit()` 在 `db_write_scope` 内）。

### 4.3 busy_timeout 二级兜底（15s）

`busy_timeout` 已从 30000ms 调整为 15000ms（`database.py` `_apply_sqlite_pragmas` + sync/async engine `connect_args timeout=15`），对齐前端 axios timeout=20s。主修复（`db_write_scope` 串行化写者 + `to_thread` 消除循环冻结）后锁竞争窗口已极短，15s 足够兜底；若压测显示误触 `SQLITE_BUSY` 可独立回退 30s（无耦合）。

### 4.4 已知技术债（未接入，后续处理）

- `_sync_speed_schedule`（`cron_executor.py:54-107`）：每分钟持 sync `SessionLocal` 做 HTTP，非 DB 写者但持 session 做 IO。P3。
- `tracker_candidate_pool`（被 `message_logger` 同步触发，未注册 `task_profiles`）。P3。
- `torrent_sync.py` API 触发路径 / `qb_tr_add_torrents_async` 全量同步不经 `db_write_scope`。P3。
