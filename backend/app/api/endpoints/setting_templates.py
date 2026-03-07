# -*- coding: utf-8 -*-
"""
配置模板管理API

提供配置模板的CRUD和应用接口
"""
import logging
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Path, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import utils
from app.database import get_db
from app.services.template_service import TemplateService
from app.downloader.models import BtDownloaders

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

@router.get(
    "",
    summary="获取模板列表",
    response_model=CommonResponse,
    tags=["配置模板"]
)
def get_setting_templates(
    req: Request = None,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    downloader_type: Optional[int] = Query(None, description="下载器类型过滤：0=qBittorrent, 1=Transmission"),
    is_system_default: Optional[bool] = Query(None, description="是否系统默认模板过滤")
):
    """
    获取配置模板列表

    支持分页、按下载器类型过滤、按是否系统默认过滤
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

        # 2. 获取用户ID
        user_id = get_current_user_id(token)

        # 3. 调用TemplateService
        service = TemplateService(db)
        filters = {}
        if downloader_type is not None:
            filters["downloader_type"] = downloader_type
        if is_system_default is not None:
            filters["is_system_default"] = is_system_default

        templates = service.list_templates(user_id=user_id, filters=filters)

        # 4. 分页处理
        total = len(templates)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_templates = templates[start:end]

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "total": total,
                "page": page,
                "pageSize": page_size,
                "list": paginated_templates
            }
        )

    except Exception as e:
        logger.error(f"获取模板列表失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "",
    summary="创建模板",
    response_model=CommonResponse,
    tags=["配置模板"]
)
async def create_setting_template(
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    创建新的配置模板

    用户可以创建自定义模板，系统默认模板只能通过系统初始化创建
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

        # 2. 获取用户ID
        user_id = get_current_user_id(token)
        if not user_id:
            return CommonResponse(
                status="error",
                msg="无法获取用户信息",
                code="401",
                data=None
            )

        # 3. 获取请求体数据
        try:
            body_data = await req.json()
        except Exception as e:
            logger.error(f"解析请求体失败: {e}")
            return CommonResponse(
                status="error",
                msg=f"请求体格式错误: {str(e)}",
                code="422",
                data=None
            )

        # 4. 构建模板数据
        template_data = {
            "name": body_data.get("name"),
            "description": body_data.get("description"),
            "downloader_type": body_data.get("downloaderType"),
            "template_config": body_data.get("templateConfig")
        }

        # 5. 调用TemplateService创建模板
        try:
            service = TemplateService(db)
            template = service.create_template(user_id, template_data)

            logger.info(f"创建模板成功: name={template_data['name']}, user_id={user_id}")

            return CommonResponse(
                status="success",
                msg="创建成功",
                code="200",
                data=template
            )

        except ValueError as e:
            logger.warning(f"创建模板失败（参数错误）: {e}")
            return CommonResponse(
                status="error",
                msg=str(e),
                code="422",
                data=None
            )

    except Exception as e:
        db.rollback()
        logger.error(f"创建模板失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.put(
    "/{template_id}",
    summary="更新模板",
    response_model=CommonResponse,
    tags=["配置模板"]
)
async def update_setting_template(
    template_id: int = Path(..., description="模板ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    更新配置模板

    系统默认模板不能更新
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

        # 2. 获取用户ID
        user_id = get_current_user_id(token)
        if not user_id:
            return CommonResponse(
                status="error",
                msg="无法获取用户信息",
                code="401",
                data=None
            )

        # 3. 获取请求体数据
        try:
            body_data = await req.json()
        except Exception as e:
            logger.error(f"解析请求体失败: {e}")
            return CommonResponse(
                status="error",
                msg=f"请求体格式错误: {str(e)}",
                code="422",
                data=None
            )

        # 4. 调用TemplateService更新模板
        try:
            service = TemplateService(db)
            template = service.update_template(template_id, user_id, body_data)

            logger.info(f"更新模板成功: template_id={template_id}")

            return CommonResponse(
                status="success",
                msg="更新成功",
                code="200",
                data=template
            )

        except ValueError as e:
            logger.warning(f"更新模板失败（参数错误）: {e}")
            # 根据错误消息返回不同的状态码
            if "不存在" in str(e):
                code = "404"
            elif "系统默认" in str(e) or "无权" in str(e):
                code = "403"
            else:
                code = "422"
            return CommonResponse(
                status="error",
                msg=str(e),
                code=code,
                data=None
            )

    except Exception as e:
        db.rollback()
        logger.error(f"更新模板失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.delete(
    "/{template_id}",
    summary="删除模板",
    response_model=CommonResponse,
    tags=["配置模板"]
)
def delete_setting_template(
    template_id: int = Path(..., description="模板ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    删除配置模板

    系统默认模板不能删除
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

        # 2. 获取用户ID
        user_id = get_current_user_id(token)
        if not user_id:
            return CommonResponse(
                status="error",
                msg="无法获取用户信息",
                code="401",
                data=None
            )

        # 3. 调用TemplateService删除模板
        try:
            service = TemplateService(db)
            service.delete_template(template_id, user_id)

            logger.info(f"删除模板成功: template_id={template_id}")

            return CommonResponse(
                status="success",
                msg="删除成功",
                code="200",
                data=None
            )

        except ValueError as e:
            logger.warning(f"删除模板失败（参数错误）: {e}")
            # 根据错误消息返回不同的状态码
            if "不存在" in str(e):
                code = "404"
            elif "系统默认" in str(e) or "无权" in str(e):
                code = "403"
            else:
                code = "400"
            return CommonResponse(
                status="error",
                msg=str(e),
                code=code,
                data=None
            )

    except Exception as e:
        db.rollback()
        logger.error(f"删除模板失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/{template_id}/apply/{downloader_id}",
    summary="应用模板到下载器",
    response_model=CommonResponse,
    tags=["配置模板"]
)
async def apply_template_to_downloader(
    template_id: int = Path(..., description="模板ID"),
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    将模板配置应用到下载器

    1. 将模板配置保存到下载器设置表
    2. 应用配置到下载器
    3. 如果模板包含分时段规则，同时创建规则记录
    4. 如果模板包含路径映射配置，询问用户是否应用
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

        # 2. 获取用户ID
        user_id = get_current_user_id(token)

        # 3. 获取请求体参数
        try:
            body_data = await req.json()
        except Exception as e:
            body_data = {}

        apply_path_mapping = body_data.get("apply_path_mapping", None)

        # 4. 调用TemplateService应用模板
        try:
            service = TemplateService(db)
            result = service.apply_template(
                template_id=template_id,
                downloader_id=downloader_id,
                user_id=user_id,
                override=True,
                apply_path_mapping=apply_path_mapping
            )

            if result["success"]:
                return CommonResponse(
                    status="success",
                    msg=result["message"],
                    code="200",
                    data={"downloader_id": downloader_id}
                )
            elif result.get("needs_path_mapping_confirmation"):
                # 需要用户确认路径映射
                return CommonResponse(
                    status="partial",
                    msg=result["message"],
                    code="206",  # Partial Content
                    data={
                        "downloader_id": downloader_id,
                        "needs_path_mapping_confirmation": True,
                        "has_path_mapping": True
                    }
                )
            else:
                return CommonResponse(
                    status="error",
                    msg=result["message"],
                    code="500",
                    data=None
                )

        except ValueError as e:
            logger.warning(f"应用模板失败（参数错误）: {e}")
            # 根据错误消息返回不同的状态码
            if "不存在" in str(e):
                code = "404"
            elif "不匹配" in str(e):
                code = "400"
            else:
                code = "422"
            return CommonResponse(
                status="error",
                msg=str(e),
                code=code,
                data=None
            )

    except Exception as e:
        db.rollback()
        logger.error(f"应用模板失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )
