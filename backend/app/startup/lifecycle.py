import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.startup.routers_initializer import init_routers
from app.downloader.initialization import startup_event
from app.tasks.cron_executor import cron_executor
from app.tasks.scheduler.dashboard_stats import DashboardStatsJob


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
            stmt = (
                update(CronTask)
                .where(CronTask.dr == 0)
                .where(CronTask.task_status != 2)
                .values(task_status=2)
            )

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


async def init_default_notifications():
    """
    初始化默认通知（幂等操作，已存在则跳过）

    包括：
    1. 欢迎通知
    2. 当前版本更新说明通知
    """
    try:
        from app.database import AsyncSessionLocal
        from app.models.notification import Notification
        from sqlalchemy import select
        from datetime import datetime

        async with AsyncSessionLocal() as db:
            # 检查是否已存在欢迎通知
            existing_welcome = await db.execute(
                select(Notification).where(Notification.title == "欢迎使用 BtDeck")
            )
            if existing_welcome.scalar_one_or_none():
                print("[SKIP] 欢迎通知已存在，跳过创建")
            else:
                # 创建欢迎通知
                welcome_notification = Notification(
                    type="system",
                    title="欢迎使用 BtDeck",
                    content="感谢您使用 BtDeck！这是您的第一条系统通知。通知中心会在这里显示版本更新和系统消息。",
                    priority="info",
                    is_read=False,
                    extra_data=None,
                    created_at=datetime.now()
                )
                db.add(welcome_notification)
                await db.commit()
                await db.refresh(welcome_notification)
                print(f"[OK] 欢迎通知创建成功 (ID: {welcome_notification.id})")

            # 检查是否已存在当前版本更新通知
            from app.yamlConfig import yaml
            current_version = yaml.get("app.version", "1.0.4")
            version_title = f"BtDeck v{current_version} 版本更新"

            existing_version = await db.execute(
                select(Notification).where(
                    Notification.type == "version_update",
                    Notification.title == version_title
                )
            )
            if existing_version.scalar_one_or_none():
                print(f"[SKIP] 版本更新通知已存在，跳过创建")
            else:
                # 创建版本更新通知
                version_content = f"""
## 🎉 BtDeck v{current_version} 版本更新

### 新增功能

**🔔 通知中心**
- 全新的通知中心模块，集中管理系统消息和版本更新
- 支持通知分页查询、已读/未读状态管理
- 自动检查 GitHub 版本更新并推送通知

**📊 实时速度监控**
- 种子列表新增独立的下载/上传速度列
- 活跃种子自动排序到列表顶部
- 支持通过专用接口获取活跃种子状态

**🔍 Tracker 关键词池**
- 新增 Tracker 关键词池功能，自动初始化默认关键词数据
- 支持关键词的拖拽排序和批量管理

### 优化改进

**⚡ 性能优化**
- qBittorrent 速度接口使用 status_filter 参数减少数据传输
- 修复种子速度监控的线程池泄漏问题
- 改进异常处理机制，提升系统稳定性

**🛠️ 开发基础设施**
- 新增 Harness 开发基础设施，规范开发流程
- 完善项目文档和开发指南

### 技术细节

- 新增 API 端点：`GET /api/v1/torrents/active-torrents`
- 新增通知管理接口：`/api/v1/notifications/*`
- 数据库迁移：新增 notification 表

---
查看完整更新内容，请访问 GitHub Release 页面。
"""

                version_notification = Notification(
                    type="version_update",
                    title=version_title,
                    content=version_content.strip(),
                    priority="info",
                    is_read=False,
                    extra_data={
                        "version": current_version,
                        "release_url": "https://github.com/StrainThomas/BtDeck/releases"
                    },
                    created_at=datetime.now()
                )
                db.add(version_notification)
                await db.commit()
                await db.refresh(version_notification)
                print(f"[OK] 版本更新通知创建成功 (ID: {version_notification.id})")

    except Exception as e:
        print(f"[WARN] 默认通知初始化失败: {e}")
        import traceback
        traceback.print_exc()


async def check_version_update_task(app: FastAPI):
    """
    后台版本更新检查任务

    启动时检查 GitHub Release 是否有新版本，如有则创建通知。
    """
    try:
        from app.database import AsyncSessionLocal
        from app.services.notification_service import NotificationService
        from app.yamlConfig import yaml

        async with AsyncSessionLocal() as db:
            service = NotificationService(db)
            # 从配置文件获取当前版本
            current_version = yaml.get("app.version", "1.0.0")
            await service.check_version_update(current_version)
    except Exception as e:
        print(f"[WARN] 版本更新检查失败: {e}")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    定义应用的生命周期事件

    启动顺序：
    1. 执行数据库迁移（确保schema最新）
    2. 初始化路由
    3. 数据库连接初始化
    4. 更新定时任务状态
    5. 启动定时任务调度器
    6. FastAPI 服务启动（yield前完成）
    7. 下载器数据加载（后台异步，不阻塞启动）
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
    print("=== 执行数据库迁移 ===")
    from app.core.migration import run_alembic_migrations
    migration_success = run_alembic_migrations()
    if migration_success:
        print("[OK] 数据库迁移完成")
    else:
        print("[WARN] 数据库迁移失败，继续启动（开发模式）")

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

    # 1.6 初始化默认通知（欢迎通知、版本更新通知）
    print("=== 初始化默认通知 ===")
    try:
        await init_default_notifications()
        print("[OK] 默认通知初始化完成")
    except Exception as e:
        print(f"[WARN] 默认通知初始化失败: {e}")
        import traceback
        traceback.print_exc()

    # 2. 初始化路由
    init_routers(app)

    # 3. 数据库连接初始化
    await init_database_connection()

    # 4. 更新定时任务表数据：将dr=0的数据状态改为空闲
    await update_cron_task_status()

    # 5. 启动定时任务调度器
    try:
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

    # 7. 在 yield 之前创建后台任务（不等待完成）
    # 这样 FastAPI 启动后，下载器在后台异步加载
    print("=== 创建后台下载器加载任务（将在 FastAPI 启动后执行）===")

    # ✅ 保存后台任务引用，用于后续清理
    downloader_task = asyncio.create_task(startup_event(app))  # ← 传递正确的 app 实例
    app.state.downloader_task = downloader_task

    dashboard_stats_task = asyncio.create_task(run_dashboard_stats_loop(app))
    app.state.dashboard_stats_task = dashboard_stats_task

    # 版本更新检查任务
    version_check_task = asyncio.create_task(check_version_update_task(app))
    app.state.version_check_task = version_check_task

    # yield - FastAPI 在这里启动，下载器任务在后台继续执行
    try:
        yield
    finally:
        # ✅ 清理：取消未完成的后台任务
        print("=== 清理后台任务 ===")
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

        # 停止定时任务调度器
        print("Shutting down...")
        try:
            await cron_executor.stop()
        except Exception as e:
            print(f"Error stopping cron scheduler: {e}")

        # 清理速度监控线程池（防止资源泄漏）
        try:
            from app.api.endpoints.torrent_speed import _speed_executor
            _speed_executor.shutdown(wait=True)
            print("✅ 速度监控线程池已关闭")
        except Exception as e:
            print(f"⚠️  关闭线程池时出错: {e}")

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

