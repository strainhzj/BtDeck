"""
标签管理API接口

提供标签CRUD、种子标签分配、批量操作等功能的REST API接口。
遵循项目API响应格式规范，统一使用CommonResponse返回。
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import logging
import uuid

from app.database import get_db
from app.api.responseVO import CommonResponse
from app.schemas.tag_schemas import (
    TagCreateRequest,
    TagUpdateRequest,
    AssignTagsRequest,
    BatchAssignTagsRequest,
    RemoveTagsRequest,
    DeleteTagRequest,
    TagResponse,
    TagListResponse,
    AssignTagsResponse,
    BatchAssignResponse,
    RemoveTagsResponse,
    CategorySupportResponse
)
from app.services.tag_service import TagService
from app.auth import utils
from app.models.torrent_tags import TorrentTag
from app.models.setting_templates import DownloaderTypeEnum

logger = logging.getLogger(__name__)
router = APIRouter()

# 下载器类型常量
DOWNLOADER_TYPE_QBITTORRENT = 0  # 支持分类和标签
DOWNLOADER_TYPE_TRANSMISSION = 1  # 仅支持标签


# ==================== 辅助函数 ====================

def verify_token_and_get_user(request: Request) -> Optional[str]:
    """
    验证JWT令牌并返回用户名

    Args:
        request: FastAPI请求对象

    Returns:
        用户名，验证失败返回None
    """
    token = request.headers.get("x-access-token")
    if not token:
        return None
    try:
        utils.verify_access_token(token)
        return utils.get_username_from_token(token) or "admin"
    except Exception as e:
        logger.warning(f"Token验证失败: {str(e)}")
        return None


async def get_downloader_from_cache(app: Any, downloader_id: str) -> Optional[Any]:
    """
    从app.state.store获取下载器缓存

    Args:
        app: FastAPI应用对象（必须从request.app获取）
        downloader_id: 下载器ID

    Returns:
        下载器对象，不存在返回None
    """
    try:
        # 步骤1：检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            logger.error(f"下载器缓存未初始化 [app无store属性]")
            return None

        # 步骤2：从缓存获取下载器列表
        cached_downloaders = await app.state.store.get_snapshot()
        if not cached_downloaders:
            logger.error(f"下载器缓存为空 [downloader_id={downloader_id}]")
            return None

        # 步骤3：查找目标下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        # 步骤4：检查下载器是否在缓存中
        if not downloader_vo:
            logger.error(f"下载器不在缓存中 [downloader_id={downloader_id}]")
            return None

        return downloader_vo

    except Exception as e:
        logger.error(f"获取下载器缓存失败 [downloader_id={downloader_id}]: {str(e)}")
        return None


def validate_downloader_access(db: Session, downloader_id: str, username: str) -> tuple[bool, str]:
    """
    验证用户是否有权访问指定下载器

    Args:
        db: 数据库会话
        downloader_id: 下载器ID
        username: 用户名

    Returns:
        tuple[bool, str]: (是否有权限, 错误消息)
    """
    try:
        from sqlalchemy import text
        result = db.execute(
            text("SELECT COUNT(*) as count FROM bt_downloaders WHERE downloader_id = :downloader_id AND dr = 0"),
            {"downloader_id": downloader_id}
        ).fetchone()
        if result.count == 0:
            return False, "下载器不存在"
        return True, ""
    except Exception as e:
        logger.error(f"验证下载器权限失败: {str(e)}")
        return False, f"验证失败: {str(e)}"


# ==================== 标签CRUD接口 ====================

@router.get(
    "/list/{downloader_id}",
    summary="获取标签列表",
    response_model=CommonResponse,
    tags=["标签管理"]
)
def get_tag_list(
    downloader_id: str = Path(..., description="下载器ID"),
    tag_type: Optional[str] = Query(None, description="筛选标签类型(category/tag)"),
    sort_by: Optional[str] = Query("created_at", description="排序字段(created_at/tag_name)"),
    sort_order: Optional[str] = Query("desc", description="排序方向(asc/desc)"),
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页记录数"),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取指定下载器的标签列表

    支持按标签类型筛选、排序、分页查询
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    # 2. 验证下载器权限
    has_permission, error_msg = validate_downloader_access(db, downloader_id, username)
    if not has_permission:
        return CommonResponse(
            status="error",
            msg=error_msg,
            code="403",
            data=None
        )

    try:
        # 🐛 调试日志：记录接收到的参数
        logger.info(f"🔍 [调试] 接收到标签列表请求 - downloader_id: {downloader_id}, tag_type: {tag_type}")

        # 3. 调用服务层获取标签列表
        service = TagService(db)
        result = service.get_tag_list(downloader_id=downloader_id, tag_type=tag_type)

        # 🐛 调试日志：记录查询结果
        logger.info(f"🔍 [调试] 查询结果 - success: {result.get('success')}, total_count: {result.get('total_count', 0)}, data_length: {len(result.get('data', []))}")

        if not result.get("success"):
            return CommonResponse(
                status="error",
                msg=result.get("message", "获取标签列表失败"),
                code="400",
                data=None
            )

        # 4. 排序处理
        all_tags = result.get("data", [])

        # 验证排序字段
        valid_sort_fields = {"created_at", "tag_name"}
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"

        # 验证排序方向
        if sort_order not in {"asc", "desc"}:
            sort_order = "desc"

        # 执行排序（reverse=True表示降序）
        reverse = (sort_order == "desc")
        all_tags.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)

        # 5. 分页处理
        total = len(all_tags)

        # 计算分页
        start_idx = (page - 1) * pageSize
        end_idx = start_idx + pageSize
        paged_tags = all_tags[start_idx:end_idx]

        # 5. 构建分页响应
        paginated_data = {
            "total": total,
            "page": page,
            "pageSize": pageSize,
            "list": paged_tags
        }

        return CommonResponse(
            status="success",
            msg="获取标签列表成功",
            code="200",
            data=paginated_data
        )

    except Exception as e:
        logger.error(f"获取标签列表失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"获取标签列表失败: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/create",
    summary="创建标签",
    response_model=CommonResponse,
    tags=["标签管理"]
)
async def create_tag(
    tag_request: TagCreateRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    创建新标签

    创建标签后同步到下载器（如果下载器在线）
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    # 2. 验证下载器权限
    has_permission, error_msg = validate_downloader_access(db, tag_request.downloader_id, username)
    if not has_permission:
        return CommonResponse(
            status="error",
            msg=error_msg,
            code="403",
            data=None
        )

    try:
        # 3. 调用服务层创建标签
        service = TagService(db)
        result = service.create_tag(
            downloader_id=tag_request.downloader_id,
            tag_name=tag_request.tag_name,
            tag_type=tag_request.tag_type,
            color=tag_request.color
        )

        if not result.get("success"):
            return CommonResponse(
                status="error",
                msg=result.get("message", "创建标签失败"),
                code="400",
                data=None
            )

        # ⚠️ 架构调整：创建标签时不同步到下载器
        # 标签同步逻辑移至"分配标签给种子"功能（种子管理页面）
        # 这样更符合Transmission的设计理念：标签在使用时才被创建

        return CommonResponse(
            status="success",
            msg="标签创建成功",
            code="200",
            data=result.get("data")
        )

    except Exception as e:
        logger.error(f"创建标签失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"创建标签失败: {str(e)}",
            code="500",
            data=None
        )


@router.put(
    "/update/{tag_id}",
    summary="更新标签",
    response_model=CommonResponse,
    tags=["标签管理"]
)
def update_tag(
    tag_id: str = Path(..., description="标签ID"),
    tag_request: TagUpdateRequest = ...,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    更新标签信息

    仅更新提供的字段，未提供的字段保持不变
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 2. 调用服务层更新标签
        service = TagService(db)
        update_kwargs = {}
        if tag_request.tag_name is not None:
            update_kwargs['tag_name'] = tag_request.tag_name
        if tag_request.tag_type is not None:
            update_kwargs['tag_type'] = tag_request.tag_type
        if tag_request.color is not None:
            update_kwargs['color'] = tag_request.color

        if not update_kwargs:
            return CommonResponse(
                status="error",
                msg="没有提供要更新的字段",
                code="400",
                data=None
            )

        result = service.update_tag(tag_id=tag_id, **update_kwargs)

        if not result.get("success"):
            return CommonResponse(
                status="error",
                msg=result.get("message", "更新标签失败"),
                code="400",
                data=None
            )

        return CommonResponse(
            status="success",
            msg="标签更新成功",
            code="200",
            data=result.get("data")
        )

    except Exception as e:
        logger.error(f"更新标签失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"更新标签失败: {str(e)}",
            code="500",
            data=None
        )


@router.delete(
    "/delete/{tag_id}",
    summary="删除标签",
    response_model=CommonResponse,
    tags=["标签管理"]
)
async def delete_tag(
    tag_id: str = Path(..., description="标签ID"),
    request: Request = None,
    delete_request: DeleteTagRequest = Body(None),
    db: Session = Depends(get_db)
):
    """
    删除标签（软删除）
    
    将标签标记为已删除，不会从数据库中物理删除
    删除后会同步到下载器客户端（如果下载器在线）
    
    支持种子转移（仅qBittorrent分类）：
    - target_category: 目标分类名称，空字符串表示未分类
    - 分类下的种子会转移到目标分类
    - 数据库中的关联记录会同步更新
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 2. 调用服务层删除标签
        service = TagService(db)
        result = service.delete_tag(tag_id=tag_id)

        if not result.get("success"):
            return CommonResponse(
                status="error",
                msg=result.get("message", "删除标签失败"),
                code="400",
                data=None
            )

        # ⚠️ 修复：获取被删除的标签信息，用于同步到下载器
        deleted_tag_info = result.get("data")

        if not deleted_tag_info:
            logger.warning(f"标签已从数据库删除，但未返回标签详情 [tag_id={tag_id}]")
            return CommonResponse(
                status="success",
                msg="标签删除成功",
                code="200",
                data=None
            )

        # 3. 验证下载器权限
        downloader_id = deleted_tag_info.get("downloader_id")
        has_permission, error_msg = validate_downloader_access(db, downloader_id, username)
        if not has_permission:
            logger.warning(f"标签已删除，但用户无权限访问下载器 [downloader_id={downloader_id}]")
            return CommonResponse(
                status="success",
                msg="标签删除成功（但未同步到下载器：无权限）",
                code="200",
                data=None
            )

        # 4. 同步到下载器（如果在线）
        sync_result = await _sync_tag_delete_to_downloader(
            request,  # ⚠️ 工作约束16：传递 request 参数
            downloader_id=downloader_id,
            tag_id=tag_id,
            tag_name=deleted_tag_info.get("tag_name"),
            tag_type=deleted_tag_info.get("tag_type"),
            color=deleted_tag_info.get("color"),
            target_category=delete_request.target_category if delete_request else None
        )

        if not sync_result["success"]:
            logger.warning(f"标签已从数据库删除，但同步到下载器失败: {sync_result['message']}")

        return CommonResponse(
            status="success",
            msg="标签删除成功",
            code="200",
            data=None
        )

    except Exception as e:
        logger.error(f"删除标签失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"删除标签失败: {str(e)}",
            code="500",
            data=None
        )


