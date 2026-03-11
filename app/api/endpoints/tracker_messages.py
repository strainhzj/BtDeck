"""
Tracker消息记录CRUD API接口

提供消息记录的查询、删除、添加到关键词池和批量操作功能
注意: TrackerMessageLog使用物理删除，不使用dr字段
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
import uuid
from datetime import datetime
import logging

from app.database import get_db
from app.api.responseVO import CommonResponse
from app.api.schemas.tracker_messages import (
    TrackerMessageResponse,
    AddToPoolRequest,
    BatchOperationRequest,
    BatchAddToPoolRequest,
    BatchDeleteMessagesRequest
)
from app.torrents.models import TrackerMessageLog, TrackerKeywordConfig
from app.api.schemas.tracker_keywords import TrackerKeywordResponse
from app.auth import utils
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="查询消息记录列表")
def get_messages(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    tracker_host: str = Query(None, description="筛选: tracker地址"),
    is_processed: bool = Query(None, description="筛选: 是否已处理"),
    db: Session = Depends(get_db)
):
    """
    查询消息记录列表(分页)

    支持筛选:
    - tracker_host: tracker地址(模糊匹配)
    - is_processed: 是否已处理
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
        # 构建查询 - TrackerMessageLog不使用dr字段
        query = db.query(TrackerMessageLog)

        if tracker_host:
            query = query.filter(TrackerMessageLog.tracker_host.like(f"%{tracker_host}%"))
        if is_processed is not None:
            query = query.filter(TrackerMessageLog.is_processed == is_processed)

        # 分页
        total = query.count()
        messages = query.order_by(
            TrackerMessageLog.first_seen.desc()
        ).offset((page - 1) * page_size).limit(page_size).all()

        items = [TrackerMessageResponse.model_validate(m).model_dump() for m in messages]

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
        logger.error(f"查询消息记录列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{log_id}", summary="获取单条消息")
def get_message(
    log_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """获取指定ID的消息"""
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
        message = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.log_id == log_id
        ).first()

        if not message:
            return CommonResponse(
                status="error",
                msg="消息不存在",
                code="404",
                data=None
            )

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data=TrackerMessageResponse.model_validate(message).model_dump()
        )

    except Exception as e:
        logger.error(f"获取消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("", summary="创建消息记录")
def create_message(
    message_data: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    创建新的消息记录

    注意: 此接口主要用于测试和手动添加，实际使用中消息由定时任务自动记录
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
        # 检查是否已存在相同的消息（按tracker_host和msg组合）
        existing = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.tracker_host == message_data.get("tracker_host"),
            TrackerMessageLog.msg == message_data.get("msg")
        ).first()

        if existing:
            # 更新existing记录
            existing.occurrence_count += 1
            existing.last_seen = datetime.now()
            if message_data.get("judgment_result"):
                existing.judgment_result = message_data.get("judgment_result")
            if message_data.get("keyword_type"):
                existing.keyword_type = message_data.get("keyword_type")

            db.commit()
            db.refresh(existing)

            return CommonResponse(
                status="success",
                msg="消息记录已更新",
                code="200",
                data=TrackerMessageResponse.model_validate(existing).model_dump()
            )

        # 创建新消息
        new_message = TrackerMessageLog(
            log_id=str(uuid.uuid4()),
            tracker_host=message_data.get("tracker_host"),
            msg=message_data.get("msg"),
            judgment_result=message_data.get("judgment_result", "unknown"),
            keyword_type=message_data.get("keyword_type"),
            sample_torrents=message_data.get("sample_torrents"),
            sample_urls=message_data.get("sample_urls"),
            is_processed=message_data.get("is_processed", False),
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            occurrence_count=1,
            create_time=datetime.now(),
            update_time=datetime.now(),
            create_by=utils.get_username_from_token(token) or "admin",
            update_by=utils.get_username_from_token(token) or "admin"
        )

        db.add(new_message)
        db.commit()
        db.refresh(new_message)

        logger.info(f"创建消息记录成功: log_id={new_message.log_id}")

        return CommonResponse(
            status="success",
            msg="创建成功",
            code="200",
            data=TrackerMessageResponse.model_validate(new_message).model_dump()
        )

    except Exception as e:
        db.rollback()
        logger.error(f"创建消息记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/{log_id}", summary="更新消息记录")
def update_message(
    log_id: str,
    update_data: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    """更新消息记录的状态和字段"""
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
        message = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.log_id == log_id
        ).first()

        if not message:
            return CommonResponse(
                status="error",
                msg="消息不存在",
                code="404",
                data=None
            )

        # 更新字段
        if "is_processed" in update_data:
            message.is_processed = update_data["is_processed"]
        if "judgment_result" in update_data:
            message.judgment_result = update_data["judgment_result"]
        if "keyword_type" in update_data:
            message.keyword_type = update_data["keyword_type"]

        message.update_time = datetime.now()
        message.update_by = utils.get_username_from_token(token) or "admin"

        db.commit()
        db.refresh(message)

        logger.info(f"更新消息记录成功: log_id={log_id}")

        return CommonResponse(
            status="success",
            msg="更新成功",
            code="200",
            data=TrackerMessageResponse.model_validate(message).model_dump()
        )

    except Exception as e:
        db.rollback()
        logger.error(f"更新消息记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


def get_statistics(
    request: Request,
    db: Session = Depends(get_db)
):
    """获取消息记录的统计信息"""
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
        # 统计总数
        total = db.query(TrackerMessageLog).count()

        # 统计未处理数
        unprocessed = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.is_processed == False
        ).count()

        # 统计成功关键词数
        success = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.keyword_type == "success"
        ).count()

        # 统计失败关键词数
        failure = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.keyword_type == "failure"
        ).count()

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "total": total,
                "unprocessed": unprocessed,
                "success": success,
                "failure": failure
            }
        )

    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/{log_id}/add-to-pool", summary="添加消息到关键词池")
def add_message_to_pool(
    log_id: str,
    pool_request: AddToPoolRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    将消息添加到关键词池

    自动创建关键词配置,并标记消息为已处理
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
        # 查询消息 - 不使用dr字段过滤
        message = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.log_id == log_id
        ).first()

        if not message:
            return CommonResponse(
                status="error",
                msg="消息不存在",
                code="404",
                data=None
            )

        # 检查关键词是否已存在 (keyword全局唯一,不区分dr状态)
        existing = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword == message.msg
        ).first()

        if existing:
            if existing.dr == 0:
                # 活跃记录，不允许添加
                return CommonResponse(
                    status="error",
                    msg=f"该关键词已存在于{existing.keyword_type}池中",
                    code="400",
                    data=None
                )
            else:
                # 已删除记录，恢复它
                logger.info(f"添加到池: 恢复已删除的关键词 {existing.keyword_id}")

                # 完全使用新数据覆盖
                existing.keyword_type = pool_request.keyword_type
                existing.language = pool_request.language
                existing.priority = pool_request.priority
                existing.enabled = True
                existing.description = pool_request.description
                existing.dr = 0  # 恢复
                existing.update_time = datetime.now()
                existing.update_by = utils.get_username_from_token(token) or "admin"

                # 标记消息为已处理
                message.is_processed = True
                message.keyword_type = pool_request.keyword_type

                db.commit()
                db.refresh(existing)

                logger.info(f"添加消息到关键词池成功(恢复): log_id={log_id}, keyword_id={existing.keyword_id}")

                return CommonResponse(
                    status="success",
                    msg=f"关键词已恢复到{pool_request.keyword_type}池",
                    code="200",
                    data=TrackerKeywordResponse.model_validate(existing).model_dump()
                )

        # 创建新关键词
        new_keyword = TrackerKeywordConfig(
            keyword_id=str(uuid.uuid4()),
            keyword_type=pool_request.keyword_type,
            keyword=message.msg,
            language=pool_request.language,
            priority=pool_request.priority,
            enabled=True,
            description=pool_request.description,
            create_time=datetime.now(),
            update_time=datetime.now(),
            create_by=utils.get_username_from_token(token) or "admin",
            update_by=utils.get_username_from_token(token) or "admin",
            dr=0
        )

        # 标记消息为已处理
        message.is_processed = True
        message.keyword_type = pool_request.keyword_type

        db.add(new_keyword)
        db.commit()
        db.refresh(new_keyword)

        logger.info(f"添加消息到关键词池成功: log_id={log_id}, keyword_id={new_keyword.keyword_id}")

        return CommonResponse(
            status="success",
            msg="添加成功",
            code="200",
            data=TrackerKeywordResponse.model_validate(new_keyword).model_dump()
        )

    except Exception as e:
        db.rollback()
        logger.error(f"添加消息到关键词池失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加失败: {str(e)}")


