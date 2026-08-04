# -*- coding: utf-8 -*-
"""
下载器设置 PUT 接口回归测试

覆盖 PUT /api/v1/downloaders/{id}/settings 的参数校验 + 正向保存回读。
该端点是纯 DB 零网络（已确认：PUT 不调下载器 client）。

关键架构点（经探索确认）：
- 用 get_db（同步 Session）+ require_authenticated_user，可直接用同步内存库 override。
- 端点用裸 SQL（text()）读写 downloader_settings / speed_schedule_rules 表，
  无 Pydantic body schema，全部手写校验，失败返回 HTTP 200 + code='422'（非 Pydantic 422）。
- speed_unit 必须是 0(KB/s) 或 1(MB/s)；start_time < end_time；weekdays 非空且 0-6 或 1-7。
- 密码字段走 SM4 加密（encrypt_password），测试 patch 掉避免 YAML 配置依赖。
- 空 body {} 合法，会创建全默认配置。
- 下载器不存在 → code='404'（verify_downloader_exists 查 bt_downloaders dr=0）。
"""

from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.downloader.models import BtDownloaders
from app.models.downloader_settings import DownloaderSetting
from app.models.speed_schedule_rules import SpeedScheduleRule  # noqa: F401  (建表注册)

URL = "/api/v1/downloaders/{dl_id}/settings"


@pytest.fixture
def db_session():
    """同步内存库，建 bt_downloaders + downloader_settings + speed_schedule_rules 三表。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [BtDownloaders.__table__, DownloaderSetting.__table__, SpeedScheduleRule.__table__]
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    # 预置一个下载器（verify_downloader_exists 查 dr=0）
    session.add(BtDownloaders(downloader_id="dl-1", nickname="qbt", downloader_type=0))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """独立 FastAPI app，override get_db + 认证。patch SM4 加密避免 YAML 依赖。"""
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
    # patch SM4 加密：返回固定密文（避免读 YAML 配置）
    with patch("app.api.endpoints.downloader_settings.encrypt_password", lambda p: f"enc_{p}"):
        yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _url(dl_id="dl-1"):
    return URL.format(dl_id=dl_id)


# ==================== 组1：正向保存 + 回读 ====================


class TestSaveAndReadback:
    def test_empty_body_creates_default_config(self, client, db_session):
        """空 body {} 合法 → 创建全默认配置，code='200'。"""
        r = client.put(_url(), json={})
        body = r.json()
        assert body["code"] == "200"
        # 验证落库（裸 SQL 查）
        row = db_session.execute(
            text(
                "SELECT dl_speed_limit, ul_speed_limit, enable_schedule FROM downloader_settings WHERE downloader_id='dl-1'"
            )
        ).fetchone()
        assert row is not None
        assert row[0] == 0  # 默认不限速

    def test_global_speed_saved_without_rules(self, client, db_session):
        """不带规则时，全局速度限制正确保存（隔离全局逻辑，避免规则变量遮蔽干扰）。"""
        body = {
            "dlSpeedLimit": 1024,
            "dlSpeedUnit": 0,
            "ulSpeedLimit": 512,
            "ulSpeedUnit": 1,
            "enableSchedule": False,
        }
        r = client.put(_url(), json=body)
        assert r.json()["code"] == "200"
        row = db_session.execute(
            text(
                "SELECT dl_speed_limit, ul_speed_limit, enable_schedule FROM downloader_settings WHERE downloader_id='dl-1'"
            )
        ).fetchone()
        assert row[0] == 1024
        assert row[1] == 512
        assert row[2] == 0  # enable_schedule False

    def test_schedule_rule_saved_and_readback(self, client, db_session):
        """含规则时，规则正确落库且不得覆盖全局速度限制。"""
        body = {
            "dlSpeedLimit": 1024,
            "dlSpeedUnit": 0,
            "ulSpeedLimit": 512,
            "ulSpeedUnit": 1,
            "enableSchedule": True,
            "schedule_rules": [
                {
                    "start_time": "09:00",
                    "end_time": "18:00",
                    "weekdays": [0, 1, 2, 3, 4],
                    "download": {"enabled": True, "speed_limit": 2048, "speed_unit": 0},
                    "upload": {"enabled": True, "speed_limit": 256, "speed_unit": 0},
                }
            ],
        }
        r = client.put(_url(), json=body)
        assert r.json()["code"] == "200"
        # 回读验证规则落库
        rules = db_session.execute(
            text(
                "SELECT start_time, end_time FROM speed_schedule_rules WHERE downloader_setting_id IN (SELECT id FROM downloader_settings WHERE downloader_id='dl-1')"
            )
        ).fetchall()
        assert len(rules) == 1
        assert rules[0][0] == "09:00"
        assert rules[0][1] == "18:00"
        # 规则使用独立变量解析，不能污染全局限速字段。
        global_row = db_session.execute(
            text(
                "SELECT dl_speed_limit, ul_speed_limit, dl_speed_unit, ul_speed_unit "
                "FROM downloader_settings WHERE downloader_id='dl-1'"
            )
        ).fetchone()
        assert (global_row[0], global_row[1], int(global_row[2]), int(global_row[3])) == (1024, 512, 0, 1)

    @pytest.mark.parametrize("downloader_type", [0, 1])
    def test_schedule_save_then_apply_uses_global_speed(self, client, db_session, downloader_type):
        """保存分时段规则后，立即应用仍应使用全局限速（qBittorrent/Transmission）。

        实现按真实 datetime.now() 判定规则是否命中，因此本用例必须把时间冻结到
        规则时段（09:00–18:00、周一~周五）之外，否则在工作日白天跑 CI 时规则会
        命中，导致应用的是规则速度而非全局限速，与测试语义相悖。
        """
        db_session.execute(
            text("UPDATE bt_downloaders SET downloader_type=:type WHERE downloader_id='dl-1'"),
            {"type": downloader_type},
        )
        db_session.commit()

        body = {
            "dlSpeedLimit": 100,
            "dlSpeedUnit": 1,
            "ulSpeedLimit": 200,
            "ulSpeedUnit": 0,
            "enableSchedule": True,
            "schedule_rules": [
                {
                    "start_time": "09:00",
                    "end_time": "18:00",
                    "weekdays": [0, 1, 2, 3, 4],
                    "download": {"enabled": True, "speed_limit": 900, "speed_unit": 0},
                    "upload": {"enabled": True, "speed_limit": 800, "speed_unit": 0},
                }
            ],
        }
        assert client.put(_url(), json=body).json()["code"] == "200"

        cached_client = MagicMock()
        cached_downloader = SimpleNamespace(downloader_id="dl-1", fail_time=0, client=cached_client)
        from app.main import app as runtime_app

        previous_store = getattr(runtime_app.state, "store", None)
        runtime_app.state.store = SimpleNamespace(get_snapshot_sync=lambda: [cached_downloader])
        # 冻结到周日 03:00：规则时段为工作日 09:00–18:00，此刻必然不命中，
        # 故 apply 走全局限速基线。
        try:
            with freeze_time("2026-03-15 03:00:00"):
                response = client.post(f"{_url()}/apply")
        finally:
            runtime_app.state.store = previous_store

        assert response.json()["code"] == "200"
        if downloader_type == 0:
            cached_client.app_set_preferences.assert_called_once_with(
                prefs={
                    "dl_limit": 100 * 1024 * 1024,
                    "up_limit": 200 * 1024,
                    "queueing_enabled": True,
                    "dl_queue_track": True,
                    "ul_queue_track": True,
                }
            )
        else:
            cached_client.set_session.assert_called_once_with(
                speed_limit_down=100 * 1024,
                speed_limit_down_enabled=True,
                speed_limit_up=200,
                speed_limit_up_enabled=True,
            )

    def test_password_encrypted_on_save(self, client, db_session):
        """password 字段保存时被 SM4 加密（patch 后为 enc_<明文>）。"""
        r = client.put(_url(), json={"password": "secret"})
        assert r.json()["code"] == "200"
        row = db_session.execute(text("SELECT password FROM downloader_settings WHERE downloader_id='dl-1'")).fetchone()
        assert row[0] == "enc_secret", "密码须加密存储，非明文"


# ==================== 组2：参数校验（全部 code='422'，非 Pydantic 422） ====================


class TestParamValidation:
    def test_dl_speed_unit_invalid_returns_422(self, client):
        """dl_speed_unit 非 0/1 → code='422'。"""
        r = client.put(_url(), json={"dlSpeedUnit": 2})
        body = r.json()
        assert body["code"] == "422"
        assert "KB/s" in body["msg"] or "MB/s" in body["msg"]

    def test_ul_speed_unit_invalid_returns_422(self, client):
        """ul_speed_unit 非 0/1 → code='422'，msg 含单位提示。"""
        r = client.put(_url(), json={"ulSpeedUnit": 5})
        body = r.json()
        assert body["code"] == "422"
        assert "KB/s" in body["msg"] or "MB/s" in body["msg"]

    def test_dl_speed_limit_negative_returns_422(self, client):
        """dl_speed_limit 负数 → code='422'，msg 含非负整数提示。"""
        r = client.put(_url(), json={"dlSpeedLimit": -1})
        body = r.json()
        assert body["code"] == "422"
        assert "非负整数" in body["msg"]

    def test_start_time_after_end_time_returns_422(self, client):
        """start_time >= end_time → code='422'。"""
        r = client.put(
            _url(),
            json={
                "schedule_rules": [
                    {
                        "start_time": "18:00",
                        "end_time": "09:00",
                        "weekdays": [0, 1, 2],
                        "speed_limit": 100,
                        "speed_unit": 0,
                    }
                ]
            },
        )
        body = r.json()
        assert body["code"] == "422"
        assert "开始时间必须早于结束时间" in body["msg"]

    def test_empty_weekdays_returns_422(self, client):
        """weekdays 空数组 → code='422'。"""
        r = client.put(
            _url(),
            json={
                "schedule_rules": [
                    {
                        "start_time": "09:00",
                        "end_time": "18:00",
                        "weekdays": [],
                        "speed_limit": 100,
                        "speed_unit": 0,
                    }
                ]
            },
        )
        body = r.json()
        assert body["code"] == "422"
        assert "星期选择不能为空" in body["msg"]

    def test_weekdays_out_of_range_returns_422(self, client):
        """weekdays 含 8（超 0-6 和 1-7 范围）→ code='422'。"""
        r = client.put(
            _url(),
            json={
                "schedule_rules": [
                    {
                        "start_time": "09:00",
                        "end_time": "18:00",
                        "weekdays": [8],
                        "speed_limit": 100,
                        "speed_unit": 0,
                    }
                ]
            },
        )
        assert r.json()["code"] == "422"
        assert "星期" in r.json()["msg"] or "1-7" in r.json()["msg"]

    def test_missing_start_time_returns_422(self, client):
        """规则缺 start_time → code='422'。"""
        r = client.put(
            _url(),
            json={
                "schedule_rules": [
                    {
                        "end_time": "18:00",
                        "weekdays": [0],
                        "speed_limit": 100,
                        "speed_unit": 0,
                    }
                ]
            },
        )
        body = r.json()
        assert body["code"] == "422"
        assert "start_time" in body["msg"]

    def test_schedule_rules_not_array_returns_422(self, client):
        """schedule_rules 非数组 → code='422'，msg 含数组提示。"""
        r = client.put(_url(), json={"schedule_rules": "not_array"})
        body = r.json()
        assert body["code"] == "422"
        assert "数组" in body["msg"]

    def test_invalid_time_format_returns_422(self, client):
        """start_time 格式非 HH:MM → code='422'，msg 含时间格式提示。"""
        r = client.put(
            _url(),
            json={
                "schedule_rules": [
                    {
                        "start_time": "25:00",
                        "end_time": "18:00",
                        "weekdays": [0],
                        "speed_limit": 100,
                        "speed_unit": 0,
                    }
                ]
            },
        )
        body = r.json()
        assert body["code"] == "422"
        assert "时间格式" in body["msg"]


# ==================== 组3：下载器不存在 + 认证 ====================


class TestNotFoundAndAuth:
    def test_downloader_not_found_returns_404(self, client):
        """下载器不存在 → code='404'。"""
        r = client.put(_url("nonexistent"), json={})
        assert r.json()["code"] == "404"

    def test_no_auth_returns_401(self, db_session):
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
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.put(_url(), json={})
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "401"
