# 代码审查边界场景测试 + 修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为最近两次提交 (dbe3d19, 6803889) 引入的5个CRITICAL + 4个HIGH问题编写边界单元测试，然后以TDD方式逐个修复

**Architecture:** 每个问题独立一个测试文件，mock外部依赖（数据库、下载器客户端、FastAPI app），测试完成后修改源码使测试通过

**Tech Stack:** pytest, unittest.mock, FastAPI test utilities

---

## Task 1: C1 — get_torrent_info 参数数量不匹配

**Files:**
- Create: `tests/api/test_torrent_crud_review.py`
- Modify: `app/api/endpoints/torrent_crud.py:773`
- Modify: `app/services/torrent_crud_service.py:514-524`

**Step 1: Write the failing test**

```python
# tests/api/test_torrent_crud_review.py
import pytest
from unittest.mock import MagicMock, patch


def test_get_torrent_info_parameter_mismatch():
    """
    C1: get_torrent_info 定义3个参数 (db, info_id, downloader_id)，
    但 torrent_crud.py:773 调用时传了4个参数 (db, info_id, downloader_id, downloader_name)
    """
    from app.services.torrent_crud_service import get_torrent_info
    import inspect

    sig = inspect.signature(get_torrent_info)
    params = list(sig.parameters.keys())
    assert params == ['db', 'info_id', 'downloader_id'], \
        f"get_torrent_info 参数应为 (db, info_id, downloader_id)，实际为 {params}"


def test_get_torrent_call_passes_correct_args():
    """验证调用处传参数量与定义一致"""
    from app.services.torrent_crud_service import get_torrent_info
    import inspect

    sig = inspect.signature(get_torrent_info)
    expected_count = len(sig.parameters)  # 3

    # 模拟调用：应该只传3个参数
    db = MagicMock()
    with pytest.raises(TypeError):
        # 传4个参数应该失败（当前bug状态）
        get_torrent_info(db, "info-001", "dl-001", "downloader_name")
```

**Step 2: Run test**

```bash
cd BtDeck && python -m pytest tests/api/test_torrent_crud_review.py -v
```

**Step 3: Fix — torrent_crud.py:773 移除第4个参数**

```python
# Before
torrent = get_torrent_info(db, info_id, downloader_id, downloader_name)
# After
torrent = get_torrent_info(db, info_id, downloader_id)
```

**Step 4: Run test again → PASS**

**Step 5: Commit**

```bash
git add tests/api/test_torrent_crud_review.py app/api/endpoints/torrent_crud.py
git commit -m "fix(C1): 修复 get_torrent_info 参数数量不匹配问题"
```

---

## Task 2: C2 — downloader.save_path / path_mapping 属性不存在

**Files:**
- Create: `tests/api/test_torrent_backup_review.py`
- Modify: `app/api/endpoints/torrent_backup.py:155,186,826,833`

**Step 1: Write the failing test**

