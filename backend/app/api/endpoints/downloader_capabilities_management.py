# -*- coding: utf-8 -*-
"""
下载器能力配置管理API

提供能力配置的更新、重置、删除等管理接口
"""
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Request, Path, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.responseVO import CommonResponse
from app.auth import utils
from app.database import get_db
from app.services.downloader_capabilities_manager import DownloaderCapabilitiesManager

router = APIRouter()
logger = logging.getLogger(__name__)


# ========== 请求模型 ==========

class UpdateCapabilitiesRequest(BaseModel):
    """更新能力配置请求模型"""
    supports_speed_scheduling: Optional[bool] = Field(None, description="是否支持分时段限速")
    supports_transfer_speed: Optional[bool] = Field(None, description="是否支持传输速度控制")
    supports_connection_limits: Optional[bool] = Field(None, description="是否支持连接限制")
    supports_queue_settings: Optional[bool] = Field(None, description="是否支持队列设置")
    supports_download_paths: Optional[bool] = Field(None, description="是否支持路径设置")
    supports_port_settings: Optional[bool] = Field(None, description="是否支持端口设置")
    supports_advanced_settings: Optional[bool] = Field(None, description="是否支持高级设置")
    supports_peer_limits: Optional[bool] = Field(None, description="是否支持Peer限制")
    set_manual_override: Optional[bool] = Field(True, description="是否设置为手动覆盖（设置为True后不再自动同步）")

    class Config:
        populate_by_name = True


# ========== 辅助函数 ==========

def verify_token(req: Request) -> tuple[bool, Optional[str]]:
    """验证JWT令牌

    Args:
        req: FastAPI请求对象

    Returns:
        tuple[bool, Optional[str]]: (是否验证成功, 错误消息)
    """
    token = req.headers.get("x-access-token")
    if not token:
        return False, "未认证"

    try:
        utils.verify_access_token(token)
        return True, None
    except Exception as e:
        return False, f"token验证失败: {str(e)}"


# ========== API端点 ==========

@router.put(
    "/{downloader_id}/capabilities",
    summary="更新下载器能力配置",
    response_model=CommonResponse,
    tags=["下载器能力管理"]
)
def update_downloader_capabilities(
    downloader_id: str = Path(..., description="下载器ID"),
    request_data: UpdateCapabilitiesRequest = Body(..., description="能力配置数据"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    更新下载器能力配置（用户手动修改）

    功能说明：
    - 更新指定的能力开关状态
    - 默认设置为手动覆盖模式（manual_override=True），后续不再自动同步
    - 支持部分更新（只修改提供的字段）

    使用场景：
    - 用户希望强制启用某个功能（即使下载器不支持）
    - 用户希望禁用某个功能（即使下载器支持）
    """
    try:
        # 1. JWT认证
        is_valid, error_msg = verify_token(req)
        if not is_valid:
            return CommonResponse(
                status="error",
                msg=error_msg,
                code="401",
                data=None
            )

        # 2. 构建能力字典（只包含非None的字段）
        capabilities_dict = request_data.model_dump(exclude_none=True, exclude={"set_manual_override"})

        if not capabilities_dict:
            return CommonResponse(
                status="error",
                msg="没有提供需要更新的能力配置",
                code="400",
                data=None
            )

        # 3. 更新能力配置
        manager = DownloaderCapabilitiesManager(db)
        db_capabilities = manager.update_capabilities(
            downloader_id=downloader_id,
            capabilities_dict=capabilities_dict,
            set_manual_override=request_data.set_manual_override
        )

        # 4. 获取更新后的能力字典
        capabilities_dict_result = db_capabilities.get_capabilities_dict()

        return CommonResponse(
            status="success",
            msg=f"更新能力配置成功，manual_override={request_data.set_manual_override}",
            code="200",
            data={
                "downloader_id": downloader_id,
                "capabilities": capabilities_dict_result,
                "manual_override": db_capabilities.manual_override,
                "updated_at": db_capabilities.updated_at.isoformat() if db_capabilities.updated_at else None
            }
        )

    except Exception as e:
        logger.error(f"更新下载器能力配置失败: {downloader_id}, 错误: {e}")
        return CommonResponse(
            status="error",
            msg=f"更新失败: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/{downloader_id}/capabilities/reset",
    summary="重置下载器能力配置",
    response_model=CommonResponse,
    tags=["下载器能力管理"]
)
def reset_downloader_capabilities(
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    重置下载器能力配置为默认值

    功能说明：
    - 删除现有的能力配置
    - 根据下载器类型创建新的默认配置
    - 清除手动覆盖标记（后续可以自动同步）

    使用场景：
    - 用户希望恢复默认行为
    - 清除手动覆盖，允许系统自动同步
    """
    try:
        # 1. JWT认证
        is_valid, error_msg = verify_token(req)
        if not is_valid:
            return CommonResponse(
                status="error",
                msg=error_msg,
                code="401",
                data=None
            )

        # 2. 重置能力配置
        manager = DownloaderCapabilitiesManager(db)
        db_capabilities = manager.reset_to_default(downloader_id=downloader_id)

        # 3. 获取重置后的能力字典
        capabilities_dict = db_capabilities.get_capabilities_dict()

        return CommonResponse(
            status="success",
            msg="重置能力配置成功",
            code="200",
            data={
                "downloader_id": downloader_id,
                "capabilities": capabilities_dict,
                "manual_override": db_capabilities.manual_override,
                "synced_from_downloader": db_capabilities.synced_from_downloader
            }
        )

    except Exception as e:
        logger.error(f"重置下载器能力配置失败: {downloader_id}, 错误: {e}")
        return CommonResponse(
            status="error",
            msg=f"重置失败: {str(e)}",
            code="500",
            data=None
        )


@router.delete(
    "/{downloader_id}/capabilities",
    summary="删除下载器能力配置",
    response_model=CommonResponse,
    tags=["下载器能力管理"]
)
def delete_downloader_capabilities(
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    删除下载器能力配置

    功能说明：
    - 删除数据库中的能力配置记录
    - 下次查询时会重新创建默认配置

    注意：
    - 此操作不可逆，请谨慎使用
    - 删除后会自动创建默认配置
    """
    try:
        # 1. JWT认证
        is_valid, error_msg = verify_token(req)
        if not is_valid:
            return CommonResponse(
                status="error",
                msg=error_msg,
                code="401",
                data=None
            )

        # 2. 删除能力配置
        manager = DownloaderCapabilitiesManager(db)
        deleted = manager.delete_capabilities(downloader_id=downloader_id)

        if deleted:
            return CommonResponse(
                status="success",
                msg="删除能力配置成功",
                code="200",
                data={"downloader_id": downloader_id}
            )
        else:
            return CommonResponse(
                status="success",
                msg="能力配置不存在",
                code="200",
                data={"downloader_id": downloader_id}
            )

    except Exception as e:
        logger.error(f"删除下载器能力配置失败: {downloader_id}, 错误: {e}")
        return CommonResponse(
            status="error",
            msg=f"删除失败: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/{downloader_id}/capabilities/sync",
    summary="从下载器同步能力配置",
    response_model=CommonResponse,
    tags=["下载器能力管理"]
)
def sync_downloader_capabilities(
    downloader_id: str = Path(..., description="下载器ID"),
    force: Optional[bool] = False,
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    从下载器同步能力配置到数据库

    功能说明：
    - 连接下载器获取实际能力
    - 更新数据库中的能力配置
    - 如果是手动覆盖模式，需要force=True才能更新

    参数：
    - force: 是否强制更新（忽略manual_override标记）

    使用场景：
    - 下载器功能升级后，同步新的能力
    - 强制覆盖手动配置
    """
    try:
        # 1. JWT认证
        is_valid, error_msg = verify_token(req)
        if not is_valid:
            return CommonResponse(
                status="error",
                msg=error_msg,
                code="401",
                data=None
            )

        # 2. 从下载器获取能力
        from app.downloader.models import BtDownloaders
        from app.services.downloader_settings_manager import DownloaderSettingsManager

        # 查询下载器信息
        downloader = db.query(BtDownloaders).filter(
            BtDownloaders.downloader_id == downloader_id,
            BtDownloaders.dr == 0
        ).first()

        if not downloader:
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 初始化设置管理器并获取能力
        try:
            settings_manager = DownloaderSettingsManager(downloader)
            downloader_capabilities = settings_manager.get_supported_capabilities()

            # 同步到数据库
            capabilities_manager = DownloaderCapabilitiesManager(db)
            db_capabilities = capabilities_manager.sync_from_downloader(
                downloader_id=downloader_id,
                downloader_capabilities=downloader_capabilities,
                force=force
            )

            # 获取同步后的能力字典
            capabilities_dict = db_capabilities.get_capabilities_dict()

            return CommonResponse(
                status="success",
                msg=f"同步能力配置成功，force={force}",
                code="200",
                data={
                    "downloader_id": downloader_id,
                    "capabilities": capabilities_dict,
                    "synced_from_downloader": db_capabilities.synced_from_downloader,
                    "last_sync_at": db_capabilities.last_sync_at.isoformat() if db_capabilities.last_sync_at else None,
                    "manual_override": db_capabilities.manual_override
                }
            )

        except Exception as downloader_error:
            return CommonResponse(
                status="error",
                msg=f"连接下载器失败: {str(downloader_error)}",
                code="503",
                data=None
            )

    except Exception as e:
        logger.error(f"同步下载器能力配置失败: {downloader_id}, 错误: {e}")
        return CommonResponse(
            status="error",
            msg=f"同步失败: {str(e)}",
            code="500",
            data=None
        )
