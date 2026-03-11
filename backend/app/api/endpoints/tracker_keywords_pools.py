"""
Tracker关键词池管理API接口

提供关键词在四个池子间移动、查询等功能：
- candidate: 候选池
- ignored: 忽略池
- success: 成功池
- failed: 失败池
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
import logging
from sqlalchemy import func

from app.database import get_db
from app.api.responseVO import CommonResponse
from app.torrents.models import TrackerKeywordConfig
from app.auth import utils

logger = logging.getLogger(__name__)
router = APIRouter()


# 池子标签映射常量
class PoolLabels:
    """池子标签常量"""
    CANDIDATE = '📋 候选池'
    IGNORED = '⏭️ 忽略池'
    SUCCESS = '✅ 成功池'
    FAILED = '❌ 失败池'

    @classmethod
    def get_label(cls, pool_type: str) -> str:
        """获取池子标签"""
        label_map = {
            'candidate': cls.CANDIDATE,
            'ignored': cls.IGNORED,
            'success': cls.SUCCESS,
            'failed': cls.FAILED
        }
        return label_map.get(pool_type, pool_type)


@router.get("/pool", summary="获取池子关键词列表")
def get_pool_keywords(
    pool_type: str,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取指定池子的关键词列表（分页）

    Args:
        pool_type: 池子类型 (candidate/ignored/success/failed)
        keyword: 关键词筛选（可选）
        page: 页码（从1开始）
        page_size: 每页数量
        request: 请求对象
        db: 数据库会话
    """
    # JWT验证
    token = request.headers.get("x-access-token") if request else None
    try:
        if token:
            utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    # 验证池子类型
    valid_pool_types = ['candidate', 'ignored', 'success', 'failed']
    if pool_type not in valid_pool_types:
        return CommonResponse(
            status="error",
            msg=f"无效的池子类型，必须是: {', '.join(valid_pool_types)}",
            code="400",
            data=None
        )

    try:
        # 构建查询
        query = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_type == pool_type,
            TrackerKeywordConfig.dr == 0
        )

        # 关键词筛选
        if keyword:
            query = query.filter(TrackerKeywordConfig.keyword.contains(keyword))

        # 总数
        total = query.count()

        # 分页
        offset = (page - 1) * page_size
        keywords = query.offset(offset).limit(page_size).all()

        # 转换为字典格式
        list_data = []
        for kw in keywords:
            list_data.append({
                "keyword_id": kw.keyword_id,
                "keyword": kw.keyword,
                "pool_type": kw.keyword_type,
                "create_time": kw.create_time.strftime('%Y-%m-%d %H:%M:%S') if kw.create_time else None
            })

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "total": total,
                "page": page,
                "pageSize": page_size,
                "list": list_data
            }
        )
    except Exception as e:
        logger.error(f"查询池子关键词失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/move", summary="移动关键词到指定池子")
