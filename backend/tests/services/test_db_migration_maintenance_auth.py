"""维护认证测试（database-migration-ui W2-5，PLANS §5.3/§11 T05）。

- 只读用户读取器（SQLite mode=ro；users 表缺 seed → NO_USERS 离线恢复）；
- 密码/TOTP 纯读校验；停用/强制改密拒绝；失败限流锁定；
- 维护 token：独立 aud/scope/jti；过期/重放/吊销拒绝；续期旋转；普通
  access token 不能过维护校验（verify_access_token 要求 verify_secret，
  维护 token 不携带——双向不可互用）；
- **零源写**：认证全程（成功/失败/限流）源库 data_version 不变（T05）。
"""

from __future__ import annotations

import sqlite3
import time

import jwt as pyjwt
import pytest

from app.auth.security import get_password_hash
from app.services.db_migration.maintenance_auth import (
    MAINTENANCE_TOKEN_AUDIENCE,
    MAINTENANCE_TOKEN_SCOPE,
    MaintenanceAuthService,
    MaintenanceAuthError,
    sqlite_user_reader,
)

PW = "S3cret-maintenance-pw"
TWOFA_HASH_PW = "Another-s3cret-1"


def _make_users_db(path, *, rows=None):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, "
        "two_factor_flag TEXT, two_factor_secret TEXT, is_active BOOLEAN, must_change_password BOOLEAN)"
    )
    for row in rows or [(1, "admin", get_password_hash(PW), None, None, 1, 0)]:
        conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?)", row)
    conn.commit()
    conn.close()
    return str(path)


