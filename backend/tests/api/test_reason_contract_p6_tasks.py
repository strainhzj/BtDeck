# -*- coding: utf-8 -*-
"""双语 P6-4a 错误契约测试（定时任务域：cron_tasks 全端点）。

锁定的不变量（对齐 P2/P4/P5/P6-3 契约批）：
- CommonResponse 信封四字段不变；仅 data 新增 reasonCode 字段（B03 兼容冻结）；
- reasonCode 取值属对外契约，本文件逐路径钉死（前端 errors.byCode TASKS_* 依赖）；
- 动态拼接 msg（str(e)/task_id/任务编码/任务名/类型值）只进日志，msg 固定（防泄露 + 可翻译）；
- CRUD 业务失败（编码/名称冲突）原文明细只进日志，按 TASKS_TASK_CONFLICT 稳定分类；
- 安全策略 403（自定义脚本禁用 / Android 主机形态不支持）携带独立 reasonCode；
- 成功路径（含带计数的汇总 msg）不在契约范围，仅钉 data 形状不回归。
"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import get_current_user, require_authenticated_user
from app.database import Base, get_async_db, get_db
from app.tasks.cron_models import CronTask

URL = "/api/v1/cronTasks"

ENDPOINT_FILE = "app/api/endpoints/cron_tasks.py"

EXPECTED_REASON_CODES = {
    "TASKS_CUSTOM_SCRIPTS_DISABLED",
    "TASKS_CUSTOM_SCRIPTS_HOST_UNSUPPORTED",
    "TASKS_UNSUPPORTED_TASK_TYPE",
    "TASKS_EXECUTOR_NOT_ALLOWED",
    "TASKS_TASK_CONFLICT",
    "TASKS_NOT_FOUND",
    "TASKS_CREATE_FAILED",
    "TASKS_LIST_FAILED",
    "TASKS_GET_FAILED",
    "TASKS_UPDATE_FAILED",
    "TASKS_DELETE_FAILED",
    "TASKS_EXECUTE_FAILED",
    "TASKS_PAUSE_FAILED",
    "TASKS_RESUME_FAILED",
    "TASKS_INTERRUPT_FAILED",
    "TASKS_LOG_LIST_FAILED",
    "TASKS_LOG_STATS_FAILED",
    "TASKS_LOG_DELETE_FAILED",
    "TASKS_LOG_EXPORT_FAILED",
    "TASKS_LOG_CLEANUP_FAILED",
    "TASKS_CLEANUP_CONDITION_REQUIRED",
    "TASKS_CLEANUP_DAYS_INVALID",
    "TASKS_CLEANUP_INVALID_PARAMS",
    "TASKS_CLEANUP_EXECUTE_FAILED",
    "TASKS_CLEANUP_PREVIEW_FAILED",
    "TASKS_SYNTAX_VALIDATE_FAILED",
    "TASKS_CRON_VALIDATE_FAILED",
    "TASKS_PYTHON_CLASS_FAILED",
    "TASKS_TYPE_CONFIG_FAILED",
}


def _reason_code(body: dict) -> str:
    data = body["data"]
    assert isinstance(data, dict), f"data 应为携带 reasonCode 的 dict，实际: {data!r}"
    assert set(data.keys()) == {"reasonCode"}, f"data 仅应含 reasonCode，实际: {data!r}"
    return data["reasonCode"]


@pytest.fixture()
def sync_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[CronTask.__table__])
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(sync_engine):
    Session = sessionmaker(bind=sync_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    """内存库 + 认证豁免的 TestClient。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")

    with patch("app.database.SessionLocal", return_value=db_session):
        yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


def _seed_task(db, task_id=1, task_code="t1", task_name="task-1", task_type=4, enabled=True):
    row = CronTask(
        task_id=task_id,
        task_code=task_code,
        task_name=task_name,
        task_type=task_type,
        executor="app.tasks.scheduler.downloader_cache_sync.CachedDownloaderSyncTask",
        cron_plan="0 3 * * *",
        task_status=2,
        enabled=enabled,
        dr=0,
    )
    db.add(row)
    db.commit()
    return row