def move_keyword_to_pool(
    request_data: dict,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    移动单个关键词到指定池子

    Args:
        request_data: 包含 keyword_id 和 target_pool
        request: 请求对象
        db: 数据库会话
    """
    # JWT验证
    token = request.headers.get("x-access-token") if request else None
    try:
        if token:
            utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    keyword_id = request_data.get("keyword_id")
    target_pool = request_data.get("target_pool")

    if not keyword_id or not target_pool:
        return CommonResponse(
            status="error",
            msg="缺少必要参数: keyword_id 和 target_pool",
            code="400",
            data=None
        )

    # 验证池子类型
    valid_pool_types = ['candidate', 'ignored', 'success', 'failed']
    if target_pool not in valid_pool_types:
        return CommonResponse(
            status="error",
            msg=f"无效的目标池子类型，必须是: {', '.join(valid_pool_types)}",
            code="400",
            data=None
        )

    try:
        # 查找关键词
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

        # 更新池子类型
        old_pool_type = keyword.keyword_type
        keyword.keyword_type = target_pool
        keyword.update_time = func.now()

        db.commit()
        db.refresh(keyword)

        logger.info(f"关键词 '{keyword.keyword}' 已从 {old_pool_type} 移动到 {target_pool}")

        return CommonResponse(
            status="success",
            msg=f"关键词已移动到 {target_pool}",
            code="200",
            data=None
        )
    except Exception as e:
        db.rollback()
        logger.error(f"移动关键词失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"移动失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/batch-move", summary="批量移动关键词到指定池子")
def batch_move_keywords(
    request_data: dict,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    批量移动关键词到指定池子

    Args:
        request_data: 包含 keyword_ids 列表和 target_pool
        request: 请求对象
        db: 数据库会话
    """
    # JWT验证
    token = request.headers.get("x-access-token") if request else None
    try:
        if token:
            utils.verify_access_token(token)
    except Exception as e:
        logger.info(f"Token验证失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg="token验证失败",
            code="401",
            data=None
        )

    keyword_ids = request_data.get("keyword_ids", [])
    target_pool = request_data.get("target_pool")

    if not keyword_ids or not target_pool:
        return CommonResponse(
            status="error",
            msg="缺少必要参数: keyword_ids 和 target_pool",
            code="400",
            data=None
        )

    if not isinstance(keyword_ids, list):
        return CommonResponse(
            status="error",
            msg="keyword_ids 必须是列表",
            code="400",
            data=None
        )

    # 验证池子类型
    valid_pool_types = ['candidate', 'ignored', 'success', 'failed']
    if target_pool not in valid_pool_types:
        return CommonResponse(
            status="error",
            msg=f"无效的目标池子类型，必须是: {', '.join(valid_pool_types)}",
            code="400",
            data=None
        )

    try:
        # 查找关键词
        keywords = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_id.in_(keyword_ids),
            TrackerKeywordConfig.dr == 0
        ).all()

        if not keywords:
            return CommonResponse(
                status="error",
                msg="未找到有效关键词",
                code="404",
                data=None
            )

        # 批量更新
        for keyword in keywords:
            keyword.keyword_type = target_pool
            keyword.update_time = func.now()

        db.commit()

        logger.info(f"已批量移动 {len(keywords)} 个关键词到 {target_pool}")

        return CommonResponse(
            status="success",
            msg=f"已移动 {len(keywords)} 个关键词到 {target_pool}",
            code="200",
            data={"moved_count": len(keywords)}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"批量移动关键词失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"批量移动失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/pool/statistics", summary="获取所有池子的统计信息")
def get_pool_statistics(
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取所有池子的关键词统计信息

    Args:
        request: 请求对象
        db: 数据库会话
    """
    # JWT验证
    token = request.headers.get("x-access-token") if request else None
    try:
        if token:
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
        # 查询各池子数量
        stats = db.query(
            TrackerKeywordConfig.keyword_type,
            func.count(TrackerKeywordConfig.keyword_id)
        ).filter(
            TrackerKeywordConfig.dr == 0
        ).group_by(
            TrackerKeywordConfig.keyword_type
        ).all()

        # 构建结果
        result = {
            "candidate_count": 0,
            "ignored_count": 0,
            "success_count": 0,
            "failed_count": 0
        }

        for pool_type, count in stats:
            if pool_type == 'candidate':
                result['candidate_count'] = count
            elif pool_type == 'ignored':
                result['ignored_count'] = count
            elif pool_type == 'success':
                result['success_count'] = count
            elif pool_type == 'failed':
                result['failed_count'] = count

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data=result
        )
    except Exception as e:
        logger.error(f"查询池子统计信息失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )


@router.get("/pool/search-all", summary="全局搜索所有池子的关键词")
def search_all_pools(
    keyword: Optional[str] = None,
    pool_types: Optional[str] = None,  # 逗号分隔的池子类型，如 "candidate,success"
    time_range: Optional[str] = None,  # today/week/month
    sort_by: Optional[str] = None,  # time_desc/time_asc/name_asc
    page: int = 1,
    page_size: int = 20,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    在所有池子中搜索关键词（支持高级筛选）

    性能优化建议：
    - 建议在tracker_keyword_config表的(keyword_type, dr)字段上创建复合索引
    - 如果数据量超过10万，考虑使用ElasticSearch全文搜索
    - 时间范围筛选已优化为使用自然周/自然月，提升查询准确性

    Args:
        keyword: 关键词筛选（模糊匹配）
        pool_types: 池子类型筛选（逗号分隔，如 "candidate,success"）
        time_range: 时间范围筛选 (today/week/month)
        sort_by: 排序方式 (time_desc/time_asc/name_asc)
        page: 页码（从1开始）
        page_size: 每页数量
        request: 请求对象
        db: 数据库会话
    """
    # JWT验证
    token = request.headers.get("x-access-token") if request else None
    try:
        if token:
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
        from datetime import datetime, timedelta

        # 解析池子类型筛选
        valid_pool_types = ['candidate', 'ignored', 'success', 'failed']
        if pool_types:
            pool_type_list = [pt.strip() for pt in pool_types.split(',') if pt.strip()]
            # 验证池子类型
            invalid_types = [pt for pt in pool_type_list if pt not in valid_pool_types]
            if invalid_types:
                return CommonResponse(
                    status="error",
                    msg=f"无效的池子类型: {', '.join(invalid_types)}",
                    code="400",
                    data=None
                )
        else:
            pool_type_list = valid_pool_types  # 默认搜索所有池子

        # 构建基础查询
        query = db.query(TrackerKeywordConfig).filter(
            TrackerKeywordConfig.keyword_type.in_(pool_type_list),
            TrackerKeywordConfig.dr == 0
        )

        # 关键词筛选（模糊搜索）
        if keyword:
            query = query.filter(TrackerKeywordConfig.keyword.contains(keyword))

        # 时间范围筛选
        if time_range:
            now = datetime.now()
            if time_range == 'today':
                # 今天：从00:00:00开始
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                query = query.filter(TrackerKeywordConfig.create_time >= start_time)
            elif time_range == 'week':
                # 本周：从本周一00:00:00开始（自然周）
                days_since_monday = now.weekday()  # 0=周一, 6=周日
                start_time = (now - timedelta(days=days_since_monday)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                query = query.filter(TrackerKeywordConfig.create_time >= start_time)
            elif time_range == 'month':
                # 本月：从本月1日00:00:00开始（自然月）
                start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                query = query.filter(TrackerKeywordConfig.create_time >= start_time)

        # 排序
        if sort_by == 'time_desc':
            query = query.order_by(TrackerKeywordConfig.create_time.desc())
        elif sort_by == 'time_asc':
            query = query.order_by(TrackerKeywordConfig.create_time.asc())
        elif sort_by == 'name_asc':
            query = query.order_by(TrackerKeywordConfig.keyword.asc())
        else:
            # 默认按创建时间倒序
            query = query.order_by(TrackerKeywordConfig.create_time.desc())

        # 总数
        total = query.count()

        # 分页
        offset = (page - 1) * page_size
        keywords = query.offset(offset).limit(page_size).all()

        # 转换为字典格式（混合显示，标注所属池子）
        list_data = []
        for kw in keywords:
            list_data.append({
                "keyword_id": kw.keyword_id,
                "keyword": kw.keyword,
                "pool_type": kw.keyword_type,
                "pool_label": PoolLabels.get_label(kw.keyword_type),
                "create_time": kw.create_time.strftime('%Y-%m-%d %H:%M:%S') if kw.create_time else None
            })

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "total": total,
                "page": page,
                "pageSize": page_size,
                "list": list_data
            }
        )
    except Exception as e:
        logger.error(f"全局搜索关键词失败: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"搜索失败: {str(e)}",
            code="500",
            data=None
        )