def _data_version(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA data_version").fetchone()[0]
    finally:
        conn.close()


def _service(tmp_path, rows=None, *, now=None, name="users.db"):
    db = _make_users_db(tmp_path / name, rows=rows)
    return MaintenanceAuthService(
        str(tmp_path), sqlite_user_reader(db), secret_key="unit-secret", now=now
    )


class TestAuthenticate:
    def test_ok_issues_maintenance_token(self, tmp_path):
        svc = _service(tmp_path)
        result = svc.authenticate(username="admin", password=PW, attempt_id="sqlite-to-pg/x" * 0 or None)
        token = result["maintenance_token"]
        payload = pyjwt.decode(
            token, svc._secret, algorithms=["HS256"], audience=MAINTENANCE_TOKEN_AUDIENCE
        )
        assert payload["scope"] == MAINTENANCE_TOKEN_SCOPE
        assert "jti" in payload
        assert "verify_secret" not in payload  # 普通 access 面不可用

    def test_wrong_password_invalid(self, tmp_path):
        svc = _service(tmp_path)
        with pytest.raises(MaintenanceAuthError, match="MAINTENANCE_AUTH_INVALID"):
            svc.authenticate(username="admin", password="wrong")

    def test_totp_flow(self, tmp_path):
        import pyotp

        secret = pyotp.random_base32()
        svc = _service(
            tmp_path,
            rows=[(1, "admin", get_password_hash(PW), "1", secret, 1, 0)],
        )
        with pytest.raises(MaintenanceAuthError, match="TOTP_REQUIRED"):
            svc.authenticate(username="admin", password=PW)
        with pytest.raises(MaintenanceAuthError, match="MAINTENANCE_AUTH_TOTP_INVALID"):
            svc.authenticate(username="admin", password=PW, twofa_code="000000")
        code = pyotp.TOTP(secret).now()
        assert svc.authenticate(username="admin", password=PW, twofa_code=code)

    def test_inactive_and_must_change_rejected(self, tmp_path):
        svc = _service(tmp_path, rows=[(1, "admin", get_password_hash(PW), None, None, 0, 0)])
        with pytest.raises(MaintenanceAuthError, match="ACCOUNT_NOT_ALLOWED"):
            svc.authenticate(username="admin", password=PW)
        svc2 = _service(tmp_path, rows=[(1, "admin", get_password_hash(PW), None, None, 1, 1)], name="users2.db")
        with pytest.raises(MaintenanceAuthError, match="ACCOUNT_NOT_ALLOWED"):
            svc2.authenticate(username="admin", password=PW)

    def test_failure_lockout(self, tmp_path):
        clock = {"t": 1000.0}
        svc = _service(tmp_path, now=lambda: clock["t"])
        for _ in range(5):
            with pytest.raises(MaintenanceAuthError):
                svc.authenticate(username="admin", password="bad")
        with pytest.raises(MaintenanceAuthError, match="MAINTENANCE_AUTH_LOCKED"):
            svc.authenticate(username="admin", password=PW)
        clock["t"] += 901  # 锁定窗口过后恢复
        assert svc.authenticate(username="admin", password=PW)

    def test_no_users_table_offline_recovery(self, tmp_path):
        db = tmp_path / "empty.db"
        sqlite3.connect(str(db)).close()  # 空库无 users 表
        svc = MaintenanceAuthService(str(tmp_path), sqlite_user_reader(str(db)), secret_key="s")
        with pytest.raises(MaintenanceAuthError, match="MAINTENANCE_AUTH_NO_USERS"):
            svc.authenticate(username="admin", password=PW)


class TestToken:
    def _token(self, svc, **kw):
        return svc.authenticate(username="admin", password=PW, **kw)["maintenance_token"]

    def test_verify_ok_and_replay_after_revoke(self, tmp_path):
        svc = _service(tmp_path)
        token = self._token(svc)
        assert svc.verify_token(token)["sub"] == "admin"
        assert svc.revoke(token) is True
        with pytest.raises(MaintenanceAuthError, match="MAINTENANCE_TOKEN_INVALID"):
            svc.verify_token(token)

    def test_expired_rejected(self, tmp_path):
        clock = {"t": 1000.0}
        svc = _service(tmp_path, now=lambda: clock["t"], )
        svc.token_ttl = 1
        token = self._token(svc)
        clock["t"] += 10
        real_now = time.time
        import app.services.db_migration.maintenance_auth as ma

        ma_time = ma.time.time
        ma.time.time = lambda: clock["t"]
        try:
            with pytest.raises(MaintenanceAuthError):
                svc.verify_token(token)
        finally:
            ma.time.time = ma_time
            del real_now

    def test_normal_access_token_rejected_on_maintenance_face(self, tmp_path):
        """普通 access token（无维护 aud/scope/jti）不能过维护校验。"""
        from app.auth.utils import create_access_token

        svc = _service(tmp_path)
        normal = create_access_token({"sub": "admin", "user_id": "1", "verify_secret": "x"})
        with pytest.raises(MaintenanceAuthError):
            svc.verify_token(normal)

    def test_unknown_jti_forged_rejected(self, tmp_path):
        svc = _service(tmp_path)
        forged = pyjwt.encode(
            {
                "sub": "admin",
                "aud": MAINTENANCE_TOKEN_AUDIENCE,
                "scope": MAINTENANCE_TOKEN_SCOPE,
                "jti": "not-issued",
                "exp": int(time.time()) + 600,
            },
            svc._secret,
            algorithm="HS256",
        )
        with pytest.raises(MaintenanceAuthError):
            svc.verify_token(forged)

    def test_renew_rotates_old_jti(self, tmp_path):
        svc = _service(tmp_path)
        old = self._token(svc)
        new = svc.renew(old)
        assert new["maintenance_token"] != old
        with pytest.raises(MaintenanceAuthError):
            svc.verify_token(old)  # 旧 jti 已旋转作废（重放拒）
        assert svc.verify_token(new["maintenance_token"])

    def test_revoke_all(self, tmp_path):
        svc = _service(tmp_path)
        t1 = self._token(svc)
        t2 = self._token(svc)
        assert svc.revoke_all() >= 2
        for t in (t1, t2):
            with pytest.raises(MaintenanceAuthError):
                svc.verify_token(t)

    def test_admin_assertion_via_existing_auth(self, tmp_path):
        svc = _service(tmp_path)
        record = svc.assert_admin_via_existing_auth("admin")
        assert record.username == "admin"
        with pytest.raises(MaintenanceAuthError):
            svc.assert_admin_via_existing_auth("ghost")


class TestZeroSourceWrite:
    def test_auth_attempts_never_touch_source(self, tmp_path):
        db = _make_users_db(tmp_path / "users.db")
        svc = MaintenanceAuthService(str(tmp_path), sqlite_user_reader(db), secret_key="s")
        before = _data_version(db)
        try:
            svc.authenticate(username="admin", password="wrong")
        except MaintenanceAuthError:
            pass
        try:
            svc.authenticate(username="admin", password=PW)
        except MaintenanceAuthError:
            pass
        token = None
        svc2 = MaintenanceAuthService(str(tmp_path), sqlite_user_reader(db), secret_key="s")
        try:
            token = svc2.authenticate(username="admin", password=PW)["maintenance_token"]
        except MaintenanceAuthError:
            pass
        if token:
            svc2.revoke(token)
        assert _data_version(db) == before, "维护认证全程必须零源写（T05）"
