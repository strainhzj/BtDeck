# -*- coding: utf-8 -*-
"""Task log cleanup guard and filter tests."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AuthenticatedUserInfo, require_authenticated_user
from app.database import Base
from app.tasks.cron_models import CronTask
from app.tasks.cron_crud import TaskLogsCRUD
from app.tasks.models import TaskLogs


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[CronTask.__table__, TaskLogs.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[TaskLogs.__table__, CronTask.__table__])


@pytest.fixture
def client(db_session):
    from app.api.api import api_router
    from app.database import get_db

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUserInfo(
        username="admin", payload={"sub": "admin", "user_id": 1}, token="test-token", user_id=1
    )
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _add_log(db_session, log_id: int, days_old: int, success: bool):
    log = TaskLogs(
        log_id=log_id,
        task_id=None,
        task_name=f"task-{log_id}",
        task_type=1,
        start_time=datetime.now() - timedelta(days=days_old),
        success=success,
        log_detail="test",
        dr=0,
    )
    db_session.add(log)
    db_session.commit()
    return log


def _active_ids(db_session):
    return {row.log_id for row in db_session.query(TaskLogs).filter(TaskLogs.dr == 0).all()}


def test_empty_payload_returns_error_and_does_not_mass_delete(client, db_session):
    _add_log(db_session, 1, days_old=30, success=True)
    _add_log(db_session, 2, days_old=30, success=False)

    response = client.post("/api/v1/cronTasks/logs/cleanup", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "400"
    assert _active_ids(db_session) == {1, 2}


def test_crud_empty_payload_guard_does_not_mass_delete(db_session):
    _add_log(db_session, 1, days_old=30, success=True)

    result = TaskLogsCRUD.cleanup_task_logs(db_session)

    assert not result.success
    assert _active_ids(db_session) == {1}


def test_negative_days_returns_error(client, db_session):
    _add_log(db_session, 1, days_old=30, success=True)

    response = client.post("/api/v1/cronTasks/logs/cleanup", json={"days": -1})

    assert response.status_code == 200
    assert response.json()["code"] == "400"
    assert _active_ids(db_session) == {1}


def test_crud_negative_days_returns_error(db_session):
    _add_log(db_session, 1, days_old=30, success=True)

    result = TaskLogsCRUD.cleanup_task_logs(db_session, days=-1)

    assert not result.success
    assert _active_ids(db_session) == {1}


def test_valid_days_parameter_deletes_only_old_logs(client, db_session):
    _add_log(db_session, 1, days_old=30, success=True)
    _add_log(db_session, 2, days_old=1, success=True)

    response = client.post("/api/v1/cronTasks/logs/cleanup", json={"days": 7})

    assert response.status_code == 200
    assert response.json()["code"] == "200"
    assert response.json()["data"]["cleaned"] == 1
    assert _active_ids(db_session) == {2}


def test_keep_success_true_only_deletes_failed_logs(client, db_session):
    _add_log(db_session, 1, days_old=30, success=True)
    _add_log(db_session, 2, days_old=30, success=False)

    response = client.post("/api/v1/cronTasks/logs/cleanup", json={"keep_success": True})

    assert response.status_code == 200
    assert response.json()["code"] == "200"
    assert _active_ids(db_session) == {1}


def test_keep_error_true_only_deletes_successful_logs(client, db_session):
    _add_log(db_session, 1, days_old=30, success=True)
    _add_log(db_session, 2, days_old=30, success=False)

    response = client.post("/api/v1/cronTasks/logs/cleanup", json={"keep_error": True})

    assert response.status_code == 200
    assert response.json()["code"] == "200"
    assert _active_ids(db_session) == {2}
