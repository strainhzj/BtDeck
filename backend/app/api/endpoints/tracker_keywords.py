"""
Tracker关键词CRUD API接口

提供关键词的创建、查询、更新、删除和批量操作功能

性能优化建议:
1. 速率限制: 建议添加slowapi或fastapi-limiter中间件限制API调用频率
   - 安装: pip install slowapi
   - 使用: @limiter.limit("100/minute") (每分钟最多100次请求)
2. 缓存: 查询接口可以使用Redis缓存热点数据
3. 数据库索引: 确保keyword和keyword_type字段有复合索引
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
import uuid
from datetime import datetime
import logging

from app.database import get_db
from app.api.responseVO import CommonResponse
from app.api.schemas.tracker_keywords import (
    TrackerKeywordCreate,
    TrackerKeywordUpdate,
    TrackerKeywordResponse,
    BatchOperationRequest
)
from app.torrents.models import TrackerKeywordConfig
from app.auth import utils
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", summary="创建关键词")
def create_keyword(
    keyword: TrackerKeywordCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    创建新的tracker关键词

    Args:
        keyword: 关键词数据
        request: 请求对象(用于JWT验证)
        db: 数据库会话
    """
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 额外验证参数长度，防止数据库错误
        if keyword.keyword and len(keyword.keyword) > 200:
            return CommonResponse(
                status="error",
                msg="关键词长度超过限制(最大200字符)",
                code="400",
                data=None
            )
        if keyword.language and len(keyword.language) > 10:
            return CommonResponse(
                status="error",
                msg="语言代码长度超过限制(最大10字符)",
                code="400",
                data=None
            )
        if keyword.category and len(keyword.category) > 50:
            return CommonResponse(
                status="error",
                msg="分类长度超过限制(最大50字符)",
                code="400",
                data=None
            )
        if keyword.description and len(keyword.description) > 200:
            return CommonResponse(
                status="error",
                msg="描述长度超过限制(最大200字符)",
                code="400",
                data=None
            )

        # 检查关键词是否已存在 (keyword全局唯一,不区分keyword_type和dr状态)
        existing = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword == keyword.keyword
        ).first()

        if existing:
            if existing.dr == 0:
                # 活跃记录，不允许创建
                return CommonResponse(
                    status="error",
                    msg=f"该关键词已存在于{existing.keyword_type}池中",
                    code="400",
                    data=None
                )
            else:
                # 已删除记录(dr=1)，恢复它
                logger.info(f"恢复已删除的关键词: {existing.keyword_id}, keyword={keyword.keyword}")

                # 完全使用新数据覆盖
                existing.keyword_type = keyword.keyword_type
                existing.language = keyword.language
                existing.priority = keyword.priority
                existing.enabled = keyword.enabled
                existing.category = keyword.category
                existing.description = keyword.description
                existing.dr = 0  # 恢复
                existing.update_time = datetime.now()
                existing.update_by = utils.get_username_from_token(token) or "admin"

                db.commit()
                db.refresh(existing)

                logger.info(f"恢复关键词成功: {existing.keyword_id}")

                return CommonResponse(
                    status="success",
                    msg=f"关键词已恢复到{keyword.keyword_type}池",
                    code="200",
                    data=TrackerKeywordResponse.model_validate(existing).model_dump()
                )

        # 创建新关键词
        new_keyword = TrackerKeywordConfig(
            keyword_id=str(uuid.uuid4()),
            keyword_type=keyword.keyword_type,
            keyword=keyword.keyword,
            language=keyword.language,
            priority=keyword.priority,
            enabled=keyword.enabled,
            category=keyword.category,
            description=keyword.description,
            create_time=datetime.now(),
            update_time=datetime.now(),
            create_by=utils.get_username_from_token(token) or "admin",
            update_by=utils.get_username_from_token(token) or "admin",
            dr=0
        )

        db.add(new_keyword)
        db.commit()
        db.refresh(new_keyword)

        logger.info(f"创建关键词成功: {new_keyword.keyword_id}")

        return CommonResponse(
            status="success",
            msg="关键词创建成功",
            code="200",
            data=TrackerKeywordResponse.model_validate(new_keyword).model_dump()
        )

    except Exception as e:
        db.rollback()
        logger.error(f"创建关键词失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("", summary="查询关键词列表")
def get_keywords(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword_type: Optional[str] = Query(None, description="筛选: 类型"),
    language: Optional[str] = Query(None, description="筛选: 语言"),
    enabled: Optional[bool] = Query(None, description="筛选: 是否启用"),
    db: Session = Depends(get_db)
):
    """
    查询关键词列表(分页)

    支持筛选:
    - keyword_type: success/failure
    - language: 语言代码
    - enabled: true/false
    """
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        # 构建查询
        query = db.query(TrackerKeywordConfig).filter(TrackerKeywordConfig.dr == 0)

        if keyword_type:
            query = query.filter(TrackerKeywordConfig.keyword_type == keyword_type)
        if language:
            query = query.filter(TrackerKeywordConfig.language == language)
        if enabled is not None:
            query = query.filter(TrackerKeywordConfig.enabled == enabled)

        # 分页
        total = query.count()
        keywords = query.order_by(
            TrackerKeywordConfig.priority.desc(),
            TrackerKeywordConfig.create_time.desc()
        ).offset((page - 1) * page_size).limit(page_size).all()

        items = [TrackerKeywordResponse.model_validate(k).model_dump() for k in keywords]

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "total": total,
                "page": page,
                "pageSize": page_size,
                "list": items
            }
        )

    except Exception as e:
        logger.error(f"查询关键词列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{keyword_id}", summary="获取单个关键词")
