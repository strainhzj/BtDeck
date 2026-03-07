"""
重复种子查询接口

基于数据库查询,直接返回重复的种子列表
支持按名称、下载器、状态等条件过滤，并返回分页结果
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_
from typing import Optional

from app.api.responseVO import CommonResponse
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_db
from app.torrents.models import TorrentInfo
from app.torrents.responseVO import TorrentInfoVO
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class DuplicateQueryRequest(BaseModel):
    """重复种子查询请求参数"""
    name_like: Optional[str] = Field(None, description="种子名称模糊搜索")
    downloader_id: Optional[str] = Field(None, description="下载器ID")
    status: Optional[str] = Field(None, description="种子状态")
    min_size: Optional[int] = Field(None, description="最小文件大小(字节)")
    page: int = Field(1, ge=1, description="页码(从1开始)")
    pageSize: int = Field(20, ge=1, le=200, description="每页记录数")


@router.post("/duplicates", response_model=CommonResponse)
async def get_duplicate_torrents(
    request: DuplicateQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    查询重复种子（严格模式）

    基于数据库torrent_info表,查询符合条件的种子记录。
    只返回hash值出现次数≥2的种子记录（有重复的种子）。

    实现逻辑：
    1. 先按条件过滤种子记录
    2. 统计每个hash的出现次数
    3. 只返回出现次数≥2的种子
    4. 对重复种子进行分页

    Args:
        request: 查询请求参数
            - name_like: 可选,种子名称模糊搜索
            - downloader_id: 可选,指定下载器ID过滤
            - status: 可选,种子状态过滤(如seeding, downloading等)
            - min_size: 可选,最小文件大小(字节)
            - page: 页码(从1开始)
            - pageSize: 每页记录数
        current_user: 当前登录用户
        db: 数据库会话

    Returns:
        CommonResponse: 包含重复种子列表的响应
        {
            "code": "200",
            "msg": "查询成功",
            "data": {
                "total": 10,        # 有重复的种子总记录数
                "page": 1,          # 当前页码
                "pageSize": 20,     # 每页记录数
                "list": [TorrentInfoVO, ...]  # 重复种子列表
            },
            "status": "success"
        }
    """
    try:
        # 计算偏移量
        offset = (request.page - 1) * request.pageSize

        # 构建基础过滤条件
        base_conditions = [
            TorrentInfo.dr == 0,  # 未删除
            TorrentInfo.hash.isnot(None),
            TorrentInfo.hash != ''  # hash不为空
        ]

        # 应用过滤条件
        if request.name_like:
            base_conditions.append(TorrentInfo.name.like(f'%{request.name_like}%'))

        if request.downloader_id:
            base_conditions.append(TorrentInfo.downloader_id == request.downloader_id)

        if request.status:
            base_conditions.append(TorrentInfo.status == request.status)

        if request.min_size is not None:
            base_conditions.append(TorrentInfo.size >= request.min_size)

        # 第一步：构建子查询，找出符合条件的所有种子
        filtered_torrents = (
            select(TorrentInfo.hash)
            .where(and_(*base_conditions))
            .alias()
        )

        # 第二步：统计每个hash的出现次数，找出重复的hash（出现次数≥2）
        duplicate_hashes_subquery = (
            select(
                filtered_torrents.c.hash,
                func.count().label('hash_count')
            )
            .group_by(filtered_torrents.c.hash)
            .having(func.count() >= 2)
            .alias()
        )

        # 第三步：查询所有hash在重复列表中的种子记录
        main_query = (
            select(TorrentInfo)
            .join(
                duplicate_hashes_subquery,
                TorrentInfo.hash == duplicate_hashes_subquery.c.hash
            )
            .where(and_(*base_conditions))
        )

        # 排序：先按hash倒序，再按添加时间倒序
        main_query = main_query.order_by(TorrentInfo.hash.desc(), TorrentInfo.added_date.desc())

        # 查询有重复的种子总数
        count_query = select(func.count()).select_from(main_query.alias())
        total_result = db.execute(count_query).scalar()
        total = total_result if total_result else 0

        # 应用分页
        main_query = main_query.offset(offset).limit(request.pageSize)

        # 执行查询
        result = db.execute(main_query)
        torrent_records = result.scalars().all()

        # 转换为VO格式
        torrent_list = [
            TorrentInfoVO.from_orm(torrent).model_dump(by_alias=False)
            for torrent in torrent_records
        ]

        logger.info(
            f"查询重复种子成功: 用户={current_user.username}, "
            f"条件={request.name_like or '全部'}, "
            f"总记录数={total}, 返回记录数={len(torrent_list)}"
        )

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "total": total,
                "page": request.page,
                "pageSize": request.pageSize,
                "list": torrent_list
            }
        )

    except Exception as e:
        logger.error(f"查询重复种子失败: {e}", exc_info=True)

        # 返回错误信息,但状态码为200
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )
