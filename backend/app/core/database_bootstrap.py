# -*- coding: utf-8 -*-
"""早期只读数据库引导（database-migration-ui W1-3，PLANS §4.1/§4.3）。

不依赖 ``app.database`` / ``app.core.config``（引擎与 settings 均在模块加载期
产生副作用）——本模块只做**纯只读解析与状态检测**，供启动分流在 PG 驱动
加载、建引擎、Alembic、seed 之前消费：

1. EffectiveDatabaseConfig：完整有效配置（§4.1）——config.yaml ``database.active``
   存在则**完整覆盖**相应方言配置（含 sqlite_path/TLS，禁止混入另一方言字段）；
   无 active 时保留原 env 行为。active 损坏/不合法 → 抛错 fail-closed，
   **绝不回退 env 或重建默认配置**（复核意见 3）。
2. 平台分流：Android 本机服务发现 PG env 或 PG active → 在驱动加载前明确拒绝
   （§4.3 步骤 1，D6 冻结决策：安卓不支持 PostgreSQL）。
3. 只读状态检测：SQLite 半成品导入标记 / 本地 db-migration control 与
   pending attempt（§4.2 布局）。
4. ``evaluate_startup_disposition``：W1 fail-closed 分流桩——检测到受管
   active/pending/未完成态而核验能力未完备（W3 交付完整 commit/ACK 核验）
   时拒绝普通启动，只给出只读指引。

安全：密码仅经 ``PostgresParams.password`` 存取（repr 排除）；对外摘要一律
``masked_summary()``（无密码/无完整 URL）。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from app.core.database_protocol import (
    ATTEMPTS_DIRNAME,
    CONTROL_FILE,
    DB_MIGRATION_DIR,
    IMPORT_MARKER_TABLE,
    MANIFEST_FILENAME,
    is_valid_attempt_id,
)

DIALECT_SQLITE = "sqlite"
DIALECT_POSTGRESQL = "postgresql"
VALID_DIALECTS = frozenset({DIALECT_SQLITE, DIALECT_POSTGRESQL})

ACTIVE_CONFIG_VERSION = 1
_SSL_MODES = frozenset({"disable", "prefer", "require", "verify-ca", "verify-full"})
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class ManagedConfigError(RuntimeError):
    """受管有效配置（database.active）损坏/不合法——fail-closed，禁止回 env。"""


class ManagedStateError(RuntimeError):
    """本地受管状态文件（control/manifest）损坏——fail-closed，禁止默认化。"""


class PlatformDatabaseUnsupportedError(RuntimeError):
    """当前平台不支持所选数据库方言（如 Android 本机服务 × PostgreSQL）。"""


def _require_str(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManagedConfigError(f"database.active.{what} 必须为非空字符串（当前: {value!r}）")
    return value


def _require_uuid(value: Any, what: str) -> str:
    text = _require_str(value, what)
    if not _UUID_RE.fullmatch(text):
        raise ManagedConfigError(f"database.active.{what} 必须为 UUID（当前: {text!r}）")
    return text


@dataclass(frozen=True)
class PostgresParams:
    """结构化 PG 目标参数（§4.1；URL 构造统一走 URL.create，见 target_params）。"""

    host: str
    port: int
    user: str
    password: str = field(repr=False)  # 绝不进 repr/日志
    database: str
    schema: str = "public"
    sslmode: str = "prefer"
    ssl_root_cert: Optional[str] = None
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

    def __post_init__(self) -> None:
        if self.sslmode not in _SSL_MODES:
            raise ManagedConfigError(f"database.active.postgresql.sslmode 非法: {self.sslmode!r}")
        if self.sslmode in ("verify-ca", "verify-full") and not self.ssl_root_cert:
            raise ManagedConfigError(f"sslmode={self.sslmode} 需要 ssl_root_cert 指向 CA 证书路径")
        if not (1 <= int(self.port) <= 65535):
            raise ManagedConfigError(f"port 越界: {self.port}")
        if int(self.pool_size) < 1 or int(self.max_overflow) < 0 or int(self.pool_timeout) < 1:
            raise ManagedConfigError("连接池参数非法（pool_size>=1 / max_overflow>=0 / pool_timeout>=1）")

    def masked(self) -> Dict[str, Any]:
        """脱敏摘要（状态接口/日志专用；无密码）。"""
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "database": self.database,
            "schema": self.schema,
            "sslmode": self.sslmode,
            "sslRootCert": self.ssl_root_cert,
            "poolSize": self.pool_size,
            "maxOverflow": self.max_overflow,
            "poolTimeout": self.pool_timeout,
        }


@dataclass(frozen=True)
class EffectiveDatabaseConfig:
    """完整有效配置（§4.1）：active（受管）优先并完整覆盖；否则 env 回退。"""

    source: str  # "active" | "env"
    dialect: str
    sqlite_path: Optional[str]
    pg: Optional[PostgresParams]
    generation: Optional[str] = None
    expected_database_id: Optional[str] = None
    receipt_attempt_id: Optional[str] = None
    revision_at_import: Optional[str] = None
    switched_at: Optional[str] = None
    switched_by: Optional[str] = None

    def masked_summary(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "dialect": self.dialect,
            "sqlitePath": self.sqlite_path,
            "postgresql": self.pg.masked() if self.pg is not None else None,
            "generation": self.generation,
            "expectedDatabaseId": self.expected_database_id,
            "receiptAttemptId": self.receipt_attempt_id,
            "revisionAtImport": self.revision_at_import,
        }


def _active_pg_params(section: Mapping[str, Any]) -> PostgresParams:
    if not isinstance(section, Mapping):
        raise ManagedConfigError("database.active.postgresql 必须为映射节")
    return PostgresParams(
        host=_require_str(section.get("host"), "postgresql.host"),
        port=int(section.get("port", 5432)),
        user=_require_str(section.get("user"), "postgresql.user"),
        password=str(section.get("password", "") or ""),
        database=_require_str(section.get("database"), "postgresql.database"),
        schema=str(section.get("schema", "public") or "public"),
        sslmode=str(section.get("sslmode", "prefer") or "prefer"),
        ssl_root_cert=section.get("ssl_root_cert"),
        pool_size=int(section.get("pool_size", 10)),
        max_overflow=int(section.get("max_overflow", 20)),
        pool_timeout=int(section.get("pool_timeout", 30)),
    )


def load_active_config(config_path: os.PathLike[str] | str) -> Optional[Dict[str, Any]]:
    """只读解析 config.yaml 的 ``database.active``；缺失返回 None；损坏抛错（不回 env）。"""
    path = Path(config_path)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ManagedConfigError(f"config.yaml 解析失败（受管配置损坏，拒绝默认化）: {exc}") from exc
    database = data.get("database")
    if not isinstance(database, Mapping) or "active" not in database:
        return None
    active = database.get("active")
    if not isinstance(active, Mapping):
        raise ManagedConfigError("database.active 存在但不是映射——受管配置损坏，拒绝回退 env")
    return dict(active)


def _config_from_active(active: Mapping[str, Any]) -> EffectiveDatabaseConfig:
    """受管 active → EffectiveDatabaseConfig（严格校验，任一字段不合法即抛错）。"""
    if active.get("version") != ACTIVE_CONFIG_VERSION:
        raise ManagedConfigError(
            f"database.active.version 必须为 {ACTIVE_CONFIG_VERSION}（当前: {active.get('version')!r}）"
        )
    dialect = active.get("dialect")
    if dialect not in VALID_DIALECTS:
        raise ManagedConfigError(f"database.active.dialect 必须为 sqlite/postgresql（当前: {dialect!r}）")
    generation = _require_uuid(active.get("generation"), "generation")
    expected_database_id = _require_uuid(active.get("expected_database_id"), "expected_database_id")
    receipt_attempt_id = _require_str(active.get("receipt_attempt_id"), "receipt_attempt_id")
    if not is_valid_attempt_id(receipt_attempt_id):
        raise ManagedConfigError(f"database.active.receipt_attempt_id 形态非法: {receipt_attempt_id!r}")
    revision_at_import = _require_str(active.get("revision_at_import"), "revision_at_import")

    if dialect == DIALECT_SQLITE:
        pg_section = active.get("postgresql")
        if pg_section:
            raise ManagedConfigError("dialect=sqlite 时禁止混入 postgresql 节（§4.1 方言互斥）")
        raw_path = _require_str(active.get("sqlite_path"), "sqlite_path")
        if not os.path.isabs(raw_path):
            raise ManagedConfigError(f"sqlite_path 必须为已验证的绝对路径（当前: {raw_path!r}）")
        return EffectiveDatabaseConfig(
            source="active",
            dialect=DIALECT_SQLITE,
            sqlite_path=raw_path,
            pg=None,
            generation=generation,
            expected_database_id=expected_database_id,
            receipt_attempt_id=receipt_attempt_id,
            revision_at_import=revision_at_import,
            switched_at=active.get("switched_at"),
            switched_by=active.get("switched_by"),
        )

    if active.get("sqlite_path"):
        raise ManagedConfigError("dialect=postgresql 时禁止混入 sqlite_path（§4.1 方言互斥）")
    return EffectiveDatabaseConfig(
        source="active",
        dialect=DIALECT_POSTGRESQL,
        sqlite_path=None,
        pg=_active_pg_params(active.get("postgresql") or {}),
        generation=generation,
        expected_database_id=expected_database_id,
        receipt_attempt_id=receipt_attempt_id,
        revision_at_import=revision_at_import,
        switched_at=active.get("switched_at"),
        switched_by=active.get("switched_by"),
    )


def _config_from_env(environ: Mapping[str, str]) -> EffectiveDatabaseConfig:
    """env 回退：与 settings/startup_guard 同源的方言判定与默认值（§2.1 契约）。"""
    raw = (environ.get("DB_TYPE") or "sqlite").strip().lower()
    dialect = "postgresql" if raw in ("postgres", "pg") else raw
    if dialect not in VALID_DIALECTS:
        raise ManagedConfigError(f"DB_TYPE 配置非法: {raw!r}（仅支持 sqlite / postgresql），拒绝静默回落")
    if dialect == DIALECT_POSTGRESQL:
        sslmode = (environ.get("DB_SSLMODE") or "prefer").strip().lower()
        if sslmode not in _SSL_MODES:
            raise ManagedConfigError(f"DB_SSLMODE 配置非法: {sslmode!r}")
        ssl_root_cert = environ.get("DB_SSL_ROOT_CERT") or None
        if sslmode in ("verify-ca", "verify-full") and not ssl_root_cert:
            raise ManagedConfigError(f"DB_SSLMODE={sslmode} 需要 DB_SSL_ROOT_CERT")
        pg = PostgresParams(
            host=environ.get("DB_HOST", "localhost"),
            port=int(environ.get("DB_PORT", "5432")),
            user=environ.get("DB_USER", "btdeck"),
            password=environ.get("DB_PASSWORD", ""),
            database=environ.get("DB_NAME", "btdeck"),
            sslmode=sslmode,
            ssl_root_cert=ssl_root_cert,
            pool_size=int(environ.get("DB_POOL_SIZE", "10")),
            max_overflow=int(environ.get("DB_MAX_OVERFLOW", "20")),
            pool_timeout=int(environ.get("DB_POOL_TIMEOUT", "30")),
        )
        return EffectiveDatabaseConfig(source="env", dialect=DIALECT_POSTGRESQL, sqlite_path=None, pg=pg)
    sqlite_path = environ.get("DATABASE_PATH") or None
    return EffectiveDatabaseConfig(source="env", dialect=DIALECT_SQLITE, sqlite_path=sqlite_path, pg=None)


def resolve_effective_database_config(
    config_path: os.PathLike[str] | str | None = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> EffectiveDatabaseConfig:
    """解析完整有效配置：active 存在 → 严格解析并完整覆盖；否则 env 回退（§4.1）。"""
    if config_path is None:
        # 与 settings.CONFIG_PATH 同源语义的最小镜像（不能 import config：避免
        # settings 实例化副作用）；生产路径应由调用方显式传入
        config_dir = os.getenv("CONFIG_DIR") or str(Path(__file__).resolve().parents[2] / "config")
        config_path = str(Path(config_dir) / "config.yaml")
    active = load_active_config(config_path)
    if active is not None:
        return _config_from_active(active)
    return _config_from_env(environ if environ is not None else os.environ)


# =============================================================================
# 平台分流（§4.3 步骤 1：安卓拒 PG 发生在驱动加载与建引擎之前）
# =============================================================================


def assert_platform_database_support(effective: EffectiveDatabaseConfig, *, platform: Optional[str] = None) -> None:
    """Android 本机服务 × PostgreSQL（env 或 active 均算）→ 立即拒绝。

    调用时机：bootstrap 早期，先于 PG 驱动 import 与任何引擎构造。
    """
    if effective.dialect != DIALECT_POSTGRESQL:
        return
    if platform is None:
        from app.core.platform_capabilities import resolve_platform

        platform = resolve_platform()
    # 与 platform_capabilities.PLATFORM_ANDROID_SERVER 同值（避免为字面量再拉一层导入）
    if platform == "android-server":
        raise PlatformDatabaseUnsupportedError(
            "Android 本机服务不支持 PostgreSQL（冻结决策 D6）：检测到 PG 配置"
            f"（来源: {effective.source}），在加载驱动之前拒绝启动；"
            "安卓伴侣的数据库能力由所连接服务端报告"
        )


# =============================================================================
# 只读状态检测（§4.2 布局 / SQLite 半成品标记）
# =============================================================================


def _sqlite_ro_connect(db_path: os.PathLike[str] | str) -> sqlite3.Connection:
    """只读 URI 连接（绝不隐式创建空库；文件缺失由调用方先判存在）。"""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def sqlite_has_import_marker(db_path: os.PathLike[str] | str) -> bool:
    """SQLite 文件是否存在未完成导入标记表（pg_to_sqlite 半成品检测）。"""
    if not Path(db_path).exists():
        return False
    conn = _sqlite_ro_connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (IMPORT_MARKER_TABLE,)
        ).fetchone()
        return row is not None
    except sqlite3.DatabaseError:
        # 文件存在但非 SQLite 库（损坏/半写入）：fail-closed 视为可疑，交由上层处置
        return True
    finally:
        conn.close()


def db_migration_dir(config_dir: os.PathLike[str] | str) -> Path:
    return Path(config_dir) / DB_MIGRATION_DIR


def read_control(config_dir: os.PathLike[str] | str) -> Optional[Dict[str, Any]]:
    """只读 control.json；缺失返回 None；存在但损坏 → 抛错（禁止默认化）。"""
    path = db_migration_dir(config_dir) / CONTROL_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManagedStateError(f"{path} 解析失败（受管状态损坏，拒绝默认化）: {exc}") from exc
    if not isinstance(data, dict):
        raise ManagedStateError(f"{path} 必须为 JSON 对象")
    return data


def pending_attempt_from_control(control: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not control:
        return None
    value = control.get("pending_attempt")
    if value is None:
        return None
    if not isinstance(value, str) or not is_valid_attempt_id(value):
        raise ManagedStateError(f"control.pending_attempt 形态非法: {value!r}")
    return value


def list_attempt_ids(config_dir: os.PathLike[str] | str, *, limit: int = 256) -> list[str]:
    """列出 attempts/ 下存在 manifest 的完整 attempt_id（有界；目录名仅含安全 UUID）。

    磁盘布局（§4.2）：``attempts/<uuid 尾段>/manifest.json``——不把带 ``/`` 的
    attempt_id 直接当路径；完整 attempt_id 以 manifest 内声明为准。
    """
    attempts = db_migration_dir(config_dir) / ATTEMPTS_DIRNAME
    if not attempts.is_dir():
        return []
    result = []
    for child in sorted(attempts.iterdir())[:limit]:
        if not (child.is_dir() and _UUID_RE.fullmatch(child.name)):
            continue
        manifest_path = child / MANIFEST_FILENAME
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ManagedStateError(f"{manifest_path} 解析失败（受管状态损坏）")
        attempt_id = data.get("attempt_id") if isinstance(data, dict) else None
        if isinstance(attempt_id, str) and is_valid_attempt_id(attempt_id):
            result.append(attempt_id)
    return result


def read_manifest(config_dir: os.PathLike[str] | str, attempt_id: str) -> Dict[str, Any]:
    """只读指定 attempt 的 manifest.json（形态校验 + UUID 尾段目录映射防穿越）。"""
    if not is_valid_attempt_id(attempt_id):
        raise ManagedStateError(f"attempt_id 形态非法（拒绝路径映射）: {attempt_id!r}")
    path = db_migration_dir(config_dir) / ATTEMPTS_DIRNAME / attempt_id.rsplit("/", 1)[1] / MANIFEST_FILENAME
    if not path.exists():
        raise ManagedStateError(f"manifest 不存在: {attempt_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManagedStateError(f"{path} 解析失败（受管状态损坏）: {exc}") from exc
    if not isinstance(data, dict):
        raise ManagedStateError(f"{path} 必须为 JSON 对象")
    if data.get("attempt_id") != attempt_id:
        raise ManagedStateError(f"{path} 声明的 attempt_id 与请求不一致（{data.get('attempt_id')!r}）")
    return data


# =============================================================================
# W1 fail-closed 启动分流桩（复核意见 3：核验不完备即拒绝，且先于 seed/修复）
# ==============================================================================

DISPOSITION_NORMAL = "normal"
DISPOSITION_FAIL_CLOSED = "fail_closed"

REASON_ACTIVE_CONFIG_UNVERIFIED = "ACTIVE_CONFIG_UNVERIFIED"
REASON_PENDING_ATTEMPT_PRESENT = "PENDING_ATTEMPT_PRESENT"
REASON_IMPORT_MARKER_PRESENT = "IMPORT_MARKER_PRESENT"


@dataclass(frozen=True)
class StartupDisposition:
    mode: str
    reason_code: str
    detail: str

    @property
    def normal(self) -> bool:
        return self.mode == DISPOSITION_NORMAL


REASON_ACTIVATION_COMPLETE = "ACTIVATION_COMPLETE"
REASON_ACTIVATION_PENDING_RESTART = "ACTIVATION_PENDING_RESTART"


def evaluate_startup_disposition(
    effective: EffectiveDatabaseConfig,
    *,
    control: Optional[Mapping[str, Any]] = None,
    pending_attempt: Optional[str] = None,
    sqlite_marker_present: bool = False,
    pending_commit_phase: Optional[str] = None,
) -> StartupDisposition:
    """fail-closed 分流：受管态存在而核验未完备 → 拒绝普通启动（只读指引）。

    - active × 双 ACK 完成（pending attempt commit_phase=ACTIVATED_ACK）：
      **正常启动**（§4.4：合法旧 revision 是升级输入，交 migrate_database
      升至新 head；W3 移除 W1"active 一律未核验"桩；全量摘要复核归 W5/W6）；
    - active × 未完成激活（含 COMMITTED 待重启/待 ACK）→ fail-closed 维护；
    - control/pending attempt：存在未完成受管切换 → fail-closed；
    - SQLite 导入标记：pg_to_sqlite 半成品 → fail-closed（PG 侧标记由
      migration.py 既有逻辑拒启，语义一致）。

    fail-closed 不等于失败：调用方（W1-4 接线/W2 维护分支）据此进入只读
    恢复路径，绝不在本判断后继续 seed/修复/后台任务。
    """
    if effective.source == "active":
        if pending_attempt is not None and pending_commit_phase == "ACTIVATED_ACK":
            # 双 ACK 完成的激活：身份/凭据已在 ACK 事务内核验；正常升级路径
            return StartupDisposition(DISPOSITION_NORMAL, REASON_ACTIVATION_COMPLETE, "")
        if pending_attempt is not None and pending_commit_phase == "COMMITTED":
            return StartupDisposition(
                DISPOSITION_FAIL_CLOSED,
                REASON_ACTIVATION_PENDING_RESTART,
                "存在已提交（COMMITTED）未完成 ACK 的切换：进入维护分支幂等 redo"
                "（完成配置发布与目标 ACK）后重启/继续。",
            )
        return StartupDisposition(
            DISPOSITION_FAIL_CLOSED,
            REASON_ACTIVE_CONFIG_UNVERIFIED,
            "存在受管有效配置 database.active，且激活核验未完备（无 ACTIVATED_ACK "
            "凭据）：拒绝普通启动以防未核实切换；请经迁移控制面完成激活或恢复。",
        )
    if pending_attempt is not None:
        return StartupDisposition(
            DISPOSITION_FAIL_CLOSED,
            REASON_PENDING_ATTEMPT_PRESENT,
            f"检测到未完成受管切换 attempt（{pending_attempt}）：拒绝普通启动，"
            "进入只读恢复；请用迁移控制面恢复或显式放弃后重启。",
        )
    if sqlite_marker_present:
        return StartupDisposition(
            DISPOSITION_FAIL_CLOSED,
            REASON_IMPORT_MARKER_PRESENT,
            "SQLite 库存在未完成导入标记（pg→sqlite 半成品）：拒绝普通启动"
            "以防 seed/后台任务修改半成品数据；请重跑迁移或显式放弃。",
        )
    return StartupDisposition(DISPOSITION_NORMAL, "", "")
