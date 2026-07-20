# -*- coding: utf-8 -*-
"""
tracker.replace_tracker() 端点 RPC 异常兜底回归测试

修复目标：消除因 ``qb_replace_tracker`` / ``tr_replace_tracker`` 调用无 try/except
导致的"RPC 异常冒泡到全局 500"风险（prod-hotfix-2026-07-19 同类风险）。

根因：
    replace_tracker 端点（tracker.py:147-287）原 line 251-254 直接调用
    ``qb_replace_tracker`` / ``tr_replace_tracker``，这两个辅助函数（tracker.py:681-734）
    内部无 try/except。当 RPC 调用抛非领域异常时（如 transmission_rpc→requests.post
    内部 json.dumps 撞 ValueError 实例 → TypeError，正是 prod-hotfix 报错路径），
    异常直接冒泡到全局 unhandled_exception_handler，使原本应返回业务结果的请求变成 500。

    对照：add_tracker（tracker.py:119）/ modify_tracker（tracker.py:325）的循环体内
    都有 ``try/except Exception`` 兜底，唯独 replace_tracker 没有。

修复：
    - replace_tracker 端点循环内为 RPC 调用包 try/except Exception
    - 单个 downloader 失败不影响其它 downloader 处理（部分成功语义）
    - 记录 success_count / failed_count，RPC 失败时写失败审计日志（对齐 modify_tracker）
    - return data 新增 success_count/failed_count 字段（affected_count 向后兼容）

本测试直接 ``await replace_tracker(...)``（绕过 FastAPI 路由层与 auth 依赖），
mock AsyncSession 按端点 6 次 db.execute 顺序返回预设数据，
用真实 ``BtDownloaders`` 实例让 ``is_qbittorrent``/``is_transmission`` property 正常工作。
"""

from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.endpoints.tracker import replace_tracker


# ============================================================================
# 辅助函数
# ============================================================================


def _make_downloader(*, downloader_id: str, downloader_type: int):
    """用真实 BtDownloaders 实例，让 is_qbittorrent/is_transmission property 正常工作。

    MagicMock(spec=BtDownloaders) 会把 property 也变成 truthy mock 对象，
    导致 is_qbittorrent/is_transmission 同时为 True，走错分支。必须用真实实例。
    downloader_type: 0=qBittorrent, 1=Transmission
    """
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


def _make_tracker_info(*, tracker_info_id: str = "ti-1", downloader_id: str = "dl-1"):
    """构造 tracker_info 行的 mock。"""
    m = MagicMock()
    m.tracker_info_id = tracker_info_id
    m.tracker_url = "http://old.example.com/announce"
    m.tracker_id = "orig-tracker-id"
    # 端点 line 213-214 会改写这两个字段后 db.add(row)
    return m


def _make_torrent(*, info_id: str = "ti-1", downloader_id: str = "dl-1"):
    """构造 torrent 行的 mock。"""
    m = MagicMock()
    m.info_id = info_id
    m.name = "test-torrent"
    m.downloader_id = downloader_id
    return m


def _result(rows: List[Any], *, scalar_one: bool = False):
    """构造 db.execute 的返回值对象。

    scalar_one=True 时支持 .scalar_one_or_none()，否则只支持 .scalars().all() / .all()。
    """
    r = MagicMock()
    if scalar_one:
        r.scalar_one_or_none.return_value = rows[0] if rows else None
    r.scalars.return_value.all.return_value = rows
    r.all.return_value = rows
    return r


def _build_db(
    *,
    tracker_info_list: List[Any],
    torrent: Any,
    downloaders: List[Any],
    torrent_ids_per_downloader: Optional[List[List[str]]] = None,
):
    """构造一个 AsyncSession mock，按 replace_tracker 端点的 db.execute 调用顺序返回数据。

    端点对 db.execute 的调用顺序（单 downloader 场景）：
      1. select(trackerInfoModel)        → tracker_info_list
      2. select(torrentInfoModel)        → torrent（每个 tracker_info 一次，测试场景只 1 个）
      3. update text(...)                 → 无返回值用
      4. select(distinct(downloader_id))  → downloader_id_list
      5. select(BtDownloaders)            → downloader（每个 downloader 一次）
      6. select(torrent_id)               → torrent_ids（每个 downloader 一次）

    多 downloader 场景下，第 5/6 步会按 downloader 数量重复。
    """
    db = MagicMock()
    n = {"i": 0}

    downloader_id_list = [(dl.downloader_id,) for dl in downloaders]
    if torrent_ids_per_downloader is None:
        torrent_ids_per_downloader = [["hash" + dl.downloader_id] for dl in downloaders]

    results = [
        # 1. tracker_info_list
        _result(tracker_info_list),
        # 2. torrent（每个 tracker_info 一次；测试场景 tracker_info_list 长度 == 1）
    ]
    for _ in tracker_info_list:
        results.append(_result([torrent], scalar_one=True))
    # 3. update text(...)
    results.append(MagicMock())
    # 4. downloader_id_list
    results.append(_result(downloader_id_list))
    # 5/6. 每个 downloader 两次查询（downloader + torrent_ids）
    for dl, tids in zip(downloaders, torrent_ids_per_downloader):
        results.append(_result([dl], scalar_one=True))   # 查 downloader
        results.append(_result([(t,) for t in tids]))     # 查 torrent_ids

    async def _execute(*args, **kwargs):
        i = n["i"]
        n["i"] += 1
        return results[i] if i < len(results) else MagicMock()

    db.execute = _execute
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _make_args(db, *, replace_url="http://old.example.com/announce",
               target_url="http://new.example.com/announce"):
    """构造 replace_tracker 端点的公共参数。"""
    return dict(
        req=MagicMock(),
        background_tasks=MagicMock(),
        _user=None,
        replace_tracker_url=replace_url,
        target_tracker_url=target_url,
        db=db,
    )


# ============================================================================
# 核心回归用例：RPC 异常兜底
# ============================================================================


@pytest.mark.asyncio
async def test_qb_replace_tracker_type_error_does_not_bubble():
    """qBittorrent 分支：qb_replace_tracker 抛 TypeError 时被兜底，不冒泡。

    精确复刻 prod 报错字符串：transmission_rpc→requests.post(json=query) 内部
    json.dumps 撞 ValueError 实例 → TypeError。
    修复前：异常直接冒泡到全局 handler → 500。
    修复后：返回 code=200 + failed_count=1。
    """
    dl = _make_downloader(downloader_id="dl-1", downloader_type=0)  # qBittorrent
    db = _build_db(
        tracker_info_list=[_make_tracker_info()],
        torrent=_make_torrent(),
        downloaders=[dl],
    )

    with patch(
        "app.api.endpoints.tracker.qb_replace_tracker",
        side_effect=TypeError("Object of type ValueError is not JSON serializable"),
    ):
        result = await replace_tracker(**_make_args(db))

    # 关键：不再冒泡，端点正常返回
    assert result.code == "200"
    assert result.data["failed_count"] == 1
    assert result.data["success_count"] == 0
    # affected_count 向后兼容，仍存在
    assert result.data["affected_count"] == 1


@pytest.mark.asyncio
async def test_tr_replace_tracker_failure_caught():
    """Transmission 分支：tr_replace_tracker 抛 ValueError 时被兜底。

    覆盖两个独立 RPC 函数（qb_replace_tracker / tr_replace_tracker），
    确保两侧分支都有兜底。
    注意：Transmission 的 torrent_id 在端点 line 255 会做 int() 转换，
    所以 torrent_ids 必须返回可 int() 的值（整数字符串或整数）。
    """
    dl = _make_downloader(downloader_id="dl-tr", downloader_type=1)  # Transmission
    db = _build_db(
        tracker_info_list=[_make_tracker_info(downloader_id="dl-tr")],
        torrent=_make_torrent(downloader_id="dl-tr"),
        downloaders=[dl],
        torrent_ids_per_downloader=[[12345]],  # Transmission 用整数 torrent_id
    )

    with patch(
        "app.api.endpoints.tracker.tr_replace_tracker",
        side_effect=ValueError("invalid torrent id format"),
    ):
        result = await replace_tracker(**_make_args(db))

    assert result.code == "200"
    assert result.data["failed_count"] == 1
    assert result.data["success_count"] == 0


@pytest.mark.asyncio
async def test_partial_failure_continues_other_downloaders():
    """多 downloader 场景：第一个 RPC 失败、第二个成功，验证部分成功语义。

    确保单个 downloader 失败不影响其它 downloader 处理（与 modify_tracker 循环行为一致）。
    """
    dl1 = _make_downloader(downloader_id="dl-fail", downloader_type=0)
    dl2 = _make_downloader(downloader_id="dl-ok", downloader_type=0)
    db = _build_db(
        tracker_info_list=[_make_tracker_info()],
        torrent=_make_torrent(),
        downloaders=[dl1, dl2],
    )

    call_count = {"n": 0}

    def _qb_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise TypeError("first downloader RPC failed")
        # 第二个 downloader 正常返回

    with patch("app.api.endpoints.tracker.qb_replace_tracker", side_effect=_qb_side_effect):
        result = await replace_tracker(**_make_args(db))

    assert result.code == "200"
    assert result.data["success_count"] == 1
    assert result.data["failed_count"] == 1
    assert call_count["n"] == 2  # 两个 downloader 都被处理了


# ============================================================================
# 边界用例：早期返回路径
# ============================================================================


@pytest.mark.asyncio
async def test_empty_tracker_info_returns_404():
    """tracker_info_list 为空时返回 code=404（line 184-185 早期返回）。

    覆盖循环外的早期返回路径，确保修改未影响"未找到要替换的 tracker"分支。
    """
    db = _build_db(
        tracker_info_list=[],  # 空
        torrent=_make_torrent(),
        downloaders=[],
    )

    result = await replace_tracker(**_make_args(db))

    assert result.code == "404"
    assert result.status == "error"
    assert "未找到" in result.msg


@pytest.mark.asyncio
async def test_downloader_not_exist_increments_failed():
    """downloader 不存在时 failed_count 增加（与 modify_tracker:343-344 对齐）。

    锚定"缺失计失败"的语义决策：原代码只 continue 不计数，
    修复后参照 modify_tracker 把"下载器不存在"计为 failed_count。
    """
    # 构造一个 downloader_id 能查到（line 4）、但 BtDownloaders 查不到（line 5 返回 None）的场景
    db = MagicMock()
    n = {"i": 0}
    results = [
        _result([_make_tracker_info()]),              # 1. tracker_info_list
        _result([_make_torrent()], scalar_one=True),  # 2. torrent
        MagicMock(),                                   # 3. update
        _result([("dl-missing",)]),                    # 4. downloader_id_list
        _result([], scalar_one=True),                  # 5. 查 downloader 返回 None
    ]

    async def _execute(*args, **kwargs):
        i = n["i"]
        n["i"] += 1
        return results[i] if i < len(results) else MagicMock()

    db.execute = _execute
    db.add = MagicMock()
    db.commit = AsyncMock()

    result = await replace_tracker(**_make_args(db))

    assert result.code == "200"
    assert result.data["failed_count"] == 1
    assert result.data["success_count"] == 0


# ============================================================================
# 对照用例：正常路径
# ============================================================================


@pytest.mark.asyncio
async def test_all_succeed_returns_full_success():
    """对照测试：全部成功时 success_count=N, failed_count=0。

    确保兜底逻辑不影响正常路径。
    """
    dl = _make_downloader(downloader_id="dl-ok", downloader_type=0)
    db = _build_db(
        tracker_info_list=[_make_tracker_info()],
        torrent=_make_torrent(),
        downloaders=[dl],
    )

    with patch("app.api.endpoints.tracker.qb_replace_tracker"):
        result = await replace_tracker(**_make_args(db))

    assert result.code == "200"
    assert result.data["success_count"] == 1
    assert result.data["failed_count"] == 0


@pytest.mark.asyncio
async def test_data_structure_backward_compatible():
    """data 字段结构完整：affected_count/success_count/failed_count 三字段齐全。

    锚定向后兼容契约：affected_count 保留（前端虽未读，但为兼容性保留），
    新增 success_count/failed_count。
    """
    dl = _make_downloader(downloader_id="dl-ok", downloader_type=0)
    db = _build_db(
        tracker_info_list=[_make_tracker_info()],
        torrent=_make_torrent(),
        downloaders=[dl],
    )

    with patch("app.api.endpoints.tracker.qb_replace_tracker"):
        result = await replace_tracker(**_make_args(db))

    assert result.code == "200"
    data = result.data
    # 三字段齐全
    assert "affected_count" in data
    assert "success_count" in data
    assert "failed_count" in data
    # 类型正确
    assert isinstance(data["affected_count"], int)
    assert isinstance(data["success_count"], int)
    assert isinstance(data["failed_count"], int)
    # msg 含成功/失败计数
    assert "成功" in result.msg
    assert "失败" in result.msg