```python
# tests/api/test_torrent_backup_review.py
import pytest
from unittest.mock import MagicMock, patch


def _make_downloader_vo(**overrides):
    """创建模拟的 DownloaderCheckVO 对象"""
    vo = MagicMock()
    vo.downloader_id = "dl-001"
    vo.host = "192.168.1.1"
    vo.port = 8080
    vo.username = "admin"
    vo.password = "password"
    vo.fail_time = 0
    vo.downloader_type = 0
    vo.torrent_save_path = "/downloads"
    vo.path_mapping_rules = None
    # 不设置 save_path 和 path_mapping（DownloaderCheckVO 上不存在这些属性）
    del vo.save_path
    del vo.path_mapping
    for k, v in overrides.items():
        setattr(vo, k, v)
    return vo


def test_get_downloader_from_store_returns_vo_without_save_path():
    """
    C2: get_downloader_from_store 返回的 DownloaderCheckVO 没有 save_path 属性，
    但代码访问了 downloader.save_path
    """
    from app.api.endpoints.torrent_backup import get_downloader_from_store

    app = MagicMock()
    vo = _make_downloader_vo()
    app.state.store.get_snapshot_sync.return_value = [vo]

    result = get_downloader_from_store("dl-001", app)
    assert result is not None
    # 验证返回对象有正确的属性
    assert hasattr(result, 'torrent_save_path')
    assert result.torrent_save_path == "/downloads"


def test_backup_accesses_correct_save_path_attribute():
    """
    C2: 备份接口应使用 torrent_save_path 而不是 save_path
    """
    from app.api.endpoints.torrent_backup import get_downloader_from_store

    app = MagicMock()
    vo = _make_downloader_vo()
    app.state.store.get_snapshot_sync.return_value = [vo]

    downloader = get_downloader_from_store("dl-001", app)

    # 应该能访问 torrent_save_path，不应该访问 save_path
    assert downloader.torrent_save_path == "/downloads"
    with pytest.raises(AttributeError):
        _ = downloader.save_path


def test_backup_accesses_correct_path_mapping_attribute():
    """
    C2: 备份接口应使用 path_mapping_rules 而不是 path_mapping
    """
    from app.api.endpoints.torrent_backup import get_downloader_from_store

    app = MagicMock()
    vo = _make_downloader_vo(path_mapping_rules='{"rules": []}')
    app.state.store.get_snapshot_sync.return_value = [vo]

    downloader = get_downloader_from_store("dl-001", app)
    assert downloader.path_mapping_rules is not None
    with pytest.raises(AttributeError):
        _ = downloader.path_mapping
```

**Step 2: Run test → FAIL (AttributeError on save_path/path_mapping)**

**Step 3: Fix — torrent_backup.py**

```python
# Line 155: Before
if downloader.path_mapping:
# After
if getattr(downloader, 'path_mapping_rules', None):

# Line 157: Before
path_mapping_service = PathMappingService(downloader.path_mapping)
# After
path_mapping_service = PathMappingService(downloader.path_mapping_rules)

# Line 186: Before
save_path=downloader.save_path,
# After
save_path=getattr(downloader, 'torrent_save_path', None),

# Line 826, 833: Before
save_path=downloader.save_path
# After
save_path=getattr(downloader, 'torrent_save_path', None)
```

**Step 4: Run test → PASS**

**Step 5: Commit**

```bash
git add tests/api/test_torrent_backup_review.py app/api/endpoints/torrent_backup.py
git commit -m "fix(C2): 修复 downloader 属性名不匹配（save_path→torrent_save_path, path_mapping→path_mapping_rules）"
```

---

## Task 3: C3 — async_db 会话在 async with 块外使用

**Files:**
- Create: `tests/api/test_torrent_deletion_review.py`
- Modify: `app/api/endpoints/torrent_deletion.py:182-306,421-448,513-541`

**Step 1: Write the failing test**

