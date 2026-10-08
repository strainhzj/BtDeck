# -*- coding: utf-8 -*-
"""TorrentLookupService 单元测试。

覆盖：
- qB/TR 单 hash 命中与未命中（含 VO 统一口径：progress 0~100、epoch 日期、
  qB completion_on sentinel 归 0、TR datetime 转 epoch、labels join）
- 批量合并单请求、分块上限（qB 100 / TR 200）、部分缺失语义
- hash 归一化（大写入 → 小写出）与非法 hash 快速失败（不发远程请求）
- store 快照三态（不在缓存 / fail_time>0 / client None）与 rTorrent 未适配
- TR Status(str, Enum) 语义（str() 为 "Status.seeding"，必须经 .lower() 取值）
- 远程异常归一（保留已成功块的部分数据语义）
"""

import enum
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.runtime_context import RuntimeContext
from app.services.torrent_lookup_service import _TR_FIELDS, TorrentLookupService

HASH_A = "a" * 40
HASH_B = "b" * 40
HASH_C = "c" * 40

QB_EPOCH_SENTINEL = -8640000000000  # qB 未完成 completion_on 的 libtorrent sentinel
TR_ADDED_DT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
TR_ADDED_EPOCH = int(TR_ADDED_DT.timestamp())


def _make_store(downloaders: List[Any]):
    async def get_snapshot():
        return list(downloaders)

    return SimpleNamespace(get_snapshot=get_snapshot)


def _make_downloader(downloader_id: str = "dl-1", downloader_type: int = 0, client: Any = None, fail_time: int = 0):
    return SimpleNamespace(
        downloader_id=downloader_id,
        nickname=f"n-{downloader_id}",
        downloader_type=downloader_type,
        client=client,
        fail_time=fail_time,
    )


def _qb_torrent(hash_value: str = HASH_A, state: str = "metaDL", **overrides: Any):
    base = dict(
        hash=hash_value,
        name="qb-name",
        size=1024,
        state=state,
        progress=0.5,
        ratio=2.5,
        downloaded=100,
        uploaded=250,
        save_path="/downloads/qb",
        completion_on=QB_EPOCH_SENTINEL,
        added_on=1700000000,
        category="cat",
        tags="tag1, tag2",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _tr_torrent(hash_value: str = HASH_B, status: Any = "Seeding", **overrides: Any):
    base = dict(
        hash_string=hash_value.upper(),
        name="tr-name",
        total_size=2048,
        status=status,
        progress=55.5,
        ratio=1.5,
        downloaded_ever=200,
        uploaded_ever=300,
        download_dir="/downloads/tr",
        done_date=None,
        added_date=TR_ADDED_DT,
        labels=["l1", "l2"],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def call_spy():
    """patch call_downloader_api（service 模块引用点），断言调用参数并按 side_effect 返回。"""
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=AsyncMock()) as mock:
        yield mock


# ---------- 单 hash：qB ----------


async def test_get_by_hash_qb_hit():
    call_spy = AsyncMock(return_value=[_qb_torrent()])
    store = _make_store([_make_downloader(client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        vo, err = await TorrentLookupService(store).get_by_hash("dl-1", HASH_A.upper())
    assert err is None
    assert vo is not None
    # 统一口径断言
    assert vo["hash"] == HASH_A  # 小写归一
    assert vo["name"] == "qb-name"
    assert vo["size"] == 1024
    assert vo["state"] == "downloading"  # metaDL 归一化为 downloading
    assert vo["raw_state"] == "metaDL"
    assert vo["progress"] == 50.0  # qB 0~1 → 0~100
    assert vo["ratio"] == 2.5
    assert vo["downloaded"] == 100
    assert vo["uploaded"] == 250
    assert vo["download_path"] == "/downloads/qb"
    assert vo["completion_date"] == 0  # sentinel 归 0
    assert vo["addition_date"] == 1700000000
    assert vo["category"] == "cat"
    assert vo["tags"] == "tag1, tag2"
    # 调用契约：INTERACTIVE lane + torrent_hashes 参数（服务端索引；kwargs 是关键字形参名）
    call_spy.assert_awaited_once()
    args, kwargs = call_spy.await_args
    assert args[0] == "dl-1"
    assert args[1].value == "interactive"
    assert kwargs["kwargs"] == {"torrent_hashes": [HASH_A]}
    assert kwargs["operation"] == "torrent_lookup_qb"


async def test_get_by_hash_qb_miss():
    store = _make_store([_make_downloader(client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=AsyncMock(return_value=[])):
        vo, err = await TorrentLookupService(store).get_by_hash("dl-1", HASH_A)
    assert vo is None
    assert err is None  # 不存在 ≠ 错误


# ---------- 单 hash：TR ----------


async def test_get_by_hash_tr_hit():
    call_spy = AsyncMock(return_value=[_tr_torrent()])
    store = _make_store([_make_downloader(downloader_type=1, client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        vo, err = await TorrentLookupService(store).get_by_hash("dl-1", HASH_B)
    assert err is None and vo is not None
    assert vo["hash"] == HASH_B
    assert vo["size"] == 2048
    assert vo["state"] == "seeding"
    assert vo["raw_state"] == "seeding"
    assert vo["progress"] == 55.5  # TR SDK 已是 0~100，透传
    assert vo["completion_date"] == 0  # done_date None → 0
    assert vo["addition_date"] == TR_ADDED_EPOCH  # datetime → epoch 秒
    assert vo["category"] == "l1 l2"
    assert vo["tags"] == "l1,l2"
    # 调用契约：ids + 最小字段投影（不含 id/hashString，SDK 自动补）
    call_spy.assert_awaited_once()
    args, kwargs = call_spy.await_args
    assert args[1].value == "interactive"
    call_kwargs = kwargs["kwargs"]
    assert call_kwargs["ids"] == [HASH_B]
    assert call_kwargs["arguments"] == list(_TR_FIELDS)
    assert "id" not in call_kwargs["arguments"]
    assert "hashString" not in call_kwargs["arguments"]


async def test_get_by_hash_tr_done_date():
    done = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    store = _make_store([_make_downloader(downloader_type=1, client=MagicMock())])
    with patch(
        "app.services.torrent_lookup_service.call_downloader_api",
        new=AsyncMock(return_value=[_tr_torrent(done_date=done)]),
    ):
        vo, _ = await TorrentLookupService(store).get_by_hash("dl-1", HASH_B)
    assert vo is not None and vo["completion_date"] == int(done.timestamp())


class _FakeStatus(str, enum.Enum):
    """模拟 transmission-rpc Status(str, Enum)：str() 输出 'Status.seeding' 而 lower() 正常。"""

    SEEDING = "seeding"
    STOPPED = "stopped"


async def test_get_by_hash_tr_status_enum_semantics():
    store = _make_store([_make_downloader(downloader_type=1, client=MagicMock())])
    torrent = _tr_torrent(status=_FakeStatus.STOPPED)
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=AsyncMock(return_value=[torrent])):
        vo, err = await TorrentLookupService(store).get_by_hash("dl-1", HASH_B)
    assert err is None and vo is not None
    # str(Status.STOPPED) == 'Status.STOPPED'，必须经 .lower() 取值而非 str().lower()
    assert vo["raw_state"] == "stopped"
    assert vo["state"] == "paused"


# ---------- 批量 ----------


async def test_get_by_hashes_qb_single_request():
    call_spy = AsyncMock(return_value=[_qb_torrent(HASH_A), _qb_torrent(HASH_B)])
    store = _make_store([_make_downloader(client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        result, err = await TorrentLookupService(store).get_by_hashes("dl-1", [HASH_B, HASH_A, HASH_B])
    assert err is None
    assert set(result.keys()) == {HASH_A, HASH_B}
    call_spy.assert_awaited_once()  # 去重 + 合并单请求
    assert call_spy.await_args.kwargs["kwargs"]["torrent_hashes"] == [HASH_B, HASH_A]  # 保序


async def test_get_by_hashes_qb_chunking():
    hashes = [("a" if i % 2 == 0 else "b") + f"{i:039d}" for i in range(150)]
    call_spy = AsyncMock(side_effect=[[], []])
    store = _make_store([_make_downloader(client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        result, err = await TorrentLookupService(store).get_by_hashes("dl-1", hashes)
    assert err is None and result == {}
    assert call_spy.await_count == 2  # 100 + 50
    first = call_spy.await_args_list[0].kwargs["kwargs"]["torrent_hashes"]
    second = call_spy.await_args_list[1].kwargs["kwargs"]["torrent_hashes"]
    assert len(first) == 100 and len(second) == 50
    assert first[0] == hashes[0] and second[0] == hashes[100]


async def test_get_by_hashes_tr_chunk_boundary():
    hashes = [("c" if i % 2 == 0 else "d") + f"{i:039d}" for i in range(200)]
    call_spy = AsyncMock(side_effect=[[]])
    store = _make_store([_make_downloader(downloader_type=1, client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        await TorrentLookupService(store).get_by_hashes("dl-1", hashes)
    call_spy.assert_awaited_once()  # 200 恰好一块
    assert len(call_spy.await_args.kwargs["kwargs"]["ids"]) == 200


async def test_get_by_hashes_partial_missing():
    """请求 3 个返回 2 个：缺失 hash 不在结果中（不存在 ≠ 错误）。"""
    call_spy = AsyncMock(return_value=[_qb_torrent(HASH_A), _qb_torrent(HASH_B)])
    store = _make_store([_make_downloader(client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        result, err = await TorrentLookupService(store).get_by_hashes("dl-1", [HASH_A, HASH_B, HASH_C])
    assert err is None
    assert set(result.keys()) == {HASH_A, HASH_B}
    assert HASH_C not in result


async def test_get_by_hashes_partial_failure_keeps_successful_chunk():
    """第二块失败：err 非空 + 保留第一块成功数据（部分成功语义）。"""
    hashes = [("a" if i % 2 == 0 else "b") + f"{i:039d}" for i in range(120)]
    call_spy = AsyncMock(side_effect=[[_qb_torrent(hashes[0])], RuntimeError("boom")])
    store = _make_store([_make_downloader(client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        result, err = await TorrentLookupService(store).get_by_hashes("dl-1", hashes)
    assert err is not None and "boom" in err
    assert set(result.keys()) == {hashes[0]}


async def test_get_by_hashes_dirty_entry_skipped():
    """单条转换异常（脏数据）跳过，不炸批量。"""

    class Dirty:
        @property
        def hash(self):  # 类型: ignore[override]
            raise TypeError("dirty")

    call_spy = AsyncMock(return_value=[Dirty(), _qb_torrent(HASH_A)])
    store = _make_store([_make_downloader(client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        result, err = await TorrentLookupService(store).get_by_hashes("dl-1", [HASH_A])
    assert err is None
    assert set(result.keys()) == {HASH_A}


# ---------- 快速失败与校验 ----------


async def test_invalid_hash_fast_fail_without_remote_call(call_spy: AsyncMock):
    store = _make_store([_make_downloader(client=MagicMock())])
    result, err = await TorrentLookupService(store).get_by_hashes("dl-1", ["not-a-hash"])
    assert result == {}
    assert err is not None and "hash" in err
    call_spy.assert_not_awaited()  # 毫秒级快速失败：非法输入不发远程请求


async def test_v2_64_hex_hash_accepted():
    v2 = "0123456789abcdef" * 4
    call_spy = AsyncMock(return_value=[])
    store = _make_store([_make_downloader(client=MagicMock())])
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        result, err = await TorrentLookupService(store).get_by_hashes("dl-1", [v2])
    assert err is None and result == {}
    call_spy.assert_awaited_once()


async def test_empty_hashes_no_call(call_spy: AsyncMock):
    store = _make_store([_make_downloader(client=MagicMock())])
    result, err = await TorrentLookupService(store).get_by_hashes("dl-1", [])
    assert (result, err) == ({}, None)
    call_spy.assert_not_awaited()


# ---------- store 解析三态与类型门控 ----------


@pytest.mark.parametrize(
    "downloader, expect_fragment",
    [
        (None, "下载器不在缓存中"),
        (_make_downloader(fail_time=3), "下载器当前不可用"),
        (_make_downloader(client=None), "没有可用客户端"),
    ],
)
async def test_downloader_unavailable_states(call_spy: AsyncMock, downloader: Optional[Any], expect_fragment: str):
    items = [] if downloader is None else [downloader]
    result, err = await TorrentLookupService(_make_store(items)).get_by_hashes("dl-1", [HASH_A])
    assert result == {}
    assert err is not None and expect_fragment in err
    call_spy.assert_not_awaited()


async def test_store_missing(call_spy: AsyncMock):
    result, err = await TorrentLookupService(None).get_by_hashes("dl-1", [HASH_A])
    assert result == {} and err is not None and "未初始化" in err


async def test_snapshot_error_normalized(call_spy: AsyncMock):
    async def boom():
        raise RuntimeError("store down")

    result, err = await TorrentLookupService(SimpleNamespace(get_snapshot=boom)).get_by_hashes("dl-1", [HASH_A])
    assert result == {} and err is not None and "store down" in err


async def test_rtorrent_unsupported(call_spy: AsyncMock):
    store = _make_store([_make_downloader(downloader_type=2, client=MagicMock())])
    result, err = await TorrentLookupService(store).get_by_hashes("dl-1", [HASH_A])
    assert result == {}
    assert err is not None and "rtorrent" in err
    call_spy.assert_not_awaited()


async def test_downloader_type_none_defaults_qb():
    """normalize(None) 兼容归 0=qB：仍然走 qB 分支。"""
    call_spy = AsyncMock(return_value=[])
    downloader = _make_downloader(client=MagicMock())
    downloader.downloader_type = None
    with patch("app.services.torrent_lookup_service.call_downloader_api", new=call_spy):
        result, err = await TorrentLookupService(_make_store([downloader])).get_by_hashes("dl-1", [HASH_A])
    assert err is None and result == {}
    call_spy.assert_awaited_once()
    assert "torrent_hashes" in call_spy.await_args.kwargs["kwargs"]


# ---------- 注入 ----------


async def test_from_context_injection():
    store = _make_store([])
    svc = TorrentLookupService.from_context(RuntimeContext(store=store))
    assert svc.store is store


# 说明：不在此处验证真实 downloader_api_runtime 线程池路径——全局单例在
# 全量测试中被 test_downloader_api_runtime shutdown 后不重建，跨文件依赖
# 全局态必然脆弱；lane 调度契约已由上述 patch 断言（interactive）覆盖，
# 真实执行路径归 test_downloader_api_runtime 职责。
