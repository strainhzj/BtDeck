# -*- coding: utf-8 -*-
"""维护认证与本地受保护状态（database-migration-ui W2-5，PLANS §5.3/§11 T05）。

维护模式的独立认证面——**不走普通 login/refresh 路径**（那些会写 LoginLog、
做密码格式自动升级、写 refresh token 行，全部违反维护期源零写铁律）：

- 账户/密码/TOTP 校验复用既有纯函数（``verify_password``/``verify_totp``），
  但用户行经**只读连接**读取（SQLite ``mode=ro`` / PG 会话级
  ``default_transaction_read_only=on``），校验成功/失败**均零源写**；
- 签发**独立 audience/scope 的短期维护 token**（默认 15 分钟）：绑定
  attempt/epoch/deployment，含 jti；普通业务 API 的 ``verify_access_token``
  要求 ``verify_secret`` 字段——维护 token 不携带，普通端点天然拒绝；
  维护端点校验 aud/scope/jti/吊销，普通 access token 无维护 aud 同样拒绝；
- 失败限流/会话撤销/重放防护落**本地受保护状态文件**（0600 RMW + 文件锁）；
  唯一 jti 有效（旧 jti 重放即拒）；
- ``start`` 前的"实际管理员"检查：不能把 require_authenticated_user 的
  "有 token"当管理员——必须回查库内用户行（存在 + is_active + 非强制改密）；
- 缺 seed（无 users 表/无行，T06）→ 认证不可用，提示离线恢复（不绕过鉴权）。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import jwt

from app.core.database_protocol import DB_MIGRATION_DIR

MAINTENANCE_TOKEN_AUDIENCE = "btdeck-maintenance"
MAINTENANCE_TOKEN_SCOPE = "maintenance"
MAINTENANCE_TOKEN_TTL_SECONDS = 15 * 60
MAINTENANCE_TOKEN_ALGORITHM = "HS256"

AUTH_STATE_FILENAME = "maintenance-auth-state.json"

FAIL_WINDOW_SECONDS = 300
FAIL_LIMIT = 5
LOCKOUT_SECONDS = 900


class MaintenanceAuthError(RuntimeError):
    """维护认证失败（reason_code 稳定字符串，endpoint 译 CommonResponse）。"""


REASON_INVALID_CREDENTIALS = "MAINTENANCE_AUTH_INVALID"
REASON_TOTP_REQUIRED = "MAINTENANCE_AUTH_TOTP_REQUIRED"
REASON_TOTP_INVALID = "MAINTENANCE_AUTH_TOTP_INVALID"
REASON_LOCKED = "MAINTENANCE_AUTH_LOCKED"
REASON_ACCOUNT_NOT_ALLOWED = "MAINTENANCE_AUTH_ACCOUNT_NOT_ALLOWED"
REASON_TOKEN_INVALID = "MAINTENANCE_TOKEN_INVALID"
REASON_NO_USERS = "MAINTENANCE_AUTH_NO_USERS"  # 缺 seed：转离线恢复，不绕过鉴权


@dataclass(frozen=True)
class MaintenanceUserRecord:
    """只读用户行快照（认证最小字段面；不外泄）。"""

    id: int
    username: str
    password_hash: str
    two_factor_flag: Optional[str]
    two_factor_secret: Optional[str]
    is_active: Optional[bool]
    must_change_password: bool


# ---------------------------------------------------------------------------
# 只读用户读取器（SQLite / PG）
# ---------------------------------------------------------------------------


def sqlite_user_reader(sqlite_path: str) -> Callable[[str], Optional[MaintenanceUserRecord]]:
    import sqlite3

    def _read(username: str) -> Optional[MaintenanceUserRecord]:
        conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        try:
            try:
                row = conn.execute(
                    "SELECT id, username, password, two_factor_flag, two_factor_secret, is_active, "
                    "must_change_password FROM users WHERE username = ?",
                    (username,),
                ).fetchone()
            except sqlite3.OperationalError:
                raise MaintenanceAuthError(REASON_NO_USERS)  # 缺 seed：无 users 表
        finally:
            conn.close()
        return _row_to_record(row)

    return _read


def pg_user_reader(pg_url: str) -> Callable[[str], Optional[MaintenanceUserRecord]]:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    engine = create_engine(pg_url, poolclass=NullPool)

    def _read(username: str) -> Optional[MaintenanceUserRecord]:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET default_transaction_read_only = on")
            try:
                row = conn.execute(
                    text(
                        "SELECT id, username, password, two_factor_flag, two_factor_secret, is_active, "
                        "must_change_password FROM users WHERE username = :u"
                    ),
                    {"u": username},
                ).fetchone()
            except Exception as exc:
                if "users" in str(exc).lower() or "undefinedtable" in str(exc).lower().replace(" ", ""):
                    raise MaintenanceAuthError(REASON_NO_USERS) from exc
                raise
        return _row_to_record(tuple(row) if row is not None else None)

    return _read


def _row_to_record(row: Optional[tuple]) -> Optional[MaintenanceUserRecord]:
    if row is None:
        return None
    return MaintenanceUserRecord(
        id=int(row[0]),
        username=str(row[1]),
        password_hash=str(row[2] or ""),
        two_factor_flag=row[3],
        two_factor_secret=row[4],
        is_active=(bool(row[5]) if row[5] is not None else None),
        must_change_password=bool(row[6] or False),
    )


# ---------------------------------------------------------------------------
# 本地受保护状态（失败限流/签发注册/吊销）
# ---------------------------------------------------------------------------


class _AuthStateFile:
    """0600 原子 RMW + 文件锁（fcntl 可用时跨进程，否则进程内锁兜底）。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._thread_lock = threading.Lock()
        self._file_lock_path = path.with_suffix(".lock")

    @contextlib.contextmanager
    def _locked(self):
        import fcntl

        self._thread_lock.acquire()
        fh = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(self._file_lock_path, "a+")
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if fh is not None:
                with contextlib.suppress(OSError):
                    import fcntl as _f

                    _f.flock(fh.fileno(), _f.LOCK_UN)
                fh.close()
            self._thread_lock.release()

    def load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {"fail_counts": {}, "locked_until": {}, "issued": {}}
        if not isinstance(data, dict):
            return {"fail_counts": {}, "locked_until": {}, "issued": {}}
        data.setdefault("fail_counts", {})
        data.setdefault("locked_until", {})
        data.setdefault("issued", {})
        return data

    def save(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.{uuid.uuid4().hex[:8]}.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)

    def update(self, mutator: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
        with self._locked():
            data = self.load()
            mutator(data)
            self.save(data)
            return data


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------


class MaintenanceAuthService:
    """维护认证：密码/TOTP 只读校验 + 独立短 token 签发/续期/吊销 + 限流。"""

    def __init__(
        self,
        config_dir: os.PathLike[str] | str,
        user_reader: Callable[[str], Optional[MaintenanceUserRecord]],
        *,
        secret_key: str,
        token_ttl: int = MAINTENANCE_TOKEN_TTL_SECONDS,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self._state = _AuthStateFile(Path(config_dir) / DB_MIGRATION_DIR / AUTH_STATE_FILENAME)
        self._user_reader = user_reader
        self._secret = hashlib.sha256((str(secret_key) + ":maintenance-v1").encode("utf-8")).hexdigest()
        self._ttl = int(token_ttl)
        self._now = now or time.time

    # ------------------------------------------------------------------
    # 登录（零源写）
    # ------------------------------------------------------------------

    def authenticate(
        self,
        *,
        username: str,
        password: str,
        twofa_code: Optional[str] = None,
        attempt_id: Optional[str] = None,
        epoch: Optional[str] = None,
        deployment_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """校验账户并签发维护 token；所有失败路径零源写（T05）。"""
        if not username or not password:
            raise MaintenanceAuthError(REASON_INVALID_CREDENTIALS)
        if self._is_locked(username):
            raise MaintenanceAuthError(REASON_LOCKED)

        record = self._user_reader(username)
        from app.auth.security import verify_password

        ok = record is not None and verify_password(password, record.password_hash)
        if not ok:
            self._record_failure(username)
            raise MaintenanceAuthError(REASON_INVALID_CREDENTIALS)

        assert record is not None
        if record.is_active is False:
            raise MaintenanceAuthError(REASON_ACCOUNT_NOT_ALLOWED)  # 停用账户不签发
        if record.must_change_password:
            raise MaintenanceAuthError(REASON_ACCOUNT_NOT_ALLOWED)  # 强制改密限制（§5.3）
        if (record.two_factor_flag or "") == "1":
            from app.auth.utils import verify_totp

            if not twofa_code:
                raise MaintenanceAuthError(REASON_TOTP_REQUIRED)
            if not verify_totp(record.two_factor_secret, twofa_code):
                self._record_failure(username)
                raise MaintenanceAuthError(REASON_TOTP_INVALID)

        self._clear_failures(username)
        return self._issue(record, attempt_id=attempt_id, epoch=epoch, deployment_id=deployment_id)

    # ------------------------------------------------------------------
    # token 签发/校验/续期/吊销
    # ------------------------------------------------------------------

    def _issue(
        self,
        record: MaintenanceUserRecord,
        *,
        attempt_id: Optional[str],
        epoch: Optional[str],
        deployment_id: Optional[str],
    ) -> Dict[str, Any]:
        now = self._now()
        jti = uuid.uuid4().hex
        payload = {
            "sub": record.username,
            "user_id": str(record.id),
            "aud": MAINTENANCE_TOKEN_AUDIENCE,
            "scope": MAINTENANCE_TOKEN_SCOPE,
            "attempt_id": attempt_id,
            "epoch": epoch,
            "deployment_id": deployment_id,
            "jti": jti,
            "iat": int(now),
            "exp": int(now) + self._ttl,
        }
        token = jwt.encode(payload, self._secret, algorithm=MAINTENANCE_TOKEN_ALGORITHM)
        self._state.update(
            lambda data: data["issued"].update({jti: {"username": record.username, "exp": payload["exp"]}})
        )
        return {
            "maintenance_token": token,
            "token_type": "bearer",
            "expires_in": self._ttl,
            "username": record.username,
        }

    def verify_token(self, token: str) -> Dict[str, Any]:
        """校验维护 token（aud/scope/exp/jti 注册且未吊销；重放即拒）。"""
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[MAINTENANCE_TOKEN_ALGORITHM],
                audience=MAINTENANCE_TOKEN_AUDIENCE,
                options={"require": ["exp", "sub", "jti", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise MaintenanceAuthError(REASON_TOKEN_INVALID) from exc
        if payload.get("scope") != MAINTENANCE_TOKEN_SCOPE:
            raise MaintenanceAuthError(REASON_TOKEN_INVALID)
        jti = payload.get("jti")
        data = self._state.load()
        entry = data["issued"].get(jti) if isinstance(jti, str) else None
        if not isinstance(entry, dict) or entry.get("revoked"):
            raise MaintenanceAuthError(REASON_TOKEN_INVALID)  # 未知 jti/已吊销：重放或伪造
        return payload

    def renew(self, token: str, *, attempt_id: Optional[str] = None, epoch: Optional[str] = None) -> Dict[str, Any]:
        """续期：旧 jti 旋转作废 + 重读用户行复核（账户被停用/强制改密即拒）。"""
        payload = self.verify_token(token)
        record = self._user_reader(str(payload["sub"]))
        if record is None or record.is_active is False or record.must_change_password:
            raise MaintenanceAuthError(REASON_ACCOUNT_NOT_ALLOWED)

        def _mutate(data: Dict[str, Any]) -> None:
            old = data["issued"].get(str(payload.get("jti")))
            if isinstance(old, dict):
                old["revoked"] = True

        self._state.update(_mutate)
        return self._issue(
            record,
            attempt_id=attempt_id or payload.get("attempt_id"),
            epoch=epoch or payload.get("epoch"),
            deployment_id=payload.get("deployment_id"),
        )

    def revoke(self, token: str) -> bool:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[MAINTENANCE_TOKEN_ALGORITHM],
                audience=MAINTENANCE_TOKEN_AUDIENCE,
                options={"verify_exp": False},
            )
        except jwt.PyJWTError:
            return False
        jti = str(payload.get("jti"))

        def _mutate(data: Dict[str, Any]) -> None:
            entry = data["issued"].get(jti)
            if isinstance(entry, dict):
                entry["revoked"] = True

        self._state.update(_mutate)
        return True

    def revoke_all(self) -> int:
        """会话撤销（维护退出/放弃时全量作废）。"""

        def _mutate(data: Dict[str, Any]) -> None:
            for entry in data["issued"].values():
                if isinstance(entry, dict):
                    entry["revoked"] = True

        data = self._state.update(_mutate)
        return sum(1 for e in data["issued"].values() if isinstance(e, dict) and e.get("revoked"))

    # ------------------------------------------------------------------
    # "实际管理员"检查（§5.3：有 token ≠ 管理员；回查库内用户行）
    # ------------------------------------------------------------------

    def assert_admin_via_existing_auth(self, username: str) -> MaintenanceUserRecord:
        """W3 start 端点前置：现有认证用户必须库内存在、启用、非强制改密。"""
        record = self._user_reader(username)
        if record is None:
            raise MaintenanceAuthError(REASON_ACCOUNT_NOT_ALLOWED)
        if record.is_active is False:
            raise MaintenanceAuthError(REASON_ACCOUNT_NOT_ALLOWED)
        if record.must_change_password:
            raise MaintenanceAuthError(REASON_ACCOUNT_NOT_ALLOWED)
        return record

    # ------------------------------------------------------------------
    # 限流（本地状态；缺 seed 之外绝不写源库）
    # ------------------------------------------------------------------

    def _is_locked(self, username: str) -> bool:
        data = self._state.load()
        until = data["locked_until"].get(username, 0)
        return float(until) > self._now()

    def _record_failure(self, username: str) -> None:
        now = self._now()

        def _mutate(data: Dict[str, Any]) -> None:
            window = data.setdefault("fail_window", {})
            first = float(window.get(username, 0))
            if now - first > FAIL_WINDOW_SECONDS:
                window[username] = now
                data["fail_counts"][username] = 0
            data["fail_counts"][username] = int(data["fail_counts"].get(username, 0)) + 1
            if data["fail_counts"][username] >= FAIL_LIMIT:
                data["locked_until"][username] = now + LOCKOUT_SECONDS
                data["fail_counts"][username] = 0

        self._state.update(_mutate)

    def _clear_failures(self, username: str) -> None:
        def _mutate(data: Dict[str, Any]) -> None:
            data["fail_counts"].pop(username, None)
            data["locked_until"].pop(username, None)
            data.get("fail_window", {}).pop(username, None)

        self._state.update(_mutate)