def get_keyword(
    keyword_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """获取指定ID的关键词"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        keyword = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_id == keyword_id,
            TrackerKeywordConfig.dr == 0
        ).first()

        if not keyword:
            return CommonResponse(
                status="error",
                msg="关键词不存在",
                code="404",
                data=None
            )

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data=TrackerKeywordResponse.model_validate(keyword).model_dump()
        )

    except Exception as e:
        logger.error(f"获取关键词失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.put("/{keyword_id}", summary="更新关键词")
def update_keyword(
    keyword_id: str,
    keyword_update: TrackerKeywordUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """更新指定ID的关键词"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        keyword = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_id == keyword_id,
            TrackerKeywordConfig.dr == 0
        ).first()

        if not keyword:
            return CommonResponse(
                status="error",
                msg="关键词不存在",
                code="404",
                data=None
            )

        # 获取原始keyword值
        original_keyword_value = keyword.keyword

        # 更新字段
        update_data = keyword_update.model_dump(exclude_unset=True)

        # 如果要更新keyword字段，需要检查是否与其他记录冲突
        if "keyword" in update_data and update_data["keyword"] != original_keyword_value:
            # 检查新的keyword值是否已存在
            existing = db.query(TrackerKeywordConfig).filter(
                TrackerKeywordConfig.keyword == update_data["keyword"]
            ).first()

            if existing:
                if existing.dr == 0:
                    # 与活跃记录冲突，不允许更新
                    return CommonResponse(
                        status="error",
                        msg=f"关键词\"{update_data['keyword']}\"已存在于{existing.keyword_type}池中",
                        code="400",
                        data=None
                    )
                else:
                    # 与已删除记录冲突，恢复它并删除当前记录
                    logger.info(f"更新关键词: 恢复已删除的记录 {existing.keyword_id}，删除当前记录 {keyword_id}")

                    # 恢复已删除记录
                    existing.keyword_type = update_data.get("keyword_type", keyword.keyword_type)
                    existing.language = update_data.get("language", keyword.language)
                    existing.priority = update_data.get("priority", keyword.priority)
                    existing.enabled = update_data.get("enabled", keyword.enabled)
                    existing.category = update_data.get("category", keyword.category)
                    existing.description = update_data.get("description", keyword.description)
                    existing.dr = 0  # 恢复
                    existing.update_time = datetime.now()
                    existing.update_by = utils.get_username_from_token(token) or "admin"

                    # 删除当前记录
                    keyword.dr = 1
                    keyword.update_time = datetime.now()

                    db.commit()
                    db.refresh(existing)

                    return CommonResponse(
                        status="success",
                        msg=f"关键词已更新并恢复到{existing.keyword_type}池",
                        code="200",
                        data=TrackerKeywordResponse.model_validate(existing).model_dump()
                    )

        # 正常更新
        for field, value in update_data.items():
            setattr(keyword, field, value)

        keyword.update_time = datetime.now()
        keyword.update_by = utils.get_username_from_token(token) or "admin"

        db.commit()
        db.refresh(keyword)

        logger.info(f"更新关键词成功: {keyword_id}")

        return CommonResponse(
            status="success",
            msg="更新成功",
            code="200",
            data=TrackerKeywordResponse.model_validate(keyword).model_dump()
        )

    except Exception as e:
        db.rollback()
        logger.error(f"更新关键词失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/{keyword_id}", summary="删除关键词")
