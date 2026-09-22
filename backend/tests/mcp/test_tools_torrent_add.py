# -*- coding: utf-8 -*-
"""MCP W3-③ torrent_add_file 单元回归（feature mcp-service-capabilities-2026-08-28）。

覆盖内容校验链（服务器路径/URL/磁力拒绝、base64 严格解码、10/64MiB 双上限、
bencode 与 info hash 提取）、TorrentAddService 共用边界（服务以 monkeypatch
替身注入——真实下载器成功路径留 W4 等价批）、幂等重放、审计口径与错误码映射。
不依赖 MCP SDK。
"""

import base64
import hashlib
from typing import Any, Dict, List
from unittest.mock import patch

import bencodepy
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.principal import AuthenticatedPrincipal
from app.database import Base
from app.mcp.catalog import ToolCallContext
from app.mcp.contracts import (
    TORRENT_UPLOAD_DEFAULT_MAX_BYTES,
    TORRENT_UPLOAD_HARD_MAX_BYTES,
    spec_by_code,
)
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.runtime import McpRuntime
from app.mcp.tools.idempotency import reset_for_tests
from app.mcp.tools.torrent_add import (
    _decode_torrent_payload,
    _effective_upload_limit,
    _extract_info_digest,
    handle_torrent_add_file,
)
from app.services.torrent_add_service import TorrentAddResult
from app.torrents.models import TorrentInfo

ADD_SPEC = spec_by_code("torrent.add")


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=1, username="admin", is_active=True, must_change_password=False, token="t", payload={}
    )


def _minimal_torrent(extra_pieces: int = 0) -> bytes:
    """最小合法 .torrent（bencode dict + info dict）；extra_pieces 用于撑大体积。"""
    return bencodepy.encode(
        {
            b"announce": b"http://tracker.example.com/announce",
            b"info": {
                b"name": b"mcp-add",
                b"piece length": 16384,
                b"length": 1024,
                b"pieces": b"\x00" * (20 + extra_pieces),
            },
        }
    )


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _args(torrent_b64: str, downloader_id: str = "1", key: str = "k-1") -> Dict[str, Any]:
    return {
        "torrent_file_b64": torrent_b64,
        "downloader_id": downloader_id,
        "confirm": True,
        "idempotency_key": key,
    }


class _FakeAsyncSession:
    async def close(self) -> None:  # pragma: no cover - 占位
        pass


class _StateWithStore:
    store = object()


@pytest.fixture
def runtime():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[TorrentInfo.__table__])
    factory = sessionmaker(bind=engine)
    rt = McpRuntime(
        state=None,
        session_factory=factory,
        async_session_factory=lambda: _FakeAsyncSession(),  # type: ignore[arg-type]
        settings_provider=lambda: None,
    )
    rt.mark_ready()
    rt.state = _StateWithStore()
    yield rt, factory
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_caches():
    reset_for_tests()
    yield
    reset_for_tests()


AUDIT_CALLS: List[Dict[str, Any]] = []


async def _capture_audit(runtime, call_context, principal, detail, result, error_message=None):
    AUDIT_CALLS.append({"detail": detail, "result": result})
    return None


@pytest.fixture(autouse=True)
def _no_audit():
    with patch("app.mcp.tools.common.log_tool_audit", new=_capture_audit):
        yield


@pytest.fixture(autouse=True)
def _clear_audit_calls():
    AUDIT_CALLS.clear()
    yield


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BTDECK_MCP_TORRENT_UPLOAD_MAX_BYTES", raising=False)
    yield


def _success_result(created: bool = True) -> TorrentAddResult:
    return TorrentAddResult(
        status="success",
        code="200",
        msg="种子添加成功",
        info_hash="a" * 40,
        info_id="i-9",
        name="mcp-add",
        downloader_nickname="qbt-main",
        created=created,
    )


# ==============================================================================
# 上传校验链（纯函数）
# ==============================================================================


