import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import text, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.torrents.models import TorrentInfo, TrackerInfo as TrackerInfoModel

logger = logging.getLogger(__name__)


# ===========================================================================
# Torrent CRUD
# ===========================================================================

def get_tracker_by_tracker_url(db, torrent_info_id, tracker_url):
    return db.query(TrackerInfoModel).filter(
        TrackerInfoModel.torrent_info_id == torrent_info_id).filter(
        TrackerInfoModel.tracker_url == tracker_url).filter(
        TrackerInfoModel.dr == 0).first()


def create_torrent(db: Session, torrent_data: Dict[str, Any]) -> TorrentInfo:
    """
    创建新的种子记录

    Args:
        db: 数据库会话
        torrent_data: 种子数据字典

    Returns:
        新创建的种子信息对象
    """
    # 如果没有提供ID，则生成一个UUID
    if "id_" not in torrent_data:
        torrent_data["id_"] = str(uuid.uuid4())

    db_torrent = TorrentInfo(**torrent_data)
    db.add(db_torrent)
    db.commit()
    db.refresh(db_torrent)
    return db_torrent


def get_torrent(db: Session, torrent_id: str) -> Optional[TorrentInfo]:
    """
    通过ID获取种子信息

    Args:
        db: 数据库会话
        torrent_id: 种子ID

    Returns:
        种子信息对象或None
    """
    return db.query(TorrentInfo).filter(TorrentInfo.info_id == torrent_id).first()


def get_torrent_by_hash(
        db: Session,
        hash_value: str,
        downloader_id: Optional[str] = None
) -> Optional[TorrentInfo]:
    """
    通过哈希值获取种子信息

    Args:
        db: 数据库会话
        hash_value: 种子哈希值
        downloader_id: 下载器ID（可选，用于限定查询范围）

    Returns:
        种子信息对象或None
    """
    query = db.query(TorrentInfo).filter(
        TorrentInfo.hash == hash_value,
        TorrentInfo.dr == 0  # 只查询未删除的记录
    )

    # 如果提供了 downloader_id，则限定查询范围
    if downloader_id is not None:
        query = query.filter(TorrentInfo.downloader_id == downloader_id)

    return query.first()


def get_torrents(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        tags: Optional[str] = None,
        category: Optional[str] = None
) -> List[TorrentInfo]:
    """
    获取种子列表，支持分页和过滤

    Args:
        db: 数据库会话
        skip: 跳过记录数
        limit: 返回记录数上限
        status: 按状态过滤
        tags: 按标签过滤
        category: 按分类过滤

    Returns:
        种子信息对象列表
    """
    query = db.query(TorrentInfo)

    if status:
        query = query.filter(TorrentInfo.status == status)
    if tags:
        query = query.filter(TorrentInfo.tags.like(f"%{tags}%"))
    if category:
        query = query.filter(TorrentInfo.category == category)

    return query.offset(skip).limit(limit).all()


def search_torrents_by_name(db: Session, name_query: str, skip: int = 0, limit: int = 100) -> List[TorrentInfo]:
    """
    通过名称搜索种子

    Args:
        db: 数据库会话
        name_query: 名称搜索关键词
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        种子信息对象列表
    """
    return db.query(TorrentInfo).filter(
        TorrentInfo.name.like(f"%{name_query}%")
    ).offset(skip).limit(limit).all()


def update_torrent(db: Session, torrent_id: str, torrent_data: Dict[str, Any]) -> Optional[TorrentInfo]:
    """
    更新种子信息

    Args:
        db: 数据库会话
        torrent_id: 种子ID
        torrent_data: 更新的种子数据

    Returns:
        更新后的种子信息对象或None（如果未找到）
    """
    # 确保使用正确的ID字段名
    db_torrent = db.query(TorrentInfo).filter(TorrentInfo.info_id == torrent_id).first()
    if not db_torrent:
        return None

    try:
        # 更新对象属性
        for key, value in torrent_data.items():
            if hasattr(db_torrent, key):
                setattr(db_torrent, key, value)

        db.commit()
        db.refresh(db_torrent)
        return db_torrent
    except SQLAlchemyError as e:
        db.rollback()
        raise e  # 重新抛出异常，便于调试


def delete_torrent(db: Session, torrent_id: str) -> bool:
    """
    删除种子信息

    Args:
        db: 数据库会话
        torrent_id: 种子ID

    Returns:
        操作是否成功
    """
    db_torrent = get_torrent(db, torrent_id)
    if not db_torrent:
        return False

    db.delete(db_torrent)
    db.commit()
    return True


def get_torrents_count(
        db: Session,
        status: Optional[str] = None,
        category: Optional[str] = None
) -> int:
    """
    获取种子总数

    Args:
        db: 数据库会话
        status: 按状态过滤
        category: 按分类过滤

    Returns:
        符合条件的种子数量
    """
    query = db.query(TorrentInfo)

    if status:
        query = query.filter(TorrentInfo.status == status)
    if category:
        query = query.filter(TorrentInfo.category == category)

    return query.count()


def get_torrents_by_save_path(db: Session, path: str, skip: int = 0, limit: int = 100) -> List[TorrentInfo]:
    """
    通过保存路径获取种子列表

    Args:
        db: 数据库会话
        path: 保存路径（支持部分匹配）
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        种子信息对象列表
    """
    return db.query(TorrentInfo).filter(
        TorrentInfo.save_path.like(f"%{path}%")
    ).offset(skip).limit(limit).all()


# ===========================================================================
# Tracker CRUD
# ===========================================================================

# 创建操作
def create_tracker(db: Session, tracker_data: Dict[str, Any]) -> TrackerInfoModel:
    """
    创建新的 tracker 记录

    Args:
        db: 数据库会话
        tracker_data: 包含 tracker 信息的字典

    Returns:
        新创建的 tracker 记录
    """
    # 如果没有提供 tracker_id，生成一个 UUID
    if "tracker_id" not in tracker_data:
        tracker_data["tracker_id"] = str(uuid.uuid4())

    # 设置默认值
    if "dr" not in tracker_data:
        tracker_data["dr"] = 0

    db_tracker = TrackerInfoModel(**tracker_data)
    db.add(db_tracker)
    db.commit()
    db.refresh(db_tracker)
    return db_tracker


# 读取操作
def get_tracker(db: Session, tracker_id: str) -> Optional[TrackerInfoModel]:
    """
    通过 ID 获取 tracker 记录

    Args:
        db: 数据库会话
        tracker_id: tracker 的 ID

    Returns:
        tracker 记录或 None
    """
    return db.query(TrackerInfoModel).filter(
        and_(
            TrackerInfoModel.tracker_id == tracker_id,
            TrackerInfoModel.dr == 0
        )
    ).first()


def get_trackers_by_torrent(db: Session, torrent_info_id: str) -> List[TrackerInfoModel]:
    """
    获取指定种子的所有 tracker

    Args:
        db: 数据库会话
        torrent_info_id: 种子的 ID

    Returns:
        tracker 记录列表
    """
    return db.query(TrackerInfoModel).filter(
        and_(
            TrackerInfoModel.torrent_info_id == torrent_info_id,
            TrackerInfoModel.dr == 0
        )
    ).all()


def get_trackers(db: Session, skip: int = 0, limit: int = 100) -> List[TrackerInfoModel]:
    """
    获取所有 tracker 记录，支持分页

    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的最大记录数

    Returns:
        tracker 记录列表
    """
    return db.query(TrackerInfoModel).filter(TrackerInfoModel.dr == 0).offset(skip).limit(limit).all()


def get_trackers_by_status(db: Session, status: str) -> List[TrackerInfoModel]:
    """
    获取指定状态的所有 tracker

    Args:
        db: 数据库会话
        status: tracker 状态

    Returns:
        tracker 记录列表
    """
    return db.query(TrackerInfoModel).filter(
        and_(
            TrackerInfoModel.tracker_status == status,
            TrackerInfoModel.dr == 0
        )
    ).all()


# 更新操作
def update_tracker(db: Session, tracker_id: str, tracker_data: Dict[str, Any]) -> Optional[TrackerInfoModel]:
    """
    更新 tracker 记录

    Args:
        db: 数据库会话
        tracker_id: 要更新的 tracker ID
        tracker_data: 包含要更新的字段的字典

    Returns:
        更新后的 tracker 记录或 None
    """
    # 确保 tracker_data 是字典类型
    if not isinstance(tracker_data, dict):
        raise TypeError("tracker_data 必须是字典类型")

    db_tracker = get_tracker(db, tracker_id)
    if not db_tracker:
        return None

    try:
        # 更新属性
        for key, value in tracker_data.items():
            if hasattr(db_tracker, key):
                setattr(db_tracker, key, value)

        db.commit()
        db.refresh(db_tracker)
        return db_tracker
    except Exception as e:
        db.rollback()
        raise e


def update_tracker_status(db: Session, tracker_id: str, status: str, msg: Optional[str] = None) -> Optional[
    TrackerInfoModel]:
    """
    更新 tracker 状态

    Args:
        db: 数据库会话
        tracker_id: tracker ID
        status: 新状态
        msg: 可选的状态消息

    Returns:
        更新后的 tracker 记录或 None
    """
    update_data = {"tracker_status": status}
    if msg is not None:
        update_data["last_scrape_msg"] = msg

    return update_tracker(db, tracker_id, update_data)


# 删除操作
def delete_tracker(db: Session, tracker_id: str) -> bool:
    """
    标记 tracker 为已删除（软删除）

    Args:
        db: 数据库会话
        tracker_id: 要删除的 tracker ID

    Returns:
        是否成功删除
    """
    db_tracker = get_tracker(db, tracker_id)
    if not db_tracker:
        return False

    db_tracker.dr = 1
    db.commit()
    return True


def hard_delete_tracker(db: Session, tracker_id: str) -> bool:
    """
    从数据库中物理删除 tracker 记录

    Args:
        db: 数据库会话
        tracker_id: 要删除的 tracker ID

    Returns:
        是否成功删除
    """
    db_tracker = db.query(TrackerInfoModel).filter(TrackerInfoModel.tracker_id == tracker_id).filter(TrackerInfoModel.dr == 1).first()
    if not db_tracker:
        return False

    db.delete(db_tracker)
    db.commit()
    return True


def delete_trackers_by_torrent(db: Session, torrent_info_id: str) -> int:
    """
    删除与指定种子关联的所有 tracker（软删除）

    Args:
        db: 数据库会话
        torrent_info_id: 种子 ID

    Returns:
        删除的记录数
    """
    trackers = get_trackers_by_torrent(db, torrent_info_id)
    count = 0

    for tracker in trackers:
        tracker.dr = 1
        count += 1

    db.commit()
    return count


# ===========================================================================
# TorrentInfo CRUD (composite-key based)
# ===========================================================================

def create_torrent_info(
        db: Session,
        info_id: str,
        downloader_id: str,
        downloader_name: str,
        torrent_id: str,
        hash: str,
        name: str,
        save_path: str,
        size: float,
        status: str,
        torrent_file: str,
        added_date: int,
        completed_date: Optional[int] = None,
        ratio: str = "0.0",
        ratio_limit: str = "",
        tags: str = "",
        category: str = "",
        super_seeding: str = "0",
        enabled: int = 1,
        dr: int = 0
) -> TorrentInfo:
    """创建新的种子信息记录"""
    db_torrent = TorrentInfo(
        id_=info_id,
        downloader_id=downloader_id,
        downloader_name=downloader_name,
        torrent_id=torrent_id,
        hash=hash,
        name=name,
        save_path=save_path,
        size=size,
        status=status,
        torrent_file=torrent_file,
        added_date=added_date,
        completed_date=completed_date,
        ratio=ratio,
        ratio_limit=ratio_limit,
        tags=tags,
        category=category,
        super_seeding=super_seeding,
        enabled=enabled,
        dr=dr
    )
    db.add(db_torrent)
    db.commit()
    db.refresh(db_torrent)
    return db_torrent


def get_torrent_info(
        db: Session,
        info_id: str,
        downloader_id: str,
) -> Optional[TorrentInfo]:
    """根据复合主键获取种子信息"""
    return db.query(TorrentInfo).filter(
        TorrentInfo.info_id == info_id,
        TorrentInfo.downloader_id == downloader_id,
        TorrentInfo.dr == 0
    ).first()


def update_torrent_info(
        db: Session,
        info_id: str,
        downloader_id: str,
        update_data: Dict[str, Any]
) -> Optional[TorrentInfo]:
    """更新种子信息"""
    db_torrent = get_torrent_info(db, info_id, downloader_id)
    if not db_torrent:
        return None

    # 过滤掉不允许更新的字段
    allowed_fields = {
        "torrent_id", "hash", "name", "save_path", "size", "status",
        "torrent_file", "added_date", "completed_date", "ratio", "ratio_limit",
        "tags", "category", "super_seeding", "enabled", "dr"
    }

    for field, value in update_data.items():
        if field in allowed_fields and hasattr(db_torrent, field):
            setattr(db_torrent, field, value)

    db.commit()
    db.refresh(db_torrent)
    return db_torrent


def delete_torrent_info(
        db: Session,
        info_id: str,
        downloader_id: str
) -> bool:
    """软删除种子信息"""
    db_torrent = get_torrent_info(db, info_id, downloader_id)
    if not db_torrent:
        return False

    db_torrent.dr = 1
    logger.info(f"[delete_torrent_info] 软删除种子: info_id={info_id}, 设置 dr=1")
    db_torrent.update_time = datetime.now()
    db_torrent.update_by = "admin"
    # 删除tracker表数据
    db.execute(text(
        "update tracker_info set update_time=datetime('now'),dr=1 where torrent_info_id =:info_id;")
        , {"info_id": info_id})
    db.commit()
    return True


# ===========================================================================
# 批量操作 & 统计
# ===========================================================================

# 批量操作
def bulk_create_torrent_infos(
        db: Session,
        torrents_data: List[Dict[str, Any]]
) -> List[TorrentInfo]:
    """批量创建种子信息"""
    db_torrents = []
    for torrent_data in torrents_data:
        # 确保必要字段存在
        required_fields = ["info_id", "downloader_id", "downloader_name", "torrent_id", "hash", "name", "save_path",
                           "size", "status", "torrent_file", "added_date"]
        if not all(field in torrent_data for field in required_fields):
            continue

        db_torrent = TorrentInfo(
            id_=torrent_data["info_id"],
            downloader_id=torrent_data["downloader_id"],
            downloader_name=torrent_data["downloader_name"],
            torrent_id=torrent_data["torrent_id"],
            hash=torrent_data["hash"],
            name=torrent_data["name"],
            save_path=torrent_data["save_path"],
            size=torrent_data["size"],
            status=torrent_data["status"],
            torrent_file=torrent_data["torrent_file"],
            added_date=torrent_data["added_date"],
            completed_date=torrent_data.get("completed_date"),
            ratio=torrent_data.get("ratio", "0.0"),
            ratio_limit=torrent_data.get("ratio_limit", ""),
            tags=torrent_data.get("tags", ""),
            category=torrent_data.get("category", ""),
            super_seeding=torrent_data.get("super_seeding", "0"),
            enabled=torrent_data.get("enabled", 1),
            dr=torrent_data.get("dr", 0)
        )
        db_torrents.append(db_torrent)

    db.add_all(db_torrents)
    db.commit()
    for torrent in db_torrents:
        db.refresh(torrent)
    return db_torrents


# 统计方法
def count_torrent_infos(
        db: Session,
        downloader_id: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None
) -> int:
    """统计符合条件的种子数量"""
    query = db.query(TorrentInfo).filter(TorrentInfo.dr == 0)

    if downloader_id:
        query = query.filter(TorrentInfo.downloader_id == downloader_id)

    if status:
        query = query.filter(TorrentInfo.status == status)

    if category:
        query = query.filter(TorrentInfo.category == category)

    return query.count()
