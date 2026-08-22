# -*- coding: utf-8 -*-
"""CachedDownloaderSyncTask 长期离线剔除（offline_since）单元测试。

背景：fail_time 剔除机制是死代码（check_and_remove_invalid 无调用方），
失效下载器永久滞留 store 缓存。本批改动引入 offline_since（首次离线时间戳，
由状态轮询维护）作为剔除判据——last_update 是"轮询时间戳"（离线时也被刷新），
不能表达离线持续时长（评审 C-1 修正）。

测试策略（参考 test_downloader_add_encryption 的 patch 模式）：
- FakeStore 注入 app.state.store，记录 _remove_items 调用
- patch app.database.SessionLocal（_single_sync_execution 函数内 import 点）
- DB 行与缓存 downloader_id 保持一致 → new_downloaders 为空，跳过步骤6/7，
  聚焦步骤5.5 的剔除分支
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.tasks.scheduler.downloader_cache_sync import (
    _OFFLINE_EVICT_SECONDS,
    CachedDownloaderSyncTask,
)

# ============ 辅助构造 ============


class _FakeRow:
    def __init__(self, data):
        self._data = dict(data)

    def _asdict(self):
        return self._data


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeDB:
    """模拟 SessionLocal：execute 返回预设行（bt_downloaders 查询结果）。"""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, stmt):  # noqa: ANN001 - 对齐 SQLAlchemy Session 签名
        return _FakeResult([_FakeRow(r) for r in self._rows])

    def close(self):
        pass


class _FakeStore:
    """模拟 app.state.store：记录 _remove_items 调用（SimpleNamespace 按身份比较）。"""

    def __init__(self, items):
        self._items = list(items)
        self.removed = []
        self._buffer = []
        self._processing = False

    async def get_snapshot(self):
        return list(self._items)

    async def _remove_items(self, items):
        self.removed.extend(items)
        self._items = [i for i in self._items if i not in items]


def _make_cached_dl(dl_id="dl_1", *, is_online=True, offline_since=None, nickname="cached_dl"):
    return SimpleNamespace(
        downloader_id=dl_id,
        nickname=nickname,
        fail_time=0,
        is_online=is_online,
        offline_since=offline_since,
    )


def _make_db_row(dl_id="dl_1", nickname="cached_dl"):
    return {
        "downloader_id": dl_id,
        "host": "127.0.0.1",
        "nickname": nickname,
        "username": "admin",
        "status": 1,
        "enabled": True,
        "is_search": "0",
        "downloader_type": 0,
        "port": 8080,
        "password": "x",
        "is_ssl": "0",
        "torrent_save_path": "",
    }


async def _run_sync(cached_items, db_rows):
    """执行 _single_sync_execution，返回 FakeStore（含 removed 记录）。"""
    store = _FakeStore(cached_items)
    fake_app = SimpleNamespace(state=SimpleNamespace(store=store))
    task = CachedDownloaderSyncTask(app=fake_app)
    with (
        patch("app.database.SessionLocal", return_value=_FakeDB(db_rows)),
        patch(
            "app.downloader.initialization._check_and_add_new_downloader",
            new=AsyncMock(return_value=True),
        ),
    ):
        await task._single_sync_execution()
    return store


# ============ 步骤5.5：长期离线剔除 ============


class TestLongOfflineEviction:
    """offline_since 判据：仅剔除持续离线超阈值的缓存成员。"""

    async def test_long_offline_evicted(self):
        """持续离线超过阈值（300s）→ 从缓存移除。"""
        dl = _make_cached_dl(is_online=False, offline_since=time.time() - (_OFFLINE_EVICT_SECONDS + 100))
        store = await _run_sync([dl], [_make_db_row()])
        assert store.removed == [dl]
        assert store._items == []

    async def test_offline_without_since_not_evicted(self):
        """offline_since 缺失（冷启动未探测/旧对象）→ 不剔除，防误删。"""
        dl = _make_cached_dl(is_online=False, offline_since=None)
        store = await _run_sync([dl], [_make_db_row()])
        assert store.removed == []
        assert store._items == [dl]

    async def test_short_offline_not_evicted(self):
        """短暂离线（端口抖动，<300s）→ 不剔除。"""
        dl = _make_cached_dl(is_online=False, offline_since=time.time() - 60)
        store = await _run_sync([dl], [_make_db_row()])
        assert store.removed == []
        assert store._items == [dl]

    async def test_online_not_evicted(self):
        """在线下载器（含 offline_since 残留）→ 不剔除。"""
        dl = _make_cached_dl(is_online=True, offline_since=time.time() - 9999)
        store = await _run_sync([dl], [_make_db_row()])
        assert store.removed == []
        assert store._items == [dl]

    async def test_mixed_only_stale_offline_evicted(self):
        """混合场景：仅长期离线者被剔除，在线/短暂离线者保留。"""
        stale = _make_cached_dl("dl_stale", is_online=False, offline_since=time.time() - 600, nickname="stale")
        fresh_off = _make_cached_dl("dl_fresh", is_online=False, offline_since=time.time() - 30, nickname="fresh")
        online = _make_cached_dl("dl_ok", is_online=True, nickname="ok")
        store = await _run_sync(
            [stale, fresh_off, online],
            [_make_db_row("dl_stale", "stale"), _make_db_row("dl_fresh", "fresh"), _make_db_row("dl_ok", "ok")],
        )
        assert store.removed == [stale]
        assert set(d.downloader_id for d in store._items) == {"dl_fresh", "dl_ok"}

    async def test_orphan_still_removed_alongside_offline(self):
        """孤立剔除（步骤5，DB 不存在）与离线剔除（步骤5.5）互不干扰。"""
        orphan = _make_cached_dl("dl_orphan", is_online=True, nickname="orphan")  # DB 无此行
        stale = _make_cached_dl("dl_stale", is_online=False, offline_since=time.time() - 400, nickname="stale")
        store = await _run_sync([orphan, stale], [_make_db_row("dl_stale", "stale")])
        assert len(store.removed) == 2
        assert orphan in store.removed and stale in store.removed
        assert store._items == []


# ============ _set_online_status：offline_since 生命周期 ============


class TestSetOnlineStatus:
    """状态轮询维护 offline_since 的语义：首次离线记录、持续离线不覆盖、恢复清空。"""

    def test_first_offline_records_since(self):
        from app.downloader.initialization import _set_online_status

        dl = SimpleNamespace(is_online=True, offline_since=None)
        before = time.time()
        _set_online_status(dl, False)
        assert dl.is_online is False
        assert dl.offline_since is not None and dl.offline_since >= before

    def test_repeated_offline_keeps_first_since(self):
        from app.downloader.initialization import _set_online_status

        dl = SimpleNamespace(is_online=False, offline_since=1000.0)
        _set_online_status(dl, False)
        assert dl.offline_since == 1000.0  # 不覆盖首次时间戳

    def test_recover_online_clears_since(self):
        from app.downloader.initialization import _set_online_status

        dl = SimpleNamespace(is_online=False, offline_since=1000.0)
        _set_online_status(dl, True)
        assert dl.is_online is True
        assert dl.offline_since is None

    def test_object_without_since_attribute(self):
        """旧对象无 offline_since 属性 → 首次离线时补建（getattr 兜底）。"""
        from app.downloader.initialization import _set_online_status

        dl = SimpleNamespace(is_online=True)  # 无 offline_since 字段
        _set_online_status(dl, False)
        assert dl.offline_since is not None


# ============ 集成级：_update_downloader_status 的 offline_since 维护 ============


class TestUpdateDownloaderStatusOfflineSince:
    """状态轮询真实流程中 offline_since 的记录/保持/清空（速度跳过与缓存剔除的信号源）。

    _set_online_status 的纯单测见 TestSetOnlineStatus；此处验证
    _update_downloader_status 的各置位分支（端口不可达/异常/在线恢复）
    确实经 helper 维护 offline_since——信号源断裂会让 A-1 跳过与
    A-2 剔除同时失效。host 用 127.0.0.1 跳过 ping3 分支。
    """

    def _make_dl(self):
        return SimpleNamespace(
            nickname="dl",
            host="127.0.0.1",
            port=8080,
            downloader_type=0,
        )

    def _patch_port(self, monkeypatch, *, online=None, exc=None):
        """patch check_port_connectivity：返回在线/离线或抛异常。"""
        from unittest.mock import AsyncMock

        from app.downloader import initialization as init_mod

        if exc is not None:

            async def _raise(*a, **k):
                raise exc

            monkeypatch.setattr(init_mod, "check_port_connectivity", _raise)
        else:
            monkeypatch.setattr(init_mod, "check_port_connectivity", AsyncMock(return_value=online))

    async def test_port_unreachable_records_offline_since(self, monkeypatch):
        """端口不可达 → is_online=False + offline_since 记录 + last_update 刷新。"""
        import time

        from app.downloader import initialization as init_mod

        self._patch_port(monkeypatch, online=False)
        dl = self._make_dl()
        before = time.time()
        ok = await init_mod._update_downloader_status(dl)

        assert ok is True  # 端口不通也算更新成功（离线是有效状态）
        assert dl.is_online is False
        assert dl.offline_since is not None and dl.offline_since >= before
        assert dl.last_update >= before
        assert dl.upload_speed == 0 and dl.download_speed == 0

    async def test_port_check_exception_records_offline_since(self, monkeypatch):
        """端口检查抛异常 → 同样记录 offline_since（异常路径不丢信号）。"""
        from app.downloader import initialization as init_mod

        self._patch_port(monkeypatch, exc=OSError("network unreachable"))
        dl = self._make_dl()
        ok = await init_mod._update_downloader_status(dl)

        assert ok is True
        assert dl.is_online is False
        assert dl.offline_since is not None

    async def test_consecutive_offline_keeps_first_timestamp(self, monkeypatch):
        """连续两轮离线 → offline_since 保持首次时间戳（不随轮询刷新）。"""
        from app.downloader import initialization as init_mod

        self._patch_port(monkeypatch, online=False)
        dl = self._make_dl()

        await init_mod._update_downloader_status(dl)
        first_since = dl.offline_since
        await init_mod._update_downloader_status(dl)

        assert dl.offline_since == first_since, "offline_since 必须是首次离线时间，不是最近轮询时间"

    async def test_recover_online_clears_offline_since(self, monkeypatch):
        """离线 → 在线恢复 → offline_since 清空且速度字段恢复。"""
        from unittest.mock import AsyncMock

        from app.downloader import initialization as init_mod

        dl = self._make_dl()

        # 第一轮：离线
        self._patch_port(monkeypatch, online=False)
        await init_mod._update_downloader_status(dl)
        assert dl.offline_since is not None

        # 第二轮：恢复在线（端口通 + qB 状态成功）
        self._patch_port(monkeypatch, online=True)
        monkeypatch.setattr(
            init_mod,
            "_get_qbittorrent_status",
            AsyncMock(return_value={"upload_speed": 12.5, "download_speed": 34.7}),
        )
        ok = await init_mod._update_downloader_status(dl)

        assert ok is True
        assert dl.is_online is True
        assert dl.offline_since is None
        assert dl.upload_speed == 12.5
        assert dl.download_speed == 34.7


# ============ 自愈闭环：剔除后下一轮重新加入 ============


class TestEvictionRejoinLoop:
    """A-2 闭环锚点：被剔除者恢复在线后，下一轮同步经 _check_and_add_new_downloader 重新入缓存。"""

    async def test_evicted_downloader_readded_next_round(self, monkeypatch):
        import time

        stale = _make_cached_dl("dl_back", is_online=False, offline_since=time.time() - 600, nickname="back")
        store = _FakeStore([stale])
        fake_app = SimpleNamespace(state=SimpleNamespace(store=store))

        check_add = AsyncMock(return_value=True)

        # 第一轮：长期离线 → 剔除
        with (
            patch("app.database.SessionLocal", return_value=_FakeDB([_make_db_row("dl_back", "back")])),
            patch("app.downloader.initialization._check_and_add_new_downloader", new=check_add),
        ):
            await CachedDownloaderSyncTask(app=fake_app)._single_sync_execution()
        assert store.removed == [stale]
        check_add.assert_not_called()  # 同轮对比基于剔除前快照，不会立即重加

        # 第二轮：缓存已无该成员 → 进入 new_downloaders → 重新校验入缓存
        with (
            patch("app.database.SessionLocal", return_value=_FakeDB([_make_db_row("dl_back", "back")])),
            patch("app.downloader.initialization._check_and_add_new_downloader", new=check_add),
        ):
            await CachedDownloaderSyncTask(app=fake_app)._single_sync_execution()

        check_add.assert_called_once()
        assert check_add.await_args.args[1]["downloader_id"] == "dl_back"


# ============ VO 契约：offline_since 字段默认值 ============


class TestDownloaderCheckVOContract:
    """DownloaderCheckVO 的 offline_since 字段契约（缓存/接口/序列化的稳定默认值）。"""

    def test_offline_since_defaults(self):
        from app.downloader.request import DownloaderCheckVO

        vo = DownloaderCheckVO()
        assert vo.offline_since is None
        # 既有默认值锚点：is_online 默认 False（冷启动未探测语义）
        assert vo.is_online is False
        assert vo.last_update is None

    def test_offline_since_roundtrip(self):
        import time

        from app.downloader.request import DownloaderCheckVO

        vo = DownloaderCheckVO(nickname="x", offline_since=1700000000.5)
        assert vo.offline_since == 1700000000.5
        vo.offline_since = time.time()
        assert vo.offline_since > 1700000000.5