def delete_keyword(
    keyword_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """删除指定ID的关键词(软删除)"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    try:
        keyword = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_id == keyword_id,
            TrackerKeywordConfig.dr == 0
        ).first()

        if not keyword:
            return CommonResponse(
                status="error",
                msg="关键词不存在",
                code="404",
                data=None
            )

        # 软删除
        keyword.dr = 1
        keyword.update_time = datetime.now()

        db.commit()

        logger.info(f"删除关键词成功: {keyword_id}")

        return CommonResponse(
            status="success",
            msg="删除成功",
            code="200",
            data=None
        )

    except Exception as e:
        db.rollback()
        logger.error(f"删除关键词失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/batch", summary="批量创建关键词")
def batch_create_keywords(
    keywords_data: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    """批量创建关键词"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(status="error", msg="token验证失败", code="401", data=None)

    try:
        keywords_list = keywords_data.get("keywords", [])
        if not keywords_list:
            return CommonResponse(
                status="error",
                msg="关键词列表不能为空",
                code="400",
                data=None
            )

        # 检查列表内是否有重复的keyword
        keywords_in_request = [kw.get("keyword") for kw in keywords_list]
        if len(keywords_in_request) != len(set(keywords_in_request)):
            return CommonResponse(
                status="error",
                msg="批量创建的关键词列表中存在重复的keyword",
                code="400",
                data=None
            )

        created_keywords = []
        restored_keywords = []
        skipped_keywords = []
        username = utils.get_username_from_token(token) or "admin"

        for kw_data in keywords_list:
            keyword = kw_data.get("keyword")

            # 检查是否已存在 (keyword全局唯一,不区分dr状态)
            existing = db.query(TrackerKeywordConfig).filter(
                TrackerKeywordConfig.keyword == keyword
            ).first()

            if existing:
                if existing.dr == 0:
                    # 活跃记录，跳过
                    skipped_keywords.append({
                        "keyword": keyword,
                        "keyword_type": existing.keyword_type,
                        "reason": "已存在"
                    })
                    continue
                else:
                    # 已删除记录，恢复它
                    logger.info(f"批量创建: 恢复已删除的关键词 {existing.keyword_id}")

                    # 完全使用新数据覆盖
                    existing.keyword_type = kw_data.get("keyword_type", "failure")
                    existing.language = kw_data.get("language", "universal")
                    existing.category = kw_data.get("category")
                    existing.description = kw_data.get("description")
                    existing.priority = kw_data.get("priority", 1000)
                    existing.enabled = kw_data.get("enabled", True)
                    existing.dr = 0  # 恢复
                    existing.update_time = datetime.now()
                    existing.update_by = username

                    restored_keywords.append(existing)
                    continue

            # 创建新关键词
            new_keyword = TrackerKeywordConfig(
                keyword_id=str(uuid.uuid4()),
                keyword_type=kw_data.get("keyword_type", "failure"),
                keyword=keyword,
                language=kw_data.get("language", "universal"),
                category=kw_data.get("category"),
                description=kw_data.get("description"),
                priority=kw_data.get("priority", 1000),
                enabled=kw_data.get("enabled", True),
                create_time=datetime.now(),
                update_time=datetime.now(),
                create_by=username,
                update_by=username,
                dr=0
            )

            db.add(new_keyword)
            created_keywords.append(new_keyword)

        db.commit()

        # 刷新并序列化
        result = []
        for kw in created_keywords:
            db.refresh(kw)
            result.append(TrackerKeywordResponse.model_validate(kw).model_dump())

        for kw in restored_keywords:
            db.refresh(kw)
            result.append(TrackerKeywordResponse.model_validate(kw).model_dump())

        logger.info(f"批量创建关键词成功: 创建{len(created_keywords)}个, 恢复{len(restored_keywords)}个, 跳过{len(skipped_keywords)}个")

        return CommonResponse(
            status="success",
            msg=f"成功创建{len(created_keywords)}个, 恢复{len(restored_keywords)}个, 跳过{len(skipped_keywords)}个关键词",
            code="200",
            data={
                "created": len(created_keywords),
                "restored": len(restored_keywords),
                "skipped": len(skipped_keywords),
                "skipped_details": skipped_keywords,
                "keywords": result
            }
        )

    except Exception as e:
        db.rollback()
        logger.error(f"批量创建关键词失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量创建失败: {str(e)}")


@router.post("/batch/enable", summary="批量启用关键词")
def batch_enable_keywords(
    batch_req: BatchOperationRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """批量启用关键词"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(status="error", msg="token验证失败", code="401", data=None)

    try:
        # 查询并更新
        keywords = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_id.in_(batch_req.keyword_ids),
            TrackerKeywordConfig.dr == 0
        ).all()

        count = 0
        for keyword in keywords:
            keyword.enabled = True
            keyword.update_time = datetime.now()
            count += 1

        db.commit()

        logger.info(f"批量启用关键词成功: {count}个")

        return CommonResponse(
            status="success",
            msg=f"成功启用{count}个关键词",
            code="200",
            data={"updated_count": count}
        )

    except Exception as e:
        db.rollback()
        logger.error(f"批量启用关键词失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量启用失败: {str(e)}")


@router.post("/batch/disable", summary="批量禁用关键词")
def batch_disable_keywords(
    batch_req: BatchOperationRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """批量禁用关键词"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(status="error", msg="token验证失败", code="401", data=None)

    try:
        # 查询并更新
        keywords = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_id.in_(batch_req.keyword_ids),
            TrackerKeywordConfig.dr == 0
        ).all()

        count = 0
        for keyword in keywords:
            keyword.enabled = False
            keyword.update_time = datetime.now()
            count += 1

        db.commit()

        logger.info(f"批量禁用关键词成功: {count}个")

        return CommonResponse(
            status="success",
            msg=f"成功禁用{count}个关键词",
            code="200",
            data={"updated_count": count}
        )

    except Exception as e:
        db.rollback()
        logger.error(f"批量禁用关键词失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量禁用失败: {str(e)}")


@router.put("/batch/status", summary="批量更新关键词状态")
def batch_update_status(
    status_data: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    """批量更新关键词的启用状态"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(status="error", msg="token验证失败", code="401", data=None)

    try:
        keyword_ids = status_data.get("keyword_ids", [])
        enabled = status_data.get("enabled")

        if not keyword_ids:
            return CommonResponse(
                status="error",
                msg="关键词ID列表不能为空",
                code="400",
                data=None
            )

        # 查询并更新
        keywords = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_id.in_(keyword_ids),
            TrackerKeywordConfig.dr == 0
        ).all()

        count = 0
        for keyword in keywords:
            keyword.enabled = enabled
            keyword.update_time = datetime.now()
            count += 1

        db.commit()

        logger.info(f"批量更新关键词状态成功: {count}个, enabled={enabled}")

        return CommonResponse(
            status="success",
            msg=f"成功更新{count}个关键词的状态",
            code="200",
            data={"updated_count": count}
        )

    except Exception as e:
        db.rollback()
        logger.error(f"批量更新关键词状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量更新状态失败: {str(e)}")


@router.post("/batch/delete", summary="批量删除关键词")
def batch_delete_keywords(
    batch_req: BatchOperationRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """批量删除关键词(软删除)"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(status="error", msg="token验证失败", code="401", data=None)

    try:
        # 查询并软删除
        keywords = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_id.in_(batch_req.keyword_ids),
            TrackerKeywordConfig.dr == 0
        ).all()

        count = 0
        for keyword in keywords:
            keyword.dr = 1
            keyword.update_time = datetime.now()
            count += 1

        db.commit()

        logger.info(f"批量删除关键词成功: {count}个")

        return CommonResponse(
            status="success",
            msg=f"成功删除{count}个关键词",
            code="200",
            data={"deleted_count": count}
        )

    except Exception as e:
        db.rollback()
        logger.error(f"批量删除关键词失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")
