# -*- coding: utf-8 -*-
"""
下载器能力探测API

提供获取下载器支持功能列表的接口，支持持久化能力配置
"""
import logging

from fastapi import APIRouter, Depends, Request, Path
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import utils
from app.database import get_db
from app.services.downloader_settings_manager import DownloaderSettingsManager
from app.services.downloader_capabilities_manager import DownloaderCapabilitiesManager
from app.downloader.models import BtDownloaders
from app.models.downloader_capabilities_vo import DownloaderCapabilitiesVO
from app.models.downloader_capabilities import DownloaderCapabilities as DownloaderCapabilitiesModel
from app.models.setting_templates import DownloaderTypeEnum

router = APIRouter()
logger = logging.getLogger(__name__)


# ========== 辅助函数 ==========

def _get_default_capabilities(downloader_type: int) -> dict:
    """
    根据下载器类型返回默认能力配置

    当下载器离线时，使用此函数提供默认配置，确保前端可以正常使用设置页面

    Args:
        downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）

    Returns:
        dict: 默认能力配置
    """
    # 使用枚举类规范化类型
    normalized_type = DownloaderTypeEnum.normalize(downloader_type)
    if normalized_type == DownloaderTypeEnum.QBITTORRENT:  # qBittorrent
        return {
            "schedule_speed": True,
            "transfer_speed": True,
            "connection_limits": True,
            "queue_settings": True,
            "download_paths": True,
            "advanced_settings": True
        }
    elif normalized_type == DownloaderTypeEnum.TRANSMISSION:  # Transmission
        return {
            "schedule_speed": True,  # ✅ Transmission支持(应用层定时任务实现)
            "transfer_speed": True,
            "connection_limits": True,
            "queue_settings": True,
            "download_paths": True,
            "advanced_settings": False  # Transmission 高级设置较少
        }
    else:
        return {}


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


# ========== API端点 ==========

@router.get(
    "/{downloader_id}/capabilities",
    summary="获取下载器支持的功能列表",
    response_model=CommonResponse,
    tags=["下载器能力"]
)
def get_downloader_capabilities(
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取指定下载器支持的功能列表

    返回下载器支持的功能，如速度控制、分时段限速、路径设置等
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

        # 3. 查询下载器信息
        downloader_sql = """
            SELECT downloader_id, nickname, host, port, username, password, downloader_type
            FROM bt_downloaders
            WHERE downloader_id = :downloader_id AND dr = 0
        """
        downloader_result = db.execute(text(downloader_sql), {"downloader_id": downloader_id}).fetchone()

        if not downloader_result:
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 4. 构建下载器对象
        downloader = BtDownloaders(
            downloader_id=downloader_result.downloader_id,
            nickname=downloader_result.nickname,
            host=downloader_result.host,
            port=downloader_result.port,
            username=downloader_result.username,
            password=downloader_result.password,
            downloader_type=downloader_result.downloader_type
        )

        # 5. 【优先】从数据库获取持久化能力配置
        try:
            capabilities_manager = DownloaderCapabilitiesManager(db)
            db_capabilities = capabilities_manager.get_capabilities(
                downloader_id=downloader_id,
                create_if_not_exists=True,
                default_for_type=downloader_result.downloader_type
            )

            # 如果数据库中存在配置，优先使用
            if db_capabilities:
                logger.info(f"从数据库获取能力配置: {downloader_id}, 手动覆盖={db_capabilities.manual_override}")

                # 构建能力字典
                capabilities_dict = db_capabilities.get_capabilities_dict()

                capabilities_vo = DownloaderCapabilitiesVO(
                    downloader_id=downloader_id,
                    downloader_type=downloader_result.downloader_type,
                    capabilities=capabilities_dict
                )

                return CommonResponse(
                    status="success",
                    msg="获取成功（从数据库）",
                    code="200",
                    data=capabilities_vo.model_dump(by_alias=True)
                )

        except Exception as e:
            logger.warning(f"从数据库获取能力配置失败: {downloader_id}, 错误: {e}")

        # 6. 【降级】如果数据库中没有配置，尝试从下载器实时获取
        try:
            manager = DownloaderSettingsManager(downloader)
            capabilities = manager.get_supported_capabilities()

            # 同步到数据库
            try:
                capabilities_manager.sync_from_downloader(
                    downloader_id=downloader_id,
                    downloader_capabilities=capabilities,
                    force=False
                )
                logger.info(f"从下载器同步能力配置到数据库成功: {downloader_id}")
            except Exception as sync_error:
                logger.warning(f"同步能力配置到数据库失败: {downloader_id}, 错误: {sync_error}")

            # 构建VO并返回
            capabilities_vo = DownloaderCapabilitiesVO(
                downloader_id=downloader_id,
                downloader_type=downloader_result.downloader_type,
                capabilities=capabilities
            )

            return CommonResponse(
                status="success",
                msg="获取成功（从下载器同步）",
                code="200",
                data=capabilities_vo.model_dump(by_alias=True)
            )

        except Exception as e:
            # 7. 【最后降级】下载器离线或连接失败时，返回数据库中的默认配置
            logger.warning(f"下载器离线，使用数据库默认能力配置: {downloader_result.nickname}, 错误: {e}")

            try:
                # 再次尝试从数据库获取（此时应该已经创建了默认配置）
                db_capabilities = capabilities_manager.get_capabilities(
                    downloader_id=downloader_id,
                    create_if_not_exists=True,
                    default_for_type=downloader_result.downloader_type
                )

                capabilities_dict = db_capabilities.get_capabilities_dict()

                capabilities_vo = DownloaderCapabilitiesVO(
                    downloader_id=downloader_id,
                    downloader_type=downloader_result.downloader_type,
                    capabilities=capabilities_dict
                )

                return CommonResponse(
                    status="success",
                    msg="下载器离线，使用数据库配置",
                    code="200",
                    data=capabilities_vo.model_dump(by_alias=True)
                )

            except Exception as db_error:
                logger.error(f"获取数据库能力配置失败: {downloader_id}, 错误: {db_error}")

                # 8. 【终极降级】使用硬编码的默认能力配置
                default_capabilities = _get_default_capabilities(downloader_result.downloader_type)

                capabilities_vo = DownloaderCapabilitiesVO(
                    downloader_id=downloader_id,
                    downloader_type=downloader_result.downloader_type,
                    capabilities=default_capabilities
                )

                return CommonResponse(
                    status="success",
                    msg="下载器离线，返回系统默认配置",
                    code="200",
                    data=capabilities_vo.model_dump(by_alias=True)
                )

    except Exception as e:
        logger.error(f"获取下载器能力失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )
