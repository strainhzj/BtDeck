# -*- coding: utf-8 -*-
"""
定时任务安全策略回归测试

覆盖 cron_tasks 的安全闸门逻辑（防脚本注入绕过）：
- _validate_task_type_allowed：纯函数，按 task_type + BTDECK_ALLOW_CUSTOM_SCRIPTS 判定
- _validate_update_task_type：更新时防绕过（创建 type=4 → 更新改 type=0 必须被拦）
- POST /add + PUT /{task_id} 端点级集成（安全闸门在 db 写入前）

安全模型（cron_tasks.py:186-219）：
- 内置类型 {4,5,6}（python内部类/清理回收站/审计导出）→ 始终放行
- 自定义脚本类型 {0,1,2,3}（shell/cmd/powershell/python脚本）→ 默认禁用（403），
  仅当 settings.BTDECK_ALLOW_CUSTOM_SCRIPTS=True 时放行
- 未知类型（7/-1/99）→ 400

关键设计点：
- 安全闸门不抛 HTTPException，而是返回 CommonResponse（HTTP 200，code 写在体里）
- 403 响应的 msg 必须含 BTDECK_ALLOW_CUSTOM_SCRIPTS 提示（安全指引）
- _validate_update_task_type 防绕过：即使创建用 type=4，更新改 type=0 也被拦；
  且更新不带 task_type 时读 DB 现有值再校验
- /add 成功路径会调 cron_executor.add_task_to_scheduler（enabled=True 时），
  测试用 enabled=False 避开调度器副作用，专注安全逻辑
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.api.endpoints.cron_tasks import (
    BUILTIN_TASK_TYPES,
    CUSTOM_SCRIPT_TASK_TYPES,
    _validate_task_type_allowed,
    _validate_update_task_type,
)
from app.auth.dependencies import require_authenticated_user
from app.core.config import settings
from app.database import Base, get_db
from app.tasks.cron_models import CronTask

URL_ADD = "/api/v1/cronTasks/add"
URL_UPDATE = "/api/v1/cronTasks/{task_id}"


def _make_body(*, task_type, task_code="test_code_unique", task_name="测试任务", enabled=False, **extra):
    """构造最小合法 CronTaskCreate body。

    enabled=False 避开 cron_executor.add_task_to_scheduler 副作用（专注安全逻辑）。
    """
    body = {
        "task_name": task_name,
        "task_code": task_code,
        "task_type": task_type,
        "executor": "app.tasks.system_tasks.SystemTask",
        "cron_plan": "0 3 * * *",
        "enabled": enabled,
    }
    body.update(extra)
    return body


# ==================== 组1：_validate_task_type_allowed 纯函数 ====================


class TestValidateTaskTypeAllowed:
    """安全闸门纯函数：输入 task_type + 全局开关，输出 Optional[CommonResponse]。"""

    def test_builtin_types_allowed(self):
        """内置类型 4/5/6 始终放行（返回 None），无论开关状态。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            for t in BUILTIN_TASK_TYPES:
                assert _validate_task_type_allowed(t) is None, f"内置类型 {t} 须放行"

    def test_builtin_types_allowed_even_when_scripts_enabled(self):
        """开关开启时内置类型仍放行（不受影响）。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", True):
            for t in BUILTIN_TASK_TYPES:
                assert _validate_task_type_allowed(t) is None

    def test_custom_script_types_blocked_by_default(self):
        """自定义脚本类型 0/1/2/3 默认禁用（返回 code='403'）。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            for t in CUSTOM_SCRIPT_TASK_TYPES:
                resp = _validate_task_type_allowed(t)
                assert resp is not None, f"脚本类型 {t} 默认应被禁用"
                assert resp.code == "403"
                assert resp.status == "error"

    def test_custom_script_types_allowed_when_flag_enabled(self):
        """开关开启时脚本类型放行。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", True):
            for t in CUSTOM_SCRIPT_TASK_TYPES:
                assert _validate_task_type_allowed(t) is None, f"开关开后脚本类型 {t} 应放行"

    def test_403_message_contains_enable_hint(self):
        """403 响应 msg 必须含 BTDECK_ALLOW_CUSTOM_SCRIPTS 提示（安全指引）。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            resp = _validate_task_type_allowed(0)
            assert "BTDECK_ALLOW_CUSTOM_SCRIPTS" in resp.msg

    @pytest.mark.parametrize("bad_type", [7, -1, 99, 100])
    def test_unknown_type_returns_400(self, bad_type):
        """未知类型（非 0-6）返回 code='400'（非 403）。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            resp = _validate_task_type_allowed(bad_type)
            assert resp is not None
            assert resp.code == "400", f"未知类型 {bad_type} 须返回 400"
            assert str(bad_type) in resp.msg

    def test_unknown_type_400_even_when_scripts_enabled(self):
        """开关开启时未知类型仍返回 400（开关只放行 0-3，不放行未知）。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", True):
            resp = _validate_task_type_allowed(99)
            assert resp.code == "400"


