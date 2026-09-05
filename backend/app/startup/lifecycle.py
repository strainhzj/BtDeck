import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.core.config import settings
from app.core.startup_guard import resolve_runtime_info, validate_scheduler_scope
from app.downloader.initialization import startup_event
from app.tasks.cron_executor import cron_executor
from app.tasks.scheduler.dashboard_stats import DashboardStatsJob


async def run_wal_snapshot_loop(app: FastAPI) -> None:
    """周期性只读 WAL 快照（W4-1 第二部分）。

    - 每 SYNC_WAL_SNAPSHOT_INTERVAL_SECONDS 秒经 snapshot_wal_stats 读取
      -wal 文件字节数，发射 EVENT_WAL_SNAPSHOT（wal_bytes / wal_growth_bytes /
      busy_count / checkpoint_busy）。
    - busy_count 非零 → WARNING（计划第 5 节「SQLite busy 每 5 分钟大于 0：
      warning」）；当前 snapshot_wal_stats 无连接句柄恒为 None，接入 PASSIVE
      checkpoint 读数后该分支生效。
    - 只读观测：绝不执行 TRUNCATE checkpoint；观测异常吞掉继续下一轮，
      关闭观测不影响同步治理。
    - 间隔配置 <=0 时由调用方决定不启动本循环。
    """
    from app.services.sync_observability import EVENT_WAL_SNAPSHOT, log_event, snapshot_wal_stats

    interval = float(settings.SYNC_WAL_SNAPSHOT_INTERVAL_SECONDS)
    last_wal_bytes = 0
    while True:
        try:
            stats = snapshot_wal_stats(str(settings.DATABASE_PATH))
            growth = max(0, stats["wal_bytes"] - last_wal_bytes) if last_wal_bytes > 0 else 0
            last_wal_bytes = stats["wal_bytes"]
            busy = stats.get("busy_count")
            level = logging.WARNING if busy is not None and busy > 0 else logging.INFO
            log_event(
                EVENT_WAL_SNAPSHOT,
                level=level,
                wal_bytes=stats["wal_bytes"],
                wal_growth_bytes=growth,
                busy_count=busy,
                checkpoint_busy=stats.get("checkpoint_busy"),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[WARN] WAL 快照任务失败: {exc}")
        await asyncio.sleep(interval)


async def run_process_memory_loop(app: FastAPI) -> None:
    """周期性进程 RSS 采样（OOM 治理 2026-09-05 批次 5）。

    - 每 SYNC_PROCESS_MEMORY_SAMPLE_SECONDS 秒经 get_process_rss_mb 采集一次
      RSS，发射 EVENT_PROCESS_MEMORY（rss_mb / sample_interval_seconds），并
      刷新模块级 _LAST_RSS_MB 供 /sync 健康端点读取（last-sample 模式，端点
      不触发采集）。
    - 平台不可用（如 macOS）时 rss_mb 为 None，仍发射事件留采样心跳，便于
      区分"未启动循环"与"平台不支持"。
    - 采样后按 SYNC_PROCESS_MEMORY_TRIM_ENABLED（默认开）触发分配器空闲归还
      （glibc malloc_trim / bionic M_PURGE），把同步分批循环造成的 RSS 高水位
      棘轮变锯齿——移动端实测重启后 819MB 数小时爬到 2.2GB 的主要成分。
    - 纯只读观测 + 空闲时机归还：异常吞掉继续下一轮，关闭观测不影响任何业务；
      间隔配置 <=0 时由调用方决定不启动本循环（照 6.6 WAL 门控模式）。
    """
    from app.services.sync_observability import (
        EVENT_PROCESS_MEMORY,
        get_process_rss_mb,
        log_event,
        release_free_heap_memory,
    )

    interval = float(settings.SYNC_PROCESS_MEMORY_SAMPLE_SECONDS)
    while True:
        try:
            rss_mb = get_process_rss_mb()
            heap_trimmed = release_free_heap_memory() if settings.SYNC_PROCESS_MEMORY_TRIM_ENABLED else False
            level = logging.INFO if rss_mb is not None else logging.DEBUG
            log_event(
                EVENT_PROCESS_MEMORY,
                level=level,
                rss_mb=rss_mb,
                sample_interval_seconds=interval,
                heap_trimmed=heap_trimmed,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[WARN] 进程内存采样任务失败: {exc}")
        await asyncio.sleep(interval)


async def run_dashboard_stats_loop(app: FastAPI) -> None:
    """Periodic dashboard stats refresh loop."""
    job = DashboardStatsJob(app=app)
    app.state.dashboard_stats_job = job
    interval = getattr(job, "default_interval", 60)

    while True:
        try:
            await job.execute(app=app)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[WARN] dashboard stats task failed: {exc}")

        await asyncio.sleep(interval)


async def update_cron_task_status():
    """
    应用启动时更新定时任务表数据：将dr=0的数据状态改为空闲(task_status=2)
    """
    try:
        from sqlalchemy import update
        from app.tasks.cron_models import CronTask
        from app.database import SessionLocal

        # 使用同步方式操作数据库
        db = SessionLocal()
        try:
            # 查询所有dr=0且task_status!=2的记录
            stmt = update(CronTask).where(CronTask.dr == 0).where(CronTask.task_status != 2).values(task_status=2)

            result = db.execute(stmt)
            db.commit()

            if result.rowcount > 0:
                print(f"已更新 {result.rowcount} 条定时任务记录状态为空闲")
        finally:
            db.close()

    except Exception as e:
        print(f"更新定时任务状态失败: {e}")
        import traceback

        traceback.print_exc()


async def check_version_update_task(app: FastAPI):
    """
    后台版本更新检查任务

    启动时检查 GitHub Release 是否有新版本，如有则创建通知。
    版本信息从 app.version 模块读取，保持版本号统一管理。
    """
    try:
        from app.database import AsyncSessionLocal
        from app.services.notification_service import NotificationService
        from app.version import CURRENT_VERSION

        async with AsyncSessionLocal() as db:
            service = NotificationService(db)
            # 从版本模块获取当前版本
            await service.check_version_update(CURRENT_VERSION)
    except Exception as e:
        print(f"[WARN] 版本更新检查失败: {e}")
        import traceback

        traceback.print_exc()


async def add_version_update_notification_task(app: FastAPI):
    """
    启动时自动添加版本更新通知

    检查数据库中是否已有当前版本的通知，如果没有则自动创建。
    版本信息从 app.version 模块读取，便于集中管理。
    """
    try:
        from app.database import AsyncSessionLocal
        from app.services.notification_service import NotificationService
        from app.version import CURRENT_VERSION, get_version_content, get_version_info

        # 从版本模块获取信息
        notification_title = f"BtDeck v{CURRENT_VERSION} 版本更新"
        version_content = get_version_content(CURRENT_VERSION)
        version_info = get_version_info(CURRENT_VERSION)

        if not version_content:
            print(f"[WARN] 未找到 v{CURRENT_VERSION} 的版本更新内容")
            return

        async with AsyncSessionLocal() as db:
            service = NotificationService(db)

            # 检查是否已存在该版本通知
            from sqlalchemy import select
            from app.models.notification import Notification

            existing = await db.execute(select(Notification).where(Notification.title == notification_title))
            if existing.scalar_one_or_none():
                print(f"[INFO] v{CURRENT_VERSION} 版本更新通知已存在，跳过创建")
                return

            # 创建版本更新通知
            notification = await service.create_notification(
                type="version_update",
                title=notification_title,
                content=version_content,
                priority="info",
                extra_data={
                    "version": CURRENT_VERSION,
                    "previous_version": version_info.get("previous_version", ""),
                    "release_url": version_info.get("release_url", ""),
                    "published_at": f"{version_info.get('release_date', '')}T00:00:00Z",
                },
            )
            print(f"[OK] 已自动创建 v{CURRENT_VERSION} 版本更新通知 (ID: {notification.id})")

    except Exception as e:
        print(f"[WARN] 添加版本更新通知失败: {e}")
        import traceback

        traceback.print_exc()


async def init_database_connection():
    """
    初始化数据库连接并验证
    """
    try:
        from sqlalchemy import text
        from app.database import SessionLocal

        print("=== 开始初始化数据库连接 ===")
        db = SessionLocal()
        try:
            # 执行简单查询验证连接
            result = db.execute(text("SELECT 1")).scalar()
            if result == 1:
                print("[OK] 数据库连接成功")
            else:
                print("[WARN] 数据库查询返回异常结果")
        finally:
            db.close()
    except Exception as e:
        print(f"[ERROR] 数据库连接失败: {e}")
        import traceback

        traceback.print_exc()
        raise


async def reconcile_orphan_file_state() -> dict[str, int]:
    """在调度器启动前幂等补齐历史隔离候选对应的扫描明细。"""
    from app.database import AsyncSessionLocal
    from app.services.orphan_file_service import OrphanFileService

    async with AsyncSessionLocal() as db:
        return await OrphanFileService(db).reconcile_stable_candidate_details()


async def recover_interrupted_orphan_scans(session_factory: Any = None) -> int:
    """把残留 running 的孤儿扫描记录标记为 failed（服务重启恢复）。

    落库分批后，扫描中途崩溃会残留 status=running 的记录：清理门禁
    (_evaluate_cleanup_snapshot) 对 running 与 failed 都拒清理，但 running
    会让 get_orphan_list 的 display_scan 为 None 导致列表空白。恢复为 failed
    后列表回退显示最近一次 completed 扫描，状态机语义正确。
    恢复不改门禁放行语义（仍需下一次成功扫描产生 completed）。

    Args:
        session_factory: 可注入的异步 session 工厂（默认 AsyncSessionLocal；
            测试可传内存库工厂）。

    Returns:
        恢复（running → failed）的记录数。
    """
    from datetime import datetime

    from sqlalchemy import update

    from app.database import AsyncSessionLocal
    from app.models.orphan_file import OrphanScanResult
    from app.tasks.resource_guard import admission_controller

    factory = session_factory or AsyncSessionLocal
    recovered = 0
    async with factory() as db:
        async with admission_controller.db_write_scope():
            result = await db.execute(
                update(OrphanScanResult)
                .where(OrphanScanResult.status == "running")
                .values(
                    status="failed",
                    error_message="服务重启后自动标记失败（扫描未完成）",
                    updated_at=datetime.utcnow(),
                )
            )
            recovered = getattr(result, "rowcount", None) or 0
            if recovered:
                await db.commit()
            else:
                await db.rollback()
    return recovered


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    定义应用的生命周期事件

    启动顺序：
    1. 执行数据库迁移（确保schema最新）
    2. 数据库连接初始化
    3. 更新定时任务状态
    4. 启动定时任务调度器
    5. FastAPI 服务启动（yield前完成）
    6. 下载器数据加载（后台异步，不阻塞启动）
    """
    print("Starting up...")
    app.state.start_time = time.time()
    app.state.torrent_stats = {"active": 0, "downloading": 0, "seeding": 0, "paused": 0}

    # 0. 初始化配置文件（必须在所有其他初始化之前）
    # 修复：uvicorn启动时不会执行main.py的if __name__块，所以需要在lifespan中调用
    print("=== 初始化配置文件 ===")
    from app.database import init_config_file
    from app.yamlConfig import yaml

    try:
        init_config_file()
        yaml.reload()  # ✨ 重新加载配置，确保 yaml 对象读取到刚生成的配置
        print("[OK] 配置文件初始化完成")
    except Exception as e:
        print(f"[ERROR] 配置文件初始化失败: {e}")
        import traceback

        traceback.print_exc()

    # 1. 执行数据库迁移（在所有其他初始化之前）
    # 四轨治理后统一入口：migrate_database()（编程式 alembic，含幽灵版本救援/备份）
    # 无论 DEV 与否，只要迁移未完成就停止启动。继续加载新 ORM 会把首因掩盖为
    # ``no such column``，并可能让后台任务在不一致 schema 上运行。
    print("=== 执行数据库迁移 ===")
    from app.core.migration import migrate_database

    try:
        if not migrate_database():
            raise RuntimeError("数据库迁移未完成，拒绝在不一致 schema 上启动")
        print("[OK] 数据库迁移完成")
    except Exception as e:
        print(f"[ERROR] 数据库迁移失败: {e}")
        import traceback

        traceback.print_exc()
        raise

    # 1.5 初始化数据库初始数据（admin用户、配置、定时任务等）
    # 修复：uvicorn启动时不会执行main.py的if __name__块，所以需要在lifespan中调用
    print("=== 初始化数据库数据 ===")
    from app.database import init_db

    try:
        init_db()
        print("[OK] 数据库初始数据创建完成")
    except Exception as e:
        print(f"[ERROR] 数据库初始数据创建失败: {e}")
        import traceback

        traceback.print_exc()

    # 1.7 安全钩子：把历史遗留的明文下载器密码加密回写（幂等，密钥缺失时跳过）
    print("=== 加密明文下载器密码 ===")
    try:
        from app.downloader.initialization import encrypt_plaintext_downloader_passwords

        encrypted_rows = encrypt_plaintext_downloader_passwords()
        if encrypted_rows:
            print(f"[OK] 已加密 {encrypted_rows} 条明文下载器密码")
        else:
            print("[OK] 无需加密的明文下载器密码")
    except Exception as e:
        print(f"[WARN] 明文下载器密码加密钩子失败（不阻塞启动）: {e}")

    # 2. 数据库连接初始化
    await init_database_connection()

    # 2.5 对账历史隔离候选，避免新读模型重新展示已移走文件。
    print("=== 对账孤儿文件隔离状态 ===")
    try:
        reconciliation = await reconcile_orphan_file_state()
        print(
            "[OK] 孤儿文件隔离状态对账完成: "
            f"更新 {reconciliation['updated_count']} 条，"
            f"未匹配 {reconciliation['unmatched_count']} 条"
        )
    except Exception as e:
        print(f"[ERROR] 孤儿文件隔离状态对账失败: {e}")
        import traceback

        traceback.print_exc()
        if not settings.DEV:
            raise
        print("[WARN] DEV 模式继续启动；本次孤儿文件对账不得视为通过")

    # 2.6 恢复残留 running 的孤儿扫描记录（落库分批后崩溃残留的兜底恢复）。
    print("=== 恢复中断的孤儿扫描记录 ===")
    try:
        _recovered_scans = await recover_interrupted_orphan_scans()
        if _recovered_scans:
            print(f"[OK] 已恢复 {_recovered_scans} 条残留 running 扫描记录为 failed")
        else:
            print("[OK] 无残留 running 扫描记录")
    except Exception as e:
        print(f"[ERROR] 孤儿扫描记录恢复失败: {e}")
        import traceback

        traceback.print_exc()
        if not settings.DEV:
            raise

    # 3. 更新定时任务表数据：将dr=0的数据状态改为空闲
    await update_cron_task_status()

    # 4. 启动定时任务调度器
    # W2-4 纵深防御（P0-06）：scheduler 单实例断言——SQLite 多 Worker 已被 main.py
    # 启动前置校验挡住，此处兜底：SQLite + WORKERS!=1 拒绝启动 scheduler；
    # PostgreSQL + 多 Worker 时记录显式状态（Leader 选举未实现）。
    try:
        _startup_backend, _startup_workers, _ = resolve_runtime_info()
        validate_scheduler_scope(_startup_backend, _startup_workers)
        # ✅ 修复：在启动调度器前设置 app 实例
        cron_executor.set_app(app)
        await cron_executor.start()
        print("[OK] 定时任务调度器已成功启动")
    except Exception as e:
        print(f"[ERROR] 启动定时任务调度器失败: {e}")
        import traceback

        traceback.print_exc()

    # 5. 此时 FastAPI 服务已准备好启动
    print("=== FastAPI 服务准备就绪，即将启动 ===")

    # 6. 在 yield 之前创建后台任务（不等待完成）
    # 这样 FastAPI 启动后，下载器在后台异步加载
    print("=== 创建后台下载器加载任务（将在 FastAPI 启动后执行）===")

    # ✅ 保存后台任务引用，用于后续清理
    downloader_task = asyncio.create_task(startup_event(app))  # ← 传递正确的 app 实例
    app.state.downloader_task = downloader_task

    # 持久化隔离区彻底删除任务：立即恢复上次进程的 pending/running 任务。
    from app.services.orphan_purge_job_service import get_orphan_purge_dispatcher

    orphan_purge_dispatcher = get_orphan_purge_dispatcher(app)
    orphan_purge_recovery_task = asyncio.create_task(orphan_purge_dispatcher.recover_pending_jobs())
    app.state.orphan_purge_recovery_task = orphan_purge_recovery_task

    # 持久化孤儿扫描任务：queued 在启动后继续执行；残留 running 已在上方标 failed。
    from app.services.orphan_scan_job_service import get_orphan_scan_dispatcher

    orphan_scan_dispatcher = get_orphan_scan_dispatcher(app)
    orphan_scan_recovery_task = asyncio.create_task(orphan_scan_dispatcher.recover_pending_scans())
    app.state.orphan_scan_recovery_task = orphan_scan_recovery_task

    dashboard_stats_task = asyncio.create_task(run_dashboard_stats_loop(app))
    app.state.dashboard_stats_task = dashboard_stats_task

    # 版本更新检查任务
    version_check_task = asyncio.create_task(check_version_update_task(app))
    app.state.version_check_task = version_check_task

    # 本地版本更新通知任务（自动添加，不依赖 GitHub）
    version_notification_task = asyncio.create_task(add_version_update_notification_task(app))
    app.state.version_notification_task = version_notification_task

    # 6.5 事件循环 lag 采样器挂载（W4-1 第二部分）：观测启动失败不阻断应用启动；
    # SYNC_LAG_SAMPLER_ENABLED=False 时 start_lag_sampler 返回空句柄 no-op。
    try:
        from app.services.sync_observability import start_lag_sampler

        lag_sampler_handle = start_lag_sampler()
        app.state.sync_lag_sampler = lag_sampler_handle
        print(f"[OK] 事件循环 lag 采样器已启动 (enabled={lag_sampler_handle.enabled})")
    except Exception as e:
        app.state.sync_lag_sampler = None
        print(f"[WARN] 事件循环 lag 采样器启动失败（不阻断启动）: {e}")

    # 6.6 WAL 只读周期快照（W4-1 第二部分）：仅当间隔配置 >0 时启动；
    # 观测任务失败不阻断应用启动/关闭。移动端 profile（2026-09-05）：
    # android-server 形态跳过——每分钟一次 SQLite PRAGMA 探测 + 文件 stat
    # 在手机上诊断价值低，徒增后台 I/O 与分配（服务端形态不受影响）。
    wal_snapshot_task = None
    if float(settings.SYNC_WAL_SNAPSHOT_INTERVAL_SECONDS) > 0:
        from app.core.platform_capabilities import is_android_server

        if is_android_server():
            print("[OK] android-server 运行形态：跳过 WAL 只读周期快照（移动端诊断价值低）")
        else:
            wal_snapshot_task = asyncio.create_task(run_wal_snapshot_loop(app))
            app.state.wal_snapshot_task = wal_snapshot_task
            print("[OK] WAL 只读周期快照任务已启动")

    # 6.7 存量 added_date 回填（W3-3）：仅当开关开启时启动（默认关闭）；
    # 失败不阻断应用启动。
    added_date_backfill_task = None
    if settings.INFO_SYNC_STARTUP_BACKFILL_ENABLED:
        from app.services.torrent_added_date_backfill import backfill_torrent_added_dates

        added_date_backfill_task = asyncio.create_task(backfill_torrent_added_dates(app))
        app.state.added_date_backfill_task = added_date_backfill_task
        print("[OK] 存量 added_date 回填任务已启动")

    # 6.8 进程 RSS 周期采样（OOM 治理 2026-09-05）：仅当间隔配置 >0 时启动；
    # 观测任务失败不阻断应用启动/关闭（照 6.6 WAL 门控模式）。
    process_memory_task = None
    if float(settings.SYNC_PROCESS_MEMORY_SAMPLE_SECONDS) > 0:
        process_memory_task = asyncio.create_task(run_process_memory_loop(app))
        app.state.process_memory_task = process_memory_task
        print("[OK] 进程 RSS 周期采样任务已启动")

    # yield - FastAPI 在这里启动，下载器任务在后台继续执行
    try:
        yield
    finally:
        # ✅ 清理：取消未完成的后台任务
        print("=== 清理后台任务 ===")
        torrent_batch_tasks = list(getattr(app.state, "torrent_batch_tasks", set()))
        pending_torrent_batch_tasks = [task for task in torrent_batch_tasks if not task.done()]
        for task in pending_torrent_batch_tasks:
            task.cancel()
        if pending_torrent_batch_tasks:
            await asyncio.gather(*pending_torrent_batch_tasks, return_exceptions=True)

        if orphan_purge_recovery_task and not orphan_purge_recovery_task.done():
            orphan_purge_recovery_task.cancel()
            try:
                await orphan_purge_recovery_task
            except asyncio.CancelledError:
                print("✅ 隔离区彻底删除恢复任务已取消")
            except Exception as e:
                print(f"⚠️  取消隔离区彻底删除恢复任务时出错: {e}")
        try:
            await orphan_purge_dispatcher.shutdown()
        except Exception as e:
            print(f"⚠️  关闭隔离区彻底删除调度器时出错: {e}")

        if orphan_scan_recovery_task and not orphan_scan_recovery_task.done():
            orphan_scan_recovery_task.cancel()
            try:
                await orphan_scan_recovery_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"⚠️  取消孤儿扫描恢复任务时出错: {e}")
        try:
            await orphan_scan_dispatcher.shutdown()
        except Exception as e:
            print(f"⚠️  关闭孤儿扫描调度器时出错: {e}")

        if downloader_task and not downloader_task.done():
            print("取消未完成的下载器加载任务...")
            downloader_task.cancel()
            try:
                await downloader_task
            except asyncio.CancelledError:
                print("✅ 下载器加载任务已取消")
            except Exception as e:
                print(f"⚠️  取消任务时出错: {e}")

        if dashboard_stats_task and not dashboard_stats_task.done():
            print("取消仪表盘统计任务...")
            dashboard_stats_task.cancel()
            try:
                await dashboard_stats_task
            except asyncio.CancelledError:
                print("✅ 仪表盘统计任务已取消")
            except Exception as e:
                print(f"⚠️  取消仪表盘统计任务时出错: {e}")

        if version_check_task and not version_check_task.done():
            print("取消版本检查任务...")
            version_check_task.cancel()
            try:
                await version_check_task
            except asyncio.CancelledError:
                print("✅ 版本检查任务已取消")
            except Exception as e:
                print(f"⚠️  取消版本检查任务时出错: {e}")

        if version_notification_task and not version_notification_task.done():
            print("取消版本通知任务...")
            version_notification_task.cancel()
            try:
                await version_notification_task
            except asyncio.CancelledError:
                print("✅ 版本通知任务已取消")
            except Exception as e:
                print(f"⚠️  取消版本通知任务时出错: {e}")

        # 停止定时任务调度器
        print("Shutting down...")
        try:
            await cron_executor.stop()
        except Exception as e:
            print(f"Error stopping cron scheduler: {e}")

        # 关闭下载器 API runtime（三 lane executor + flush 残留日志统计）。
        # 速度接口（torrent_speed）已接入 INTERACTIVE lane，不再有独立 _speed_executor。
        # sync-resource-governance code review 修复：确保应用退出时关闭 lane executor，
        # 避免线程池泄漏 + 触发日志聚合器最终 flush。
        try:
            from app.services.downloader_api_runtime import downloader_api_runtime

            downloader_api_runtime.shutdown()
            print("✅ 下载器 API runtime 已关闭")
        except Exception as e:
            print(f"⚠️  关闭下载器 API runtime 时出错: {e}")

        # 取消 WAL 只读周期快照任务（W4-1 第二部分）：异常不阻断关闭。
        if wal_snapshot_task and not wal_snapshot_task.done():
            print("取消 WAL 快照任务...")
            wal_snapshot_task.cancel()
            try:
                await wal_snapshot_task
            except asyncio.CancelledError:
                print("✅ WAL 快照任务已取消")
            except Exception as e:
                print(f"⚠️  取消 WAL 快照任务时出错: {e}")

        # 取消存量 added_date 回填任务（W3-3）：异常不阻断关闭。
        if added_date_backfill_task and not added_date_backfill_task.done():
            print("取消 added_date 回填任务...")
            added_date_backfill_task.cancel()
            try:
                await added_date_backfill_task
            except asyncio.CancelledError:
                print("✅ added_date 回填任务已取消")
            except Exception as e:
                print(f"⚠️  取消 added_date 回填任务时出错: {e}")

        # 取消进程 RSS 周期采样任务（OOM 治理 2026-09-05）：异常不阻断关闭。
        if process_memory_task and not process_memory_task.done():
            print("取消进程 RSS 采样任务...")
            process_memory_task.cancel()
            try:
                await process_memory_task
            except asyncio.CancelledError:
                print("✅ 进程 RSS 采样任务已取消")
            except Exception as e:
                print(f"⚠️  取消进程 RSS 采样任务时出错: {e}")

        # 关闭事件循环 lag 采样器（W4-1 第二部分）：空句柄 stop() no-op，
        # 异常不阻断关闭。
        try:
            lag_handle = getattr(app.state, "sync_lag_sampler", None)
            if lag_handle is not None:
                lag_handle.stop()
            print("✅ 事件循环 lag 采样器已关闭")
        except Exception as e:
            print(f"⚠️  关闭事件循环 lag 采样器时出错: {e}")

    # # 初始化插件
    # plugin_init_task = asyncio.create_task(init_plugins_async())
    # try:
    #     # 在此处 yield，表示应用已经启动，控制权交回 FastAPI 主事件循环
    #     yield
    # finally:
    #     print("Shutting down...")
    #     try:
    #         # 取消插件初始化
    #         plugin_init_task.cancel()
    #         await plugin_init_task
    #     except asyncio.CancelledError:
    #         print("Plugin installation task cancelled.")
    #     except Exception as e:
    #         print(f"Error during plugin installation shutdown: {e}")
    #     # 清理模块
    #     shutdown_modules(app)
    #     # 关闭工作流
    #     stop_workflow(app)
