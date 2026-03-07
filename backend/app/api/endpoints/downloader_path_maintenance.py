# -*- coding: utf-8 -*-
"""
下载器路径维护API端点

提供下载器路径信息的CRUD API接口。
"""
import logging
from typing import Optional, List, Annotated

from fastapi import APIRouter, Depends, Request, Path, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.responseVO import CommonResponse
from app.database import get_db
from app.auth import utils
from app.models.downloader_path_maintenance import DownloaderPathMaintenance
from app.services.path_maintenance_service import PathMaintenanceService

router = APIRouter()
logger = logging.getLogger(__name__)


# ========== 辅助函数 ==========

def get_current_user_id(token: str) -> Optional[int]:
    """
    从JWT token中获取用户ID

    Args:
        token: JWT访问令牌

    Returns:
        Optional[int]: 用户ID，失败返回None
    """
    try:
        decoded = utils.verify_access_token(token)
        user_id = decoded.get("user_id")
        return int(user_id) if user_id else None
    except Exception as e:
        logger.error(f"获取用户ID失败: {e}")
        return None


def verify_downloader_exists(db: Session, downloader_id: str) -> bool:
    """
    验证下载器是否存在

    Args:
        db: 数据库会话
        downloader_id: 下载器ID

    Returns:
        bool: 存在返回True，否则返回False
    """
    try:
        sql = """
            SELECT COUNT(*) as count FROM bt_downloaders
            WHERE downloader_id = :downloader_id AND dr = 0
        """
        result = db.execute(text(sql), {"downloader_id": downloader_id}).fetchone()
        return result.count > 0 if result else False
    except Exception as e:
        logger.error(f"验证下载器存在性失败: {e}")
        return False


# ========== 模型定义 ==========

from pydantic import BaseModel, Field


class PathCreateRequest(BaseModel):
    """创建路径请求"""
    path_type: str = Field(..., description="路径类型：default或active")
    path_value: str = Field(..., description="路径值（绝对路径）")
    is_enabled: bool = Field(True, description="是否启用")


class PathUpdateRequest(BaseModel):
    """更新路径请求"""
    path_value: Optional[str] = Field(None, description="路径值")
    is_enabled: Optional[bool] = Field(None, description="是否启用")


# ========== API端点 ==========