# ==================== 组2：_validate_update_task_type 防绕过 ====================


@pytest.fixture
def db_session():
    """同步内存库，建 cron_task 表（_validate_update_task_type 不带 type 时读 DB 现有值）。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[CronTask.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_cron_task(db, *, task_id=None, task_type=4, task_code="existing"):
    """插入一条 CronTask（用于更新防绕过测试的预置数据）。"""
    task = CronTask(
        task_name="预置任务",
        task_code=task_code,
        task_type=task_type,
        executor="app.tasks.system_tasks.SystemTask",
        cron_plan="0 3 * * *",
        enabled=False,
    )
    db.add(task)
    db.commit()
    return task


class TestValidateUpdateTaskType:
    """更新时防绕过：创建 type=4 → 更新改 type=0 必须被拦。"""

    def test_explicit_change_to_script_type_blocked(self, db_session):
        """更新时显式带 task_type=0 → 被 403 拦截（防绕过核心）。"""
        task = _make_cron_task(db_session, task_type=4)
        update_data = SimpleNamespace(task_type=0)
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            resp = _validate_update_task_type(db_session, task.task_id, update_data)
        assert resp is not None
        assert resp.code == "403"

    def test_explicit_change_to_builtin_allowed(self, db_session):
        """更新时显式带 task_type=4 → 放行。"""
        task = _make_cron_task(db_session, task_type=0)
        update_data = SimpleNamespace(task_type=4)
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            resp = _validate_update_task_type(db_session, task.task_id, update_data)
        assert resp is None

    def test_no_type_field_reads_db_existing_script_blocked(self, db_session):
        """更新不带 task_type → 读 DB 现有 task_type=0 → 被 403 拦截。

        防"任务已被外部改成脚本类型，更新时不带 type 绕过校验"。
        """
        task = _make_cron_task(db_session, task_type=0)
        update_data = SimpleNamespace(task_type=None)
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            resp = _validate_update_task_type(db_session, task.task_id, update_data)
        assert resp is not None
        assert resp.code == "403"

    def test_no_type_field_reads_db_existing_builtin_allowed(self, db_session):
        """更新不带 task_type → 读 DB 现有 task_type=4 → 放行。"""
        task = _make_cron_task(db_session, task_type=4)
        update_data = SimpleNamespace(task_type=None)
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            resp = _validate_update_task_type(db_session, task.task_id, update_data)
        assert resp is None

    def test_update_nonexistent_task_no_error(self, db_session):
        """更新不存在的 task_id（不带 type）→ 读 DB 返回 None → 放行（不阻塞后续 404）。"""
        update_data = SimpleNamespace(task_type=None)
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            resp = _validate_update_task_type(db_session, 99999, update_data)
        assert resp is None, "任务不存在时安全闸门不应阻塞（留给 CRUD 返回 404）"


# ==================== 组3：端点级集成（POST /add） ====================


@pytest.fixture
def client_factory(db_session):
    """返回构造 client 的工厂，便于切换 BTDECK_ALLOW_CUSTOM_SCRIPTS 后重建 app。

    /add 和 /{task_id} 共用 require_authenticated_user + get_db override。
    """

    def _make_client():
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        def override_get_db():
            db = sessionmaker(bind=db_session.bind)()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
        return TestClient(app, raise_server_exceptions=False)

    return _make_client


class TestAddEndpointSecurity:
    """POST /add 端点：安全闸门在 db 写入前执行。"""

    def test_add_script_type_blocked_returns_403(self, client_factory):
        """type=0（shell）默认禁用 → code='403'，且不写库。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            c = client_factory()
            r = c.post(URL_ADD, json=_make_body(task_type=0))
        body = r.json()
        assert body["code"] == "403"
        assert "BTDECK_ALLOW_CUSTOM_SCRIPTS" in body["msg"]

    def test_add_builtin_type_succeeds(self, db_session, client_factory):
        """type=4（内置）放行 → code='200'，任务落库。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            c = client_factory()
            r = c.post(URL_ADD, json=_make_body(task_type=4, task_code="builtin_ok"))
        body = r.json()
        assert body["code"] == "200"
        # 验证落库（任务名）
        task = db_session.query(CronTask).filter_by(task_code="builtin_ok").first()
        assert task is not None
        assert task.task_type == 4

    def test_add_unknown_type_returns_400(self, client_factory):
        """type=7（未知）→ code='400'。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            c = client_factory()
            r = c.post(URL_ADD, json=_make_body(task_type=7))
        assert r.json()["code"] == "400"

    def test_add_script_type_allowed_when_flag_enabled(self, db_session, client_factory):
        """开关开启时 type=0 放行 → code='200'。"""
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", True):
            c = client_factory()
            r = c.post(URL_ADD, json=_make_body(task_type=0, task_code="script_ok"))
        body = r.json()
        assert body["code"] == "200"

    def test_add_no_auth_returns_401(self, db_session):
        """无认证 → 401（detail 是 dict）。"""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        def override_get_db():
            db = sessionmaker(bind=db_session.bind)()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        # 不 override require_authenticated_user → 走真实认证 → 无 token 拒绝
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(URL_ADD, json=_make_body(task_type=4))
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "401"


