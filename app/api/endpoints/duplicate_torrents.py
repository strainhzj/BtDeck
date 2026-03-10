"""
重复种子查询接口

基于数据库查询,直接返回重复的种子列表
支持按名称、下载器、状态等条件过滤，并返回分页结果
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_
from typing import Optional, Dict, List
import logging

from app.api.responseVO import CommonResponse
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_db
from app.torrents.models import TorrentInfo, TrackerInfo
from app.torrents.responseVO import TorrentInfoVO
from app.torrents.trackerVO import TrackerInfoVO
from app.models.setting_templates import DownloaderTypeEnum
from app.enums.tracker_status import QBittorrentTrackerStatus, TransmissionTrackerStatus

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

        # ✅ 新增：批量查询tracker信息（避免N+1查询问题）
        if torrent_records:
            # 提取所有种子的info_id
            torrent_info_ids = [t.info_id for t in torrent_records]

            # 批量查询tracker信息
            all_trackers = db.query(TrackerInfo).filter(
                TrackerInfo.torrent_info_id.in_(torrent_info_ids),
                TrackerInfo.dr == 0  # 只查询未逻辑删除的tracker
            ).all()

            # 按torrent_info_id分组tracker信息
            tracker_map: Dict[str, List[TrackerInfo]] = {}
            for tracker in all_trackers:
                if tracker.torrent_info_id not in tracker_map:
                    tracker_map[tracker.torrent_info_id] = []
                tracker_map[tracker.torrent_info_id].append(tracker)

            # 查询所有下载器类型（用于tracker状态映射）
            downloader_types = {}
            try:
                from app.downloader.models import BtDownloaders
                downloaders = db.query(
                    BtDownloaders.downloader_id,
                    BtDownloaders.downloader_type
                ).filter(
                    BtDownloaders.downloader_id.in_([t.downloader_id for t in torrent_records])
                ).all()

                for dl in downloaders:
                    dl_type_raw = dl.downloader_type
                    dl_type_int = DownloaderTypeEnum.normalize(dl_type_raw)
                    downloader_types[dl.downloader_id] = DownloaderTypeEnum(dl_type_int).to_name()
            except Exception as e:
                logger.warning(f"查询下载器类型失败，使用默认值: {e}")
        else:
            tracker_map = {}
            downloader_types = {}

        # 转换为VO格式并填充tracker信息
        torrent_list = []
        for torrent in torrent_records:
            # 获取该种子的tracker列表
            trackers = tracker_map.get(torrent.info_id, [])

            # 构建tracker_info数组
            tracker_info_list = []
            tracker_names = []
            tracker_urls = []
            last_announce_succeededs = []
            last_announce_msgs = []
            last_scrape_succeededs = []

            # 获取下载器类型
            downloader_type = downloader_types.get(torrent.downloader_id, "qbittorrent")

            for tracker in trackers:
                # 映射 announce 状态
                announce_status_text = None
                if tracker.last_announce_succeeded is not None:
                    try:
                        announce_status_int = int(tracker.last_announce_succeeded)
                        if downloader_type == "qbittorrent":
                            announce_status_text = QBittorrentTrackerStatus.get_display_text(announce_status_int)
                        else:
                            announce_status_text = TransmissionTrackerStatus.get_display_text(announce_status_int)
                    except (ValueError, TypeError):
                        announce_status_text = str(tracker.last_announce_succeeded)

                # 映射 scrape 状态
                scrape_status_text = None
                if tracker.last_scrape_succeeded is not None:
                    try:
                        scrape_status_int = int(tracker.last_scrape_succeeded)
                        if downloader_type == "qbittorrent":
                            scrape_status_text = QBittorrentTrackerStatus.get_display_text(scrape_status_int)
                        else:
                            scrape_status_text = TransmissionTrackerStatus.get_display_text(scrape_status_int)
                    except (ValueError, TypeError):
                        scrape_status_text = str(tracker.last_scrape_succeeded)

                # 构建tracker_info对象
                tracker_vo = TrackerInfoVO(
                    tracker_id=tracker.tracker_id,
                    tracker_name=tracker.tracker_name,
                    tracker_url=tracker.tracker_url,
                    last_announce_succeeded=announce_status_text,
                    last_announce_msg=tracker.last_announce_msg,
                    last_scrape_succeeded=scrape_status_text,
                    last_scrape_msg=tracker.last_scrape_msg
                )
                tracker_info_list.append(tracker_vo)

                # 构建字符串字段（向后兼容）
                tracker_names.append(tracker.tracker_name or "")
                tracker_urls.append(tracker.tracker_url or "")
                last_announce_succeededs.append(announce_status_text or "")
                last_announce_msgs.append(tracker.last_announce_msg or "")
                last_scrape_succeededs.append(scrape_status_text or "")

            # 将数组转换为分号分隔的字符串
            tracker_name_str = ";".join(tracker_names) if tracker_names else ""
            tracker_url_str = ";".join(tracker_urls) if tracker_urls else ""
            last_announce_succeeded_str = ";".join(last_announce_succeededs) if last_announce_succeededs else ""
            last_announce_msg_str = ";".join(last_announce_msgs) if last_announce_msgs else ""
            last_scrape_succeeded_str = ";".join(last_scrape_succeededs) if last_scrape_succeededs else ""

            # 构建完整的TorrentInfoVO
            torrent_vo = TorrentInfoVO(
                info_id=torrent.info_id,
                downloader_id=torrent.downloader_id,
                downloader_name=torrent.downloader_name,
                torrent_id=torrent.torrent_id,
                hash=torrent.hash,
                name=torrent.name,
                save_path=torrent.save_path,
                size=torrent.size,
                status=torrent.status,
                progress=torrent.progress,
                torrent_file=torrent.torrent_file,
                added_date=torrent.added_date,
                completed_date=torrent.completed_date,
                ratio=torrent.ratio,
                ratio_limit=torrent.ratio_limit,
                tags=torrent.tags,
                category=torrent.category,
                super_seeding=torrent.super_seeding,
                enabled=torrent.enabled,
                tracker_name=tracker_name_str,
                tracker_url=tracker_url_str,
                last_announce_succeeded=last_announce_succeeded_str,
                last_announce_msg=last_announce_msg_str,
                last_scrape_succeeded=last_scrape_succeeded_str,
                tracker_info=tracker_info_list
            )

            torrent_list.append(torrent_vo.model_dump(by_alias=False))

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