class TestDecodeTorrentPayload:
    @pytest.mark.parametrize(
        "raw",
        [
            "magnet:?xt=urn:btih:0123456789",
            "MAGNET:?xt=urn:btih:0123456789",
            "http://example.com/1.torrent",
            "https://example.com/1.torrent",
            "file:///etc/passwd",
            "ftp://example.com/1.torrent",
            "C:\\torrents\\1.torrent",
            "c:/torrents/1.torrent",
            "\\\\server\\share\\1.torrent",
            "/config/qbittorrent/1.torrent",
            "config/qbittorrent/1.torrent",
        ],
    )
    def test_server_path_url_magnet_rejected(self, raw: str):
        with pytest.raises(McpToolError) as err:
            _decode_torrent_payload(raw)
        assert err.value.code is McpErrorCode.SERVER_PATH_FORBIDDEN

    def test_bad_base64_non_path_is_invalid_argument(self):
        with pytest.raises(McpToolError) as err:
            _decode_torrent_payload("not-base64!!")
        assert err.value.code is McpErrorCode.INVALID_ARGUMENT

    def test_valid_base64_leading_slash_passes_decode(self):
        """合法 base64 可能以 / 开头（首字节高两位为 11），不得误判为路径。"""
        raw_forced = base64.b64encode(b"\xff" + _minimal_torrent()).decode("ascii")
        assert raw_forced.startswith("/")
        assert _decode_torrent_payload(raw_forced) == b"\xff" + _minimal_torrent()

    def test_empty_payload_rejected(self):
        with pytest.raises(McpToolError) as err:
            _decode_torrent_payload("")
        assert err.value.code is McpErrorCode.UPLOAD_INVALID_CONTENT

    def test_oversize_rejected(self, monkeypatch):
        monkeypatch.setenv("BTDECK_MCP_TORRENT_UPLOAD_MAX_BYTES", "512")
        big = _minimal_torrent(extra_pieces=1024)  # >512B、bencode 合法
        with pytest.raises(McpToolError) as err:
            _decode_torrent_payload(_b64(big))
        assert err.value.code is McpErrorCode.UPLOAD_TOO_LARGE

    def test_valid_minimal_torrent_decodes(self):
        content = _minimal_torrent()
        assert _decode_torrent_payload(_b64(content)) == content


class TestEffectiveUploadLimit:
    def test_default_without_env(self):
        assert _effective_upload_limit() == TORRENT_UPLOAD_DEFAULT_MAX_BYTES

    def test_env_override_applies(self, monkeypatch):
        monkeypatch.setenv("BTDECK_MCP_TORRENT_UPLOAD_MAX_BYTES", "2048")
        assert _effective_upload_limit() == 2048

    @pytest.mark.parametrize("bad", ["abc", "-1", "0"])
    def test_env_invalid_falls_back_default(self, monkeypatch, bad: str):
        monkeypatch.setenv("BTDECK_MCP_TORRENT_UPLOAD_MAX_BYTES", bad)
        assert _effective_upload_limit() == TORRENT_UPLOAD_DEFAULT_MAX_BYTES

    def test_env_never_exceeds_hard_cap(self, monkeypatch):
        monkeypatch.setenv("BTDECK_MCP_TORRENT_UPLOAD_MAX_BYTES", str(TORRENT_UPLOAD_HARD_MAX_BYTES * 4))
        assert _effective_upload_limit() == TORRENT_UPLOAD_HARD_MAX_BYTES


class TestExtractInfoDigest:
    def test_minimal_torrent_digest(self):
        content = _minimal_torrent()
        expected = hashlib.sha1(bencodepy.encode(bencodepy.decode(content)[b"info"])).hexdigest()
        assert _extract_info_digest(content) == expected
        assert len(expected) == 40

    @pytest.mark.parametrize(
        "content",
        [
            b"not a torrent at all",
            b"i42e",  # 合法 bencode 但顶层非字典
            b"d4:infod6:lengthi1eee"[::-1],  # 坏 bencode
        ],
    )
    def test_invalid_content_raises(self, content: bytes):
        with pytest.raises(Exception):
            _extract_info_digest(content)

    def test_dict_without_info_raises(self):
        with pytest.raises(Exception):
            _extract_info_digest(bencodepy.encode({b"announce": b"http://t.example.com/a"}))

    def test_info_not_dict_raises(self):
        with pytest.raises(Exception):
            _extract_info_digest(bencodepy.encode({b"info": b"x", b"announce": b"http://t.example.com/a"}))


# ==============================================================================
# 处理器（service 替身）
# ==============================================================================


class TestHandleTorrentAddFile:
    async def test_success_created_payload(self, runtime):
        rt, factory = runtime
        seen: Dict[str, Any] = {}

        class _FakeService:
            def __init__(self, db, store=None):
                seen["store_is_state_store"] = store is rt.state.store

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                seen["downloader_id"] = params.downloader_id
                seen["content"] = torrent_content
                seen["operator"] = operator
                return _success_result(created=True)

        with patch("app.services.torrent_add_service.TorrentAddService", _FakeService):
            payload = await handle_torrent_add_file(
                ADD_SPEC, _principal(), _args(_b64(_minimal_torrent())), rt, ToolCallContext()
            )

        assert payload == {
            "added": True,
            "duplicate": False,
            "info_id": "i-9",
            "name": "mcp-add",
            "downloader_id": "1",
            "downloader_nickname": "qbt-main",
        }
        assert seen["store_is_state_store"] is True
        assert seen["content"] == _minimal_torrent()
        assert seen["operator"] == "admin"
        assert AUDIT_CALLS[-1]["result"] == "success"
        # 审计里的 info_hash 是处理器实测摘要（领域结果的 a*40 不进审计）
        assert AUDIT_CALLS[-1]["detail"]["info_hash"] == _extract_info_digest(_minimal_torrent())
        assert AUDIT_CALLS[-1]["detail"]["added"] is True

    async def test_duplicate_result(self, runtime):
        rt, _ = runtime

        class _FakeService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                return _success_result(created=False)

        with patch("app.services.torrent_add_service.TorrentAddService", _FakeService):
            payload = await handle_torrent_add_file(
                ADD_SPEC, _principal(), _args(_b64(_minimal_torrent())), rt, ToolCallContext()
            )
        assert payload["added"] is False
        assert payload["duplicate"] is True

    async def test_idempotent_replay_skips_service(self, runtime):
        rt, _ = runtime
        calls: List[int] = []

        class _FakeService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                calls.append(1)
                return _success_result(created=True)

        args = _args(_b64(_minimal_torrent()), key="same-key")
        with patch("app.services.torrent_add_service.TorrentAddService", _FakeService):
            first = await handle_torrent_add_file(ADD_SPEC, _principal(), dict(args), rt, ToolCallContext())
            second = await handle_torrent_add_file(ADD_SPEC, _principal(), dict(args), rt, ToolCallContext())
        assert len(calls) == 1
        assert second == first
        replay_rows = [a for a in AUDIT_CALLS if a["detail"].get("replay") is True]
        assert len(replay_rows) == 1

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("404", McpErrorCode.INVALID_ARGUMENT),
            ("400", McpErrorCode.INVALID_ARGUMENT),
            ("408", McpErrorCode.DOWNSTREAM_FAILURE),
            ("503", McpErrorCode.DOWNSTREAM_FAILURE),
            ("500", McpErrorCode.INTERNAL_ERROR),
            ("999", McpErrorCode.INTERNAL_ERROR),
        ],
    )
    async def test_service_failure_code_mapping(self, runtime, code: str, expected: McpErrorCode):
        rt, _ = runtime

        class _FakeService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                return TorrentAddResult(status="failed", code=code, msg=f"upstream detail with C:\\secret path {code}")

        with patch("app.services.torrent_add_service.TorrentAddService", _FakeService):
            with pytest.raises(McpToolError) as err:
                await handle_torrent_add_file(
                    ADD_SPEC, _principal(), _args(_b64(_minimal_torrent())), rt, ToolCallContext()
                )
        assert err.value.code is expected
        # 固定文案：上游 msg（路径/异常文本）不进错误消息与审计 detail
        assert "upstream detail" not in err.value.message
        assert "secret" not in err.value.message
        failed_rows = [a for a in AUDIT_CALLS if a["result"] == "failed"]
        assert failed_rows and failed_rows[-1]["detail"]["service_code"] == code
        assert all("upstream detail" not in str(a["detail"]) for a in AUDIT_CALLS)

    async def test_service_exception_maps_internal_error(self, runtime):
        rt, _ = runtime

        class _FakeService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                raise RuntimeError("boom with http://10.0.0.1:8080/secret")

        with patch("app.services.torrent_add_service.TorrentAddService", _FakeService):
            with pytest.raises(McpToolError) as err:
                await handle_torrent_add_file(
                    ADD_SPEC, _principal(), _args(_b64(_minimal_torrent())), rt, ToolCallContext()
                )
        assert err.value.code is McpErrorCode.INTERNAL_ERROR
        assert "10.0.0.1" not in err.value.message

    async def test_store_missing_runtime_not_ready(self, runtime):
        rt, _ = runtime
        rt.state = type("NoStore", (), {})()  # 无 store 属性 → RUNTIME_NOT_READY

        class _UnexpectedService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                raise AssertionError("store 缺失不得触达 service")

        with patch("app.services.torrent_add_service.TorrentAddService", _UnexpectedService):
            with pytest.raises(McpToolError) as err:
                await handle_torrent_add_file(
                    ADD_SPEC, _principal(), _args(_b64(_minimal_torrent())), rt, ToolCallContext()
                )
        assert err.value.code is McpErrorCode.RUNTIME_NOT_READY

    async def test_magnet_input_rejected_before_store_and_service(self, runtime):
        rt, _ = runtime
        rt.state = type("NoStore", (), {})()  # 无 store：验证仍应先行拒绝

        class _UnexpectedService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                raise AssertionError("非法输入不得触达 service")

        with patch("app.services.torrent_add_service.TorrentAddService", _UnexpectedService):
            with pytest.raises(McpToolError) as err:
                await handle_torrent_add_file(
                    ADD_SPEC, _principal(), _args("magnet:?xt=urn:btih:abc"), rt, ToolCallContext()
                )
        assert err.value.code is McpErrorCode.SERVER_PATH_FORBIDDEN
        assert AUDIT_CALLS[-1]["result"] == "failed"
        assert AUDIT_CALLS[-1]["detail"]["error_code"] == "SERVER_PATH_FORBIDDEN"
        # 审计 detail 不含输入原文
        assert "magnet" not in str(AUDIT_CALLS[-1]["detail"])

    async def test_garbage_bencode_rejected_invalid_content(self, runtime):
        rt, _ = runtime

        class _UnexpectedService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                raise AssertionError("非法内容不得触达 service")

        with patch("app.services.torrent_add_service.TorrentAddService", _UnexpectedService):
            with pytest.raises(McpToolError) as err:
                await handle_torrent_add_file(
                    ADD_SPEC, _principal(), _args(_b64(b"this is not bencode")), rt, ToolCallContext()
                )
        assert err.value.code is McpErrorCode.UPLOAD_INVALID_CONTENT

    async def test_concurrent_different_keys_isolated(self, runtime):
        """G7 并发面：不同键并发调用互不串扰——各执行一次、负载各归其键。"""
        import asyncio

        rt, _ = runtime
        calls: List[str] = []

        class _FakeService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                calls.append(params.downloader_id)
                return TorrentAddResult(
                    status="success",
                    code="200",
                    msg="",
                    info_hash="a" * 40,
                    info_id=f"i-{params.downloader_id}",
                    name="n",
                    downloader_nickname="qbt",
                    created=True,
                )

        with patch("app.services.torrent_add_service.TorrentAddService", _FakeService):
            results = await asyncio.gather(
                *[
                    handle_torrent_add_file(
                        ADD_SPEC,
                        _principal(),
                        _args(_b64(_minimal_torrent()), downloader_id=str(i), key=f"k-{i}"),
                        rt,
                        ToolCallContext(),
                    )
                    for i in range(4)
                ]
            )
        assert sorted(calls) == ["0", "1", "2", "3"]
        assert sorted(p["info_id"] for p in results) == ["i-0", "i-1", "i-2", "i-3"]
        assert all(p["added"] is True for p in results)

    async def test_concurrent_same_key_first_version_semantics(self, runtime):
        """首版口径锚定：同键并发在途调用无在途去重（两次执行），但负载一致。

        idempotency 共享 LRU 只保证"完成后重放返回首次结果"；在途窗口的重复
        执行是文档化首版限制（完整重放矩阵 W4 复核，见 idempotency.py 模块注释）。
        """
        import asyncio

        rt, _ = runtime
        calls: List[int] = []

        class _FakeService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                await asyncio.sleep(0.01)  # 复现真实服务内部下载器 await 挂起点
                calls.append(1)
                return _success_result(created=True)

        args = _args(_b64(_minimal_torrent()), key="same-key")
        with patch("app.services.torrent_add_service.TorrentAddService", _FakeService):
            first, second = await asyncio.gather(
                handle_torrent_add_file(ADD_SPEC, _principal(), dict(args), rt, ToolCallContext()),
                handle_torrent_add_file(ADD_SPEC, _principal(), dict(args), rt, ToolCallContext()),
            )
        assert len(calls) == 2  # 在途窗口两侧均执行（首版无在途去重）
        assert first == second  # 领域负载一致

    async def test_audit_detail_has_no_file_content(self, runtime):
        rt, _ = runtime
        torrent = _minimal_torrent()

        class _FakeService:
            def __init__(self, db, store=None):
                pass

            async def add_torrent(self, params, torrent_content, audit_context=None, operator="admin"):
                return _success_result(created=True)

        with patch("app.services.torrent_add_service.TorrentAddService", _FakeService):
            await handle_torrent_add_file(ADD_SPEC, _principal(), _args(_b64(torrent)), rt, ToolCallContext())
        encoded = _b64(torrent)
        for row in AUDIT_CALLS:
            detail_text = str(row["detail"])
            assert encoded not in detail_text
            assert "tracker.example.com" not in detail_text  # 种子内 announce 域名不入审计
        # 幂等键只以摘要入审计
        assert all("k-1" not in str(a["detail"]) for a in AUDIT_CALLS)