# ==================== 组4：端点级集成（PUT /{task_id} 防绕过） ====================


class TestUpdateEndpointSecurity:
    """PUT /{task_id} 端点：防绕过（创建 type=4 → 更新改 type=0 被拦）。

    注意：更新成功路径会调 cron_executor.refresh_task（cron_tasks.py:705），
    该方法用真实 AsyncSessionLocal + 单例 scheduler，有副作用。
    测试用 patch.object(cron_executor, refresh_task, AsyncMock) 隔离，
    并补 DB 落库断言（不只断 code='200'，防 no-op 假通过）。
    """

    def test_update_change_to_script_type_blocked(self, db_session, client_factory):
        """预置 type=4 任务，PUT 改 type=0 → code='403'，msg 含启用提示。"""
        task = _make_cron_task(db_session, task_type=4, task_code="to_update")
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            c = client_factory()
            r = c.put(URL_UPDATE.format(task_id=task.task_id), json={"task_type": 0})
        body = r.json()
        assert body["code"] == "403"
        assert "BTDECK_ALLOW_CUSTOM_SCRIPTS" in body["msg"]

    def test_update_change_to_unknown_type_returns_400(self, db_session, client_factory):
        """预置 type=4 任务，PUT 改 type=7（未知）→ code='400'。"""
        task = _make_cron_task(db_session, task_type=4, task_code="to_unknown")
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            c = client_factory()
            r = c.put(URL_UPDATE.format(task_id=task.task_id), json={"task_type": 7})
        assert r.json()["code"] == "400"

    def test_update_change_to_builtin_allowed(self, db_session, client_factory):
        """预置 type=0 任务，PUT 改 type=4 → 放行（需开关开），且字段落库。"""
        from unittest.mock import AsyncMock
        from app.api.endpoints import cron_tasks as cron_module

        task = _make_cron_task(db_session, task_type=0, task_code="to_promote")
        with (
            patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", True),
            patch.object(cron_module.cron_executor, "refresh_task", AsyncMock(return_value=True)),
        ):
            c = client_factory()
            r = c.put(URL_UPDATE.format(task_id=task.task_id), json={"task_type": 4})
        assert r.json()["code"] == "200"
        # 补 DB 落库断言（防 CRUD no-op 假通过）
        db_session.expire_all()
        updated = db_session.query(CronTask).get(task.task_id)
        assert updated.task_type == 4, "更新后 task_type 须真正落库"

    def test_update_rename_without_type_change_allowed(self, db_session, client_factory):
        """预置 type=4 任务，PUT 只改名不带 task_type → 放行，且名字落库。"""
        from unittest.mock import AsyncMock
        from app.api.endpoints import cron_tasks as cron_module

        task = _make_cron_task(db_session, task_type=4, task_code="rename_me")
        with (
            patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False),
            patch.object(cron_module.cron_executor, "refresh_task", AsyncMock(return_value=True)),
        ):
            c = client_factory()
            r = c.put(URL_UPDATE.format(task_id=task.task_id), json={"task_name": "新名字"})
        assert r.json()["code"] == "200"
        # 补 DB 落库断言
        db_session.expire_all()
        updated = db_session.query(CronTask).get(task.task_id)
        assert updated.task_name == "新名字", "更新后 task_name 须真正落库"


# ==================== 组4：task_type=4 executor 白名单 ====================
# 安全背景：历史实现中 type=4 的 executor 解析失败会回落到 exec() 任意代码执行
# （认证后 RCE）。修复后 API/执行/加载三层均要求 executor 为
# app.tasks. 命名空间下的严格类路径。


class TestType4ExecutorWhitelist:
    """_validate_type4_executor 纯函数 + is_internal_class_executor_allowed 白名单。"""

    @pytest.mark.parametrize(
        "evil_executor",
        [
            '__import__("os").system("echo pwned")',  # 动态导入 payload（含括号）
            'os.system("echo pwned")',  # 非白名单前缀
            "print(1)",  # 纯代码无点号
            "import os",  # import 语句
            "app.tasks;os.system",  # 分号注入
            "C:/Windows/evil",  # 路径分隔符
            "app.tasksevil.Evil",  # 前缀伪造（app.tasksevil 不以 app.tasks. 开头）
            "evils.app.tasks.Evil",  # 后缀伪造
            "..\/..\/evil",  # 穿越字符串
            "",  # 空
        ],
    )
    def test_evil_executors_rejected(self, evil_executor):
        from app.api.endpoints.cron_tasks import _validate_type4_executor
        from app.tasks.cron_executor import is_internal_class_executor_allowed

        assert is_internal_class_executor_allowed(evil_executor) is False
        resp = _validate_type4_executor(4, evil_executor)
        assert resp is not None and resp.code == "400"

    def test_builtin_class_path_allowed(self):
        from app.api.endpoints.cron_tasks import _validate_type4_executor
        from app.tasks.cron_executor import is_internal_class_executor_allowed

        ok = "app.tasks.scheduler.downloader_cache_sync.CachedDownloaderSyncTask"
        assert is_internal_class_executor_allowed(ok) is True
        assert _validate_type4_executor(4, ok) is None

    def test_type56_executor_not_validated(self):
        """type 5/6 的 executor 是 JSON 配置，不做类路径校验（正则不适用）。"""
        from app.api.endpoints.cron_tasks import _validate_type4_executor

        assert _validate_type4_executor(5, '{"cleanup_level_3": true}') is None
        assert _validate_type4_executor(6, '{"days": 30}') is None

    def test_none_executor_allowed_for_update_partial(self):
        """更新请求不带 executor 字段时不校验（CronTaskUpdate.executor 可选）。"""
        from app.api.endpoints.cron_tasks import _validate_type4_executor

        assert _validate_type4_executor(4, None) is None


class TestAddEndpointExecutorGate:
    """POST /add 端点：type=4 恶意 executor 在写库前被拒。"""

    def test_add_type4_evil_executor_returns_400(self, db_session, client_factory):
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            c = client_factory()
            r = c.post(
                URL_ADD,
                json=_make_body(
                    task_type=4,
                    task_code="evil_exec",
                    executor='__import__("os").system("echo pwned")',
                ),
            )
        assert r.json()["code"] == "400"
        assert db_session.query(CronTask).filter_by(task_code="evil_exec").first() is None

    def test_add_type4_builtin_executor_succeeds(self, db_session, client_factory):
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            c = client_factory()
            r = c.post(
                URL_ADD,
                json=_make_body(
                    task_type=4,
                    task_code="builtin_exec",
                    executor="app.tasks.scheduler.downloader_cache_sync.CachedDownloaderSyncTask",
                ),
            )
        assert r.json()["code"] == "200"
        task = db_session.query(CronTask).filter_by(task_code="builtin_exec").first()
        assert task is not None


class TestUpdateEndpointExecutorGate:
    """PUT /{task_id}：类型保持 4 但 executor 改写为恶意串 → 拒绝。"""

    def test_update_swap_executor_to_evil_blocked(self, db_session, client_factory):
        from unittest.mock import AsyncMock
        from app.api.endpoints import cron_tasks as cron_module

        task = _make_cron_task(db_session, task_type=4, task_code="swap_me")
        with (
            patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False),
            patch.object(cron_module.cron_executor, "refresh_task", AsyncMock(return_value=True)),
        ):
            c = client_factory()
            r = c.put(URL_UPDATE.format(task_id=task.task_id), json={"executor": 'os.system("evil")'})
        assert r.json()["code"] == "400"
        db_session.expire_all()
        updated = db_session.query(CronTask).get(task.task_id)
        assert updated.executor != 'os.system("evil")', "恶意 executor 不得落库"


class TestPythonClassValidationEndpointGate:
    """/validation/python-class：非白名单路径不进入 importlib。"""

    def test_validation_rejects_non_whitelisted_path(self, db_session, client_factory):
        c = client_factory()
        r = c.post(
            "/api/v1/cronTasks/validation/python-class",
            json={"class_path": "os.path"},
        )
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["valid"] is False
        assert "app.tasks." in body["data"]["message"]
