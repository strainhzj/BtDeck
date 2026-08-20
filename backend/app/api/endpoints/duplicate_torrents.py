"""
重复种子查询接口

基于数据库查询,直接返回重复的种子列表
支持按名称、下载器、状态等条件过滤，并返回分页结果
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import Column, MetaData, String, Table, and_, func, or_, select
from typing import Any, Dict, List, Literal, Optional
import logging
import uuid

from app.api.responseVO import CommonResponse
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.tracker_keyword_map import load_active_keyword_map
from app.core.tracker_status_policy import FAILED_DISPLAY_TEXT, tracker_display_failed
from app.database import get_db
from app.torrents.models import TorrentInfo, TrackerInfo
from app.torrents.responseVO import TorrentInfoVO
from app.torrents.trackerVO import TrackerInfoVO
from app.models.setting_templates import DownloaderTypeEnum
from app.enums.tracker_status import QBittorrentTrackerStatus, TransmissionTrackerStatus
from app.services.torrent_metadata import fetch_live_torrent_metadata
from app.services.deletion_task_manager import build_active_deletion_exclusion
from app.api.endpoints.torrent_speed import get_active_keys_snapshot

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
        None,
        max_length=8192,
        description="下载器ID（支持多选，逗号分隔）",
    )
    status: Optional[str] = Field(
        None,
        max_length=8192,
        description="种子状态（支持多选，逗号分隔；error 满足 status='error' 或 has_tracker_error=True 之一）",
    )
    category_like: Optional[str] = Field(None, description="分类模糊搜索")
    tags_like: Optional[str] = Field(None, description="标签模糊搜索")
    active_only: bool = Field(False, description="仅显示活动种子")
    min_size: Optional[int] = Field(None, description="最小文件大小(字节)")
    page: int = Field(1, ge=1, description="页码(从1开始)")
    pageSize: int = Field(20, ge=1, le=100000, description="每页记录数")
    sort_by: Literal["name", "size", "status", "ratio", "added_date"] = Field(
        "added_date",
        description="排序字段",
    )
    sort_order: Literal["asc", "desc"] = Field("desc", description="排序方向")

    @field_validator("downloader_id", "status")
    @classmethod
    def validate_multi_select_size(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        entries = [item.strip() for item in value.split(",") if item.strip()]
        if len(entries) > 500:
            raise ValueError("多选过滤项不能超过500个")
        return value


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
    active_table = None
    active_connection = None
    active_snapshot = None
    try:
        # 计算偏移量
        offset = (query.page - 1) * query.pageSize

        # 构建基础过滤条件
        base_conditions = [
            TorrentInfo.dr == 0,  # 未删除
            TorrentInfo.hash.isnot(None),
            TorrentInfo.hash != "",  # hash不为空
        ]
        active_deletion_exclusion = build_active_deletion_exclusion(TorrentInfo.info_id)
        if active_deletion_exclusion is not None:
            base_conditions.append(active_deletion_exclusion)

        if query.active_only:
            active_snapshot = get_active_keys_snapshot()
            if not active_snapshot.ready:
                return CommonResponse(
                    status="partial",
                    msg="活动种子快照尚未就绪，请刷新速度快照后重试",
                    code="206",
                    data={
                        "total": 0,
                        "page": query.page,
                        "pageSize": query.pageSize,
                        "list": [],
                        "activeSnapshotReady": False,
                        "activeSnapshotStatus": active_snapshot.status.value,
                    },
                )

            active_keys = set(active_snapshot.keys)
            if not active_keys:
                return CommonResponse(
                    status="success",
                    msg="查询成功",
                    code="200",
                    data={
                        "total": 0,
                        "page": query.page,
                        "pageSize": query.pageSize,
                        "list": [],
                        "activeSnapshotReady": True,
                        "activeSnapshotStatus": active_snapshot.status.value,
                    },
                )

            active_connection = db.connection()
            active_table = Table(
                f"duplicate_active_keys_{uuid.uuid4().hex}",
                MetaData(),
                Column("downloader_id", String, primary_key=True),
                Column("torrent_hash", String, primary_key=True),
                prefixes=["TEMPORARY"],
            )
            active_table.create(bind=active_connection)
            active_connection.execute(
                active_table.insert(),
                [
                    {"downloader_id": downloader_id, "torrent_hash": torrent_hash}
                    for downloader_id, torrent_hash in active_keys
                ],
            )

        # 应用过滤条件
        if query.name_like:
            base_conditions.append(TorrentInfo.name.like(f"%{query.name_like}%"))

        if query.downloader_id:
            # 支持多选：逗号分隔的字符串
            downloader_ids = list(
                dict.fromkeys(
                    downloader_id.strip() for downloader_id in query.downloader_id.split(",") if downloader_id.strip()
                )
            )
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
            statuses = list(dict.fromkeys(status.strip() for status in query.status.split(",") if status.strip()))
            # error 口径与 getList/advanced_search 一致：status='error' 或
            # has_tracker_error=True 之一即命中，避免同一种子在不同页面筛选结果分歧。
            status_conditions = []
            for status_value in statuses:
                if status_value == "error":
                    status_conditions.append(
                        or_(TorrentInfo.status == "error", TorrentInfo.has_tracker_error.is_(True))
                    )
                else:
                    status_conditions.append(TorrentInfo.status == status_value)
            if status_conditions:
                # 空列表：不添加过滤条件（避免SQL语法错误）
                base_conditions.append(or_(*status_conditions))

        if query.category_like:
            base_conditions.append(TorrentInfo.category.like(f"%{query.category_like}%"))

        if query.tags_like:
            base_conditions.append(TorrentInfo.tags.like(f"%{query.tags_like}%"))

        if query.min_size is not None:
            base_conditions.append(TorrentInfo.size >= query.min_size)

        # 第一步：构建子查询，找出符合条件的所有种子
        filtered_torrents_query = select(TorrentInfo.hash).where(and_(*base_conditions))
        if active_table is not None:
            filtered_torrents_query = filtered_torrents_query.join(
                active_table,
                and_(
                    TorrentInfo.downloader_id == active_table.c.downloader_id,
                    TorrentInfo.hash == active_table.c.torrent_hash,
                ),
            )
        filtered_torrents = filtered_torrents_query.alias()

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
        if active_table is not None:
            main_query = main_query.join(
                active_table,
                and_(
                    TorrentInfo.downloader_id == active_table.c.downloader_id,
                    TorrentInfo.hash == active_table.c.torrent_hash,
                ),
            )

        # 默认按添加时间倒序；允许列表列头在重复任务模式下继续切换排序。
        # 添加时间始终作为非时间字段的次排序键，info_id 提供稳定分页终排序键。
        sort_columns: Dict[str, Any] = {
            "name": TorrentInfo.name,
            "size": TorrentInfo.size,
            "status": TorrentInfo.status,
            "ratio": TorrentInfo.ratio,
            "added_date": TorrentInfo.added_date,
        }
        sort_column = sort_columns[query.sort_by]
        primary_order = sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
        secondary_orders: List[Any] = []
        if query.sort_by != "added_date":
            secondary_orders.append(TorrentInfo.added_date.desc())
        secondary_orders.append(TorrentInfo.info_id.desc())
        main_query = main_query.order_by(primary_order, *secondary_orders)

        # 查询有重复的种子总数
        count_query = select(func.count()).select_from(main_query.alias())
        total_result = db.execute(count_query).scalar()
        total = total_result if total_result else 0

        # 应用分页
        main_query = main_query.offset(offset).limit(query.pageSize)

        # Reuse the paginated selector for every related lookup.  Passing a page of
        # up to 100,000 ids/hashes through ``IN (...)`` exceeds SQLite's 32,766
        # bind-variable limit in the Windows build.  Joining this selector keeps
        # the number of bind parameters independent from the requested page size.
        page_identity_subquery = main_query.with_only_columns(
            TorrentInfo.info_id,
            TorrentInfo.hash,
            TorrentInfo.downloader_id,
        ).subquery()

        # 执行查询
        result = db.execute(main_query)
        torrent_records = result.scalars().all()

        # ✅ 新增：批量查询tracker信息（避免N+1查询问题）
        if torrent_records:
            # 批量查询tracker信息
            all_trackers = (
                db.query(TrackerInfo)
                .join(
                    page_identity_subquery,
                    TrackerInfo.torrent_info_id == page_identity_subquery.c.info_id,
                )
                .filter(
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
                    .join(
                        page_identity_subquery,
                        BtDownloaders.downloader_id == page_identity_subquery.c.downloader_id,
                    )
                    .distinct()
                    .all()
                )

                for dl in downloaders:
                    dl_type_raw = dl.downloader_type
                    dl_type_int = DownloaderTypeEnum.normalize(dl_type_raw)
                    downloader_types[str(dl.downloader_id)] = DownloaderTypeEnum(dl_type_int).to_name()
            except Exception as e:
                logger.warning(f"查询下载器类型失败，使用默认值: {e}")
        else:
            tracker_map = {}
            downloader_types = {}

        # 同 hash 的名称和大小是种子固有属性。即使当前分页中的某条历史记录为空，
        # 也可先从同组的完整数据库记录回填，再尝试从在线下载器获取其专属元数据。
        shared_metadata: Dict[str, Dict[str, Any]] = {}
        if torrent_records:
            page_hashes_subquery = (
                select(page_identity_subquery.c.hash)
                .where(page_identity_subquery.c.hash.isnot(None))
                .distinct()
                .subquery()
            )
            intrinsic_rows = (
                db.query(
                    TorrentInfo.hash,
                    func.max(func.nullif(TorrentInfo.name, "")).label("name"),
                    func.max(TorrentInfo.size).label("size"),
                )
                .join(
                    page_hashes_subquery,
                    TorrentInfo.hash == page_hashes_subquery.c.hash,
                )
                .filter(TorrentInfo.dr == 0)
                .group_by(TorrentInfo.hash)
                .all()
            )
            for row in intrinsic_rows:
                torrent_hash = _normalized_hash(row.hash)
                shared = shared_metadata.setdefault(torrent_hash, {})
                if row.name and not shared.get("name"):
                    shared["name"] = row.name
                if row.size and not shared.get("size"):
                    shared["size"] = int(row.size)

        live_metadata = await fetch_live_torrent_metadata(http_request.app, torrent_records, downloader_types)

        # 转换为VO格式并填充tracker信息
        # 展示覆写与 has_tracker_error 判定共用同一关键词池（每请求加载一次）
        tracker_keyword_map = load_active_keyword_map(db)
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
            downloader_type = downloader_types.get(str(torrent.downloader_id), "qbittorrent")

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

                # 展示对齐判定：与 getList 同口径，消息命中失败池时覆写
                # "工作失败"（Transmission 200+failure reason 会被记为状态码 2）。
                if tracker_display_failed(
                    tracker.last_announce_succeeded,
                    tracker.last_announce_msg,
                    tracker_keyword_map,
                    downloader_type,
                ):
                    announce_status_text = FAILED_DISPLAY_TEXT

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

                # scrape 列同口径独立覆写（只看 scrape 消息与 scrape 状态码）。
                if tracker_display_failed(
                    tracker.last_scrape_succeeded,
                    tracker.last_scrape_msg,
                    tracker_keyword_map,
                    downloader_type,
                ):
                    scrape_status_text = FAILED_DISPLAY_TEXT

                # 构建tracker_info对象
                tracker_vo = TrackerInfoVO(
                    tracker_id=str(tracker.tracker_id) if tracker.tracker_id else None,
                    tracker_name=str(tracker.tracker_name) if tracker.tracker_name else None,
                    tracker_url=str(tracker.tracker_url) if tracker.tracker_url else None,
                    last_announce_succeeded=announce_status_text,
                    last_announce_msg=str(tracker.last_announce_msg) if tracker.last_announce_msg else None,
                    last_scrape_succeeded=scrape_status_text,
                    last_scrape_msg=str(tracker.last_scrape_msg) if tracker.last_scrape_msg else None,
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
            last_announce_succeeded_str = ";".join(last_announce_succeededs) if last_announce_succeededs else ""
            last_announce_msg_str = ";".join(last_announce_msgs) if last_announce_msgs else ""
            last_scrape_succeeded_str = ";".join(last_scrape_succeededs) if last_scrape_succeededs else ""

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

        response_data = {
            "total": total,
            "page": query.page,
            "pageSize": query.pageSize,
            "list": torrent_list,
        }
        if active_snapshot is not None:
            response_data.update(
                {
                    "activeSnapshotReady": True,
                    "activeSnapshotStatus": active_snapshot.status.value,
                }
            )

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data=response_data,
        )

    except Exception as e:
        logger.error(f"查询重复种子失败: {e}", exc_info=True)

        # 返回错误信息,但状态码为200
        return CommonResponse(status="error", msg=f"查询失败: {str(e)}", code="500", data=None)
    finally:
        if active_table is not None and active_connection is not None:
            try:
                active_table.drop(bind=active_connection, checkfirst=True)
            except Exception as cleanup_error:
                logger.warning("清理重复查询活动种子临时表失败: %s", cleanup_error)
