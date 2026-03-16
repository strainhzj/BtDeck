# -*- coding: utf-8 -*-
"""
种子获取器 - 支持分片获取和增量更新

核心特性：
1. 分片获取：每批最多 100-200 个种子，避免单次请求过大
2. 字段过滤：只获取必要字段，大幅减少网络传输
3. 使用 hash：完全基于 torrent_hash，规避 ID 未持久化问题
4. 增量支持：支持全量和增量两种更新模式

@Time    : 2026-03-02
@Author  : btpManager Team
@File    : torrent_fetcher.py
"""

import logging
from typing import List, Dict, Any, Optional
from transmission_rpc import Client as TrClient

logger = logging.getLogger(__name__)


class TorrentFetcher:
    """种子获取器（支持分片）

    设计原则：
    1. 使用 torrent_hash 作为唯一标识（已持久化）
    2. 分批获取，避免单次请求超时
    3. 最小化字段获取，提升性能
    4. 支持 Transmission 和 qBittorrent
    """

    # Transmission 每片大小（根据性能测试）
    TR_BATCH_SIZE = 200  # 每批200个种子

    # qBittorrent 每片大小
    QB_BATCH_SIZE = 100  # 每批100个种子

    # Transmission 最小字段集（仅用于统计）
    TR_MINIMAL_FIELDS = ['id', 'hashString', 'status', 'name']

    # Transmission 统计字段集（用于状态统计）
    TR_STATS_FIELDS = ['hashString', 'status']

    @staticmethod
    def get_transmission_torrents_batch(
        client: TrClient,
        torrent_hashes: Optional[List[str]] = None,
        batch_size: int = TR_BATCH_SIZE,
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """分片获取 Transmission 种子

        Args:
            client: Transmission 客户端
            torrent_hashes: 要查询的种子 hash 列表（None=全量）
            batch_size: 每批大小
            fields: 要获取的字段列表（None=使用最小字段集）

        Returns:
            所有批次的种子列表，格式：[{'hash': str, 'status': str, 'name': str}, ...]

        Examples:
            >>> # 全量获取（分片）
            >>> torrents = TorrentFetcher.get_transmission_torrents_batch(client)
            >>>
            >>> # 指定 hash 获取（增量）
            >>> hashes = ['abc123...', 'def456...']
            >>> torrents = TorrentFetcher.get_transmission_torrents_batch(client, hashes)
            >>>
            >>> # 只获取统计字段
            >>> torrents = TorrentFetcher.get_transmission_torrents_batch(
            ...     client,
            ...     fields=['hashString', 'status']
            ... )
        """
        if fields is None:
            fields = TorrentFetcher.TR_STATS_FIELDS
        include_name = 'name' in fields

        def _safe_attr(obj, attr, default):
            try:
                return getattr(obj, attr)
            except (AttributeError, KeyError):
                return default

        all_torrents = []
        batch_count = 0

        try:
            # 如果没有指定 hash 列表，全量获取（分片）
            if torrent_hashes is None:
                logger.debug("开始全量获取 Transmission 种子...")

                # 第一次调用：获取所有种子的 hash（轻量级）
                all_torrents_lite = client.get_torrents(
                    arguments=['id', 'hashString']
                )

                torrent_hashes = [t.hashString for t in all_torrents_lite]
                logger.debug(f"发现 {len(torrent_hashes)} 个种子，开始分片获取...")

            # 分批获取
            total_batches = (len(torrent_hashes) - 1) // batch_size + 1

            for i in range(0, len(torrent_hashes), batch_size):
                batch = torrent_hashes[i:i + batch_size]
                batch_count += 1

                # 关键：使用 hash 而不是 ID（ID 不持久化）
                torrents = client.get_torrents(
                    ids=batch,  # 支持字符串 hash 列表
                    arguments=fields
                )

                # 转换为统一格式
                batch_data = [
                    {
                        'hash': _safe_attr(t, 'hashString', ''),
                        'status': _safe_attr(t, 'status', 'unknown'),
                        'name': _safe_attr(t, 'name', '') if include_name else ''
                    }
                    for t in torrents
                ]

                all_torrents.extend(batch_data)

                if batch_count % 5 == 0:  # 每5批输出一次日志
                    logger.debug(f"已获取 {batch_count}/{total_batches} 批，共 {len(all_torrents)} 个种子")

            logger.debug(f"Transmission 种子获取完成：{len(all_torrents)} 个，{batch_count} 批")
            return all_torrents

        except Exception as e:
            logger.error(f"获取 Transmission 种子失败（批次 {batch_count}）: {e}")
            # 返回已获取的部分数据
            return all_torrents

    @staticmethod
    def get_transmission_recently_active(
        client: TrClient,
        fields: Optional[List[str]] = None
    ) -> tuple[List[Dict[str, Any]], List[int]]:
        """获取 Transmission 最近活动的种子（增量更新）

        Args:
            client: Transmission 客户端
            fields: 要获取的字段列表

        Returns:
            (活动种子列表, 已删除的ID列表)

        Note:
            返回的 removed_ids 是 ID 而不是 hash，需要额外处理
            建议在增量更新时忽略 removed_ids，依赖 hash 自然过期
        """
        if fields is None:
            fields = TorrentFetcher.TR_STATS_FIELDS
        include_name = 'name' in fields

        def _safe_attr(obj, attr, default):
            try:
                return getattr(obj, attr)
            except (AttributeError, KeyError):
                return default

        try:
            # Transmission 特性：获取最近活动的种子
            # 返回：(active_torrents, removed_ids)
            active, removed_ids = client.get_recently_active_torrents(
                arguments=fields
            )

            # 转换为统一格式
            active_data = [
                {
                    'hash': _safe_attr(t, 'hashString', ''),
                    'status': _safe_attr(t, 'status', 'unknown'),
                    'name': _safe_attr(t, 'name', '') if include_name else ''
                }
                for t in active
            ]

            logger.debug(f"获取到 {len(active_data)} 个活动种子，{len(removed_ids)} 个已删除")
            return active_data, removed_ids

        except Exception as e:
            logger.error(f"获取 Transmission 活动种子失败: {e}")
            return [], []

    @staticmethod
    def get_qbittorrent_torrents_batch(
        client,
        status_filter: Optional[str] = None,
        offset: int = 0,
        limit: int = QB_BATCH_SIZE
    ) -> List[Dict[str, Any]]:
        """分片获取 qBittorrent 种子

        Args:
            client: qBittorrent 客户端
            status_filter: 状态过滤器（downloading/seeding/paused等）
            offset: 起始位置
            limit: 每批大小

        Returns:
            当前批次的种子列表，格式：[{'hash': str, 'status': str, 'name': str}, ...]

        Examples:
            >>> # 获取下载中的种子（第一批）
            >>> torrents = TorrentFetcher.get_qbittorrent_torrents_batch(
            ...     client,
            ...     status_filter='downloading'
            ... )
            >>>
            >>> # 分页获取
            >>> batch1 = TorrentFetcher.get_qbittorrent_torrents_batch(client, offset=0)
            >>> batch2 = TorrentFetcher.get_qbittorrent_torrents_batch(client, offset=100)
        """
        from app.core.torrent_status_mapper import TorrentStatusMapper

        try:
            torrents_info = client.torrents_info(
                status_filter=status_filter,
                offset=offset,
                limit=limit
            )

            # 转换为统一格式（应用状态映射）
            return [
                {
                    'hash': t.get('hash', ''),
                    'status': TorrentStatusMapper.convert_qbittorrent_status(t.get('state', 'unknown')),
                    'name': t.get('name', '')
                }
                for t in torrents_info
            ]

        except Exception as e:
            logger.error(f"获取 qBittorrent 种子失败 (offset={offset}): {e}")
            return []

    @staticmethod
    def get_qbittorrent_all_by_status(
        client,
        batch_size: int = QB_BATCH_SIZE
    ) -> Dict[str, List[Dict[str, Any]]]:
        """按状态分批获取所有 qBittorrent 种子（全量更新）

        Args:
            client: qBittorrent 客户端
            batch_size: 每批大小

        Returns:
            按状态分组的种子字典：{status: [torrents...]}
        """
        all_statuses = [
            'downloading',  # 下载中
            'seeding',      # 做种中
            'paused',       # 已暂停
            'completed',    # 已完成
            'errored'       # 错误
        ]

        result = {}

        for status in all_statuses:
            status_torrents = []
            offset = 0

            while True:
                batch = TorrentFetcher.get_qbittorrent_torrents_batch(
                    client,
                    status_filter=status,
                    offset=offset,
                    limit=batch_size
                )

                if not batch:
                    break

                status_torrents.extend(batch)
                offset += len(batch)

                # 防止无限循环
                if len(batch) < batch_size:
                    break

            result[status] = status_torrents
            logger.debug(f"qBittorrent [{status}]: {len(status_torrents)} 个")

        return result