# ====================================================================
# 一、任务类型与安全策略
# ====================================================================


class TestTaskTypeContract:
    def test_unsupported_task_type_fixed_msg(self, client):
        resp = client.post(
            URL + "/add",
            json={"task_name": "x", "task_code": "x9", "task_type": 99, "executor": "e", "cron_plan": "* * * * *"},
        )
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "TASKS_UNSUPPORTED_TASK_TYPE"
        # 类型值不得回流 msg
        assert "99" not in body["msg"]

    def test_custom_scripts_disabled_policy_403(self, client):
        with patch.object(
            __import__("app.api.endpoints.cron_tasks", fromlist=["settings"]).settings,
            "BTDECK_ALLOW_CUSTOM_SCRIPTS",
            False,
        ):
            resp = client.post(
                URL + "/add",
                json={
                    "task_name": "x",
                    "task_code": "x8",
                    "task_type": 0,
                    "executor": "echo hi",
                    "cron_plan": "* * * * *",
                },
            )
        body = resp.json()
        assert body["code"] == "403"
        assert _reason_code(body) == "TASKS_CUSTOM_SCRIPTS_DISABLED"

    def test_type4_executor_not_allowed(self, client):
        resp = client.post(
            URL + "/add",
            json={
                "task_name": "x",
                "task_code": "x7",
                "task_type": 4,
                "executor": "os.system",
                "cron_plan": "* * * * *",
                "enabled": False,
            },
        )
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "TASKS_EXECUTOR_NOT_ALLOWED"
        assert "os.system" not in body["msg"]


# ====================================================================
# 二、CRUD 失败路径
# ====================================================================


class TestCrudFailureContract:
    def test_create_duplicate_code_conflict(self, client, db_session):
        _seed_task(db_session, task_code="dup-code")
        resp = client.post(
            URL + "/add",
            json={
                "task_name": "n",
                "task_code": "dup-code",
                "task_type": 4,
                "executor": "app.tasks.x.Y",
                "cron_plan": "* * * * *",
            },
        )
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "TASKS_TASK_CONFLICT"
        # CRUD 原文明细（含任务编码值）不进 msg
        assert "dup-code" not in body["msg"]
        assert body["msg"] == "任务编码或名称已存在，请修改后重试"

    def test_get_not_found_404(self, client):
        resp = client.get(URL + "/999")
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "TASKS_NOT_FOUND"

    def test_update_not_found_404(self, client):
        resp = client.put(URL + "/999", json={"task_name": "n"})
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "TASKS_NOT_FOUND"

    def test_delete_not_found_404(self, client):
        resp = client.delete(URL + "/999")
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "TASKS_NOT_FOUND"

    def test_list_db_failure_fixed_msg(self, client):
        with patch("app.api.endpoints.cron_tasks.CronTaskCRUD.get_cron_tasks", side_effect=RuntimeError("boom-secret")):
            resp = client.get(URL + "/list")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "TASKS_LIST_FAILED"
        assert "boom-secret" not in body["msg"]

    def test_create_exception_fixed_msg(self, client):
        with patch("app.api.endpoints.cron_tasks.CronTaskCRUD.create_cron_task", side_effect=RuntimeError("boom")):
            resp = client.post(
                URL + "/add",
                json={
                    "task_name": "n",
                    "task_code": "c1",
                    "task_type": 4,
                    "executor": "app.tasks.x.Y",
                    "cron_plan": "* * * * *",
                },
            )
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "TASKS_CREATE_FAILED"
        assert "boom" not in body["msg"]


# ====================================================================
# 三、日志域失败路径与清理校验
# ====================================================================


