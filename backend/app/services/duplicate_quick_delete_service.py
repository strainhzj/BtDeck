"""
快捷删除重复种子服务

跨下载器重复种子分类逻辑（预览与执行端点共享）：

- 在所选下载器集合内，同一 hash 出现在 ≥2 个不同下载器视为一个"重复组"。
- 组内属"保留下载器"的副本 → kept（保留）。
- 组内属"非保留下载器"的副本 → to_delete（删除候选）。
- kept 为空（该 hash 仅存在于待删下载器之间）→ skipped 组，仅提示不删除，保护最后一份数据。

本服务只读取 DB 静态字段（hash/name/size/status/downloader），不拉取实时元数据，保证轻量。
"""

from typing import Any, Dict, List, Tuple

import logging

from sqlalchemy.orm import Session

from app.torrents.models import TorrentInfo
from app.services.deletion_task_manager import build_active_deletion_exclusion

logger = logging.getLogger(__name__)


def _normalized_hash(value: Any) -> str:
    """标准化 hash：去空白并转小写（对齐 duplicate_torrents.py._normalized_hash）。"""
    return str(value or "").strip().lower()


def _item(torrent: TorrentInfo) -> Dict[str, Any]:
    """将单个种子记录转为预览项（仅静态字段）。"""
    return {
        "info_id": str(torrent.info_id),
        "downloader_id": str(torrent.downloader_id),
        "downloader_name": torrent.downloader_name or "",
        "name": torrent.name or "",
        "size": torrent.size,
        "status": torrent.status or "",
        "hash": torrent.hash or "",
    }


def classify_duplicates(
    db: Session,
    downloader_ids: List[str],
    keep_downloader_ids: List[str],
    *,
    exclude_active: bool = True,
) -> List[Dict[str, Any]]:
    """跨下载器重复种子全量分类。

    Args:
        db: 数据库会话（同步）。
        downloader_ids: 待检测下载器集合（已去重、长度≥2）。
        keep_downloader_ids: 保留下载器集合（已去重、长度≥1，且为 downloader_ids 子集）。

    Returns:
        重复组列表（未分页），每组结构：
        {hash, name, size, kept: [item...], to_delete: [item...], skipped: bool}
    """
    keep_set = set(keep_downloader_ids)

    query = db.query(TorrentInfo).filter(
        TorrentInfo.dr == 0,
        TorrentInfo.hash.isnot(None),
        TorrentInfo.hash != "",
        TorrentInfo.downloader_id.in_(downloader_ids),
    )
    if exclude_active:
        active_deletion_exclusion = build_active_deletion_exclusion(TorrentInfo.info_id)
        if active_deletion_exclusion is not None:
            query = query.filter(active_deletion_exclusion)
    rows = query.all()

    # 按标准化 hash 分组
    grouped: Dict[str, List[TorrentInfo]] = {}
    for torrent in rows:
        key = _normalized_hash(torrent.hash)
        if not key:
            continue
        grouped.setdefault(key, []).append(torrent)

    groups: List[Dict[str, Any]] = []
    for raw_hash, torrents in grouped.items():
        # 仅统计 hash 出现的不同下载器数，≥2 才算跨下载器重复
        downloader_set = {str(t.downloader_id) for t in torrents}
        if len(downloader_set) < 2:
            continue

        kept = [_item(t) for t in torrents if str(t.downloader_id) in keep_set]
        to_delete = [_item(t) for t in torrents if str(t.downloader_id) not in keep_set]
        skipped = len(kept) == 0

        # 名称/大小取组内非空最大值（intrinsic 回填，对齐 duplicate_torrents.py 思想）
        name = next((t.name for t in torrents if t.name and str(t.name).strip()), "")
        size = max((t.size for t in torrents if t.size), default=None)

        # 排序：待删优先展示，其余按下载器名
        kept.sort(key=lambda it: (it["downloader_name"] or "").lower())
        to_delete.sort(key=lambda it: (it["downloader_name"] or "").lower())

        groups.append(
            {
                "hash": raw_hash,
                "name": name or "",
                "size": size,
                "kept": kept,
                "to_delete": to_delete,
                "skipped": skipped,
            }
        )

    # 稳定排序，保证分页一致性
    groups.sort(key=lambda g: ((g["name"] or "").lower(), g["hash"]))
    return groups


def summarize(groups: List[Dict[str, Any]]) -> Dict[str, int]:
    """全量汇总（不受分页影响）。"""
    return {
        "total_groups": len(groups),
        "total_delete": sum(len(g["to_delete"]) for g in groups if not g["skipped"]),
        "skipped_groups": sum(1 for g in groups if g["skipped"]),
    }


def paginate_groups(groups: List[Dict[str, Any]], page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
    """对重复组列表分页。返回 (当前页列表, 总组数)。"""
    total = len(groups)
    start = (page - 1) * page_size
    return groups[start : start + page_size], total


def collect_delete_candidates(groups: List[Dict[str, Any]]) -> List[str]:
    """收集全部待删除种子的 info_id（仅非 skipped 组）。"""
    candidates: List[str] = []
    for group in groups:
        if group["skipped"]:
            continue
        candidates.extend(item["info_id"] for item in group["to_delete"])
    return candidates