```python
# tests/api/test_torrent_deletion_review.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import ast
import inspect


def test_delete_torrent_async_session_scope():
    """
    C3: delete_torrent 中 deletion_service.delete_torrents() 应在
    async with AsyncSessionLocal() 块内调用，否则 async_db_session 已关闭
    """
    from app.api.endpoints import torrent_deletion
    import inspect

    source = inspect.getsource(torrent_deletion.delete_torrent)

    # 找到 async with AsyncSessionLocal() 的缩进级别和范围
    lines = source.split('\n')
    async_with_line = None
    async_with_indent = None
    delete_torrents_line = None

    for i, line in enumerate(lines):
        if 'async with AsyncSessionLocal()' in line:
            async_with_line = i
            async_with_indent = len(line) - len(line.lstrip())
        if 'deletion_service.delete_torrents' in line:
            delete_torrents_line = i

    assert async_with_line is not None, "未找到 async with AsyncSessionLocal()"
    assert delete_torrents_line is not None, "未找到 deletion_service.delete_torrents()"

    # delete_torrents 的缩进应该 >= async with 的缩进（表示在块内）
    delete_indent = len(lines[delete_torrents_line]) - len(lines[delete_torrents_line].lstrip())

    assert delete_indent > async_with_indent, \
        f"C3 BUG: deletion_service.delete_torrents() 在 async with 块外调用！" \
        f"async_with_indent={async_with_indent}, delete_indent={delete_indent}"


def test_bulk_delete_async_session_scope():
    """C3: bulk_delete_torrents 同样的 async with 作用域问题"""
    from app.api.endpoints import torrent_deletion
    import inspect

    source = inspect.getsource(torrent_deletion.bulk_delete_torrents)
    lines = source.split('\n')

    async_with_indices = []
    delete_torrents_indices = []

    for i, line in enumerate(lines):
        if 'async with AsyncSessionLocal()' in line:
            async_with_indices.append((i, len(line) - len(line.lstrip())))
        if 'deletion_service.delete_torrents' in line:
            delete_torrents_indices.append(i)

    # 每个delete_torrents调用都应该在某个async with块内
    for dt_line in delete_torrents_indices:
        dt_indent = len(lines[dt_line]) - len(lines[dt_line].lstrip())
        # 找到最近的async with
        in_block = False
        for aw_line, aw_indent in async_with_indices:
            if aw_line < dt_line and dt_indent > aw_indent:
                in_block = True
                break
        assert in_block, \
            f"C3 BUG: delete_torrents (line {dt_line}) 在 async with 块外调用！"
```

**Step 2: Run test → FAIL**

**Step 3: Fix — 将 `delete_torrents` 调用移入 `async with` 块内**

对 `delete_torrent`, `preview_bulk_torrent_deletion`, `bulk_delete_torrents` 三个端点，
将 `async with AsyncSessionLocal()` 块扩大到包含 `deletion_service.delete_torrents()` 调用。

**Step 4: Run test → PASS**

**Step 5: Commit**

```bash
git add tests/api/test_torrent_deletion_review.py app/api/endpoints/torrent_deletion.py
git commit -m "fix(C3): 修复异步数据库会话在 async with 块外使用导致的 DetachedInstanceError"
```

---

## Task 4: C4+C5 — torrent API 调用无异常保护

**Files:**
- Create: `tests/api/test_torrent_sync_review.py`
- Modify: `app/api/endpoints/torrent_sync.py:429,654`

**Step 1: Write the failing test**

