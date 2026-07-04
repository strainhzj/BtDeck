# 同步任务 DB 写入治理（sync-db-write-governance）

> 适用范围：`backend/app/tasks/scheduler/` 重型同步任务与 `torrents_async.py` 内的同步函数
> 关联计划：`PLANS/sync-resource-governance.md` 阶段 1（DB 写入治理）
> 强制级别：阶段 2 改造同步函数 commit 点时**必须**遵循本文档；新建同步函数**必须**遵循本文档

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

## 四、本阶段（阶段 1）现状

- `db_writer` 信号量 + `db_write_scope()` 已在 `app/tasks/resource_guard.py` 暴露。
- **生产路径暂未强制接入**：现有 `torrents_async.py` 同步函数（`qb_add_torrents_info_only_async` / `qb_sync_trackers_only_async` / `tr_*` 等）的 commit 点未改造。
- 阶段 2（`downloader_api_runtime`）改造这些同步函数时，按本指南逐个接入 `db_write_scope()` + 批量提交 + 变更检测。
