# -*- coding: utf-8 -*-
"""
qB 5.0+ Tracker repr 污染修复回归测试（P0/P1/P2）

【背景】
qbittorrent-api 的 TorrentDictionary.trackers 是 property：
- 写入（属性赋值）→ add_trackers 远程写，TrackersList 被 _list2string
  （"\n".join(map(str, ...))）序列化为 Tracker 对象 repr，整段被当作
  tracker URL 写回 qBittorrent；qB 5.0+ 自管 TrackerEntry 模型原样存储回显。
- 读取（属性访问）→ torrents_trackers 远程读（每种子一次）。

【修复点与覆盖目标】
1. P0 写侧：_enrich 内 trackers 缓存改走 _qb_set_attr（dict 条目写入，
   绕过 property setter）→ 不再触发 add_trackers 远程写。
2. P0 读侧：_qb_read_trackers 本地 dict 键优先 → 有本地数据时不再远程读；
   TorrentDictionary 无本地键时回退 property getter（qB < 5.1 兜底）；
   普通字典无键返回 None。
3. P1 采集防御：extract_tracker_rows_from_torrent / sync_add_tracker_async
   拦截非法 scheme 的污染 URL（不入库、不进 current_tracker_urls，
   mark_removed 语义自愈清理库内污染行）。
4. P2 清洗端点 cleanupPollutedTrackers：dry_run 统计 / 执行远端移除 +
   库行 dr=1 / TR 仅统计提示。

设计依据：
- 直接调用模块内部函数（与 test_torrents_async_tracker_budget 同风格）；
- 使用真实 qbittorrent-api TorrentDictionary + MagicMock client 锚定
  property 写/读语义（防止 SDK 行为漂移导致回归）；
- asyncio_mode=auto（pytest.ini）。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.endpoints import tracker as tracker_module
from app.api.endpoints import torrents_async as ta
from app.core.tracker_mapper import is_valid_tracker_url
from app.database import get_async_db
from app.main import app
from app.core.config import settings

CLEANUP_URL = f"{settings.API_V1_STR}/tracker/cleanupPollutedTrackers"

# ---------------------------------------------------------------------------
# 测试数据：与生产实证样本同构的污染 URL（Tracker repr 内嵌真实 URL）
# ---------------------------------------------------------------------------
POLLUTED_URL = (
    "Tracker({'msg': '', 'num_downloaded': -1, 'num_leeches': 116, 'num_peers': 115, "
    "num_seeds': 137, 'status': 2, 'tier': 0, "
    "'url': 'https://tracker.totheglory.im/ab576d87dc55209a18922706012fb256'})"
)
VALID_URL = "https://tracker.example.com/announce"


def _make_torrent_dictionary(trackers_local: list | None = None) -> tuple:
    """构造真实 qbittorrent-api TorrentDictionary + MagicMock client。

    Args:
        trackers_local: 预置到 data dict 的 trackers 键（模拟 qB >= 5.1
            torrents_info(include_trackers=True) 响应 / _enrich 写入的本地缓存）。

    Returns:
        (torrent_dictionary, mock_client)
    """
    from qbittorrentapi.torrents import TorrentDictionary

    client = MagicMock()
    data = {"hash": "abcdef1234567890", "name": "demo"}
    if trackers_local is not None:
        data["trackers"] = trackers_local
    td = TorrentDictionary(data=data, client=client)
    return td, client


# ---------------------------------------------------------------------------
# 1) P0 写侧：_qb_set_attr 写 trackers 不触发远程写
# ---------------------------------------------------------------------------
def test_qb_set_attr_trackers_no_remote_write() -> None:
    """dict 条目写入绕过 property setter：client 零调用，本地可读回。"""
    from qbittorrentapi.torrents import TrackersList

    td, client = _make_torrent_dictionary()
    trackers = TrackersList([{"url": VALID_URL, "status": 2}])

    ta._qb_set_attr(td, "trackers", trackers, downloader_id="dl-1")

    assert client.method_calls == [], f"不应触发远程调用，实际: {client.method_calls}"
    assert td.get("trackers") is trackers
    # 属性协议读取命中 property getter（dict 键被 data descriptor 遮蔽），
    # 但 _qb_read_trackers 会优先走 dict 键（见下）
    assert client.method_calls == []


def test_raw_assignment_triggers_remote_write_root_cause_anchor() -> None:
    """反向锚定（根因行为留档）：裸属性赋值仍会触发 add_trackers 远程写。

    该用例固化 qbittorrent-api 的 property setter 语义，防止 SDK 升级后
    行为漂移而修复方不知情（若本用例失败，说明 setter 语义变化，需复核
    _qb_set_attr/_qb_read_trackers 的绕过策略是否仍然必要/有效）。
    """
    from qbittorrentapi.torrents import TrackersList

    td, client = _make_torrent_dictionary()
    trackers = TrackersList([{"url": VALID_URL, "status": 2}])

    td.trackers = trackers

    assert any("torrents_add_trackers" in str(call) for call in client.method_calls), (
        "qbittorrent-api TorrentDictionary.trackers setter 语义发生变化："
        "属性赋值不再触发 add_trackers，请复核 P0 修复注释与回归策略"
    )
    # 裸赋值不落本地 dict（W3-1 内存缓存对 TorrentDictionary 失效的根源）
    assert "trackers" not in dict(td)


# ---------------------------------------------------------------------------
# 2) P0 读侧：_qb_read_trackers 本地优先
# ---------------------------------------------------------------------------
def test_qb_read_trackers_prefers_local_dict_no_remote() -> None:
    """TorrentDictionary 有本地 trackers 键：读取零远程调用。"""
    local_trackers = [{"url": VALID_URL, "status": 2}]
    td, client = _make_torrent_dictionary(trackers_local=local_trackers)

    data = ta._qb_read_trackers(td)

    assert data is local_trackers
    assert client.method_calls == []


def test_qb_read_trackers_fallback_getter_when_no_local_key() -> None:
    """TorrentDictionary 无本地键：回退 property getter（qB < 5.1 兜底）。"""
    td, client = _make_torrent_dictionary()
    client.torrents_trackers.return_value = []

    data = ta._qb_read_trackers(td)

    assert any("torrents_trackers" in str(call) for call in client.method_calls)
    assert data == []


def test_qb_read_trackers_plain_dict_and_namespace() -> None:
    """普通 dict 无键 → None（不走属性协议）；SimpleNamespace → 属性读取。"""
    plain = {"hash": "abc"}
    assert ta._qb_read_trackers(plain) is None

    ns_trackers = [{"url": VALID_URL}]
    ns = SimpleNamespace(hash="abc", trackers=ns_trackers)
    assert ta._qb_read_trackers(ns) is ns_trackers


# ---------------------------------------------------------------------------
# 3) P1 采集防御：非法 scheme tracker 拦截入库
# ---------------------------------------------------------------------------
def test_is_valid_tracker_url_matrix() -> None:
    """合法 scheme 白名单 / 污染 repr / DHT 伪条目 / 空值。"""
    assert is_valid_tracker_url("http://tracker.example.com/announce")
    assert is_valid_tracker_url("https://tracker.example.com/announce")
    assert is_valid_tracker_url("udp://tracker.example.com:6969/announce")
    assert is_valid_tracker_url("ws://tracker.example.com/announce")
    assert is_valid_tracker_url("wss://tracker.example.com/announce")
    assert is_valid_tracker_url("HTTPS://tracker.example.com/announce")  # scheme 大小写不敏感
    # 污染条目与伪条目
    assert not is_valid_tracker_url(POLLUTED_URL)
    assert not is_valid_tracker_url("** [DHT] **")
    assert not is_valid_tracker_url("** [PeX] **")
    assert not is_valid_tracker_url("")
    assert not is_valid_tracker_url("Tracker({'")  # 截断的 repr 片段同样拦截


def test_extract_tracker_rows_skip_polluted_entries() -> None:
    """污染 URL 不入库、不进 current_tracker_urls；合法条目正常保留。"""
    torrent_info = SimpleNamespace(
        hash="abcdef1234567890",
        trackers=[
            {"url": POLLUTED_URL, "status": 1, "msg": ""},
            {"url": VALID_URL, "status": 2, "msg": ""},
            {"url": "** [DHT] **", "status": 0, "msg": ""},
        ],
    )

    rows, current_urls = ta.extract_tracker_rows_from_torrent(
        torrent_info, torrent_info_id="info-1", downloader_type="qbittorrent", current_time=None
    )

    assert [r["tracker_url"] for r in rows] == [VALID_URL]
    assert current_urls == {VALID_URL}
    assert rows[0]["tracker_host"] == "tracker.example.com"


def test_extract_tracker_rows_reads_torrent_dictionary_locally() -> None:
    """TorrentDictionary（增量/全量路径）读取本地 trackers 键：零远程调用。"""
    local_trackers = [{"url": VALID_URL, "status": 2, "msg": ""}]
    td, client = _make_torrent_dictionary(trackers_local=local_trackers)

    rows, current_urls = ta.extract_tracker_rows_from_torrent(
        td, torrent_info_id="info-1", downloader_type="qbittorrent", current_time=None
    )

    assert client.method_calls == []
    assert [r["tracker_url"] for r in rows] == [VALID_URL]
    assert current_urls == {VALID_URL}


async def test_sync_add_tracker_async_skips_polluted_entries() -> None:
    """sync_add_tracker_async（1006 行链路）同样拦截污染条目：insert 参数仅含合法 url。

    注意：必须用 pytest-asyncio AUTO 直接 async def，禁止 asyncio.run()
    自建事件循环——downloader_api_runtime 等全局 runtime 绑定 loop 后，
    额外 loop 的创建/销毁会污染同进程后续异步测试（RSS qb proxy 实证）。
    """
    torrent_info = SimpleNamespace(
        hash="abcdef1234567890",
        trackers=[
            {"url": POLLUTED_URL, "status": 1, "msg": ""},
            {"url": VALID_URL, "status": 2, "msg": ""},
        ],
    )

    from unittest.mock import AsyncMock

    db = MagicMock()
    db.in_transaction.return_value = True
    db.execute = AsyncMock()

    await ta.sync_add_tracker_async(
        db, downloader_type="qbittorrent", mode="sync", torrent_info=torrent_info, torrent_info_id="info-1"
    )

    # insert 语句参数仅含合法 url，污染 url 被拦截
    insert_stmts = [c.args[0] for c in db.execute.call_args_list if "INSERT" in str(c.args[0]).upper()]
    assert insert_stmts, f"应产生 insert 语句，实际调用: {[str(c.args[0])[:60] for c in db.execute.call_args_list]}"
    params = insert_stmts[0].compile().params
    urls = {str(v) for v in params.values() if isinstance(v, str) and v}
    # 合法 url 存在；污染 url 及任何 repr 残片被拦截
    assert VALID_URL in urls
    assert POLLUTED_URL not in urls
    assert not any(u.startswith("Tracker(") for u in urls), f"污染 url 被拦截，实际: {urls}"


# ---------------------------------------------------------------------------
# 4) P2 清洗端点
# ---------------------------------------------------------------------------
class _FakeDbResult:
    def __init__(self, rows: list, scalars_rows: list | None = None):
        self._rows = rows
        self._scalars_rows = scalars_rows

    def all(self):
        return self._rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalars_rows or [])

    def first(self):
        return self._scalars_rows[0] if self._scalars_rows else None


def _install_cleanup_overrides(monkeypatch, polluted_rows, downloader_rows, remove_results=None):
    """安装清洗端点依赖 override：db / 下载器缓存 / 远程调用 / 审计。"""
    remove_results = remove_results or []
    call_seq = []

    class _FakeAsyncDb:
        def __init__(self):
            self.executed = []
            self.committed = 0

        async def execute(self, stmt, params=None):
            self.executed.append((stmt, params))
            if len(self.executed) == 1:
                return _FakeDbResult(polluted_rows)
            if len(self.executed) == 2:
                return _FakeDbResult([], scalars_rows=downloader_rows)
            return _FakeDbResult([])

        async def commit(self):
            self.committed += 1

    fake_db = _FakeAsyncDb()

    async def _override_db():
        yield fake_db

    async def _fake_vo_map(req):
        return {"dl-qb-1": SimpleNamespace(downloader_id="dl-qb-1", client=MagicMock())}

    async def _fake_call_downloader_api(downloader_id, lane, func, *args, **kwargs):
        call_seq.append((downloader_id, func, kwargs))
        if remove_results:
            outcome = remove_results.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
        return True

    async def _no_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(tracker_module, "_get_downloader_vo_map", _fake_vo_map)
    monkeypatch.setattr(tracker_module, "call_downloader_api", _fake_call_downloader_api)
    monkeypatch.setattr(tracker_module, "_write_tracker_audit_log_async", _no_audit)

    app.dependency_overrides[get_async_db] = _override_db
    app.dependency_overrides[tracker_module.require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    return fake_db, call_seq


def _make_downloader_row(dl_id: str, nickname: str, is_qb: bool, is_tr: bool = False):
    row = SimpleNamespace(
        downloader_id=dl_id,
        nickname=nickname,
        is_qbittorrent=is_qb,
        is_transmission=is_tr,
    )
    return row


def _cleanup_client() -> TestClient:
    """构造不触发 lifespan 的 TestClient（与 test_tracker_by_downloader_api 同模式）。

    禁止 `with TestClient(app)`：with 会触发真实应用 lifespan 启停
    （alembic 迁移/jwt_secret 写入/后台任务循环），污染同进程后续
    测试（RSS qb proxy 实证 13 failed）；不带 with 的 TestClient 不跑
    startup/shutdown 事件，请求处理不受影响。
    """
    return TestClient(app, raise_server_exceptions=False)


def test_cleanup_polluted_trackers_dry_run(monkeypatch) -> None:
    """dry_run：只统计，不调远端 remove、不写库。"""
    polluted = [
        ("tid-1", POLLUTED_URL, "hash-1", "dl-qb-1"),
        ("tid-2", "not-a-url", "hash-1", "dl-qb-1"),
        ("tid-3", VALID_URL, "hash-2", "dl-qb-1"),  # SQL 粗过滤漏网 → python 精滤保留
    ]
    downloader_rows = [_make_downloader_row("dl-qb-1", "qB主机", is_qb=True)]

    fake_db, call_seq = _install_cleanup_overrides(monkeypatch, polluted, downloader_rows)

    try:
        client = _cleanup_client()
        resp = client.post(f"{CLEANUP_URL}?dry_run=true")
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["status"] == "success"
        data = body["data"]
        assert data["dry_run"] is True
        assert data["polluted_rows_total"] == 2  # 合法 URL 被精滤排除
        assert data["by_downloader"][0]["torrents"] == 1
        assert data["by_downloader"][0]["polluted_urls"] == 2
        assert call_seq == [], "dry_run 不应调用远端 remove"
        assert fake_db.committed == 0
    finally:
        app.dependency_overrides.clear()


def test_cleanup_polluted_trackers_executes_removal(monkeypatch) -> None:
    """执行模式：qB 远端 remove_trackers 成功 → 库行 dr=1（execute update）。"""
    polluted = [
        ("tid-1", POLLUTED_URL, "hash-1", "dl-qb-1"),
        ("tid-2", "not-a-url", "hash-1", "dl-qb-1"),
    ]
    downloader_rows = [_make_downloader_row("dl-qb-1", "qB主机", is_qb=True)]

    fake_db, call_seq = _install_cleanup_overrides(monkeypatch, polluted, downloader_rows)

    try:
        client = _cleanup_client()
        resp = client.post(CLEANUP_URL)
        body = resp.json()
        assert resp.status_code == 200, body
        data = body["data"]
        assert data["removed_torrents"] == 1
        assert data["failed_torrents"] == 0
        assert data["db_rows_cleaned"] == 2
        # 远端 remove 调用参数：torrent_hash + 污染 urls 列表
        # （端点以 kwargs={...} 关键字传参，mock 的 **kwargs 捕获为嵌套字典）
        assert len(call_seq) == 1
        _, func, kwargs = call_seq[0]
        assert "torrents_remove_trackers" in str(func)
        inner = kwargs["kwargs"]
        assert inner["torrent_hash"] == "hash-1"
        assert set(inner["urls"]) == {POLLUTED_URL, "not-a-url"}
        # 库行 dr=1 批量 update 已执行
        update_stmts = [s for s, _ in fake_db.executed if "update tracker_info" in str(s)]
        assert len(update_stmts) == 1
        assert fake_db.committed == 1
    finally:
        app.dependency_overrides.clear()


def test_cleanup_polluted_trackers_transmission_stats_only(monkeypatch) -> None:
    """TR 下载器：v1 不动远端，仅统计提示。"""
    polluted = [("tid-tr", POLLUTED_URL, "hash-tr", "dl-tr-1")]
    downloader_rows = [_make_downloader_row("dl-tr-1", "TR主机", is_qb=False, is_tr=True)]

    fake_db, call_seq = _install_cleanup_overrides(monkeypatch, polluted, downloader_rows)

    try:
        client = _cleanup_client()
        resp = client.post(CLEANUP_URL)
        body = resp.json()
        assert resp.status_code == 200, body
        data = body["data"]
        assert data["by_downloader"][0]["downloader_type"] == "transmission"
        assert "Transmission" in data["by_downloader"][0]["note"]
        assert call_seq == []
        assert data["skipped_transmission_rows"] == 1
    finally:
        app.dependency_overrides.clear()


def test_cleanup_polluted_trackers_none_found(monkeypatch) -> None:
    """无污染行：直接返回 0。"""
    _install_cleanup_overrides(monkeypatch, [], [])
    try:
        client = _cleanup_client()
        resp = client.post(CLEANUP_URL)
        body = resp.json()
        assert resp.status_code == 200, body
        assert body["data"]["polluted_rows_total"] == 0
    finally:
        app.dependency_overrides.clear()
