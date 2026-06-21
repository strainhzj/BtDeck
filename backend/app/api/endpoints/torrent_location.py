import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user, AuthenticatedUserInfo
from app.database import get_db
from app.schemas.torrent_location import SetLocationRequest

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 修改种子保存路径 ====================


@router.post("/set-location", response_model=CommonResponse)
async def set_torrent_location(
    location_request: SetLocationRequest,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    修改种子保存路径

    修改一个或多个种子在同一下载器内的保存路径。
    支持选择是否移动已下载的文件。

    认证：由 require_authenticated_user 统一处理（无 token / token 无效 → HTTP 401）。
    user_id 业务校验保留：旧 token 可能不含 user_id，此时仍拒绝。
    """
    # 业务校验：token 有效但 payload 缺 user_id（旧 token）时拒绝
    if not user_info.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None},
        )

    try:
        username = user_info.username

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
            user_id=user_info.user_id,
            username=username,
            app_state=app.state,
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
                    "error_message": result["error_message"],
                },
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
                    "error_message": result["error_message"],
                },
            )

    except Exception as e:
        logger.error(f"修改种子路径API异常: {str(e)}", exc_info=True)
        return CommonResponse(status="error", msg=f"服务器错误: {str(e)}", code="500", data=None)