```python
# tests/api/test_torrent_sync_review.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


def _make_bt_downloader(**kwargs):
    """创建模拟的 BtDownloaders 对象"""
    dl = MagicMock()
    dl.downloader_id = "dl-001"
    dl.host = "192.168.1.1"
    dl.port = 8080
    dl.username = "admin"
    dl.password = "password"
    dl.nickname = "test-qb"
    dl.downloader_type = 0
    for k, v in kwargs.items():
        setattr(dl, k, v)
    return dl


def test_qb_add_torrents_handles_client_exception():
    """
    C4: qb_add_torrents 在缓存连接断开时应捕获异常，
    而非让整个函数崩溃
    """
    from app.api.endpoints.torrent_sync import qb_add_torrents

    db = MagicMock()
    downloader = _make_bt_downloader()

    # 模拟缓存中有一个已断开的客户端
    mock_vo = MagicMock()
    mock_vo.downloader_id = "dl-001"
    mock_vo.client = MagicMock()
    mock_vo.client.torrents_info.side_effect = ConnectionError("连接已断开")

    app = MagicMock()
    app.state.store.get_snapshot_sync.return_value = [mock_vo]

    # 应该不抛出异常，而是优雅处理
    result = qb_add_torrents(db, [downloader], app=app)
    assert result is None  # 函数应该安全返回


def test_tr_add_torrents_handles_client_exception():
    """
    C5: tr_add_torrents 在缓存连接断开时应捕获异常
    """
    from app.api.endpoints.torrent_sync import tr_add_torrents

    db = MagicMock()
    downloader = _make_bt_downloader(downloader_type=1, port=9091)

    mock_vo = MagicMock()
    mock_vo.downloader_id = "dl-001"
    mock_vo.client = MagicMock()
    mock_vo.client.get_torrents.side_effect = ConnectionError("连接已断开")

    app = MagicMock()
    app.state.store.get_snapshot_sync.return_value = [mock_vo]

    result = tr_add_torrents(db, [downloader], app=app)
    assert result is None


def test_qb_add_torrents_handles_new_connection_exception():
    """C4: 后备新建连接也应有异常保护"""
    from app.api.endpoints.torrent_sync import qb_add_torrents

    db = MagicMock()
    downloader = _make_bt_downloader()

    with patch('app.api.endpoints.torrent_sync.qbClient') as mock_qb:
        mock_qb.side_effect = ConnectionError("无法连接")
        result = qb_add_torrents(db, [downloader], app=None)
        assert result is None


def test_tr_add_torrents_handles_new_connection_exception():
    """C5: 后备新建 trClient 也应有异常保护"""
    from app.api.endpoints.torrent_sync import tr_add_torrents

    db = MagicMock()
    downloader = _make_bt_downloader(downloader_type=1, port=9091)

    with patch('app.api.endpoints.torrent_sync.trClient') as mock_tr:
        mock_tr.side_effect = ConnectionError("无法连接")
        result = tr_add_torrents(db, [downloader], app=None)
        assert result is None
```

**Step 2: Run test → FAIL**

**Step 3: Fix — 在 `torrents_info()` / `get_torrents()` 调用处加 try/except**

```python
# torrent_sync.py - qb_add_torrents 函数内 (约 line 654)
try:
    torrent_info_list = client.torrents_info()
except Exception as e:
    logger.error(f"获取qBittorrent种子列表失败: {str(e)}")
    return

# torrent_sync.py - tr_add_torrents 函数内 (约 line 429)
try:
    torrent_info_list = tr_client.get_torrents()
except Exception as e:
    logger.error(f"获取Transmission种子列表失败: {str(e)}")
    return
```

**Step 4: Run test → PASS**

**Step 5: Commit**

```bash
git add tests/api/test_torrent_sync_review.py app/api/endpoints/torrent_sync.py
git commit -m "fix(C4,C5): 为下载器客户端API调用添加异常保护，防止连接断开导致崩溃"
```

---

## Task 5: H1 — completion_on 为 0 或 None

**Files:**
- Modify: `tests/api/test_torrent_sync_review.py` (追加测试)
- Modify: `app/api/endpoints/torrent_sync.py:686`

**Step 1: Write the failing test**

追加到 `tests/api/test_torrent_sync_review.py`：