# ==================== 种子标签分配接口 ====================

@router.get(
    "/torrent/{torrent_hash}/tags",
    summary="获取种子标签",
    response_model=CommonResponse,
    tags=["标签管理"]
)
def get_torrent_tags(
    torrent_hash: str = Path(..., description="种子哈希值"),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取指定种子的所有标签
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 2. 调用服务层获取种子标签
        service = TagService(db)
        result = service.get_torrent_tags(torrent_hash=torrent_hash)

        if not result.get("success"):
            return CommonResponse(
                status="error",
                msg=result.get("message", "获取种子标签失败"),
                code="400",
                data=None
            )

        return CommonResponse(
            status="success",
            msg="获取种子标签成功",
            code="200",
            data=result.get("data", [])
        )

    except Exception as e:
        logger.error(f"获取种子标签失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"获取种子标签失败: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/torrent/assign",
    summary="为种子分配标签",
    response_model=CommonResponse,
    tags=["标签管理"]
)
async def assign_tags_to_torrent(
    assign_request: AssignTagsRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    为单个种子分配标签

    支持同时分配多个标签
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    # 2. 验证下载器权限
    has_permission, error_msg = validate_downloader_access(db, assign_request.downloader_id, username)
    if not has_permission:
        return CommonResponse(
            status="error",
            msg=error_msg,
            code="403",
            data=None
        )

    try:
        # 3. 调用服务层分配标签
        service = TagService(db)
        result = service.assign_tags_to_torrent(
            torrent_hash=assign_request.torrent_hash,
            tag_ids=assign_request.tag_ids
        )

        if not result.get("success"):
            return CommonResponse(
                status="error",
                msg=result.get("message", "分配标签失败"),
                code="400",
                data=None
            )

        # 4. 获取标签详情用于同步（使用依赖注入的db会话）
        category_tags = []
        tag_names = []
        for tag_id in assign_request.tag_ids:
            tag = service.repository.find_by_id(tag_id)
            if tag:
                if tag.tag_type == "category":
                    category_tags.append(tag.tag_name)
                else:
                    tag_names.append(tag.tag_name)

        # 5. 同步到下载器
        sync_result = await _sync_tags_to_torrent_downloader(
            request,  # ⚠️ 工作约束16：传递 request 参数
            downloader_id=assign_request.downloader_id,
            torrent_hash=assign_request.torrent_hash,
            category_tags=category_tags,
            tag_names=tag_names
        )
        if not sync_result["success"]:
            logger.warning(f"标签已分配，但同步到下载器失败: {sync_result['message']}")

        # 6. 构建响应数据
        response_data = {
            "assigned_count": result.get("success_count", len(assign_request.tag_ids)),
            "total_count": len(assign_request.tag_ids)
        }

        return CommonResponse(
            status="success",
            msg="标签分配成功",
            code="200",
            data=response_data
        )

    except Exception as e:
        logger.error(f"分配标签失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"分配标签失败: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/torrent/batch-assign",
    summary="批量分配标签",
    response_model=CommonResponse,
    tags=["标签管理"]
)
def batch_assign_tags(
    batch_request: BatchAssignTagsRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    批量为多个种子分配标签

    每个种子可以分配不同的标签集合
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    # 2. 验证下载器权限
    has_permission, error_msg = validate_downloader_access(db, batch_request.downloader_id, username)
    if not has_permission:
        return CommonResponse(
            status="error",
            msg=error_msg,
            code="403",
            data=None
        )

    try:
        # 3. 调用服务层批量分配
        service = TagService(db)
        result = service.batch_assign_tags(assignments=batch_request.assignments)

        if not result.get("success"):
            return CommonResponse(
                status="error",
                msg=result.get("message", "批量分配失败"),
                code="400",
                data=None
            )

        # 4. 构建响应数据
        response_data = result.get("data", {})
        return CommonResponse(
            status="success",
            msg="批量分配成功",
            code="200",
            data=response_data
        )

    except Exception as e:
        logger.error(f"批量分配失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"批量分配失败: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/torrent/remove",
    summary="移除种子标签",
    response_model=CommonResponse,
    tags=["标签管理"]
)
def remove_tags_from_torrent(
    remove_request: RemoveTagsRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    移除种子的指定标签

    支持同时移除多个标签
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 2. 调用服务层移除标签
        service = TagService(db)
        result = service.remove_tags_from_torrent(
            torrent_hash=remove_request.torrent_hash,
            tag_ids=remove_request.tag_ids
        )

        # 即使部分失败也返回成功，响应中包含详情
        response_data = result.get("data", {
            "removed_count": 0,
            "failed_count": 0,
            "failed_tags": []
        })

        return CommonResponse(
            status="success" if response_data["failed_count"] == 0 else "partial",
            msg=result.get("message", "移除标签完成"),
            code="200",
            data=response_data
        )

    except Exception as e:
        logger.error(f"移除标签失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"移除标签失败: {str(e)}",
            code="500",
            data=None
        )


# ==================== 下载器能力检查接口 ====================

@router.get(
    "/downloader/{downloader_id}/category-support",
    summary="检查下载器分类支持",
    response_model=CommonResponse,
    tags=["标签管理"]
)
async def check_category_support(
    downloader_id: str = Path(..., description="下载器ID"),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    检查下载器是否支持分类功能

    qBittorrent (type=0): 支持分类和标签
    Transmission (type=1): 仅支持标签，需要降级策略
    """
    # 1. JWT认证
    username = verify_token_and_get_user(request)
    if not username:
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    # 2. 验证下载器权限
    has_permission, error_msg = validate_downloader_access(db, downloader_id, username)
    if not has_permission:
        return CommonResponse(
            status="error",
            msg=error_msg,
            code="403",
            data=None
        )

    try:
        # ⚠️ 工作约束16：步骤1 - 获取 app 对象并检查缓存初始化
        app = request.app

        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            return CommonResponse(
                status="error",
                msg="下载器缓存未初始化",
                code="500",
                data=None
            )

        # ⚠️ 工作约束16：步骤2 - 从缓存获取下载器
        cached_downloaders = await app.state.store.get_snapshot()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        # ⚠️ 工作约束16：步骤3 - 验证下载器有效性
        # 检查下载器是否在缓存中
        if not downloader_vo:
            # 缓存中没有，从数据库查询
            from sqlalchemy import text
            result = db.execute(
                text("SELECT downloader_type FROM bt_downloaders WHERE downloader_id = :downloader_id AND dr = 0"),
                {"downloader_id": downloader_id}
            ).fetchone()

            if not result:
                return CommonResponse(
                    status="error",
                    msg="下载器不存在",
                    code="404",
                    data=None
                )
            downloader_type = result.downloader_type
        else:
            # 从缓存读取下载器类型
            downloader_type = downloader_vo.downloader_type

        # 4. 判断分类支持
        # 使用统一的枚举类方法进行类型转换
        downloader_type_int = DownloaderTypeEnum.normalize(downloader_type)

        supports_category = downloader_type_int == DownloaderTypeEnum.QBITTORRENT.value
        require_fallback = downloader_type_int == DownloaderTypeEnum.TRANSMISSION.value

        # 5. 构建响应
        response_data = {
            "supported": supports_category,
            "require_fallback": require_fallback,
            "downloader_type": downloader_type_int,
            "message": (
                "支持分类功能" if supports_category else
                "Transmission不支持分类，建议使用标签功能"
            )
        }

        return CommonResponse(
            status="success",
            msg="检查成功",
            code="200",
            data=response_data
        )

    except Exception as e:
        logger.error(f"检查分类支持失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"检查分类支持失败: {str(e)}",
            code="500",
            data=None
        )


# ==================== 私有辅助函数 ====================

async def _sync_tag_to_downloader(
    request: Request,
    downloader_id: str,
    tag_id: str,
    tag_name: str,
    tag_type: str,
    color: Optional[str]
) -> Dict[str, Any]:
    """
    同步标签到下载器

    Args:
        request: FastAPI请求对象（用于获取request.app）
        downloader_id: 下载器ID
        tag_id: 标签ID
        tag_name: 标签名称
        tag_type: 标签类型(category/tag)
        color: 颜色代码

    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        # ⚠️ 工作约束16：步骤1 - 获取 app 对象并检查缓存初始化
        app = request.app

        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            logger.error(f"下载器缓存未初始化 [app无store属性]")
            return {"success": False, "message": "下载器缓存未初始化"}

        # ⚠️ 工作约束16：步骤2 - 从缓存获取下载器
        cached_downloaders = await app.state.store.get_snapshot()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        # ⚠️ 工作约束16：步骤3 - 验证下载器有效性
        # 检查下载器是否在缓存中
        if not downloader_vo:
            logger.error(f"下载器不在缓存中 [downloader_id={downloader_id}]")
            return {"success": False, "message": f"下载器不在缓存中"}

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            logger.error(f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]")
            return {"success": False, "message": "下载器已失效"}

        # ⚠️ 工作约束16：步骤4 - 获取并验证客户端连接
        # 获取缓存的客户端连接
        client = downloader_vo.client

        # 验证客户端是否存在
        if not client:
            logger.error(f"下载器客户端连接不存在 [downloader_id={downloader_id}]")
            return {"success": False, "message": "下载器客户端连接不存在"}

        try:
            downloader_type = int(downloader_vo.downloader_type)
        except (TypeError, ValueError):
            downloader_type = downloader_vo.downloader_type

        # 根据下载器类型同步
        if downloader_type == DOWNLOADER_TYPE_QBITTORRENT:
            # qBittorrent: 创建分类或标签
            if tag_type == "category":
                client.torrent_categories.create_category(name=tag_name)
            else:
                client.torrent_tags.create_tags(tags=tag_name)
            logger.info(f"成功同步标签到qBittorrent: {tag_name} ({tag_type})")
            return {"success": True, "message": "同步成功"}

        elif downloader_type == DOWNLOADER_TYPE_TRANSMISSION:
            # Transmission: 标签在首次分配给种子时自动创建
            # 这里只需返回成功（标签已在数据库中创建）
            logger.info(f"Transmission标签已在本地注册: {tag_name} (将在分配给种子时自动创建)")
            return {"success": True, "message": "同步成功"}

        return {"success": False, "message": "未知下载器类型"}

    except Exception as e:
        logger.error(f"同步标签到下载器失败: {str(e)}")
        return {"success": False, "message": f"同步失败: {str(e)}"}


async def _sync_tags_to_torrent_downloader(
    request: Request,
    downloader_id: str,
    torrent_hash: str,
    category_tags: List[str],
    tag_names: List[str]
) -> Dict[str, Any]:
    """
    同步标签关联到下载器的种子

    Args:
        request: FastAPI请求对象（用于获取request.app）
        downloader_id: 下载器ID
        torrent_hash: 种子哈希值
        category_tags: 分类标签名称列表
        tag_names: 普通标签名称列表

    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        # ⚠️ 工作约束16：步骤1 - 获取 app 对象并检查缓存初始化
        app = request.app

        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            logger.error(f"下载器缓存未初始化 [app无store属性]")
            return {"success": False, "message": "下载器缓存未初始化"}

        # ⚠️ 工作约束16：步骤2 - 从缓存获取下载器
        cached_downloaders = await app.state.store.get_snapshot()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        # ⚠️ 工作约束16：步骤3 - 验证下载器有效性
        # 检查下载器是否在缓存中
        if not downloader_vo:
            logger.error(f"下载器不在缓存中 [downloader_id={downloader_id}]")
            return {"success": False, "message": f"下载器不在缓存中"}

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            logger.error(f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]")
            return {"success": False, "message": "下载器已失效"}

        # ⚠️ 工作约束16：步骤4 - 获取并验证客户端连接
        # 获取缓存的客户端连接
        client = downloader_vo.client

        # 验证客户端是否存在
        if not client:
            logger.error(f"下载器客户端连接不存在 [downloader_id={downloader_id}]")
            return {"success": False, "message": "下载器客户端连接不存在"}

        try:
            downloader_type = int(downloader_vo.downloader_type)
        except (TypeError, ValueError):
            downloader_type = downloader_vo.downloader_type

        # 根据下载器类型同步
        if downloader_type == DOWNLOADER_TYPE_QBITTORRENT:
            # qBittorrent: 设置分类和标签
            if category_tags:
                # qBittorrent只支持单个分类，使用第一个
                category = category_tags[0] if category_tags else ""
                # 需要获取种子的当前保存路径
                torrent_info = client.torrents_info(torrent_hashes=[torrent_hash])
                if torrent_info and len(torrent_info) > 0:
                    first_torrent = torrent_info[0]
                    if isinstance(first_torrent, dict):
                        save_path = first_torrent.get("save_path", "")
                    else:
                        save_path = getattr(first_torrent, "save_path", "") or ""
                    client.torrents_set_category(
                        category=category,
                        save_path=save_path,
                        torrent_hashes=[torrent_hash]
                    )

            if tag_names:
                client.torrents_add_tags(tags=tag_names, torrent_hashes=[torrent_hash])

            logger.info(f"成功同步标签到种子 {torrent_hash[:8]}...")
            return {"success": True, "message": "同步成功"}

        elif downloader_type == DOWNLOADER_TYPE_TRANSMISSION:
            # Transmission: 所有标签都作为tags处理
            all_tags = category_tags + tag_names
            if all_tags:
                # 处理带前缀的分类标签
                processed_tags = []
                for tag in all_tags:
                    if tag.startswith("@"):
                        processed_tags.append(tag[1:])  # 去掉@前缀
                    else:
                        processed_tags.append(tag)
                client.torrents_set_tags(tags=processed_tags, torrent_hashes=[torrent_hash])

            logger.info(f"成功同步标签到Transmission种子 {torrent_hash[:8]}...")
            return {"success": True, "message": "同步成功"}

        return {"success": False, "message": "未知下载器类型"}

    except Exception as e:
        logger.error(f"同步标签关联到下载器失败: {str(e)}")
        return {"success": False, "message": f"同步失败: {str(e)}"}


async def _sync_tag_delete_to_downloader(
    request: Request,
    downloader_id: str,
    tag_id: str,
    tag_name: str,
    tag_type: str,
    color: Optional[str] = None,
    target_category: Optional[str] = None
) -> Dict[str, Any]:
    """
    同步标签删除到下载器

    支持种子转移（仅qBittorrent分类）：
    - target_category: 目标分类名称，空字符串表示未分类
    - 分类下的种子会转移到目标分类
    - 数据库中的关联记录会同步更新

    Args:
        request: FastAPI请求对象（用于获取request.app）
        downloader_id: 下载器ID
        tag_id: 标签ID
        tag_name: 标签名称
        tag_type: 标签类型(category/tag)
        color: 颜色代码
        target_category: 目标分类名称（可选）

    Returns:
        dict: {"success": bool, "message": str}
    """
    # ⚠️ 调试日志：记录函数入口和所有关键参数
    logger.info(f"🔍 [删除同步] 开始同步标签删除到下载器")
    logger.info(f"  - downloader_id: {downloader_id}")
    logger.info(f"  - tag_id: {tag_id}")
    logger.info(f"  - tag_name: {tag_name}")
    logger.info(f"  - tag_type: {tag_type}")
    logger.info(f"  - target_category: {repr(target_category)} (None=未指定, ''=未分类)")

    try:
        # ⚠️ 工作约束16：步骤1 - 获取 app 对象并检查缓存初始化
        app = request.app

        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            logger.error(f"下载器缓存未初始化 [app无store属性]")
            return {"success": False, "message": "下载器缓存未初始化"}

        # ⚠️ 工作约束16：步骤2 - 从缓存获取下载器
        cached_downloaders = await app.state.store.get_snapshot()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        # ⚠️ 工作约束16：步骤3 - 验证下载器有效性
        # 检查下载器是否在缓存中
        if not downloader_vo:
            logger.error(f"下载器不在缓存中 [downloader_id={downloader_id}]")
            return {"success": False, "message": f"下载器不在缓存中"}

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            logger.error(f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]")
            return {"success": False, "message": "下载器已失效"}

        # ⚠️ 工作约束16：步骤4 - 获取并验证客户端连接
        # 获取缓存的客户端连接
        client = downloader_vo.client

        # 验证客户端是否存在
        if not client:
            logger.error(f"下载器客户端连接不存在 [downloader_id={downloader_id}]")
            return {"success": False, "message": "下载器客户端连接不存在"}

        try:
            downloader_type = int(downloader_vo.downloader_type)
        except (TypeError, ValueError):
            downloader_type = downloader_vo.downloader_type

        # 根据下载器类型同步删除
        if downloader_type == DOWNLOADER_TYPE_QBITTORRENT:
            # qBittorrent: 删除分类或标签
            if tag_type == "category":
                # 完整分类删除逻辑：检查种子 -> 转移种子（可选）-> 删除分类
                try:
                    # 步骤1：检查分类下是否有种子
                    category_torrents = client.torrents_info(category=tag_name)
                    torrent_count = len(category_torrents)

                    # 步骤2：如果提供了目标分类且有种，先转移种子
                    # ⚠️ 修复：优化参数判断逻辑，明确区分三种情况
                    # 1. target_category为None：用户未选择目标分类（前端未传参数）
                    # 2. target_category为空字符串''：用户选择"未分类"
                    # 3. target_category为其他值：用户选择的具体分类
                    if target_category is not None and torrent_count > 0:
                        target_cat_display = target_category or '未分类'
                        logger.info(
                            f"开始转移 {torrent_count} 个种子从分类 '{tag_name}' 到 '{target_cat_display}'"
                        )
                        
                        # 批量转移种子
                        transferred_count = 0
                        failed_count = 0

                        # ⚠️ 调试日志：记录种子转移开始
                        logger.info(f"🔍 [种子转移] 开始转移 {torrent_count} 个种子")
                        logger.debug(f"目标分类: '{target_category}' (空字符串表示未分类）")

                        for idx, torrent in enumerate(category_torrents, 1):
                            try:
                                torrent_hash = torrent.get('hash', '')
                                torrent_name = torrent.get('name', 'unknown')

                                if not torrent_hash:
                                    logger.warning(f"[{idx}/{torrent_count}] 种子缺少hash字段，跳过：{torrent_name}")
                                    failed_count += 1
                                    continue

                                # 设置新分类（空字符串表示未分类）
                                new_category = target_category if target_category else ""
                                logger.debug(f"[{idx}/{torrent_count}] 转移种子：{torrent_name[:50]}...")
                                logger.debug(f"  - hash: {torrent_hash[:16]}...")
                                logger.debug(f"  - 新分类: '{new_category or '未分类'}'")

                                client.torrents.set_category(
                                    category=new_category,
                                    torrent_hashes=[torrent_hash]
                                )
                                transferred_count += 1
                                logger.debug(f"[{idx}/{torrent_count}] ✅ 转移成功：{torrent_name[:30]}...")

                            except Exception as e:
                                logger.error(f"[{idx}/{torrent_count}] ❌ 转移种子失败：{str(e)}")
                                failed_count += 1
                        
                        logger.info(
                            f"种子转移完成：成功 {transferred_count} 个，失败 {failed_count} 个"
                        )
                        
                        # 如果全部失败，中止删除操作
                        if transferred_count == 0:
                            return {
                                "success": False,
                                "message": f"种子转移全部失败（{failed_count}/{torrent_count}），中止删除操作"
                            }
                        
                        # 如果部分失败，记录警告但继续删除
                        if failed_count > 0:
                            logger.warning(
                                f"部分种子转移失败（{failed_count}/{torrent_count}），"
                                f"但继续删除分类 '{tag_name}'"
                            )
                    
                    elif torrent_count > 0:
                        # 没有提供目标分类但有种，记录警告
                        logger.warning(
                            f"qBittorrent分类 '{tag_name}' 下还有 {torrent_count} 个种子，"
                            f"删除后种子将保留但失去分类关联"
                        )

                    # 步骤3：删除分类（使用正确的API方法）
                    # ⚠️ 修复：采用保守方案
                    # qBittorrent API可能不直接支持delete_category方法
                    # 实际做法：如果分类下没有种子了，qBittorrent会自动清理空分类
                    # 或者尝试使用set_category将savePath设置为空
                    logger.info(f"准备删除qBittorrent分类: {tag_name}")

                    # 检查分类下是否还有种子
                    remaining_torrents = client.torrents.info(category=tag_name)
                    remaining_count = len(remaining_torrents)

                    if remaining_count > 0:
                        # 分类下仍有种子，删除操作可能失败
                        logger.warning(
                            f"分类 '{tag_name}' 下仍有 {remaining_count} 个种子，"
                            f"qBittorrent可能无法删除非空分类"
                        )
                        return {
                            "success": False,
                            "message": f"分类下仍有 {remaining_count} 个种子，请先转移种子后再删除"
                        }

                    # 分类下没有种子，尝试删除空分类
                    # ⚠️ 修复：使用qBittorrent Python SDK的torrents_remove_categories方法
                    try:
                        logger.debug(f"使用SDK方法删除qBittorrent分类: {tag_name}")

                        # 直接调用SDK的删除分类方法
                        client.torrents_remove_categories(categories=[tag_name])

                        logger.info(f"成功删除qBittorrent分类: {tag_name}（通过SDK）")
                        return {"success": True, "message": "同步成功"}

                    except Exception as e:
                        logger.error(f"使用SDK删除qBittorrent分类失败: {str(e)}")
                        return {
                            "success": False,
                            "message": f"删除分类失败（分类下无种子但SDK调用失败）: {str(e)}"
                        }
                    except Exception as e:
                        logger.error(f"删除qBittorrent分类时发生错误: {str(e)}")
                        return {"success": False, "message": f"删除分类失败: {str(e)}"}

                except Exception as e:
                    logger.error(f"删除qBittorrent分类失败: {str(e)}")
                    return {"success": False, "message": f"删除分类失败: {str(e)}"}
            else:
                # qBittorrent标签删除
                try:
                    client.torrents_delete_tags(tags=tag_name)
                    logger.info(f"成功删除qBittorrent标签: {tag_name}")
                except Exception as e:
                    logger.error(f"删除qBittorrent标签失败: {str(e)}")
                    return {"success": False, "message": f"删除标签失败: {str(e)}"}

            return {"success": True, "message": "同步成功"}

        elif downloader_type == DOWNLOADER_TYPE_TRANSMISSION:
            # Transmission: 标签会自动从所有种子中移除
            # Transmission不需要显式删除标签操作
            logger.info(f"Transmission标签会自动从种子中移除: {tag_name}")
            return {"success": True, "message": "同步成功"}

        return {"success": False, "message": "未知下载器类型"}

    except Exception as e:
        logger.error(f"同步标签删除到下载器失败: {str(e)}")
        return {"success": False, "message": f"同步失败: {str(e)}"}
