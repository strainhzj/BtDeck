"""
重复种子查询接口

基于数据库查询,直接返回重复的种子列表
支持按名称、下载器、状态等条件过滤，并返回分页结果
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_
from typing import Any, Optional, Dict, List
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
from app.services.torrent_metadata import fetch_live_torrent_metadata

logger = logging.getLogger(__name__)

router = APIRouter()


def _normalized_hash(value: Any) -> str:
    return str(value or "").strip().lower()


def _overlay_metadata(target: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    """Overlay live values while refusing blank core display fields."""
    for field, value in metadata.items():
        if value is None:
            continue
        if field in {"name", "save_path", "status", "hash"} and not str(value).strip():
            continue
        target[field] = value


class DuplicateQueryRequest(BaseModel):
    """重复种子查询请求参数"""

    name_like: Optional[str] = Field(None, description="种子名称模糊搜索")
    downloader_id: Optional[str] = Field(
        None, description="下载器ID（支持多选，逗号分隔）"
    )
    status: Optional[str] = Field(None, description="种子状态（支持多选，逗号分隔）")
    min_size: Optional[int] = Field(None, description="最小文件大小(字节)")
    page: int = Field(1, ge=1, description="页码(从1开始)")
    pageSize: int = Field(20, ge=1, le=100000, description="每页记录数")


@router.post("/duplicates", response_model=CommonResponse)
async def get_duplicate_torrents(
    query: DuplicateQueryRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
        query: 查询请求参数
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
        offset = (query.page - 1) * query.pageSize

        # 构建基础过滤条件
        base_conditions = [
            TorrentInfo.dr == 0,  # 未删除
            TorrentInfo.hash.isnot(None),
            TorrentInfo.hash != "",  # hash不为空
        ]

        # 应用过滤条件
        if query.name_like:
            base_conditions.append(TorrentInfo.name.like(f"%{query.name_like}%"))

        if query.downloader_id:
            # 支持多选：逗号分隔的字符串
            downloader_ids = [
                id.strip() for id in query.downloader_id.split(",") if id.strip()
            ]
            if len(downloader_ids) == 0:
                # 空列表：不添加过滤条件（避免SQL语法错误）
                pass
            elif len(downloader_ids) == 1:
                # 单个下载器：使用精确匹配
                base_conditions.append(TorrentInfo.downloader_id == downloader_ids[0])
            else:
                # 多个下载器：使用 in_ 查询（或关系）
                base_conditions.append(TorrentInfo.downloader_id.in_(downloader_ids))

        if query.status:
            # 支持多选：逗号分隔的字符串
            statuses = [s.strip() for s in query.status.split(",") if s.strip()]
            if len(statuses) == 0:
                # 空列表：不添加过滤条件（避免SQL语法错误）
                pass
            elif len(statuses) == 1:
                # 单个状态：使用精确匹配
                base_conditions.append(TorrentInfo.status == statuses[0])
            else:
                # 多个状态：使用 or_ 组合多个条件（或关系）
                status_conditions = [TorrentInfo.status == s for s in statuses]
                base_conditions.append(or_(*status_conditions))

        if query.min_size is not None:
            base_conditions.append(TorrentInfo.size >= query.min_size)

        # 第一步：构建子查询，找出符合条件的所有种子
        filtered_torrents = (
            select(TorrentInfo.hash).where(and_(*base_conditions)).alias()
        )

        # 第二步：统计每个hash的出现次数，找出重复的hash（出现次数≥2）
        duplicate_hashes_subquery = (
            select(filtered_torrents.c.hash, func.count().label("hash_count"))
            .group_by(filtered_torrents.c.hash)
            .having(func.count() >= 2)
            .alias()
        )

        # 第三步：查询所有hash在重复列表中的种子记录
        main_query = (
            select(TorrentInfo)
            .join(
                duplicate_hashes_subquery,
                TorrentInfo.hash == duplicate_hashes_subquery.c.hash,
            )
            .where(and_(*base_conditions))
        )

        # 排序：先按hash倒序，再按添加时间倒序
        main_query = main_query.order_by(
            TorrentInfo.hash.desc(), TorrentInfo.added_date.desc()
        )

        # 查询有重复的种子总数
        count_query = select(func.count()).select_from(main_query.alias())
        total_result = db.execute(count_query).scalar()
        total = total_result if total_result else 0

        # 应用分页
        main_query = main_query.offset(offset).limit(query.pageSize)

        # 执行查询
        result = db.execute(main_query)
        torrent_records = result.scalars().all()

        # ✅ 新增：批量查询tracker信息（避免N+1查询问题）
        if torrent_records:
            # 提取所有种子的info_id
            torrent_info_ids = [str(t.info_id) for t in torrent_records]

            # 批量查询tracker信息
            all_trackers = (
                db.query(TrackerInfo)
                .filter(
                    TrackerInfo.torrent_info_id.in_(torrent_info_ids),
                    TrackerInfo.dr == 0,  # 只查询未逻辑删除的tracker
                )
                .all()
            )

            # 按torrent_info_id分组tracker信息
            tracker_map: Dict[str, List[TrackerInfo]] = {}
            for tracker in all_trackers:
                tracker_info_id = str(tracker.torrent_info_id)
                if tracker_info_id not in tracker_map:
                    tracker_map[tracker_info_id] = []
                tracker_map[tracker_info_id].append(tracker)

            # 查询所有下载器类型（用于tracker状态映射）
            downloader_types: Dict[str, str] = {}
            try:
                from app.downloader.models import BtDownloaders

                downloaders = (
                    db.query(BtDownloaders.downloader_id, BtDownloaders.downloader_type)
                    .filter(
                        BtDownloaders.downloader_id.in_(
                            [str(t.downloader_id) for t in torrent_records]
                        )
                    )
                    .all()
                )

                for dl in downloaders:
                    dl_type_raw = dl.downloader_type
                    dl_type_int = DownloaderTypeEnum.normalize(dl_type_raw)
                    downloader_types[str(dl.downloader_id)] = DownloaderTypeEnum(
                        dl_type_int
                    ).to_name()
            except Exception as e:
                logger.warning(f"查询下载器类型失败，使用默认值: {e}")
        else:
            tracker_map = {}
            downloader_types = {}

        # 同 hash 的名称和大小是种子固有属性。即使当前分页中的某条历史记录为空，
        # 也可先从同组的完整数据库记录回填，再尝试从在线下载器获取其专属元数据。
        shared_metadata: Dict[str, Dict[str, Any]] = {}
        if torrent_records:
            page_hashes = list(
                {str(torrent.hash) for torrent in torrent_records if torrent.hash}
            )
            intrinsic_rows = (
                db.query(TorrentInfo.hash, TorrentInfo.name, TorrentInfo.size)
                .filter(TorrentInfo.hash.in_(page_hashes), TorrentInfo.dr == 0)
                .all()
            )
            for row in intrinsic_rows:
                torrent_hash = _normalized_hash(row.hash)
                shared = shared_metadata.setdefault(torrent_hash, {})
                if row.name and not shared.get("name"):
                    shared["name"] = row.name
                if row.size and not shared.get("size"):
                    shared["size"] = int(row.size)

        live_metadata = await fetch_live_torrent_metadata(
            http_request.app, torrent_records, downloader_types
        )

        # 转换为VO格式并填充tracker信息
        torrent_list = []
        for torrent in torrent_records:
            # 获取该种子的tracker列表
            trackers = tracker_map.get(str(torrent.info_id), [])

            # 构建tracker_info数组
            tracker_info_list = []
            tracker_names = []
            tracker_urls = []
            last_announce_succeededs = []
            last_announce_msgs = []
            last_scrape_succeededs = []

            # 获取下载器类型
            downloader_type = downloader_types.get(
                str(torrent.downloader_id), "qbittorrent"
            )

            for tracker in trackers:
                # 映射 announce 状态
                announce_status_text = None
                if tracker.last_announce_succeeded is not None:
                    try:
                        announce_status_int = int(tracker.last_announce_succeeded)
                        if downloader_type == "qbittorrent":
                            announce_status_text = (
                                QBittorrentTrackerStatus.get_display_text(
                                    announce_status_int
                                )
                            )
                        else:
                            announce_status_text = (
                                TransmissionTrackerStatus.get_display_text(
                                    announce_status_int
                                )
                            )
                    except (ValueError, TypeError):
                        announce_status_text = str(tracker.last_announce_succeeded)

                # 映射 scrape 状态
                scrape_status_text = None
                if tracker.last_scrape_succeeded is not None:
                    try:
                        scrape_status_int = int(tracker.last_scrape_succeeded)
                        if downloader_type == "qbittorrent":
                            scrape_status_text = (
                                QBittorrentTrackerStatus.get_display_text(
                                    scrape_status_int
                                )
                            )
                        else:
                            scrape_status_text = (
                                TransmissionTrackerStatus.get_display_text(
                                    scrape_status_int
                                )
                            )
                    except (ValueError, TypeError):
                        scrape_status_text = str(tracker.last_scrape_succeeded)

                # 构建tracker_info对象
                tracker_vo = TrackerInfoVO(
                    tracker_id=str(tracker.tracker_id) if tracker.tracker_id else None,
                    tracker_name=str(tracker.tracker_name)
                    if tracker.tracker_name
                    else None,
                    tracker_url=str(tracker.tracker_url)
                    if tracker.tracker_url
                    else None,
                    last_announce_succeeded=announce_status_text,
                    last_announce_msg=str(tracker.last_announce_msg)
                    if tracker.last_announce_msg
                    else None,
                    last_scrape_succeeded=scrape_status_text,
                    last_scrape_msg=str(tracker.last_scrape_msg)
                    if tracker.last_scrape_msg
                    else None,
                )
                tracker_info_list.append(tracker_vo)

                # 构建字符串字段（向后兼容）
                tracker_names.append(str(tracker.tracker_name or ""))
                tracker_urls.append(str(tracker.tracker_url or ""))
                last_announce_succeededs.append(announce_status_text or "")
                last_announce_msgs.append(str(tracker.last_announce_msg or ""))
                last_scrape_succeededs.append(scrape_status_text or "")

            # 将数组转换为分号分隔的字符串
            tracker_name_str = ";".join(tracker_names) if tracker_names else ""
            tracker_url_str = ";".join(tracker_urls) if tracker_urls else ""
            last_announce_succeeded_str = (
                ";".join(last_announce_succeededs) if last_announce_succeededs else ""
            )
            last_announce_msg_str = (
                ";".join(last_announce_msgs) if last_announce_msgs else ""
            )
            last_scrape_succeeded_str = (
                ";".join(last_scrape_succeededs) if last_scrape_succeededs else ""
            )

            # 构建完整的 TorrentInfoVO。先用 ORM 的 to_dict 收口 SQLAlchemy
            # Column 类型，再覆盖本接口组装的 tracker 字段。
            torrent_payload = torrent.to_dict()
            torrent_payload.update(
                {
                    "tracker_name": tracker_name_str,
                    "tracker_url": tracker_url_str,
                    "last_announce_succeeded": last_announce_succeeded_str,
                    "last_announce_msg": last_announce_msg_str,
                    "last_scrape_succeeded": last_scrape_succeeded_str,
                    "tracker_info": tracker_info_list,
                }
            )
            torrent_vo = TorrentInfoVO.model_validate(torrent_payload)

            torrent_data = torrent_vo.model_dump(by_alias=False)
            torrent_hash = _normalized_hash(torrent.hash)
            shared = shared_metadata.get(torrent_hash, {})
            if not torrent_data.get("name") and shared.get("name"):
                torrent_data["name"] = shared["name"]
            if not torrent_data.get("size") and shared.get("size"):
                torrent_data["size"] = shared["size"]
            _overlay_metadata(
                torrent_data,
                live_metadata.get((str(torrent.downloader_id), torrent_hash), {}),
            )
            torrent_list.append(torrent_data)

        logger.info(
            f"查询重复种子成功: 用户={current_user.username}, "
            f"条件={query.name_like or '全部'}, "
            f"总记录数={total}, 返回记录数={len(torrent_list)}"
        )

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "total": total,
                "page": query.page,
                "pageSize": query.pageSize,
                "list": torrent_list,
            },
        )

    except Exception as e:
        logger.error(f"查询重复种子失败: {e}", exc_info=True)

        # 返回错误信息,但状态码为200
        return CommonResponse(
            status="error", msg=f"查询失败: {str(e)}", code="500", data=None
        )
