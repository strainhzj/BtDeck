# -*- coding: utf-8 -*-
"""
downloader.add() 端点 except exception 笔误回归测试

修复目标：消除因 ``except exception as e:``（downloader.py 原 line 117）
导致的"业务异常变 500 + rollback 永不执行"风险。

根因（与 prod-hotfix-2026-07-19 同源）：
    downloader.py 原顶部 ``from logging import exception``（line 4）把
    ``logging.exception`` 函数对象导入模块命名空间。原 line 117
    ``except exception as e:`` 中的 ``exception`` 指向这个函数对象，
    不是 ``BaseException`` 子类。Python 进入 except 子句时会抛::

        TypeError: catching classes that do not inherit from BaseException
        is not allowed

    这导致 db.add/db.commit 失败时：
      1. except 子句自身抛 TypeError，冒泡到 unhandled_exception_handler
         → 原本应返回 code=400 的请求变成 500
      2. db.rollback()（原 line 118）在 TypeError 抛出前永远执行不到
         → 事务无法回滚

修复：
    - 删除 ``from logging import exception``（downloader.py line 4）
    - ``except exception as e:`` → ``except Exception as e:``（line 117）

对照证据：同文件 update（line 270）、delete（line 291）端点均为
``except Exception as e:`` 的正确写法，add 端点是孤立笔误。

本测试直接 ``await add(...)``（绕过 FastAPI 路由层与 auth 依赖），
与 ``test_torrent_crud_add_fallback.py`` 风格一致。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.endpoints.downloader import add
from app.downloader.request import RequestDownloader


def _make_request() -> RequestDownloader:
    """构造合法的 RequestDownloader 请求体（path_mapping 留空，端点会跳过）。"""
    return RequestDownloader(
        host="127.0.0.1",
        nickname="test-dl",
        username="admin",
        password="adminadmin",
        is_search=False,
        downloader_type=0,  # 0=qBittorrent
        enabled=True,
        port=8080,
        is_ssl=False,
    )


def _patch_cache_sync():
    """patch _check_and_add_new_downloader，避免真实 RPC 调用。

    add() 端点在 db.commit 成功后会同步下载器缓存（真实 RPC），测试场景需绕过。
    """
    return patch(
        "app.downloader.initialization._check_and_add_new_downloader",
        new_callable=AsyncMock,
    )


@pytest.mark.asyncio
async def test_db_commit_failure_returns_400_not_500():
    """db.commit() 抛 RuntimeError 时返回 code=400，而非冒泡 500。

    修复前：except exception 抛 TypeError → 冒泡到全局 handler → 500
    修复后：except Exception 捕获 → 返回 code=400
    """
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock(side_effect=RuntimeError("database is locked"))
    db.rollback = MagicMock()

    with _patch_cache_sync():
        result = await add(downloader_request=_make_request(), _user=None, db=db)

    # 关键断言：code=400（字符串，CommonResponse.code 是 str），不是 500
    assert result.code == "400"
    assert result.status == "error"
    assert result.msg == "用户名或密码错误"


@pytest.mark.asyncio
async def test_db_commit_failure_calls_rollback():
    """db.commit() 失败时 db.rollback() 被调用。

    修复前：TypeError 在进入 except 体之前就抛出，rollback 永不执行。
    修复后：rollback 正常执行，事务回滚。
    """
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock(side_effect=RuntimeError("database is locked"))
    db.rollback = MagicMock()

    with _patch_cache_sync():
        await add(downloader_request=_make_request(), _user=None, db=db)

    assert db.rollback.called, "db.rollback 应被调用（修复前永不执行）"


@pytest.mark.asyncio
async def test_db_add_failure_returns_400():
    """db.add() 抛异常时同样返回 code=400（覆盖 try 块前段）。"""
    db = MagicMock()
    db.add = MagicMock(side_effect=OSError("connection lost"))
    db.commit = MagicMock()
    db.rollback = MagicMock()

    with _patch_cache_sync():
        result = await add(downloader_request=_make_request(), _user=None, db=db)

    assert result.code == "400"
    assert result.status == "error"
    # commit 不应被调用（add 已失败）
    assert not db.commit.called
    # rollback 应被调用
    assert db.rollback.called


@pytest.mark.asyncio
async def test_normal_add_still_works():
    """对照测试：正常流程返回 code=200（防止过度修复）。

    确保修复只影响异常路径，正常 db.add/commit 路径不受影响。
    """
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()

    with _patch_cache_sync() as mock_cache:
        result = await add(downloader_request=_make_request(), _user=None, db=db)

    assert result.code == "200"
    assert result.status == "success"
    assert result.msg == "添加成功"
    # db 操作正确执行
    assert db.add.called
    assert db.commit.called
    # 正常路径不应 rollback
    assert not db.rollback.called
    # 缓存同步被调用（immediate=True）
    assert mock_cache.called