class TestLogContract:
    def test_log_list_db_failure(self, client):
        with patch("app.api.endpoints.cron_tasks.TaskLogsCRUD.get_task_logs", side_effect=RuntimeError("boom")):
            resp = client.get(URL + "/logs")
        body = resp.json()
        assert _reason_code(body) == "TASKS_LOG_LIST_FAILED"

    def test_log_stats_db_failure(self, client):
        with patch(
            "app.api.endpoints.cron_tasks.TaskLogsCRUD.get_task_logs_statistics", side_effect=RuntimeError("boom")
        ):
            resp = client.get(URL + "/logs/statistics")
        body = resp.json()
        assert _reason_code(body) == "TASKS_LOG_STATS_FAILED"

    def test_cleanup_condition_required(self, client):
        resp = client.post(URL + "/logs/cleanup", json={})
        body = resp.json()
        assert _reason_code(body) == "TASKS_CLEANUP_CONDITION_REQUIRED"

    def test_cleanup_days_invalid(self, client):
        resp = client.post(URL + "/logs/cleanup", json={"days": -1})
        body = resp.json()
        assert _reason_code(body) == "TASKS_CLEANUP_DAYS_INVALID"

    def test_cleanup_invalid_params_422(self, client):
        resp = client.post(URL + "/logs/cleanup", json={"days": "not-a-number"})
        body = resp.json()
        assert body["code"] == "422"
        assert _reason_code(body) == "TASKS_CLEANUP_INVALID_PARAMS"


# ====================================================================
# 四、校验器与配置端点
# ====================================================================


class TestValidatorContract:
    def test_cron_validate_failure(self, client):
        with patch("app.tasks.validation_service.CronValidationService") as MockValidator:
            MockValidator.return_value.validate_expression.side_effect = RuntimeError("boom")
            resp = client.post(URL + "/validation/cron", json={"expression": "* * * * *"})
        body = resp.json()
        assert _reason_code(body) == "TASKS_CRON_VALIDATE_FAILED"

    def test_type_config_failure(self, client):
        with patch("app.tasks.validation_service.PythonClassValidationService") as MockValidator:
            MockValidator.return_value.get_available_classes.side_effect = RuntimeError("boom")
            resp = client.get(URL + "/config/task-types")
        body = resp.json()
        assert _reason_code(body) == "TASKS_TYPE_CONFIG_FAILED"

    def test_type_config_success_shape_stable(self, client):
        """成功路径 data 形状不回归（taskTypes 列表 + pythonClasses 由后端真实类驱动）。"""
        resp = client.get(URL + "/config/task-types")
        body = resp.json()
        assert body["code"] == "200"
        assert isinstance(body["data"]["taskTypes"], list)
        assert isinstance(body["data"].get("pythonClasses", []), list)


# ====================================================================
# 五、源码级契约：动态拼接禁回流 + reasonCode 清单完整
# ====================================================================


class TestSourceContract:
    def test_no_dynamic_exception_in_msg(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / ENDPOINT_FILE).read_text(encoding="utf-8")
        # 失败分支动态 msg 一律禁止（成功计数路径除外）
        for match in re.finditer(r'msg=f"[^"]*\{str\(e\)\}', text):
            raise AssertionError(f"存在动态 str(e) 进 msg: {match.group(0)}")

    def test_reason_code_inventory_complete(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / ENDPOINT_FILE).read_text(encoding="utf-8")
        used = set(re.findall(r'_tasks_error\(\s*\n?\s*"([A-Z_]+)"', text))
        assert used, "应至少登记一个 reasonCode"
        unexpected = used - EXPECTED_REASON_CODES
        assert not unexpected, f"存在未登记的 reasonCode: {sorted(unexpected)}"
        # 每个登记键都应在源码中出现（防清单腐化）
        missing = EXPECTED_REASON_CODES - used
        assert not missing, f"清单中未在源码使用的 reasonCode: {sorted(missing)}"

    def test_capability_reason_code_preserved(self):
        """P4 既有能力矩阵 reasonCode（第 536 行区域）不因本批改动丢失。"""
        root = Path(__file__).resolve().parents[2]
        text = (root / ENDPOINT_FILE).read_text(encoding="utf-8")
        assert '"reasonCode": capability_error["reason_code"]' in text