@router.delete("/{log_id}", summary="删除消息")
def delete_message(
    log_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """删除指定ID的消息(物理删除)"""
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
        message = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.log_id == log_id
        ).first()

        if not message:
            return CommonResponse(
                status="error",
                msg="消息不存在",
                code="404",
                data=None
            )

        # 物理删除
        db.delete(message)
        db.commit()

        logger.info(f"删除消息成功: {log_id}")

        return CommonResponse(
            status="success",
            msg="删除成功",
            code="200",
            data=None
        )

    except Exception as e:
        db.rollback()
        logger.error(f"删除消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/batch/add-to-pool", summary="批量添加消息到关键词池")
def batch_add_to_pool(
    batch_req: BatchAddToPoolRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """批量添加消息到关键词池（接受合并的请求体）"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(status="error", msg="token验证失败", code="401", data=None)

    try:
        # 查询消息
        messages = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.log_id.in_(batch_req.log_ids)
        ).all()

        # 一次性查询所有可能存在的关键词（包括已删除的），避免N+1查询
        message_list = [m.msg for m in messages]
        all_existing_keywords = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword.in_(message_list)
        ).all()

        # 分别构建活跃和已删除的keyword集合
        active_keywords = {}
        deleted_keywords = {}
        for kw in all_existing_keywords:
            if kw.dr == 0:
                active_keywords[kw.keyword] = kw
            else:
                deleted_keywords[kw.keyword] = kw

        count = 0
        restored = 0
        skipped = 0
        skipped_details = []
        username = utils.get_username_from_token(token) or "admin"

        for message in messages:
            # 检查关键词是否已存在
            if message.msg in active_keywords:
                # 活跃记录，跳过
                skipped += 1
                skipped_details.append({
                    "msg": message.msg,
                    "keyword_type": active_keywords[message.msg].keyword_type,
                    "reason": "已存在"
                })
                continue
            elif message.msg in deleted_keywords:
                # 已删除记录，恢复它
                existing = deleted_keywords[message.msg]
                logger.info(f"批量添加到池: 恢复已删除的关键词 {existing.keyword_id}")

                # 完全使用新数据覆盖
                existing.keyword_type = batch_req.keyword_type
                existing.language = batch_req.language
                existing.priority = batch_req.priority
                existing.enabled = True
                existing.description = batch_req.description
                existing.dr = 0  # 恢复
                existing.update_time = datetime.now()
                existing.update_by = username

                # 标记消息为已处理
                message.is_processed = True
                message.keyword_type = batch_req.keyword_type

                restored += 1
                continue

            # 创建新关键词
            new_keyword = TrackerKeywordConfig(
                keyword_id=str(uuid.uuid4()),
                keyword_type=batch_req.keyword_type,
                keyword=message.msg,
                language=batch_req.language,
                priority=batch_req.priority,
                enabled=True,
                description=batch_req.description,
                create_time=datetime.now(),
                update_time=datetime.now(),
                create_by=username,
                update_by=username,
                dr=0
            )

            # 标记消息为已处理
            message.is_processed = True
            message.keyword_type = batch_req.keyword_type

            db.add(new_keyword)
            count += 1

        db.commit()

        logger.info(f"批量添加消息到关键词池成功: {count}个添加, {restored}个恢复, {skipped}个跳过")

        return CommonResponse(
            status="success",
            msg=f"成功添加{count}条消息到关键词池，恢复{restored}条，跳过{skipped}条已存在的",
            code="200",
            data={
                "addedCount": count,
                "restoredCount": restored,
                "skippedCount": skipped,
                "skippedDetails": skipped_details
            }
        )

    except Exception as e:
        db.rollback()
        logger.error(f"批量添加消息到关键词池失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量添加失败: {str(e)}")


@router.post("/batch/delete", summary="批量删除消息")
def batch_delete_messages(
    batch_req: BatchDeleteMessagesRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """批量删除消息(物理删除，使用log_ids字段)"""
    # JWT验证
    token = request.headers.get("x-access-token")
    try:
        utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(status="error", msg="token验证失败", code="401", data=None)

    try:
        # 查询并物理删除 - 不使用dr字段
        messages = db.query(TrackerMessageLog).filter(
            TrackerMessageLog.log_id.in_(batch_req.log_ids)
        ).all()

        count = 0
        for message in messages:
            db.delete(message)
            count += 1

        db.commit()

        logger.info(f"批量删除消息成功: {count}个")

        return CommonResponse(
            status="success",
            msg=f"成功删除{count}条消息",
            code="200",
            data={"deletedCount": count}
        )

    except Exception as e:
        db.rollback()
        logger.error(f"批量删除消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")
