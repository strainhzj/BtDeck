"""批量添加种子后台任务接口测试。"""

import asyncio
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import FastAPI, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.api.endpoints import torrent_crud
from app.services import torrent_add_helpers as add_helpers
from app.services import torrent_add_helpers as batch_add_helpers
from app.services import torrent_batch_add_service as batch_service
from app.services.torrent_add_helpers import _is_sqlite_locked_error
from app.services.torrent_batch_add_service import (
    StagedTorrentFile,
    TorrentBatchAddOptions,
    _add_one_torrent,
    _create_completion_notification,
)
from app.torrents.models import TorrentInfo


@pytest.mark.asyncio
async def test_batch_add_accepts_more_than_ten_files_and_returns_immediately(tmp_path, monkeypatch):
    """批量接口不再限制数量，并在后台任务提交后立即返回 202。"""

    app = FastAPI()

    class Store:
        async def get_snapshot(self):
            return [SimpleNamespace(downloader_id="dl-1", fail_time=0, client=object())]

    app.state.store = Store()
    request = SimpleNamespace(app=app)
    staged_files = [
        StagedTorrentFile(file_name=f"test-{index}.torrent", file_path=str(tmp_path / f"test-{index}.torrent"))
        for index in range(11)
    ]
    staged_iterator = iter(staged_files)

    async def fake_stage(_upload_file):
        return next(staged_iterator)

    async def fake_process(*_args, **_kwargs):
        return None

    monkeypatch.setattr(torrent_crud, "stage_torrent_file", fake_stage)
    monkeypatch.setattr(torrent_crud, "process_torrent_batch_job", fake_process)

    files = [UploadFile(filename=staged.file_name, file=BytesIO(b"torrent")) for staged in staged_files]
    response = await torrent_crud.create_torrents_batch(
        _user=SimpleNamespace(username="tester"),
        request=request,
        torrent_files=files,
        downloader_id="dl-1",
        save_path="/downloads",
        tags="",
        category="",
        paused=False,
        skip_hash_check=False,
        is_sequential_download=False,
        is_first_last_piece_priority=False,
        upload_limit=False,
        download_limit=False,
        db=MagicMock(),
    )

    assert response.code == "202"
    assert response.data["status"] == "queued"
    assert response.data["total"] == 11

    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_batch_add_completion_notification_contains_failure_details():
    """完成通知包含成功/失败数量和失败文件，供通知中心展示。"""

    options = TorrentBatchAddOptions(
        downloader_id="dl-1",
        save_path="/downloads",
        tags="",
        category="",
        paused=False,
        skip_hash_check=False,
        is_sequential_download=False,
        is_first_last_piece_priority=False,
        upload_limit=None,
        download_limit=None,
        operator="tester",
        audit_info={},
    )
    service = MagicMock()
    service.create_notification = AsyncMock()

    class SessionContext:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *_args):
            return None

    results = [
        {"file_name": "ok.torrent", "success": True, "info_id": "info-1", "error": None},
        {"file_name": "bad.torrent", "success": False, "info_id": None, "error": "解析失败"},
    ]

    with (
        patch("app.services.torrent_batch_add_service.AsyncSessionLocal", return_value=SessionContext()),
        patch("app.services.torrent_batch_add_service.NotificationService", return_value=service),
    ):
        await _create_completion_notification("task-1", options, results)

    service.create_notification.assert_awaited_once()
    notification_kwargs = service.create_notification.await_args.kwargs
    assert notification_kwargs["priority"] == "warning"
    assert notification_kwargs["extra_data"]["task_id"] == "task-1"
    assert notification_kwargs["extra_data"]["success_count"] == 1
    assert notification_kwargs["extra_data"]["failed_list"] == [{"file_name": "bad.torrent", "reason": "解析失败"}]
    assert "bad.torrent：解析失败" in notification_kwargs["content"]


# ==================== SQLite 写锁冲突（BUSY/BUSY_SNAPSHOT）治理回归 ====================


def _sqlite_operational_error(code: Optional[int], message: str) -> OperationalError:
    """构造携带 sqlite_errorcode 的 OperationalError（模拟 Python>=3.11 的 exc.orig）。"""

    orig: Any = Exception(message)
    if code is not None:
        setattr(orig, "sqlite_errorcode", code)
    return OperationalError("INSERT INTO torrent_info ...", (), orig)


def _build_batch_options() -> TorrentBatchAddOptions:
    return TorrentBatchAddOptions(
        downloader_id="dl-1",
        save_path="/downloads",
        tags="",
        category="",
        paused=False,
        skip_hash_check=False,
        is_sequential_download=False,
        is_first_last_piece_priority=False,
        upload_limit=None,
        download_limit=None,
        operator="tester",
        audit_info={},
    )


async def _fake_lookup_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
    """fake 直调（与 runtime 行为一致：异常透传），供 lookup/tracker 模块 patch 用。"""
    return func(*args, **(kwargs or {}))


def _make_tr_vo_stub() -> SimpleNamespace:
    """TR 种子 stub：覆盖 VO 转换所需全字段（transmission-rpc 属性名）。"""
    return SimpleNamespace(
        id=9330,
        hashString="a" * 40,
        name="seed-name",
        download_dir="/downloads",
        total_size=1024.0,
        status="checking",
        progress=0.0,
        ratio=0.0,
        downloaded_ever=0,
        uploaded_ever=0,
        torrent_file="/config/torrents/x.torrent",
        added_date=datetime(2026, 9, 6, 14, 46, 23),
        done_date=None,
        labels=[],
    )


def _build_tr_environment(tmp_path: Any, monkeypatch: pytest.MonkeyPatch, commit_side_effect: Any):
    """搭建 _add_one_torrent 的 TR 下载器最小环境，返回可直接断言的 MagicMock db。

    二期改造（torrent-lookup-service-2026-10-08）：
    - 轮询/落库统一走 helpers.wait_and_upsert_torrent_row（VO 来自 lookup 真实转换），
      桩层从 create_transmission_torrent_record（已删）迁移到 _build_row_from_vo；
    - lookup/tracker 模块的 call_downloader_api fake 直调；轮询间隔置零。
    """

    torrent_file = tmp_path / "seed.torrent"
    torrent_file.write_bytes(b"torrent-bytes")

    async def fake_calculate_info_hash(_path: str) -> str:
        return "a" * 40

    record_stub = SimpleNamespace(info_id="info-1", name="seed-name", hash="a" * 40, size=1024)
    import app.services.torrent_add_helpers as add_helpers

    monkeypatch.setattr(batch_service, "calculate_info_hash", fake_calculate_info_hash)
    monkeypatch.setattr("app.services.torrent_add_helpers._build_row_from_vo", MagicMock(return_value=record_stub))
    monkeypatch.setattr(batch_service, "_write_audit_log_async", AsyncMock(return_value=None))
    monkeypatch.setattr(batch_service, "refresh_trackers_after_add", AsyncMock(return_value=True))
    monkeypatch.setattr(add_helpers, "_LOCKED_RETRY_BASE_DELAY_SECONDS", 0)
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", _fake_lookup_call)
    monkeypatch.setattr("app.services.torrent_add_helpers.call_downloader_api", _fake_lookup_call)
    monkeypatch.setattr("app.services.torrent_add_helpers.ADD_POLL_INTERVAL", 0.0)

    client = MagicMock()
    client.get_torrents = MagicMock(return_value=[_make_tr_vo_stub()])
    client.add_torrent = MagicMock(return_value=None)
    # store 快照中的 downloader 必须带 client（lookup _resolve_client 三态校验）
    downloader = SimpleNamespace(downloader_id="dl-1", downloader_type=1, nickname="tr", fail_time=0, client=client)

    async def fake_snapshot():
        return [downloader]

    store = SimpleNamespace(get_snapshot=fake_snapshot)

    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = None
    if commit_side_effect is not None:
        db.commit.side_effect = commit_side_effect
    return db, store, downloader, client, StagedTorrentFile(file_name="seed.torrent", file_path=str(torrent_file))


@pytest.mark.asyncio
async def test_add_one_torrent_closes_residual_read_transaction_before_network(tmp_path, monkeypatch):
    """根修断言：网络调用前必须先结束上一轮遗留的读事务（BUSY_SNAPSHOT 窗口消除）。"""

    db, store, downloader, client, staged_file = _build_tr_environment(tmp_path, monkeypatch, None)

    order: List[str] = []
    db.rollback.side_effect = lambda: order.append("rollback")
    client.add_torrent.side_effect = lambda *args, **kwargs: order.append("add_torrent")

    result = await _add_one_torrent(db, store, downloader, client, staged_file, _build_batch_options())
    await asyncio.sleep(0)

    assert result["success"] is True
    assert order.index("rollback") < order.index("add_torrent")
    assert db.rollback.call_count == 1


@pytest.mark.asyncio
async def test_add_one_torrent_retries_on_sqlite_locked_and_succeeds(tmp_path, monkeypatch):
    """兜底断言：首次 commit 遇 BUSY_SNAPSHOT 后回滚重建实例重试，第二次成功。"""

    db, store, downloader, client, staged_file = _build_tr_environment(
        tmp_path, monkeypatch, [_sqlite_operational_error(518, "database is locked"), None]
    )

    result = await _add_one_torrent(db, store, downloader, client, staged_file, _build_batch_options())
    await asyncio.sleep(0)

    assert result["success"] is True
    assert result["info_id"] == "info-1"
    assert db.commit.call_count == 2
    # 1 次迭代顶部根修 + 1 次重试前的锁冲突回滚
    assert db.rollback.call_count == 2
    # 每次重试都必须重建 ORM 实例（rollback 会 expunge pending 对象，复用会静默丢失 INSERT）
    from app.services import torrent_add_helpers as add_helpers

    assert add_helpers._build_row_from_vo.call_count == 2


@pytest.mark.asyncio
async def test_add_one_torrent_lock_retry_exhausted_reports_error_code(tmp_path, monkeypatch):
    """兜底断言：重试耗尽后失败，且错误串透传 sqlite_errorcode 供通知中心鉴别。"""

    # side_effect 用异常实例列表逐次抛出（传函数会把返回的异常当普通返回值吞掉）
    always_locked = [_sqlite_operational_error(518, "database is locked") for _ in range(add_helpers._LOCKED_RETRY_MAX)]
    db, store, downloader, client, staged_file = _build_tr_environment(tmp_path, monkeypatch, always_locked)

    result = await _add_one_torrent(db, store, downloader, client, staged_file, _build_batch_options())
    await asyncio.sleep(0)

    assert result["success"] is False
    assert db.commit.call_count == add_helpers._LOCKED_RETRY_MAX
    assert "sqlite_errorcode=518" in result["error"]
    assert "database is locked" in result["error"]


@pytest.mark.asyncio
async def test_add_one_torrent_does_not_retry_non_locked_errors(tmp_path, monkeypatch):
    """非锁冲突的 OperationalError 不重试，直接进入失败路径。"""

    db, store, downloader, client, staged_file = _build_tr_environment(
        tmp_path, monkeypatch, _sqlite_operational_error(None, "no such table: torrent_info")
    )

    result = await _add_one_torrent(db, store, downloader, client, staged_file, _build_batch_options())
    await asyncio.sleep(0)

    assert result["success"] is False
    assert db.commit.call_count == 1
    assert "no such table" in result["error"]
    assert "sqlite_errorcode" not in result["error"]


@pytest.mark.parametrize(
    "code,message,expected",
    [
        (5, "database is locked", True),
        (517, "database is locked", True),
        (518, "database is locked", True),
        (1, "no such table", False),
        (None, "(sqlite3.OperationalError) database is locked", True),
        (None, "(sqlite3.OperationalError) no such table: torrent_info", False),
    ],
)
def test_is_sqlite_locked_error_matrix(code: Optional[int], message: str, expected: bool):
    """锁判定矩阵：优先错误码，缺失时回退消息匹配。"""
    assert _is_sqlite_locked_error(_sqlite_operational_error(code, message)) is expected


def test_is_sqlite_locked_error_ignores_non_operational_errors():
    assert _is_sqlite_locked_error(ValueError("database is locked")) is False


# ==================== 加固层：真实会话 / qB 接线 / 退避契约 / 源码契约 ====================


@pytest.mark.asyncio
async def test_locked_retry_persists_row_with_real_sqlite_session(tmp_path, monkeypatch):
    """真实 SQLite 会话级验证：锁冲突回滚后重建实例，行确实持久化。

    MagicMock 层只能证明调用次数，无法证明 "rollback 会 expunge pending 对象、
    重试若复用旧实例会静默丢失 INSERT"——该性质只有真实 ORM 状态机能暴露。
    用全新会话验证 durable commit（而非 identity map 假象）。
    """

    engine = create_engine(f"sqlite:///{tmp_path / 'real.db'}", connect_args={"check_same_thread": False})
    TorrentInfo.__table__.create(engine)
    real_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = real_session_factory()

    # 首次 commit 抛 BUSY_SNAPSHOT（实例属性遮蔽方法，仅影响本会话对象）
    real_commit = db.commit
    commit_attempts = {"count": 0}

    def flaky_commit() -> None:
        commit_attempts["count"] += 1
        if commit_attempts["count"] == 1:
            raise _sqlite_operational_error(518, "database is locked")
        real_commit()

    db.commit = flaky_commit  # type: ignore[method-assign]

    torrent_file = tmp_path / "seed-real.torrent"
    torrent_file.write_bytes(b"torrent-bytes")
    added = datetime(2026, 9, 6, 14, 46, 23)
    tr_stub = SimpleNamespace(
        id=9330,
        hashString="a" * 40,
        name="seed-real",
        download_dir="/downloads",
        total_size=1024.0,
        status="checking",
        error=None,
        torrent_file="/config/torrents/x.torrent",
        added_date=added,
        done_date=None,
        ratio=0.0,
        seed_ratio_limit=2.0,
        labels=[],
    )
    client = MagicMock()
    client.get_torrents = MagicMock(return_value=[tr_stub])
    client.add_torrent = MagicMock(return_value=None)
    downloader = SimpleNamespace(downloader_id="dl-1", downloader_type=1, nickname="tr", fail_time=0, client=client)

    async def fake_calculate_info_hash(_path: str) -> str:
        return "a" * 40

    # 保留真实工厂（构造真实 TorrentInfo ORM 实例），仅外包一层调用计数
    import app.services.torrent_add_helpers as add_helpers

    real_factory = add_helpers._build_row_from_vo
    factory_calls: List[Any] = []

    def counting_factory(downloader_vo: Any, info_hash: str, vo: Any, operator: str = "admin") -> Any:
        factory_calls.append(vo)
        return real_factory(downloader_vo, info_hash, vo, operator)

    async def fake_snapshot() -> List[Any]:
        return [downloader]

    store = SimpleNamespace(get_snapshot=fake_snapshot)

    monkeypatch.setattr(batch_service, "calculate_info_hash", fake_calculate_info_hash)
    monkeypatch.setattr(add_helpers, "_build_row_from_vo", counting_factory)
    monkeypatch.setattr(batch_service, "_write_audit_log_async", AsyncMock(return_value=None))
    monkeypatch.setattr(batch_service, "refresh_trackers_after_add", AsyncMock(return_value=True))
    monkeypatch.setattr(add_helpers, "_LOCKED_RETRY_BASE_DELAY_SECONDS", 0)
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", _fake_lookup_call)
    monkeypatch.setattr("app.services.torrent_add_helpers.call_downloader_api", _fake_lookup_call)
    monkeypatch.setattr(add_helpers, "ADD_POLL_INTERVAL", 0.0)

    staged_file = StagedTorrentFile(file_name="seed-real.torrent", file_path=str(torrent_file))
    result = await _add_one_torrent(db, store, downloader, client, staged_file, _build_batch_options())
    await asyncio.sleep(0)

    assert result["success"] is True
    assert len(factory_calls) == 2  # 首次构造 + 锁冲突回滚后的重建
    assert commit_attempts["count"] == 2

    # 全新会话验证持久化：重试若复用被 expunge 的旧实例，这里将是 0 行（变异 M-B 的判据）
    with real_session_factory() as verify_session:
        rows = verify_session.query(TorrentInfo).filter(TorrentInfo.hash == "a" * 40).all()
        assert len(rows) == 1
        assert rows[0].downloader_name == "tr"
        assert rows[0].info_id == result["info_id"]
    engine.dispose()


@pytest.mark.asyncio
async def test_qb_branch_shares_locked_retry_path(tmp_path, monkeypatch):
    """qB 分支接线：锁冲突同样经共享重试路径（工厂重建 + 二次 commit）。"""

    torrent_file = tmp_path / "seed-qb.torrent"
    torrent_file.write_bytes(b"torrent-bytes")

    async def fake_calculate_info_hash(_path: str) -> str:
        return "b" * 40

    import app.services.torrent_add_helpers as add_helpers

    record_stub = SimpleNamespace(info_id="info-qb", name="seed-qb", hash="b" * 40, size=2048)
    qb_factory = MagicMock(return_value=record_stub)
    monkeypatch.setattr(batch_service, "calculate_info_hash", fake_calculate_info_hash)
    monkeypatch.setattr(add_helpers, "_build_row_from_vo", qb_factory)
    monkeypatch.setattr(batch_service, "_write_audit_log_async", AsyncMock(return_value=None))
    monkeypatch.setattr(batch_service, "refresh_trackers_after_add", AsyncMock(return_value=True))
    monkeypatch.setattr(add_helpers, "_LOCKED_RETRY_BASE_DELAY_SECONDS", 0)
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", _fake_lookup_call)
    monkeypatch.setattr("app.services.torrent_add_helpers.call_downloader_api", _fake_lookup_call)
    monkeypatch.setattr(add_helpers, "ADD_POLL_INTERVAL", 0.0)

    client = MagicMock()
    # qB VO 全字段 stub（torrents/info 字段名）
    client.torrents_info = MagicMock(
        return_value=[
            SimpleNamespace(
                hash="b" * 40,
                name="seed-qb",
                size=2048,
                state="downloading",
                progress=0.25,
                ratio=0.0,
                downloaded=0,
                uploaded=0,
                save_path="/downloads",
                completion_on=0,
                added_on=1700000000,
                category="",
                tags="",
            )
        ]
    )
    downloader = SimpleNamespace(downloader_id="dl-1", downloader_type=0, nickname="qb", fail_time=0, client=client)

    async def fake_snapshot() -> List[Any]:
        return [downloader]

    store = SimpleNamespace(get_snapshot=fake_snapshot)

    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = None
    db.commit.side_effect = [_sqlite_operational_error(5, "database is locked"), None]

    staged_file = StagedTorrentFile(file_name="seed-qb.torrent", file_path=str(torrent_file))
    result = await _add_one_torrent(db, store, downloader, client, staged_file, _build_batch_options())
    await asyncio.sleep(0)

    assert result["success"] is True
    assert result["info_id"] == "info-qb"
    assert db.commit.call_count == 2
    assert qb_factory.call_count == 2
    client.torrents_add.assert_called_once()


@pytest.mark.asyncio
async def test_locked_retry_backoff_is_linear(tmp_path, monkeypatch):
    """退避契约：线性递增（base×1、base×2、…），总等待远小于 busy_timeout 兜底。"""

    db, store, downloader, client, staged_file = _build_tr_environment(
        tmp_path,
        monkeypatch,
        [
            _sqlite_operational_error(518, "database is locked"),
            _sqlite_operational_error(518, "database is locked"),
            None,
        ],
    )
    # _build_tr_environment 把退避基数置 0 了——恢复真实值以断言乘数序列
    base = 0.2
    monkeypatch.setattr(add_helpers, "_LOCKED_RETRY_BASE_DELAY_SECONDS", base)
    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(batch_service.asyncio, "sleep", sleep_mock)

    result = await _add_one_torrent(db, store, downloader, client, staged_file, _build_batch_options())

    assert result["success"] is True
    assert sleep_mock.await_args_list == [call(base * 1), call(base * 2)]


def test_batch_add_lock_governance_source_contract():
    """源码契约：钉住锁治理的结构点，防未来重构"改一处忘一切"。

    二期更新（torrent-lookup-service-2026-10-08）：TR/qB 双分支的落库已收敛到
    helpers.wait_and_upsert_torrent_row 单调用点（原双分支各一处），重试函数本体
    仍在 batch_service，契约跨两个文件锚定。
    """

    source = Path(batch_service.__file__).read_text(encoding="utf-8")
    helpers_source = Path(batch_add_helpers.__file__).read_text(encoding="utf-8")

    # ① 根修 rollback 必须先于首个网络调用（calculate_info_hash）
    assert "db.rollback()\n        info_hash = await calculate_info_hash" in source
    # ② 重试落库路径：锁四件套已内联 helpers（helpers 属 MCP 共享闭包，不得
    # 反向依赖含 fastapi 的批量模块），双分支收敛为 wait_and_upsert 单调用点
    assert helpers_source.count("async def _insert_torrent_record_with_retry(") == 1
    assert helpers_source.count("wait_and_upsert_torrent_row(") >= 1
    assert "_insert_torrent_record_with_retry(" in helpers_source
    # ③ 重试循环每轮重建实例（rollback 会 expunge pending 对象）+ 失败即回滚
    assert "db_torrent = record_factory()\n        db.add(db_torrent)" in helpers_source
    assert (
        "db.rollback()\n            if not _is_sqlite_locked_error(exc) or attempt == _LOCKED_RETRY_MAX:"
        in helpers_source
    )
    # ④ 锁码集合与错误码透传（复发鉴别的观测口）
    assert "_SQLITE_BUSY_ERROR_CODES = (5, 517, 518)" in helpers_source
    assert "sqlite_errorcode=%s" in helpers_source