@router.get(
    "/{downloader_id}/paths",
    summary="获取下载器路径列表",
    response_model=CommonResponse,
    tags=["下载器路径维护"]
)
def get_paths(
    downloader_id: Annotated[str, Path(description="下载器ID")],
    path_type: Optional[str] = Query(None, description="路径类型过滤"),
    is_enabled: Optional[bool] = Query(None, description="是否启用过滤"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取下载器的路径列表

    支持按路径类型和启用状态过滤
    """
    try:
        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 验证下载器是否存在
        if not verify_downloader_exists(db, downloader_id):
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 3. 创建服务实例
        service = PathMaintenanceService(db)

        # 4. 获取路径列表
        paths = service.get_paths_by_downloader(
            downloader_id=downloader_id,  # 直接使用字符串，无需转换
            path_type=path_type,
            is_enabled=is_enabled
        )

        # 5. 转换路径列表格式
        path_list = []
        for path in paths:
            path_list.append({
                "id": path.id,
                "downloader_id": path.downloader_id,
                "path_type": path.path_type,
                "path_value": path.path_value,
                "is_enabled": path.is_enabled,
                "torrent_count": path.torrent_count,
                "last_updated_time": path.last_updated_time.isoformat() if path.last_updated_time else None,
                "created_at": path.created_at.isoformat() if path.created_at else None,
                "updated_at": path.updated_at.isoformat() if path.updated_at else None
            })

        # 6. 获取下载器名称
        downloader_info = db.execute(
            text("SELECT nickname FROM bt_downloaders WHERE downloader_id = :downloader_id AND dr = 0"),
            {"downloader_id": downloader_id}
        ).fetchone()

        downloader_name = downloader_info.nickname if downloader_info else "未知下载器"

        # 7. 构建符合前端期望的响应格式
        response_data = {
            "downloader_id": downloader_id,
            "downloader_name": downloader_name,
            "paths": path_list
        }

        return CommonResponse(
            status="success",
            msg="获取路径列表成功",
            code="200",
            data=response_data
        )

    except Exception as e:
        logger.error(f"获取路径列表失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/{downloader_id}/paths",
    summary="添加下载器路径",
    response_model=CommonResponse,
    tags=["下载器路径维护"]
)
def create_path(
    downloader_id: Annotated[str, Path(description="下载器ID")],
    request_data: PathCreateRequest,
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    添加下载器路径

    支持默认路径和活跃路径两种类型
    """
    try:
        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 验证下载器是否存在
        if not verify_downloader_exists(db, downloader_id):
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 3. 创建服务实例
        service = PathMaintenanceService(db)

        # 4. 创建路径
        path = service.create_path(
            downloader_id=downloader_id,
            path_type=request_data.path_type,
            path_value=request_data.path_value,
            is_enabled=request_data.is_enabled,
            torrent_count=0
        )

        return CommonResponse(
            status="success",
            msg="添加路径成功",
            code="200",
            data={
                "id": path.id,
                "downloader_id": path.downloader_id,
                "path_type": path.path_type,
                "path_value": path.path_value,
                "is_enabled": path.is_enabled,
                "torrent_count": path.torrent_count,
                "last_updated_time": path.last_updated_time.isoformat() if path.last_updated_time else None,
                "created_at": path.created_at.isoformat() if path.created_at else None,
                "updated_at": path.updated_at.isoformat() if path.updated_at else None
            }
        )

    except ValueError as e:
        db.rollback()
        return CommonResponse(
            status="error",
            msg=str(e),
            code="422",
            data=None
        )
    except Exception as e:
        db.rollback()
        logger.error(f"添加路径失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.put(
    "/{downloader_id}/paths/{path_id}",
    summary="更新下载器路径",
    response_model=CommonResponse,
    tags=["下载器路径维护"]
)
def update_path(
    downloader_id: Annotated[str, Path(description="下载器ID")],
    path_id: Annotated[int, Path(description="路径ID")],
    request_data: PathUpdateRequest,
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    更新下载器路径

    支持更新路径值和启用状态
    """
    try:
        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 验证下载器是否存在
        if not verify_downloader_exists(db, downloader_id):
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 3. 创建服务实例
        service = PathMaintenanceService(db)

        # 4. 更新路径
        success = service.update_path(
            path_id=path_id,
            path_value=request_data.path_value,
            is_enabled=request_data.is_enabled
        )

        if not success:
            return CommonResponse(
                status="error",
                msg="路径不存在或更新失败",
                code="404",
                data=None
            )

        # 5. 获取更新后的路径信息
        path = service.get_path_by_id(path_id)

        return CommonResponse(
            status="success",
            msg="更新路径成功",
            code="200",
            data={
                "id": path.id,
                "downloader_id": path.downloader_id,
                "path_type": path.path_type,
                "path_value": path.path_value,
                "is_enabled": path.is_enabled,
                "torrent_count": path.torrent_count,
                "last_updated_time": path.last_updated_time.isoformat() if path.last_updated_time else None,
                "created_at": path.created_at.isoformat() if path.created_at else None,
                "updated_at": path.updated_at.isoformat() if path.updated_at else None
            }
        )

    except ValueError as e:
        db.rollback()
        return CommonResponse(
            status="error",
            msg=str(e),
            code="422",
            data=None
        )
    except Exception as e:
        db.rollback()
        logger.error(f"更新路径失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.delete(
    "/{downloader_id}/paths/{path_id}",
    summary="删除下载器路径",
    response_model=CommonResponse,
    tags=["下载器路径维护"]
)
def delete_path(
    downloader_id: Annotated[str, Path(description="下载器ID")],
    path_id: Annotated[int, Path(description="路径ID")],
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    删除下载器路径（逻辑删除）

    将路径标记为未启用，不从数据库中物理删除
    """
    try:
        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 验证下载器是否存在
        if not verify_downloader_exists(db, downloader_id):
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 3. 创建服务实例
        service = PathMaintenanceService(db)

        # 4. 删除路径（逻辑删除）
        success = service.delete_path(path_id)

        if not success:
            return CommonResponse(
                status="error",
                msg="路径不存在或删除失败",
                code="404",
                data=None
            )

        return CommonResponse(
            status="success",
            msg="删除路径成功",
            code="200",
            data=None
        )

    except Exception as e:
        db.rollback()
        logger.error(f"删除路径失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.get(
    "/{downloader_id}/paths/statistics",
    summary="获取下载器路径统计",
    response_model=CommonResponse,
    tags=["下载器路径维护"]
)
def get_path_statistics(
    downloader_id: Annotated[str, Path(description="下载器ID")],
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取下载器路径统计信息

    返回路径总数、默认路径数、活跃路径数等统计信息
    """
    try:
        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 验证下载器是否存在
        if not verify_downloader_exists(db, downloader_id):
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 3. 创建服务实例
        service = PathMaintenanceService(db)

        # 4. 获取统计信息
        stats = service.get_path_count(downloader_id)

        return CommonResponse(
            status="success",
            msg="获取路径统计成功",
            code="200",
            data=stats
        )

    except Exception as e:
        logger.error(f"获取路径统计失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )
