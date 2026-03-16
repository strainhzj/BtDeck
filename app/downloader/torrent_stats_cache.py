# -*- coding: utf-8 -*-
"""
种子统计缓存管理器

核心特性：
1. 使用 torrent_hash 作为唯一标识（已持久化）
2. 支持增量更新（仅查询变更的种子）
3. 支持全量更新（重新构建缓存）
4. 自动清理过期种子
5. 提供统计功能

@Time    : 2026-03-02
@Author  : btpManager Team
@File    : torrent_stats_cache.py
"""

import time
import logging
from typing import Dict, List, Set, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TorrentCacheEntry:
    """单个种子的缓存条目"""
    status: str  # 种子状态：downloading/seeding/paused等
    last_seen: float  # 最后更新时间戳
    name: str = ""  # 种子名称（可选，用于调试）

    def is_expired(self, ttl: int = 7200) -> bool:
        """检查是否过期

        Args:
            ttl: 生存时间（秒），默认2小时

        Returns:
            是否过期
        """
        return (time.time() - self.last_seen) > ttl


class TorrentStatsCache:
    """种子统计缓存管理器

    设计原则：
    1. 使用 torrent_hash 作为键（已持久化，不依赖 ID）
    2. 支持增量更新（只更新变更的种子）
    3. 定期全量同步（保证数据完整性）
    4. 自动清理过期数据
    """

    def __init__(
        self,
        downloader_id: str,
        full_sync_interval: int = 3600,
        cache_ttl: int = 7200
    ):
        """初始化缓存管理器

        Args:
            downloader_id: 下载器ID
            full_sync_interval: 全量同步间隔（秒），默认1小时
            cache_ttl: 缓存生存时间（秒），默认2小时
        """
        self.downloader_id = downloader_id
        self.cache: Dict[str, TorrentCacheEntry] = {}  # {torrent_hash: TorrentCacheEntry}
        self.last_full_sync: float = 0  # 上次全量同步时间戳
        self.full_sync_interval = full_sync_interval
        self.cache_ttl = cache_ttl

        logger.debug(
            f"初始化种子缓存: downloader_id={downloader_id}, "
            f"全量间隔={full_sync_interval}s, TTL={cache_ttl}s"
        )

    def get_known_hashes(self) -> Set[str]:
        """获取已知的 torrent_hash 集合

        Returns:
            hash 集合
        """
        return set(self.cache.keys())

    def update_cache(self, torrents: List[Dict[str, Any]]):
        """更新缓存

        Args:
            torrents: 种子列表，格式：[{'hash': str, 'status': str, 'name': str}, ...]
        """
        updated_count = 0

        for torrent in torrents:
            hash_str = torrent.get('hash')
            status = torrent.get('status', 'unknown')
            name = torrent.get('name', '')

            if not hash_str:
                continue

            # 更新或添加条目
            self.cache[hash_str] = TorrentCacheEntry(
                status=status,
                last_seen=time.time(),
                name=name
            )
            updated_count += 1

        logger.debug(f"更新缓存: {updated_count} 个种子")

    def cleanup_expired(self, current_hashes: Optional[Set[str]] = None):
        """清理过期或不存在的种子

        Args:
            current_hashes: 当前存在的种子 hash 集合（如果提供，只保留这些）
        """
        if current_hashes is not None:
            # 模式1：只保留指定的 hash（全量同步后清理）
            to_remove = set(self.cache.keys()) - current_hashes
            for h in to_remove:
                del self.cache[h]

            if to_remove:
                logger.debug(f"清理不存在种子: {len(to_remove)} 个")
        else:
            # 模式2：清理过期的种子（增量同步）
            to_remove = [
                h for h, entry in self.cache.items()
                if entry.is_expired(self.cache_ttl)
            ]
            for h in to_remove:
                del self.cache[h]

            if to_remove:
                logger.debug(f"清理过期种子: {len(to_remove)} 个")

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息

        Returns:
            统计字典：{
                'total': 总数,
                'downloading': 下载中,
                'seeding': 做种中,
                'paused': 已暂停,
                'other': 其他
            }
        """
        # 定义精确的状态集合（避免模糊子字符串匹配导致的数据互换）
        # qBittorrent 状态值参考：https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.2+)#get-torrent-list
        DOWNLOADING_STATES = {
            'downloading',  # 下载中
            'stalledDL',    # 下载停滞（无下载速度，有上传速度）
            'queuedDL',     # 排队等待下载
            'checkingDL',   # 下载中检查数据
            'checkingUP'    # 做种中检查数据（某些版本可能使用）
        }

        SEEDING_STATES = {
            'uploading',    # 做种中
            'stalledUP',    # 做种停滞（无上传速度）
            'queuedUP',     # 排队等待做种
            'pausedUP'      # 上传暂停（已完成但在做种队列）
        }

        PAUSED_STATES = {
            'pausedDL',     # 下载暂停
            'stoppedDL'     # 停止下载（某些版本可能使用）
        }
        # 注意：pausedUP 归入"做种"而非"暂停"（因为种子已完成下载）

        downloading = 0
        seeding = 0
        paused = 0
        other = 0

        for entry in self.cache.values():
            status = entry.status.lower()

            # ✅ 使用精确状态匹配，避免模糊子字符串匹配
            if status in DOWNLOADING_STATES:
                downloading += 1
            elif status in SEEDING_STATES:
                seeding += 1
            elif status in PAUSED_STATES:
                paused += 1
            else:
                # 记录未知状态用于调试
                if status and status not in ('unknown', 'error', 'missingfiles'):
                    logger.debug(f"未识别的种子状态: {status} (种子: {entry.name})")
                other += 1

        return {
            'total': len(self.cache),
            'downloading': downloading,
            'seeding': seeding,
            'paused': paused,
            'other': other
        }

    def should_full_sync(self) -> bool:
        """判断是否需要全量同步

        Returns:
            是否需要全量同步
        """
        # 条件1：首次运行
        if len(self.cache) == 0:
            return True

        # 条件2：超过全量同步间隔
        if time.time() - self.last_full_sync > self.full_sync_interval:
            return True

        return False

    def mark_full_sync(self):
        """标记全量同步完成"""
        self.last_full_sync = time.time()
        logger.debug(f"标记全量同步完成: {self.downloader_id}")

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息（用于调试）

        Returns:
            缓存信息字典
        """
        return {
            'downloader_id': self.downloader_id,
            'total_torrents': len(self.cache),
            'last_full_sync': self.last_full_sync,
            'last_full_sync_elapsed': time.time() - self.last_full_sync,
            'should_full_sync': self.should_full_sync(),
            'stats': self.get_stats()
        }

    def clear(self):
        """清空缓存（用于测试或强制重新同步）"""
        self.cache.clear()
        self.last_full_sync = 0
        logger.debug(f"清空缓存: {self.downloader_id}")
