import re
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple

from sqlalchemy import Column, MetaData, String, Table, and_, asc, desc, false, func, or_
from sqlalchemy.orm import Session

from app.torrents.models import TorrentInfo, TrackerInfo
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.core.reannounce_config_operations import extract_domains_from_trackers
from app.services.deletion_task_manager import build_active_deletion_exclusion
from app.services.torrent_vo_conversion import convert_to_vos_with_trackers
from app.services.torrent_ratio_values import normalize_ratio

logger = logging.getLogger(__name__)


# 自定义序列化器处理特殊类型
def custom_serializer(obj):
    """处理 JSON 不支持的特殊类型"""
    if isinstance(obj, datetime):
        return obj.isoformat()  # 转换为 ISO 8601 字符串
    if isinstance(obj, set):
        return list(obj)  # 集合转列表
    if hasattr(obj, "__dict__"):
        return obj.__dict__  # 自定义对象转字典
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _escape_like_literal(value: str, escape_char: str = "\\") -> str:
    """转义 LIKE 模式中的通配符（%/_/转义符本身），配合 like(escape=...) 按字面量匹配。"""
    return "".join(f"{escape_char}{ch}" if ch in ("%", "_", escape_char) else ch for ch in value)


# 通用查询方法
def get_torrent_infos(
    db: Session,
    downloader_id: Optional[str] = None,
    downloader_name_like: Optional[str] = None,
    name_like: Optional[str] = None,
    save_path_like: Optional[str] = None,
    size_min: Optional[str] = None,
    size_max: Optional[str] = None,
    added_date_min: Optional[str] = None,
    added_date_max: Optional[str] = None,
    completed_date_min: Optional[str] = None,
    completed_date_max: Optional[str] = None,
    tags_like: Optional[str] = None,
    category_like: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    tracker: Optional[str] = None,
    tracker_domain: Optional[str] = None,
    active_keys: Optional[Set[Tuple[str, str]]] = None,
    same_content_only: bool = False,
    single_error_only: bool = False,
) -> Dict[str, Any]:
    """通用查询方法，支持多种过滤条件和排序，返回数据总数和列表"""
    # 构建基础查询（排除回收站中的种子：dr=0 且 deleted_at=NULL）
    query = db.query(TorrentInfo).filter(
        and_(TorrentInfo.dr == 0, TorrentInfo.deleted_at.is_(None))  # 只显示未移入回收站的种子
    )

    # 构建计数查询（相同的过滤条件）
    count_query = db.query(TorrentInfo).filter(
        and_(TorrentInfo.dr == 0, TorrentInfo.deleted_at.is_(None))  # 只统计未移入回收站的种子
    )

    # 业务删除状态落库前，也立即隐藏 pending/running 删除任务中的种子。
    active_deletion_exclusion = build_active_deletion_exclusion(TorrentInfo.info_id)
    if active_deletion_exclusion is not None:
        query = query.filter(active_deletion_exclusion)
        count_query = count_query.filter(active_deletion_exclusion)

    # tracker_domain 在过滤闭包与 VO 命中标记两处使用，统一在入口归一一次，
    # 避免两处各自解析造成口径漂移。
    requested_tracker_domains: List[str] = []
    if tracker_domain is not None:
        requested_tracker_domains = extract_domains_from_trackers(
            [value.strip() for value in tracker_domain.split(",") if value.strip()]
        )
        logger.debug("[tracker-domain-filter] 原始输入=%r 归一域名=%s", tracker_domain, requested_tracker_domains)

    # 添加过滤条件
    if downloader_id:
        # 支持多选：逗号分隔的字符串
        downloader_ids = [id.strip() for id in downloader_id.split(",") if id.strip()]
        if len(downloader_ids) == 0:
            # 空列表：不添加过滤条件（避免SQL语法错误）
            pass
        elif len(downloader_ids) == 1:
            # 单个下载器：使用精确匹配
            query = query.filter(TorrentInfo.downloader_id == downloader_ids[0])
            count_query = count_query.filter(TorrentInfo.downloader_id == downloader_ids[0])
        else:
            # 多个下载器：使用 in_ 查询（或关系）
            query = query.filter(TorrentInfo.downloader_id.in_(downloader_ids))
            count_query = count_query.filter(TorrentInfo.downloader_id.in_(downloader_ids))

    if downloader_name_like:
        like_pattern = f"%{downloader_name_like}%"
        query = query.filter(TorrentInfo.downloader_name.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.downloader_name.like(like_pattern))

    if name_like:
        like_pattern = f"%{name_like}%"
        query = query.filter(TorrentInfo.name.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.name.like(like_pattern))

    if save_path_like:
        like_pattern = f"%{save_path_like}%"
        query = query.filter(TorrentInfo.save_path.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.save_path.like(like_pattern))

    if size_min is not None:
        size_min_bytes = parse_size_string(size_min)
        if size_min_bytes is not None:
            query = query.filter(TorrentInfo.size >= size_min_bytes)
            count_query = count_query.filter(TorrentInfo.size >= size_min_bytes)

    if size_max is not None:
        size_max_bytes = parse_size_string(size_max)
        if size_max_bytes is not None:
            query = query.filter(TorrentInfo.size <= size_max_bytes)
            count_query = count_query.filter(TorrentInfo.size <= size_max_bytes)

    if added_date_min is not None:
        added_date_min_datetime = parse_datetime_string(added_date_min)
        if added_date_min_datetime is not None:
            query = query.filter(TorrentInfo.added_date >= added_date_min_datetime)
            count_query = count_query.filter(TorrentInfo.added_date >= added_date_min_datetime)

    if added_date_max is not None:
        added_date_max_datetime = parse_datetime_string(added_date_max)
        if added_date_max_datetime is not None:
            query = query.filter(TorrentInfo.added_date <= added_date_max_datetime)
            count_query = count_query.filter(TorrentInfo.added_date <= added_date_max_datetime)

    if completed_date_min is not None:
        completed_date_min_datetime = parse_datetime_string(completed_date_min)
        if completed_date_min_datetime is not None:
            query = query.filter(TorrentInfo.completed_date >= completed_date_min_datetime)
            count_query = count_query.filter(TorrentInfo.completed_date >= completed_date_min_datetime)

    if completed_date_max is not None:
        completed_date_max_datetime = parse_datetime_string(completed_date_max)
        if completed_date_max_datetime is not None:
            query = query.filter(TorrentInfo.completed_date <= completed_date_max_datetime)
            count_query = count_query.filter(TorrentInfo.completed_date <= completed_date_max_datetime)

    if tags_like:
        like_pattern = f"%{tags_like}%"
        query = query.filter(TorrentInfo.tags.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.tags.like(like_pattern))

    if category_like:
        like_pattern = f"%{category_like}%"
        query = query.filter(TorrentInfo.category.like(like_pattern))
        count_query = count_query.filter(TorrentInfo.category.like(like_pattern))

    # 状态与 Tracker 是种子行级属性：若参与同内容分组候选判定，组内仅剩一条
    # 错误/命中任务时整个 (name,size) 组会因“不同 Hash 数 < 2”被筛塌，与功能
    # 目的（从同内容组里找出错误/特定 Tracker 的任务）相悖。因此 same_content_only
    # 时这三个筛选延后到分组 join 之后应用，仅过滤组内显示行；普通列表模式在
    # 原位置立即应用，语义不变。
    def _apply_row_display_filters(q, cq):  # noqa: ANN001 - 内部工具函数
        if tracker:
            tracker_query_result = (
                db.query(TrackerInfo.torrent_info_id)
                .filter(TrackerInfo.tracker_url.like(f"%{_escape_like_literal(tracker)}%", escape="\\"))
                .filter(TrackerInfo.dr == 0)
                .all()
            )
            logger.debug("[tracker-filter] 关键字=%r 命中tracker行数=%d", tracker, len(tracker_query_result))
            info_id_list = [row[0] for row in tracker_query_result]
            if info_id_list:
                q = q.filter(TorrentInfo.info_id.in_(info_id_list))
                cq = cq.filter(TorrentInfo.info_id.in_(info_id_list))
            else:
                # 无任何匹配 tracker 行时应返回空列表；跳过过滤会静默放宽为返回全部。
                q = q.filter(false())
                cq = cq.filter(false())

        if tracker_domain is not None:
            requested_domains = requested_tracker_domains
            if not requested_domains:
                q = q.filter(false())
                cq = cq.filter(false())
            else:
                domain_conditions = []
                lowered_url = func.lower(TrackerInfo.tracker_url)
                lowered_host = func.lower(TrackerInfo.tracker_host)
                for domain in requested_domains:
                    # tracker_host 由同步任务保存为 netloc（可能带端口）；URL 作为
                    # 旧数据/手动写入数据的回退，均只匹配 URL 的主机部分。like 绑定
                    # escape 使域名中的 _/% 按字面量匹配；Python 侧同口径谓词见
                    # tracker_row_matches_domains。
                    escaped = _escape_like_literal(domain)
                    domain_conditions.append(
                        or_(
                            lowered_host == domain,
                            lowered_host.like(f"{escaped}:%", escape="\\"),
                            lowered_url == domain,
                            lowered_url.like(f"{escaped}/%", escape="\\"),
                            lowered_url.like(f"{escaped}:%", escape="\\"),
                            lowered_url.like(f"%://{escaped}", escape="\\"),
                            lowered_url.like(f"%://{escaped}/%", escape="\\"),
                            lowered_url.like(f"%://{escaped}:%", escape="\\"),
                        )
                    )
                tracker_domain_exists = (
                    db.query(TrackerInfo.tracker_id)
                    .filter(
                        TrackerInfo.torrent_info_id == TorrentInfo.info_id,
                        TrackerInfo.dr == 0,
                        or_(*domain_conditions),
                    )
                    .exists()
                )
                q = q.filter(tracker_domain_exists)
                cq = cq.filter(tracker_domain_exists)

        # 状态筛选：支持多选（逗号分隔），error状态满足 status='error' 或 has_tracker_error=True 之一即可
        if status:
            # 支持多选：逗号分隔的字符串
            statuses = [s.strip() for s in status.split(",") if s.strip()]

            if len(statuses) == 0:
                # 空列表：不添加过滤条件（避免SQL语法错误）
                pass
            elif len(statuses) == 1:
                # 单个状态：使用原有逻辑
                if statuses[0] == "error":
                    q = q.filter(or_(TorrentInfo.status == "error", TorrentInfo.has_tracker_error.is_(True)))
                    cq = cq.filter(or_(TorrentInfo.status == "error", TorrentInfo.has_tracker_error.is_(True)))
                else:
                    q = q.filter(TorrentInfo.status == statuses[0])
                    cq = cq.filter(TorrentInfo.status == statuses[0])
            else:
                # 多个状态：使用 or_ 组合多个条件（或关系）
                status_conditions = []
                for s in statuses:
                    if s == "error":
                        # error 状态特殊处理
                        status_conditions.append(
                            or_(TorrentInfo.status == "error", TorrentInfo.has_tracker_error.is_(True))
                        )
                    else:
                        status_conditions.append(TorrentInfo.status == s)

                if status_conditions:
                    q = q.filter(or_(*status_conditions))
                    cq = cq.filter(or_(*status_conditions))
        return q, cq

    if not same_content_only:
        query, count_query = _apply_row_display_filters(query, count_query)

    active_table = None
    active_connection = None
    try:
        # 活动集合可能远超 SQLite 绑定参数上限。将键通过 executemany 写入连接级 TEMP 表，
        # 再让列表与计数查询联接同一张表；每次 INSERT 只使用两个绑定参数。
        if active_keys is not None:
            if not active_keys:
                return {"total": 0, "data": []}

            active_connection = db.connection()
            active_table = Table(
                f"active_torrent_keys_{uuid.uuid4().hex}",
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
            join_condition = and_(
                TorrentInfo.downloader_id == active_table.c.downloader_id,
                TorrentInfo.hash == active_table.c.torrent_hash,
            )
            query = query.join(active_table, join_condition)
            count_query = count_query.join(active_table, join_condition)

        if same_content_only:
            # 从已应用普通列表筛选（含活动快照）的 count_query 派生候选组，
            # 保证名称、下载器、状态等条件与列表 total/list 口径完全一致。
            same_content_valid_row = and_(
                TorrentInfo.name.isnot(None),
                func.length(func.trim(TorrentInfo.name)) > 0,
                TorrentInfo.size.isnot(None),
                TorrentInfo.size > 0,
                TorrentInfo.hash.isnot(None),
                func.length(func.trim(TorrentInfo.hash)) > 0,
            )
            query = query.filter(same_content_valid_row)
            count_query = count_query.filter(same_content_valid_row)
            same_content_groups = (
                count_query.with_entities(
                    TorrentInfo.name.label("same_content_name"),
                    TorrentInfo.size.label("same_content_size"),
                )
                .group_by(TorrentInfo.name, TorrentInfo.size)
                .having(func.count(func.distinct(func.lower(func.trim(TorrentInfo.hash)))) >= 2)
                .subquery()
            )
            same_content_join = and_(
                TorrentInfo.name == same_content_groups.c.same_content_name,
                TorrentInfo.size == same_content_groups.c.same_content_size,
            )
            query = query.join(same_content_groups, same_content_join)
            count_query = count_query.join(same_content_groups, same_content_join)
            # 状态/Tracker 仅过滤组内显示行，不参与上方分组候选判定：
            # 组是否成立由未应用这三类筛选的候选集决定。
            query, count_query = _apply_row_display_filters(query, count_query)

        if single_error_only:
            # 快捷排查只保留错误种子；唯一性基于全局可见任务计算，不能受当前
            # 下载器、Tracker、状态等筛选条件影响，否则会把同内容的其它任务漏掉。
            error_filter = or_(TorrentInfo.status == "error", TorrentInfo.has_tracker_error.is_(True))
            query = query.filter(error_filter)
            count_query = count_query.filter(error_filter)

            unique_content_valid_row = and_(
                TorrentInfo.name.isnot(None),
                func.length(func.trim(TorrentInfo.name)) > 0,
                TorrentInfo.size.isnot(None),
                TorrentInfo.size > 0,
                TorrentInfo.hash.isnot(None),
                func.length(func.trim(TorrentInfo.hash)) > 0,
            )
            unique_content_query = db.query(TorrentInfo).filter(
                TorrentInfo.dr == 0,
                TorrentInfo.deleted_at.is_(None),
                unique_content_valid_row,
            )
            unique_deletion_exclusion = build_active_deletion_exclusion(TorrentInfo.info_id)
            if unique_deletion_exclusion is not None:
                unique_content_query = unique_content_query.filter(unique_deletion_exclusion)
            unique_content_groups = (
                unique_content_query.with_entities(
                    TorrentInfo.name.label("single_content_name"),
                    TorrentInfo.size.label("single_content_size"),
                )
                .group_by(TorrentInfo.name, TorrentInfo.size)
                .having(func.count(TorrentInfo.info_id) == 1)
                .subquery()
            )
            unique_content_join = and_(
                TorrentInfo.name == unique_content_groups.c.single_content_name,
                TorrentInfo.size == unique_content_groups.c.single_content_size,
            )
            query = query.join(unique_content_groups, unique_content_join)
            count_query = count_query.join(unique_content_groups, unique_content_join)

        # 获取总数
        total = count_query.count()

        # 处理排序
        if sort_by:
            sort_column = getattr(TorrentInfo, sort_by, None)
            if sort_column is not None:
                if sort_order and sort_order.lower() == "asc":
                    query = query.order_by(asc(sort_column))
                else:
                    query = query.order_by(desc(sort_column))
        else:
            # 默认按添加时间倒序排序
            query = query.order_by(desc(TorrentInfo.added_date))

        # 分页必须具有确定顺序；业务排序值相同时按复合主键稳定兜底，
        # 避免相邻页重复或漏行。兜底统一升序，不改变主排序方向。
        query = query.order_by(
            asc(TorrentInfo.info_id),
            asc(TorrentInfo.downloader_id),
            asc(TorrentInfo.downloader_name),
        )

        # 分页查询
        query_result_list = query.offset(skip).limit(limit).all()
        data = convert_to_vos_with_trackers(
            db,
            query_result_list,
            requested_tracker_domains=requested_tracker_domains or None,
        )

        logger.debug(
            "[torrent-list] total=%d 本页=%d tracker=%r tracker_domain=%r same_content=%s single_error=%s",
            total,
            len(data),
            tracker,
            tracker_domain,
            same_content_only,
            single_error_only,
        )
        if requested_tracker_domains:
            matched_rows = sum(
                1 for vo in data if any(getattr(row, "matched_domain", None) for row in (vo.tracker_info or []))
            )
            matched_marks = sum(
                1 for vo in data for row in (vo.tracker_info or []) if getattr(row, "matched_domain", None)
            )
            logger.debug(
                "[tracker-domain-filter] 本页%d行中%d行含命中tracker，共%d个命中标记",
                len(data),
                matched_rows,
                matched_marks,
            )

        return {"total": total, "data": data}
    finally:
        if active_table is not None and active_connection is not None:
            try:
                active_table.drop(bind=active_connection)
            except Exception:
                logger.exception("清理活动种子临时表失败: %s", active_table.name)


def get_torrent_infos_legacy(
    db: Session,
    downloader_id: Optional[str] = None,
    downloader_name_like: Optional[str] = None,
    name_like: Optional[str] = None,
    save_path_like: Optional[str] = None,
    size_min: Optional[str] = None,
    size_max: Optional[str] = None,
    added_date_min: Optional[str] = None,
    added_date_max: Optional[str] = None,
    completed_date_min: Optional[str] = None,
    completed_date_max: Optional[str] = None,
    tags_like: Optional[str] = None,
    category_like: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    tracker: Optional[str] = None,
    tracker_domain: Optional[str] = None,
    active_keys: Optional[Set[Tuple[str, str]]] = None,
    single_error_only: bool = False,
) -> List[TorrentInfo]:
    """通用查询方法（旧版本，保持兼容性），支持多种过滤条件和排序"""
    result = get_torrent_infos(
        db=db,
        downloader_id=downloader_id,
        downloader_name_like=downloader_name_like,
        name_like=name_like,
        save_path_like=save_path_like,
        size_min=size_min,
        size_max=size_max,
        added_date_min=added_date_min,
        added_date_max=added_date_max,
        completed_date_min=completed_date_min,
        completed_date_max=completed_date_max,
        tags_like=tags_like,
        category_like=category_like,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        tracker=tracker,
        tracker_domain=tracker_domain,
        active_keys=active_keys,
        single_error_only=single_error_only,
    )
    return result["data"]


def _safe_float(value: Any) -> Optional[float]:
    """Backward-compatible ratio parser used by legacy call sites.

    New update paths must use ``apply_normalized_ratio_fields`` so malformed or
    missing downloader data does not erase an existing good value.
    """
    return normalize_ratio(value).value_for_insert()


def parse_size_string(size_str: Optional[str]) -> Optional[int]:
    """将大小字符串转换为字节数"""
    if not size_str:
        return None

    # 使用正则表达式匹配数字和单位
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([BKMG]?)B?$", size_str, re.IGNORECASE)
    if not match:
        return None

    size_value = float(match.group(1))
    unit = match.group(2).upper()

    # 根据单位计算字节数
    if unit == "K":  # KB
        return int(size_value * 1024)
    elif unit == "M":  # MB
        return int(size_value * 1024 * 1024)
    elif unit == "G":  # GB
        return int(size_value * 1024 * 1024 * 1024)
    elif unit == "T":  # TB
        return int(size_value * 1024 * 1024 * 1024 * 1024)
    else:  # B (无单位或B)
        return int(size_value)


def parse_datetime_string(datetime_str: Optional[str]) -> Optional[datetime]:
    """将日期时间字符串转换为datetime对象"""
    if not datetime_str:
        return None

    # 尝试解析不同格式的日期时间字符串
    formats = [
        "%Y-%m-%d %H:%M:%S",  # yyyy-mm-dd hh24:mi:ss
        "%Y-%m-%d %H:%M",  # yyyy-mm-dd hh24:mi
        "%Y-%m-%d",  # yyyy-mm-dd
        "%Y/%m/%d %H:%M:%S",  # yyyy/mm/dd hh24:mi:ss
        "%Y/%m/%d %H:%M",  # yyyy/mm/dd hh24:mi
        "%Y/%m/%d",  # yyyy/mm/dd
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(datetime_str, fmt)
            return dt
        except ValueError:
            continue

    # 如果所有格式都失败，尝试解析ISO格式
    try:
        dt = datetime.fromisoformat(datetime_str)
        return dt
    except ValueError:
        return None


def convert_transmission_status(transmission_status: str) -> str:
    """
    将Transmission状态转换为通用状态

    注意：此函数保留以向后兼容，建议直接使用 TorrentStatusMapper.convert_transmission_status()
    """
    return TorrentStatusMapper.convert_transmission_status(transmission_status)
