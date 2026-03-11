from fastapi import APIRouter
from app.api.endpoints import login,downloader,cuser,torrents,tracker,tasks,cron_tasks,advanced_search
from app.api.endpoints import tracker_keywords, tracker_messages, tracker_test, tracker_keywords_pools, tracker_keywords_pools
from app.api.endpoints import audit_logs, recycle_bin, duplicate_torrents
from app.api.endpoints import dashboard
# 导入下载器设置相关API
from app.api.endpoints import downloader_settings, setting_templates, downloader_capabilities
from app.api.endpoints import downloader_capabilities_management
# 导入标签管理API
from app.api.endpoints import tag_management
# 导入种子文件备份API
from app.api.endpoints import torrent_backup
# 导入下载器路径维护API
from app.api.endpoints import downloader_path_maintenance
# 导入种子转移API
from app.api.endpoints import seed_transfer

api_router = APIRouter()
api_router.include_router(login.router, prefix="/auth")
api_router.include_router(downloader.router, prefix="/downloader", tags=["downloader"])
api_router.include_router(cuser.router, prefix="/user", tags=["user"])
api_router.include_router(cuser.router, prefix="/users", tags=["users"])  # 添加/users前缀支持前端调用
api_router.include_router(torrents.router, prefix="/torrents", tags=["torrents"])
api_router.include_router(tracker.router, prefix="/tracker", tags=["tracker"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(cron_tasks.router, prefix="/cronTasks", tags=["cron-tasks"])
# Dashboard
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
# 添加高级搜索路由
api_router.include_router(advanced_search.router, prefix="/advanced-search", tags=["search"])
# 添加tracker关键词和消息记录路由
# 注意：tracker_keywords_pools 必须在 tracker_keywords 之前注册，避免 /pool 被 /{keyword_id} 路由拦截
api_router.include_router(tracker_keywords_pools.router, prefix="/tracker-keywords", tags=["tracker-keywords-pools"])
api_router.include_router(tracker_keywords.router, prefix="/tracker-keywords", tags=["tracker-keywords"])
api_router.include_router(tracker_messages.router, prefix="/tracker-messages", tags=["tracker-messages"])
api_router.include_router(tracker_test.router, prefix="/tracker-test", tags=["tracker-test"])
# 添加审计日志路由
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["audit-logs"])
# 添加回收站路由
api_router.include_router(recycle_bin.router, prefix="/recycle", tags=["recycle-bin"])
# 添加重复检测路由
api_router.include_router(duplicate_torrents.router, prefix="/torrents", tags=["torrents"])
# 添加下载器设置管理路由
api_router.include_router(downloader_settings.router, prefix="/downloaders", tags=["下载器设置"])
api_router.include_router(setting_templates.router, prefix="/setting-templates", tags=["配置模板"])
api_router.include_router(downloader_capabilities.router, prefix="/downloaders", tags=["下载器能力"])
# 添加下载器能力配置管理路由
api_router.include_router(downloader_capabilities_management.router, prefix="/downloaders", tags=["下载器能力管理"])
# 添加标签管理路由
api_router.include_router(tag_management.router, prefix="/tags", tags=["标签管理"])
# 添加种子文件备份路由
api_router.include_router(torrent_backup.router, prefix="/torrents", tags=["种子备份"])
# 添加下载器路径维护路由
api_router.include_router(downloader_path_maintenance.router, prefix="/downloaders", tags=["下载器路径维护"])
# 添加种子转移路由
api_router.include_router(seed_transfer.router, prefix="/torrents", tags=["种子转移"])
