import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import utils
from app.database import get_db
from app.schemas.torrent_location import SetLocationRequest

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 修改种子保存路径 ====================

@router.post("/set-location", response_model=CommonResponse)
async def set_torrent_location(
        request: Request,
        location_request: SetLocationRequest,
        db: Session = Depends(get_db)
):
    """
    修改种子保存路径

    修改一个或多个种子在同一下载器内的保存路径。
    支持选择是否移动已下载的文件。

    Args:
        request: FastAPI请求对象
        location_request: 位置修改请求参数
        db: 数据库会话

    Returns:
        CommonResponse: 操作结果
        {
            "code": "200",
            "msg": "成功提交2个种子路径修改请求",
            "data": {
                "success": true,
                "moved_count": 2,
                "failed_count": 0,
                "error_message": null
            },
            "status": "success"
        }
    """
    try:
        # 从请求头获取用户信息
        token = request.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        # 验证token并获取用户信息
        decoded = utils.verify_access_token(token)
        user_id = decoded.get("user_id")
        username = decoded.get("username", "unknown")

        if not user_id:
            return CommonResponse(
                status="error",
                msg="无效的访问令牌",
                code="401",
                data=None
            )

        # 导入服务层（避免循环导入）
        from app.services.torrent_location_service import TorrentLocationService
        from app.factory import app

        # 创建服务实例
        service = TorrentLocationService(db=db)

        # 调用服务修改路径
        result = await service.set_location(
            downloader_id=location_request.downloader_id,
            hashes=location_request.hashes,
            target_path=location_request.target_path,
            move_files=location_request.move_files,
            user_id=int(user_id),
            username=username,
            app_state=app.state
        )

        # 构建响应消息
        if result["success"]:
            msg = f"成功提交{result['moved_count']}个种子路径修改请求"
            if result["failed_count"] > 0:
                msg += f"，{result['failed_count']}个失败"

            return CommonResponse(
                status="success",
                msg=msg,
                code="200",
                data={
                    "success": True,
                    "moved_count": result["moved_count"],
                    "failed_count": result["failed_count"],
                    "error_message": result["error_message"]
                }
            )
        else:
            return CommonResponse(
                status="error",
                msg=result["error_message"] or "修改路径失败",
                code="500",
                data={
                    "success": False,
                    "moved_count": 0,
                    "failed_count": len(location_request.hashes),
                    "error_message": result["error_message"]
                }
            )

    except Exception as e:
        logger.error(f"修改种子路径API异常: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"服务器错误: {str(e)}",
            code="500",
            data=None
        )