```python
def test_qb_add_torrents_handles_completion_on_zero():
    """
    H1: completion_on 为 0 时，datetime.fromtimestamp(0) 返回 1970 年日期，
    应该返回 None
    """
    from app.api.endpoints.torrent_sync import qb_add_torrents

    db = MagicMock()
    downloader = _make_bt_downloader()

    # 模拟返回 completion_on=0 的种子
    mock_client = MagicMock()
    mock_torrent = MagicMock()
    mock_torrent.hash = "abc123"
    mock_torrent.name = "test"
    mock_torrent.state = "paused"
    mock_torrent.save_path = "/downloads"
    mock_torrent.total_size = 1024
    mock_torrent.added_on = 1700000000  # 合法时间戳
    mock_torrent.completion_on = 0  # 未完成
    mock_torrent.ratio = 1.0
    mock_torrent.ratio_limit = -1
    mock_torrent.tags = ""
    mock_torrent.category = ""
    mock_torrent.super_seeding = False
    mock_torrent.trackers = []
    mock_client.torrents_info.return_value = [mock_torrent]

    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

    # 不应抛出 TypeError
    try:
        qb_add_torrents(db, [downloader], app=None)
    except TypeError:
        pytest.fail("completion_on=0 导致 TypeError")


def test_qb_add_torrents_handles_completion_on_none():
    """
    H1: completion_on 为 None 时不应抛出 TypeError
    """
    from app.api.endpoints.torrent_sync import qb_add_torrents

    db = MagicMock()
    downloader = _make_bt_downloader()

    mock_client = MagicMock()
    mock_torrent = MagicMock()
    mock_torrent.hash = "abc123"
    mock_torrent.name = "test"
    mock_torrent.state = "paused"
    mock_torrent.save_path = "/downloads"
    mock_torrent.total_size = 1024
    mock_torrent.added_on = 1700000000
    mock_torrent.completion_on = None  # None
    mock_torrent.ratio = 1.0
    mock_torrent.ratio_limit = -1
    mock_torrent.tags = ""
    mock_torrent.category = ""
    mock_torrent.super_seeding = False
    mock_torrent.trackers = []
    mock_client.torrents_info.return_value = [mock_torrent]

    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

    try:
        qb_add_torrents(db, [downloader], app=None)
    except TypeError:
        pytest.fail("completion_on=None 导致 TypeError")
```

**Step 2: Run test → FAIL**

**Step 3: Fix — torrent_sync.py:686**

```python
# Before
completed_date=datetime.fromtimestamp(torrent_info.completion_on),
# After
completed_date=(
    datetime.fromtimestamp(torrent_info.completion_on)
    if torrent_info.completion_on and torrent_info.completion_on > 0
    else None
),
```

**Step 4: Run test → PASS**

**Step 5: Commit**

```bash
git add tests/api/test_torrent_sync_review.py app/api/endpoints/torrent_sync.py
git commit -m "fix(H1): 防御性处理 completion_on 为 0 或 None 的情况"
```

---

## Task 6: H4 — fail_time 无 hasattr 防护

**Files:**
- Modify: `tests/api/test_torrent_backup_review.py` (追加测试)
- Modify: `app/api/endpoints/torrent_backup.py:137,766`

**Step 1: Write the failing test**

追加到 `tests/api/test_torrent_backup_review.py`：

```python
def test_fail_time_without_hasattr_guard():
    """
    H4: downloader 没有 fail_time 属性时不应崩溃
    """
    from app.api.endpoints.torrent_backup import get_downloader_from_store

    app = MagicMock()
    vo = MagicMock(spec=[])  # 空 spec，没有 fail_time
    vo.downloader_id = "dl-001"
    app.state.store.get_snapshot_sync.return_value = [vo]

    downloader = get_downloader_from_store("dl-001", app)
    assert downloader is not None
    # 不应因访问 fail_time 而 AttributeError
```

**Step 2: Run test → FAIL**

**Step 3: Fix — torrent_backup.py:137,766**

```python
# Before (line 137)
if not downloader or downloader.fail_time > 0:
# After
if not downloader or (hasattr(downloader, 'fail_time') and downloader.fail_time > 0):

# Before (line 766)
if not downloader or downloader.fail_time > 0:
# After
if not downloader or (hasattr(downloader, 'fail_time') and downloader.fail_time > 0):
```

**Step 4: Run test → PASS**

**Step 5: Commit**

```bash
git add tests/api/test_torrent_backup_review.py app/api/endpoints/torrent_backup.py
git commit -m "fix(H4): 为 fail_time 访问添加 hasattr 防护"
```

---

## Task 7: 运行完整测试套件验证无回归

**Step 1: Run all tests**

```bash
cd BtDeck && python -m pytest tests/ -v --tb=short
```

**Step 2: Verify all pass**

Expected: 所有测试通过，无回归

**Step 3: Final commit if any additional fixes needed**

---

## Task 8: 更新工作状态

```bash
python ~/.claude/skills/work-state/work_state.py record BtDeck --file /tmp/btdeck-work-state.md
```
