import asyncio
import hashlib
import re
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import bencodepy
from sqlalchemy import and_, or_, asc, desc
from sqlalchemy.orm import Session

from app.torrents.models import TorrentInfo as torrentInfoModel, TorrentInfo, TrackerInfo as trackerInfoModel, TrackerInfo
from app.torrents.responseVO import TorrentInfoVO
from app.torrents.trackerVO import TrackerInfoVO
from app.models.setting_templates import DownloaderTypeEnum
from app.core.torrent_status_mapper import TorrentStatusMapper
from transmission_rpc import Client as trClient
from app.database import AsyncSessionLocal
from app.services.audit_service import get_audit_service

logger = logging.getLogger(__name__)


# 自定义序列化器处理特殊类型
def custom_serializer(obj):
    """处理 JSON 不支持的数据类型"""
    if isinstance(obj, datetime):
        return obj.isoformat()  # 转换为 ISO 8601 字符串
    if isinstance(obj, set):
        return list(obj)  # 集合转列表
    if hasattr(obj, '__dict__'):
        return obj.__dict__  # 自定义对象转字典
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


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
) -> Dict[str, Any]:
    """通用查询方法，支持多种过滤条件和排序，返回数据总数和列表"""
    # 构建基础查询（排除回收站中的种子：dr=0 且 deleted_at=NULL）
    query = db.query(TorrentInfo).filter(
        and_(
            TorrentInfo.dr == 0,
            TorrentInfo.deleted_at.is_(None)  # 只显示未移入回收站的种子
        )
    )

    # 构建计数查询（相同的过滤条件）
    count_query = db.query(TorrentInfo).filter(
        and_(
            TorrentInfo.dr == 0,
            TorrentInfo.deleted_at.is_(None)  # 只统计未移入回收站的种子
        )
    )

    # 添加过滤条件
    if downloader_id:
        # 支持多选：逗号分隔的字符串
        downloader_ids = [id.strip() for id in downloader_id.split(',') if id.strip()]
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

    if tracker:
        tracker_query_result = db.query(TrackerInfo.torrent_info_id).filter(
            TrackerInfo.tracker_url.like(f"%{tracker}%")).filter(TrackerInfo.dr == 0).all()
        if tracker_query_result.__len__() > 0:
            info_id_list = [row[0] for row in tracker_query_result]
            query = query.filter(TorrentInfo.info_id.in_(info_id_list))
            count_query = count_query.filter(TorrentInfo.info_id.in_(info_id_list))

    # 状态筛选：支持多选（逗号分隔），error状态满足 status='error' 或 has_tracker_error=True 之一即可
    if status:
        # 支持多选：逗号分隔的字符串
        statuses = [s.strip() for s in status.split(',') if s.strip()]

        if len(statuses) == 0:
            # 空列表：不添加过滤条件（避免SQL语法错误）
            pass
        elif len(statuses) == 1:
            # 单个状态：使用原有逻辑
            if statuses[0] == 'error':
                query = query.filter(
                    or_(
                        TorrentInfo.status == 'error',
                        TorrentInfo.has_tracker_error == True
                    )
                )
                count_query = count_query.filter(
                    or_(
                        TorrentInfo.status == 'error',
                        TorrentInfo.has_tracker_error == True
                    )
                )
            else:
                query = query.filter(TorrentInfo.status == statuses[0])
                count_query = count_query.filter(TorrentInfo.status == statuses[0])
        else:
            # 多个状态：使用 or_ 组合多个条件（或关系）
            status_conditions = []
            for s in statuses:
                if s == 'error':
                    # error 状态特殊处理
                    status_conditions.append(
                        or_(
                            TorrentInfo.status == 'error',
                            TorrentInfo.has_tracker_error == True
                        )
                    )
                else:
                    status_conditions.append(TorrentInfo.status == s)

            if status_conditions:
                query = query.filter(or_(*status_conditions))
                count_query = count_query.filter(or_(*status_conditions))

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

    # 分页查询
    query_result_list = query.offset(skip).limit(limit).all()
    data = [convert_to_vo_with_trackers(db, torrent) for torrent in query_result_list]

    return {
        "total": total,
        "data": data
    }


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
        tracker=tracker
    )
    return result["data"]


def convert_to_vo(torrent: torrentInfoModel) -> TorrentInfoVO:
    """将数据库模型转换为VO对象"""
    # 将datetime对象转换为时间戳
    added_timestamp = int(torrent.added_date.timestamp()) if torrent.added_date else None
    completed_timestamp = int(torrent.completed_date.timestamp()) if torrent.completed_date else None

    return TorrentInfoVO(
        info_id=torrent.info_id,
        downloader_id=torrent.downloader_id,
        downloader_name=torrent.downloader_name,
        torrent_id=torrent.torrent_id,
        hash=torrent.hash,
        name=torrent.name,
        save_path=torrent.save_path,
        size=torrent.size,
        status=torrent.status,
        torrent_file=torrent.torrent_file,
        added_date=added_timestamp,
        completed_date=completed_timestamp,
        ratio=torrent.ratio,
        ratio_limit=torrent.ratio_limit,
        tags=torrent.tags,
        category=torrent.category,
        super_seeding=torrent.super_seeding,
        enabled=torrent.enabled
    )


def convert_to_vo_with_trackers(db: Session, torrent: torrentInfoModel) -> TorrentInfoVO:
    """将数据库模型转换为VO对象，包含tracker信息"""
    # 保持datetime对象不变，让 Pydantic 序列化时自动转换为 ISO 8601 格式

    # 导入枚举类
    from app.enums.tracker_status import QBittorrentTrackerStatus, TransmissionTrackerStatus

    # 查询关联的tracker信息
    # 🔧 修复：使用 torrent.hash 查询 tracker，因为 tracker 表的 torrent_info_id 字段存储的是 hash
    trackers = db.query(TrackerInfo).filter(
        TrackerInfo.torrent_info_id == torrent.info_id,
        TrackerInfo.dr == 0  # 只查询未逻辑删除的tracker数据
    ).all()

    # 生成tracker_info数组（新结构）
    tracker_info_list = []

    # 生成原有字符串字段（保持向后兼容）
    tracker_names = []
    tracker_urls = []
    last_announce_succeededs = []
    last_announce_msgs = []
    last_scrape_succeededs = []

    # 确定下载器类型（用于状态映射）
    # 根据 downloader_id 查询下载器类型
    downloader_type = "qbittorrent"  # 默认为 qBittorrent
    try:
        from app.downloader.models import BtDownloaders
        downloader = db.query(BtDownloaders.downloader_type).filter(
            BtDownloaders.downloader_id == torrent.downloader_id
        ).first()
        if downloader:
            # 从 Row 对象中正确提取整数值
            # SQLAlchemy 查询单列返回 Row 对象，需要通过列名或索引访问
            if hasattr(downloader, 'downloader_type'):
                # Row 对象：通过列名访问
                downloader_type_raw = downloader.downloader_type
            elif isinstance(downloader, (tuple, list)) and len(downloader) > 0:
                # 元组或列表：通过索引访问
                downloader_type_raw = downloader[0]
            else:
                # 其他情况：直接使用（兼容旧代码）
                downloader_type_raw = downloader
            # 使用统一的枚举类方法进行类型转换
            downloader_type_int = DownloaderTypeEnum.normalize(downloader_type_raw)
            downloader_type = DownloaderTypeEnum(downloader_type_int).to_name()
    except Exception as e:
        logger.warning(f"无法查询下载器类型，使用默认值 qBittorrent: {e}")

    for tracker in trackers:
        # 将数字状态转换为中文状态
        announce_status_raw = tracker.last_announce_succeeded
        scrape_status_raw = tracker.last_scrape_succeeded

        # 映射 announce 状态
        if announce_status_raw is not None:
            try:
                announce_status_int = int(announce_status_raw)
                if downloader_type == "qbittorrent":
                    announce_status_text = QBittorrentTrackerStatus.get_display_text(announce_status_int)
                else:  # transmission
                    announce_status_text = TransmissionTrackerStatus.get_display_text(announce_status_int)
            except (ValueError, TypeError):
                # 如果无法转换为整数，保持原样
                announce_status_text = str(announce_status_raw)
        else:
            announce_status_text = None

        # 映射 scrape 状态
        if scrape_status_raw is not None:
            try:
                scrape_status_int = int(scrape_status_raw)
                if downloader_type == "qbittorrent":
                    scrape_status_text = QBittorrentTrackerStatus.get_display_text(scrape_status_int)
                else:  # transmission
                    scrape_status_text = TransmissionTrackerStatus.get_display_text(scrape_status_int)
            except (ValueError, TypeError):
                # 如果无法转换为整数，保持原样
                scrape_status_text = str(scrape_status_raw)
        else:
            scrape_status_text = None

        # 构建tracker_info对象数组
        tracker_vo = TrackerInfoVO(
            tracker_id=tracker.tracker_id,
            tracker_name=tracker.tracker_name,
            tracker_url=tracker.tracker_url,
            last_announce_succeeded=announce_status_text,  # 返回中文状态
            last_announce_msg=tracker.last_announce_msg,
            last_scrape_succeeded=scrape_status_text,  # 返回中文状态
            last_scrape_msg=tracker.last_scrape_msg
        )
        tracker_info_list.append(tracker_vo)

        # 构建原有字符串字段（保持向后兼容）
        tracker_names.append(tracker.tracker_name or "")
        tracker_urls.append(tracker.tracker_url or "")
        last_announce_succeededs.append(announce_status_text or "")
        last_announce_msgs.append(tracker.last_announce_msg or "")
        last_scrape_succeededs.append(scrape_status_text or "")

    # 将数组转换为以;分隔的字符串（保持向后兼容）
    tracker_name_str = ";".join(tracker_names) if tracker_names else ""
    tracker_url_str = ";".join(tracker_urls) if tracker_urls else ""
    last_announce_succeeded_str = ";".join(last_announce_succeededs) if last_announce_succeededs else ""
    last_announce_msg_str = ";".join(last_announce_msgs) if last_announce_msgs else ""
    last_scrape_succeeded_str = ";".join(last_scrape_succeededs) if last_scrape_succeededs else ""

    return TorrentInfoVO(
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
        added_date=torrent.added_date,  # 保持 datetime 对象，让 Pydantic 自动序列化为 ISO 8601
        completed_date=torrent.completed_date,  # 保持 datetime 对象，让 Pydantic 自动序列化为 ISO 8601
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


def parse_size_string(size_str: Optional[str]) -> Optional[int]:
    """将大小字符串转换为字节数"""
    if not size_str:
        return None

    # 使用正则表达式匹配数字和单位
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([BKMG]?)B?$', size_str, re.IGNORECASE)
    if not match:
        return None

    size_value = float(match.group(1))
    unit = match.group(2).upper()

    # 根据单位计算字节数
    if unit == 'K':  # KB
        return int(size_value * 1024)
    elif unit == 'M':  # MB
        return int(size_value * 1024 * 1024)
    elif unit == 'G':  # GB
        return int(size_value * 1024 * 1024 * 1024)
    elif unit == 'T':  # TB
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


async def calculate_info_hash(torrent_file_path: str) -> str:
    """计算种子文件的info_hash"""
    try:
        # 将文件读取和解析操作放到线程池中执行
        def read_and_decode_file(file_path):
            with open(file_path, 'rb') as f:
                file_content = f.read()
            return bencodepy.decode(file_content)

        torrent_data = await asyncio.to_thread(read_and_decode_file, torrent_file_path)

        # 获取info部分并计算SHA1哈希
        info_data = bencodepy.encode(torrent_data[b'info'])
        info_hash = hashlib.sha1(info_data).hexdigest()

        return info_hash
    except Exception as e:
        raise Exception(f"计算info_hash失败: {str(e)}")


async def get_transmission_torrent_info(tr_client: trClient, info_hash: str, timeout: int = 10) -> Optional[
    Dict[str, Any]]:
    """从Transmission获取种子信息"""
    import time

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # 获取所有种子
            torrents = tr_client.get_torrents(info_hash)
            return torrents[0]
            # 查找匹配的种子
            # for torrent in torrents:
            #     if torrent.hashString.lower() == info_hash.lower():
            #         return torrent
            #
            # time.sleep(1)
        except Exception as e:
            # 如果出错，等待一会儿再试
            await asyncio.sleep(1)

    return None


def convert_transmission_status(transmission_status: str) -> str:
    """
    将Transmission状态转换为通用状态

    注意：此函数保留以向后兼容，建议直接使用 TorrentStatusMapper.convert_transmission_status()
    """
    return TorrentStatusMapper.convert_transmission_status(transmission_status)


def create_qbittorrent_torrent_record(downloader, downloader_id, qb_torrent, tmp_file_path):
    """创建qBittorrent种子信息记录"""
    db_torrent = torrentInfoModel(
        id_=str(uuid.uuid4()),
        downloader_id=downloader_id,
        downloader_name=downloader.nickname,
        torrent_id=qb_torrent.hash,
        hash=qb_torrent.hash,
        name=qb_torrent.name,
        save_path=qb_torrent.save_path,
        size=qb_torrent.total_size,
        status=TorrentStatusMapper.convert_qbittorrent_status(qb_torrent.state),
        torrent_file="/config/qbittorrent/BT_backup/" + qb_torrent.hash + ".torrent",
        # 防御性：添加时间戳范围检查，防止负数和溢出
        added_date=datetime.fromtimestamp(qb_torrent.added_on) if qb_torrent.added_on > 0 and qb_torrent.added_on <= 2147483647 else None,
        completed_date=datetime.fromtimestamp(qb_torrent.completion_on) if qb_torrent.completion_on and qb_torrent.completion_on > 0 and qb_torrent.completion_on <= 2147483647 else None,
        ratio=str(qb_torrent.ratio),
        ratio_limit=str(qb_torrent.ratio_limit) if qb_torrent.ratio_limit != -1 else "",
        tags=",".join(qb_torrent.tags) if qb_torrent.tags else "",
        category=qb_torrent.category,
        super_seeding="1" if qb_torrent.super_seeding else "0",
        enabled=1,
        create_time=datetime.fromtimestamp(qb_torrent.added_on) if qb_torrent.added_on > 0 and qb_torrent.added_on <= 2147483647 else None,
        create_by="admin",
        update_time=datetime.fromtimestamp(qb_torrent.added_on) if qb_torrent.added_on > 0 and qb_torrent.added_on <= 2147483647 else None,
        update_by="admin",
        dr=0,  # 🔧 修复：添加缺失的 dr 参数
        progress=0  # 🔧 修复：添加缺失的 progress 参数
    )
    return db_torrent


def create_transmission_torrent_record(downloader, downloader_id, tr_torrent):
    db_torrent = torrentInfoModel(
        id_=str(uuid.uuid4()),
        downloader_id=downloader_id,
        downloader_name=downloader.nickname,
        torrent_id=tr_torrent.id,
        hash=tr_torrent.hashString,
        name=tr_torrent.name,
        save_path=tr_torrent.download_dir,
        size=tr_torrent.total_size,
        status=convert_transmission_status(tr_torrent.status),
        torrent_file=tr_torrent.torrent_file,
        added_date=tr_torrent.added_date,
        completed_date=tr_torrent.done_date if tr_torrent.done_date else None,
        ratio=str(tr_torrent.seed_ratio_limit),
        ratio_limit="",
        tags=",".join(tr_torrent.labels) if hasattr(tr_torrent, 'labels') and tr_torrent.labels else "",
        category="",
        super_seeding="",
        enabled=1,
        create_time=tr_torrent.added_date,
        create_by="admin",
        update_time=tr_torrent.added_date,
        update_by="admin",
        dr=0,  # 🔧 修复：添加缺失的 dr 参数
        progress=0  # 🔧 修复：添加缺失的 progress 参数
    )
    return db_torrent


# ==================== 审计日志辅助函数 ====================

async def _write_audit_log_async(
        operation_type: str,
        operator: str,
        torrent_info_id: str,
        operation_detail: Dict[str, Any],
        torrent_name: Optional[str],
        torrent_hash: Optional[str],
        downloader_id: str,
        operation_result: str,
        error_message: Optional[str] = None,
        new_value: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        audit_info: Optional[Dict[str, str]] = None
):
    """异步写入审计日志的辅助函数"""
    try:
        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 构建完整的操作详情
            full_detail = operation_detail.copy()
            if torrent_name:
                full_detail["torrent_name"] = torrent_name
            if torrent_hash:
                full_detail["torrent_hash"] = torrent_hash

            await audit_service.log_operation(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=full_detail,
                old_value=old_value,
                new_value=new_value,
                operation_result=operation_result,
                error_message=error_message,
                downloader_id=downloader_id,
                **(audit_info or {})
            )
    except Exception as audit_error:
        logging.error(f"记录审计日志失败: {str(audit_error)}", exc_info=True)


def _safe_write_audit_log(
        operation_type: str,
        operator: str,
        torrent_info_id: str,
        operation_detail: Dict[str, Any],
        torrent_name: Optional[str],
        torrent_hash: Optional[str],
        downloader_id: str,
        operation_result: str,
        error_message: Optional[str] = None,
        new_value: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        audit_info: Optional[Dict[str, str]] = None
):
    """
    安全地写入审计日志（带异常处理和日志记录）

    修复CRITICAL #4: asyncio.create_task的异常会被静默忽略
    使用此包装函数确保审计日志异常不会丢失，同时记录到日志文件中
    """
    try:
        asyncio.create_task(
            _write_audit_log_async(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=operation_detail,
                torrent_name=torrent_name,
                torrent_hash=torrent_hash,
                downloader_id=downloader_id,
                operation_result=operation_result,
                error_message=error_message,
                new_value=new_value,
                old_value=old_value,
                audit_info=audit_info
            )
        )
    except Exception as e:
        # 记录创建任务失败（极少发生）
        logging.error(
            f"创建审计日志任务失败 [operation_type={operation_type}, torrent_info_id={torrent_info_id}]: {str(e)}",
            exc_info=True
        )
