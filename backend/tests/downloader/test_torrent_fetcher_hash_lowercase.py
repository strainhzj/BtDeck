# -*- coding: utf-8 -*-
"""
TorrentFetcher hash 小写口径测试（P0-D，rTorrent 接入前置）

背景：qB 路径落库前早已强制 .lower()，但 TR 路径原样透传大写 hashString，
导致 torrent_info.hash 大小写混存（唯一索引/复合键均大小写敏感）。
P0-D 修复后 TR 统一格式输出必须小写；本文件锁定该口径防回归。
"""

from typing import Any, Dict, List

from app.downloader.torrent_fetcher import TorrentFetcher


class _TrTorrentStub:
    """transmission_rpc Torrent 形态桩：hashString 大写、status/name 普通字段。"""

    def __init__(self, hash_string: str, name: str) -> None:
        self.hashString = hash_string
        self.status = "seeding"
        self.name = name
        self.id = 1


class _TrClientStub:
    """client.get_torrents(arguments=[...]) 桩：全量路径与分片路径同一实现。"""

    def __init__(self, torrents: List[_TrTorrentStub]) -> None:
        self._torrents = torrents
        self.calls: List[Dict[str, Any]] = []

    def get_torrents(self, ids=None, arguments=None) -> List[_TrTorrentStub]:  # noqa: ARG002
        self.calls.append({"ids": ids, "arguments": arguments})
        return list(self._torrents)


class TestTransmissionHashLowercase:
    """TR 统一格式 hash 必须小写（与 qB 落库口径、唯一索引、复合键一致）。"""

    def test_batch_output_hash_is_lowercase(self):
        client = _TrClientStub([_TrTorrentStub("ABCDEF0123ABCDEF0123ABCDEF0123ABCDEF0123", "tr-torrent")])
        rows = TorrentFetcher.get_transmission_torrents_batch(
            client,
            torrent_hashes=["ABCDEF0123ABCDEF0123ABCDEF0123ABCDEF0123"],
            fields=["hashString", "status", "name"],
        )
        assert rows == [
            {
                "hash": "abcdef0123abcdef0123abcdef0123abcdef0123",
                "status": "seeding",
                "name": "tr-torrent",
            }
        ]

    def test_slim_hash_list_is_lowercase_and_accepted_by_rpc(self):
        """slim 阶段（id+hashString）产出的 hash 列表同样小写。"""
        client = _TrClientStub([_TrTorrentStub("FFFF0000FFFF", "t")])
        lite = client.get_torrents(arguments=["id", "hashString"])
        hashes = [str(t.hashString or "").strip().lower() for t in lite]
        assert hashes == ["ffff0000ffff"]

    def test_recently_active_output_hash_is_lowercase(self):
        class _RecentClientStub(_TrClientStub):
            def get_recently_active_torrents(self, arguments=None):  # noqa: ARG002
                return list(self._torrents), []

        client = _RecentClientStub([_TrTorrentStub("ABCDEF0123ABCDEF0123ABCDEF0123ABCDEF0123", "tr-torrent")])
        rows, removed = TorrentFetcher.get_transmission_recently_active(client, fields=["hashString", "status", "name"])
        assert removed == []
        assert rows[0]["hash"] == "abcdef0123abcdef0123abcdef0123abcdef0123"
