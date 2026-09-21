"""
种子管理模块 - 聚合路由器

将原 torrents.py (5412行) 拆分为以下子模块:
- torrent_crud.py: CRUD 端点（列表、添加、查询）
- torrent_status.py: 皂停/恢复/重检端点
- torrent_deletion.py: 删除相关端点
- torrent_sync.py: 同步端点 + 同步辅助函数
- torrent_location.py: 修改保存路径端点
- torrent_speed.py: 实时速度端点
- torrent_detail.py: 种子详情明细端点（文件/Peers 列表）
- torrent_helpers.py: 共享工具函数（转换、序列化等）
- torrent_crud_service.py: DB CRUD 服务层
"""

from fastapi import APIRouter

from app.api.endpoints.torrent_crud import router as crud_router
from app.api.endpoints.torrent_status import router as status_router
from app.api.endpoints.torrent_deletion import router as deletion_router
from app.api.endpoints.torrent_sync import router as sync_router
from app.api.endpoints.torrent_location import router as location_router
from app.api.endpoints.torrent_speed import router as speed_router
from app.api.endpoints.torrent_detail import router as detail_router

router = APIRouter()

router.include_router(crud_router)
router.include_router(status_router)
router.include_router(deletion_router)
router.include_router(sync_router)
router.include_router(location_router)
router.include_router(speed_router)
router.include_router(detail_router)
