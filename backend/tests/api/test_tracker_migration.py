# -*- coding: utf-8 -*-
"""
tracker CRUD 端点迁移测试（sync-database-blocking-remediation W2-3，P0-04）

覆盖三个迁移端点 add_tracker / modify_tracker / replace_tracker 的四条路径：
1. 成功：客户端来自 app.state.store（断言 store 内 client 的方法被真实调用），
   全部下载器调用经 call_downloader_api（INTERACTIVE lane）封装。
2. 下载器超时：call_downloader_api 抛 asyncio.TimeoutError → 按既有业务语义计失败。
3. 离线：store 快照无该下载器 / fail_time>0 / 无 client → 计失败且不发起任何调用。
4. 权限失败：客户端方法抛业务异常（QbAPIError / TransmissionError）→ 计失败。

漏 await 回归：test_add_tr_path_change_torrent_really_called 断言 TR 路径
change_torrent 被真实调用——修复前 tr_add_torrents_tracker 未 await，coroutine
从不执行，change_torrent 永远不会被调用（功能静默失效）。

测试装配：直接 await 端点函数（绕过 FastAPI 路由层与 auth 依赖），mock AsyncSession
按端点 db.execute 调用顺序返回预设数据；fake store / fake client 参照
tests/services/conftest.py 的 make_downloader_vo / fake_qb_client 样板。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qbittorrentapi import APIError as QbAPIError
from transmission_rpc import TransmissionError

from app.api.endpoints.tracker import add_tracker, modify_tracker, replace_tracker

_TRACKER_URL = "http://tracker.example.com/announce"
_REPLACE_URL = "http://old.example.com/announce"
_TARGET_URL = "http://new.example.com/announce"


# ============================================================================
# fake 构造（参照 tests/services/conftest.py 样板）
# ============================================================================


def make_downloader_vo(downloader_id="dl-1", client=None, fail_time=0, downloader_type=0):
    """构造伪下载器 VO（app.state.store.get_snapshot() 返回的元素）。"""
    vo = SimpleNamespace()
    vo.downloader_id = downloader_id
    vo.client = client
    vo.fail_time = fail_time
    vo.downloader_type = downloader_type
    vo.nickname = f"test-{downloader_id}"
    return vo


def _make_req(downloader_vos):
    """伪 Request：带 app.state.store（get_snapshot 返回 VO 列表）。"""
    store = SimpleNamespace()
    store.get_snapshot = AsyncMock(return_value=list(downloader_vos))
    app = SimpleNamespace()
    app.state = SimpleNamespace(store=store)
    req = MagicMock()
    req.app = app
    return req


def _make_downloader(*, downloader_id: str, downloader_type: int):
    """真实 BtDownloaders 实例，让 is_qbittorrent/is_transmission property 正常工作。"""
    from app.downloader.models import BtDownloaders

    return BtDownloaders(
        downloader_id=downloader_id,
        nickname=f"test-{downloader_id}",
        host="127.0.0.1",
        username="admin",
        password="adminadmin",
        port=8080,
        is_ssl=False,
        status=True,
        enabled=True,
        is_search=False,
        downloader_type=downloader_type,
        dr=0,
    )


def _make_qb_torrent(trackers=None):
    """伪 qB torrent 字典（torrents_info 返回的元素，含 .trackers/.add_trackers/.remove_trackers）。"""
    t = SimpleNamespace()
    t.hash = "hash1"
    t.trackers = trackers if trackers is not None else [{"url": _TRACKER_URL, "status": 2, "msg": "ok"}]
    t.add_trackers = MagicMock()
    t.remove_trackers = MagicMock()
    return t


def _make_qb_client(torrents=None):
    """伪 qBittorrent 客户端（torrents_info 返回 [torrent]；auth.log_out 是 spy）。"""
    client = MagicMock()
    client.torrents_info.return_value = torrents if torrents is not None else [_make_qb_torrent()]
    client.auth = MagicMock()
    client.auth.log_out = MagicMock()
    return client


def _make_tr_torrent(tracker_stats=None):
    """伪 Transmission Torrent 对象（get_torrent 返回值）。"""
    stats = []
    for announce in tracker_stats or [_TRACKER_URL]:
        st = SimpleNamespace()
        st.site_name = "example"
        st.fields = {"announce": announce}
        st.last_announce_succeeded = True
        st.last_announce_result = "ok"
        st.last_scrape_succeeded = True
        st.last_scrape_result = "ok"
        stats.append(st)
    t = SimpleNamespace()
    t.id = 12345
    t.tracker_stats = stats
    return t


def _make_tr_client(torrent=None):
    """伪 Transmission 客户端（get_torrent 返回对象；change_torrent 是 spy）。"""
    client = MagicMock()
    client.get_torrent.return_value = torrent if torrent is not None else _make_tr_torrent()
    client.change_torrent = MagicMock()
    return client


def _result(*, scalar=None, rows=None, first=None):
    """构造 db.execute 返回值对象（支持 scalar_one_or_none / scalars().all() / all() / first()）。"""
    r = MagicMock()
    if scalar is not None:
        r.scalar_one_or_none.return_value = scalar
    if rows is not None:
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = rows
    if first is not None:
        r.first.return_value = first
    return r


def _make_db(executes):
    """构造 AsyncSession mock：按端点 db.execute 调用顺序返回预设数据。"""
    db = MagicMock()
    n = {"i": 0}

    async def _execute(*args, **kwargs):
        i = n["i"]
        n["i"] += 1
        return executes[i] if i < len(executes) else MagicMock()

    db.execute = _execute
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _passthrough(downloader_id, lane, func, args=(), kwargs=None, **extra):
    """call_downloader_api 透传：真实调用 func（fake client 方法），供成功路径断言。"""
    return func(*args, **(kwargs or {}))


def _patch_passthrough():
    """把端点模块内的 call_downloader_api 替换为透传 AsyncMock。"""
    return patch("app.api.endpoints.tracker.call_downloader_api", new=AsyncMock(side_effect=_passthrough))


def _patch_timeout():
    """把端点模块内的 call_downloader_api 替换为抛超时的 AsyncMock。"""
    return patch(
        "app.api.endpoints.tracker.call_downloader_api",
        new=AsyncMock(side_effect=asyncio.TimeoutError("downloader call timeout")),
    )


# ============================================================================
# add_tracker：成功路径（客户端来自 store + 漏 await 回归）
# ============================================================================


class TestAddTrackerSuccess:
    """成功路径：store 内的 client 被真实调用，db.commit 正确 await。"""

    def _args(self, req, db):
        return dict(
            req=req,
            background_tasks=MagicMock(),
            _user=None,
            torrent_info_ids="info-1",
            trackers=_TRACKER_URL,
            db=db,
        )

    @pytest.mark.asyncio
    async def test_add_qb_success_uses_store_client(self):
        """qB 路径：store 客户端 .torrents_info/.add_trackers 被真实调用。"""
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-1", torrent_id="hash1")
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        qb_client = _make_qb_client()
        db = _make_db(
            [
                _result(scalar=torrent),  # 1. 查种子
                _result(rows=[dl]),  # 2. 查下载器
            ]
        )
        req = _make_req([make_downloader_vo("dl-1", client=qb_client, downloader_type=0)])

        with _patch_passthrough():
            result = await add_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 1
        assert result.data["failed_count"] == 0
        # 客户端来自 store：断言 store 内 client 的方法被调用（修复前从不执行）
        qb_client.torrents_info.assert_called_once_with(torrent_hashes="hash1")
        qb_client.torrents_info.return_value[0].add_trackers.assert_called_once_with([_TRACKER_URL])
        # db.commit 正确 await（AsyncSession commit 是协程）
        db.commit.assert_awaited_once()
        # 禁止 logout（共享连接严禁登出）
        qb_client.auth.log_out.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_tr_path_change_torrent_really_called(self):
        """漏 await 回归：TR 路径 change_torrent 被真实调用。

        修复前 tr_add_torrents_tracker 未 await → coroutine 从不执行 → change_torrent
        永远不会被调用（功能静默失效）；修复后必须被调用。
        """
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-tr", torrent_id=12345)
        dl = _make_downloader(downloader_id="dl-tr", downloader_type=1)
        tr_client = _make_tr_client()
        db = _make_db(
            [
                _result(scalar=torrent),  # 1. 查种子
                _result(rows=[dl]),  # 2. 查下载器
                _result(rows=[]),  # 3. 查现有 tracker
                _result(first=("info-1",)),  # 4. 查 info_id
            ]
        )
        req = _make_req([make_downloader_vo("dl-tr", client=tr_client, downloader_type=1)])

        with _patch_passthrough():
            result = await add_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 1
        # 核心断言：TR 下载器方法真实执行（漏 await 修复前此处必然失败）
        tr_client.change_torrent.assert_called_once_with(12345, tracker_list=[[_TRACKER_URL]])
        tr_client.get_torrent.assert_called_once_with(12345)
        db.commit.assert_awaited_once()


# ============================================================================
# add_tracker：超时 / 离线 / 权限失败
# ============================================================================


class TestAddTrackerFailure:
    """失败路径：超时、离线、客户端异常均按既有业务语义计失败，HTTP 契约不变。"""

    def _args(self, req, db):
        return dict(
            req=req,
            background_tasks=MagicMock(),
            _user=None,
            torrent_info_ids="info-1",
            trackers=_TRACKER_URL,
            db=db,
        )

    @pytest.mark.asyncio
    async def test_add_timeout_counts_failure(self):
        """下载器超时：call_downloader_api 抛 TimeoutError → failed_count=1。"""
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-1", torrent_id="hash1")
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        db = _make_db(
            [
                _result(scalar=torrent),
                _result(rows=[dl]),
            ]
        )
        req = _make_req([make_downloader_vo("dl-1", client=_make_qb_client(), downloader_type=0)])

        with _patch_timeout():
            result = await add_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1

    @pytest.mark.asyncio
    async def test_add_offline_store_missing_counts_failure(self):
        """离线：store 快照无该下载器 → failed_count=1，且不发起任何下载器调用。"""
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-1", torrent_id="hash1")
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        db = _make_db(
            [
                _result(scalar=torrent),
                _result(rows=[dl]),
            ]
        )
        # store 快照为空（下载器不在缓存）
        req = _make_req([])

        with patch(
            "app.api.endpoints.tracker.call_downloader_api",
            new=AsyncMock(side_effect=_passthrough),
        ) as mocked_call:
            result = await add_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1
        mocked_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_offline_fail_time_counts_failure(self):
        """离线：store 中下载器 fail_time>0（失效）→ failed_count=1。"""
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-1", torrent_id="hash1")
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        db = _make_db(
            [
                _result(scalar=torrent),
                _result(rows=[dl]),
            ]
        )
        req = _make_req([make_downloader_vo("dl-1", client=_make_qb_client(), fail_time=3, downloader_type=0)])

        result = await add_tracker(**self._args(req, db))

        assert result.data["failed_count"] == 1
        assert result.data["success_count"] == 0

    @pytest.mark.asyncio
    async def test_add_offline_client_missing_counts_failure(self):
        """离线：store 中下载器无 client 连接 → failed_count=1。"""
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-1", torrent_id="hash1")
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        db = _make_db(
            [
                _result(scalar=torrent),
                _result(rows=[dl]),
            ]
        )
        req = _make_req([make_downloader_vo("dl-1", client=None, downloader_type=0)])

        result = await add_tracker(**self._args(req, db))

        assert result.data["failed_count"] == 1
        assert result.data["success_count"] == 0

    @pytest.mark.asyncio
    async def test_add_permission_error_counts_failure(self):
        """权限失败：客户端方法抛业务异常（QbAPIError）→ failed_count=1。"""
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-1", torrent_id="hash1")
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        qb_client = _make_qb_client()
        qb_client.torrents_info.side_effect = QbAPIError("Forbidden: permission denied")
        db = _make_db(
            [
                _result(scalar=torrent),
                _result(rows=[dl]),
            ]
        )
        req = _make_req([make_downloader_vo("dl-1", client=qb_client, downloader_type=0)])

        with _patch_passthrough():
            result = await add_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1


# ============================================================================
# modify_tracker：成功 / 超时 / 离线 / 权限失败
# ============================================================================


class TestModifyTracker:
    """modify_tracker 迁移：漏 await 修复（qb_change/tr_change 真实执行）+ 失败路径。"""

    def _args(self, req, db):
        return dict(
            req=req,
            background_tasks=MagicMock(),
            _user=None,
            torrent_info_ids="info-1",
            trackers=_TRACKER_URL,
            db=db,
        )

    def _qb_db(self):
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-1", torrent_id="hash1")
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        old_tracker = MagicMock(tracker_url=_TRACKER_URL)
        db = _make_db(
            [
                _result(rows=[old_tracker]),  # 1. 查旧 tracker
                _result(scalar=torrent),  # 2. 查种子
                _result(rows=[dl]),  # 3. 查下载器
                MagicMock(),  # 4. 逻辑删除旧 tracker（text update）
                _result(first=("info-1",)),  # 5. 查 info_id
            ]
        )
        return db, torrent

    @pytest.mark.asyncio
    async def test_modify_qb_success_removes_then_adds(self):
        """qB 路径：remove_trackers/add_trackers 被真实调用（漏 await 修复回归）。"""
        db, _ = self._qb_db()
        qb_client = _make_qb_client()
        req = _make_req([make_downloader_vo("dl-1", client=qb_client, downloader_type=0)])

        with _patch_passthrough():
            result = await modify_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 1
        assert result.data["failed_count"] == 0
        qb_client.torrents_info.assert_called_once_with(torrent_hashes="hash1")
        torrent_obj = qb_client.torrents_info.return_value[0]
        torrent_obj.remove_trackers.assert_called_once_with(_TRACKER_URL)
        torrent_obj.add_trackers.assert_called_once_with([_TRACKER_URL])
        db.commit.assert_awaited_once()
        qb_client.auth.log_out.assert_not_called()

    @pytest.mark.asyncio
    async def test_modify_tr_success_change_torrent_called(self):
        """TR 路径：change_torrent/get_torrent 被真实调用（漏 await 修复回归）。"""
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-tr", torrent_id=12345)
        dl = _make_downloader(downloader_id="dl-tr", downloader_type=1)
        old_tracker = MagicMock(tracker_url=_TRACKER_URL)
        db = _make_db(
            [
                _result(rows=[old_tracker]),
                _result(scalar=torrent),
                _result(rows=[dl]),
                MagicMock(),  # 逻辑删除
                _result(first=("info-1",)),
            ]
        )
        tr_client = _make_tr_client()
        req = _make_req([make_downloader_vo("dl-tr", client=tr_client, downloader_type=1)])

        with _patch_passthrough():
            result = await modify_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 1
        tr_client.change_torrent.assert_called_once_with(12345, tracker_list=[[_TRACKER_URL]])
        tr_client.get_torrent.assert_called_once_with(12345)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_modify_timeout_counts_failure(self):
        """下载器超时 → failed_count=1。"""
        db, _ = self._qb_db()
        req = _make_req([make_downloader_vo("dl-1", client=_make_qb_client(), downloader_type=0)])

        with _patch_timeout():
            result = await modify_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1

    @pytest.mark.asyncio
    async def test_modify_offline_counts_failure(self):
        """离线：store 无该下载器 → failed_count=1，不发起调用。"""
        db, _ = self._qb_db()
        req = _make_req([])

        with patch(
            "app.api.endpoints.tracker.call_downloader_api",
            new=AsyncMock(side_effect=_passthrough),
        ) as mocked_call:
            result = await modify_tracker(**self._args(req, db))

        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1
        mocked_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_modify_permission_error_counts_failure(self):
        """权限失败：客户端抛 TransmissionError → failed_count=1。"""
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id="dl-tr", torrent_id=12345)
        dl = _make_downloader(downloader_id="dl-tr", downloader_type=1)
        old_tracker = MagicMock(tracker_url=_TRACKER_URL)
        db = _make_db(
            [
                _result(rows=[old_tracker]),
                _result(scalar=torrent),
                _result(rows=[dl]),
                MagicMock(),
                _result(first=("info-1",)),
            ]
        )
        tr_client = _make_tr_client()
        tr_client.change_torrent.side_effect = TransmissionError("401 Unauthorized")
        req = _make_req([make_downloader_vo("dl-tr", client=tr_client, downloader_type=1)])

        with _patch_passthrough():
            result = await modify_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1


# ============================================================================
# replace_tracker：成功 / 超时 / 离线 / 权限失败
# ============================================================================


class TestReplaceTracker:
    """replace_tracker 迁移：RPC 兜底语义保持 + store 客户端 + 失败路径。"""

    def _args(self, req, db):
        return dict(
            req=req,
            background_tasks=MagicMock(),
            _user=None,
            replace_tracker_url=_REPLACE_URL,
            target_tracker_url=_TARGET_URL,
            db=db,
        )

    def _base_db(self, downloader, torrent_ids):
        """replace_tracker 端点的 db.execute 序列（单下载器）。"""
        tracker_info = MagicMock(tracker_url=_REPLACE_URL)
        torrent = SimpleNamespace(info_id="info-1", name="t1", downloader_id=downloader.downloader_id)
        return _make_db(
            [
                _result(rows=[tracker_info]),  # 1. 查 tracker_info
                _result(scalar=torrent),  # 2. 查种子
                MagicMock(),  # 3. 作废旧数据（text update）
                _result(rows=[(downloader.downloader_id,)]),  # 4. 查 downloader_id 列表
                _result(scalar=downloader),  # 5. 查下载器
                _result(rows=[(t,) for t in torrent_ids]),  # 6. 查 torrent_id 列表
            ]
        )

    @pytest.mark.asyncio
    async def test_replace_qb_success_uses_store_client(self):
        """qB 路径：remove_trackers/add_trackers 经 store 客户端真实执行。"""
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        db = self._base_db(dl, ["hash1"])
        qb_client = _make_qb_client()
        req = _make_req([make_downloader_vo("dl-1", client=qb_client, downloader_type=0)])

        with _patch_passthrough():
            result = await replace_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 1
        assert result.data["failed_count"] == 0
        qb_client.torrents_info.assert_called_once_with(torrent_hashes="hash1")
        torrent_obj = qb_client.torrents_info.return_value[0]
        torrent_obj.remove_trackers.assert_called_once_with(_REPLACE_URL)
        torrent_obj.add_trackers.assert_called_once_with(_TARGET_URL)
        qb_client.auth.log_out.assert_not_called()

    @pytest.mark.asyncio
    async def test_replace_tr_success_uses_store_client(self):
        """TR 路径：get_torrent/change_torrent 经 store 客户端真实执行。"""
        dl = _make_downloader(downloader_id="dl-tr", downloader_type=1)
        db = self._base_db(dl, [12345])
        tr_client = _make_tr_client(torrent=_make_tr_torrent([_REPLACE_URL]))
        req = _make_req([make_downloader_vo("dl-tr", client=tr_client, downloader_type=1)])

        with _patch_passthrough():
            result = await replace_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 1
        assert result.data["failed_count"] == 0
        tr_client.get_torrent.assert_called_once_with(12345)
        # 旧 URL 被替换为独立 tier 的新 URL
        tr_client.change_torrent.assert_called_once_with(12345, tracker_list=[[_TARGET_URL]])

    @pytest.mark.asyncio
    async def test_replace_timeout_counts_failure(self):
        """下载器超时 → 单个下载器计失败，不影响端点返回。"""
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        db = self._base_db(dl, ["hash1"])
        req = _make_req([make_downloader_vo("dl-1", client=_make_qb_client(), downloader_type=0)])

        with _patch_timeout():
            result = await replace_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1

    @pytest.mark.asyncio
    async def test_replace_offline_counts_failure(self):
        """离线：store 无该下载器 → failed_count=1，不发起调用。"""
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        db = self._base_db(dl, ["hash1"])
        req = _make_req([])

        with patch(
            "app.api.endpoints.tracker.call_downloader_api",
            new=AsyncMock(side_effect=_passthrough),
        ) as mocked_call:
            result = await replace_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1
        mocked_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_replace_permission_error_counts_failure(self):
        """权限失败：客户端抛 QbAPIError → failed_count=1（RPC 兜底语义保持）。"""
        dl = _make_downloader(downloader_id="dl-1", downloader_type=0)
        db = self._base_db(dl, ["hash1"])
        qb_client = _make_qb_client()
        qb_client.torrents_info.side_effect = QbAPIError("Forbidden: permission denied")
        req = _make_req([make_downloader_vo("dl-1", client=qb_client, downloader_type=0)])

        with _patch_passthrough():
            result = await replace_tracker(**self._args(req, db))

        assert result.code == "200"
        assert result.data["success_count"] == 0
        assert result.data["failed_count"] == 1
