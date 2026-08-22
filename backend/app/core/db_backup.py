# -*- coding: utf-8 -*-
"""
数据库迁移前备份工具

在 migrate_database() 执行 alembic upgrade 前，备份当前 app.db，
用于版本回滚（Level 2 备份还原策略，见 docs/operations/rollback-guide.md）。

设计要点：
- 用 PRAGMA wal_checkpoint(TRUNCATE) + shutil.copy2，而非 sqlite3.backup()。
  迁移发生在启动初期单进程，无并发连接，checkpoint+cp 与 backup() 同样可靠但更简单。
- 备份必须通过完整性、版本和摘要验证；失败时阻止迁移。
- 保留最近 N 份，超出自动清理最旧的，避免磁盘膨胀。
"""

import logging
import hashlib
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 备份保留份数
BACKUP_KEEP = 3
_BACKUP_TIMESTAMP_PATTERN = re.compile(r"^\d{8}-\d{6}(?:-\d{1,6})?$")


class MigrationBackupError(RuntimeError):
    """Raised when a required pre-migration backup cannot be trusted."""


def _read_backup_version(conn: sqlite3.Connection) -> Optional[str]:
    has_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
    if not has_table:
        return None
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return str(row[0]) if row else None


def list_pre_migration_backups(db_path: str) -> list[Path]:
    """List primary backup files without counting SQLite WAL/SHM sidecars."""
    database = Path(db_path)
    prefix = f"{database.name}.pre-migration-"
    backups = []
    for candidate in database.parent.glob(f"{prefix}*"):
        if not candidate.is_file():
            continue
        timestamp = candidate.name[len(prefix) :]
        if _BACKUP_TIMESTAMP_PATTERN.fullmatch(timestamp):
            backups.append(candidate)
    return sorted(backups, key=lambda path: path.name, reverse=True)


def validate_sqlite_backup(backup_path: str, *, expected_version: Optional[str]) -> dict:
    """Validate that a copied database is readable, complete and identifiable."""
    path = Path(backup_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise MigrationBackupError(f"backup is missing or empty: {path}")

    # immutable=1 guarantees validation cannot create/modify -wal/-shm sidecars.
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        integrity_rows = [str(row[0]) for row in conn.execute("PRAGMA integrity_check").fetchall()]
        if integrity_rows != ["ok"]:
            raise MigrationBackupError(f"backup integrity_check failed: {integrity_rows[:5]}")
        actual_version = _read_backup_version(conn)
    finally:
        conn.close()

    if actual_version != expected_version:
        raise MigrationBackupError(
            "backup alembic version mismatch: " f"expected={expected_version!r}, actual={actual_version!r}"
        )

    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "version": actual_version,
    }


def backup_before_migration(db_path: str) -> Optional[str]:
    """
    迁移前备份数据库。

    用 PRAGMA wal_checkpoint(TRUNCATE) 强制刷盘 WAL 日志，再 shutil.copy2 复制。
    已存在数据库的备份失败会抛出 MigrationBackupError，阻止迁移继续。

    Args:
        db_path: 数据库文件路径

    Returns:
        备份文件路径；数据库尚不存在时返回 None
    """
    try:
        if not Path(db_path).exists():
            return None

        source_conn = sqlite3.connect(db_path)
        try:
            expected_version = _read_backup_version(source_conn)
        finally:
            source_conn.close()

        # 强制 WAL 刷盘，确保 -wal 日志合并进主库后再复制
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()

        # 使用完整微秒，避免快速连续备份互相覆盖。
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = f"{db_path}.pre-migration-{ts}"
        shutil.copy2(db_path, backup_path)

        metadata = validate_sqlite_backup(backup_path, expected_version=expected_version)
        prune_old_backups(db_path, keep=BACKUP_KEEP)

        logger.info(
            "迁移前数据库备份已验证: path=%s size=%s sha256=%s version=%s",
            metadata["path"],
            metadata["size"],
            metadata["sha256"],
            metadata["version"],
        )
        return backup_path

    except Exception as e:
        logger.error("迁移前备份失败，已阻止迁移: %s", e)
        if isinstance(e, MigrationBackupError):
            raise
        raise MigrationBackupError(f"pre-migration backup failed: {e}") from e


def prune_old_backups(db_path: str, keep: int = BACKUP_KEEP) -> int:
    """
    清理旧备份，只保留最近 keep 份。

    Args:
        db_path: 数据库文件路径（用于推导备份文件名前缀）
        keep: 保留份数

    Returns:
        清理掉的备份数量
    """
    try:
        backups = list_pre_migration_backups(db_path)
        removed = 0
        for old in backups[keep:]:
            try:
                old.unlink()
                removed += 1
            except OSError:
                pass
        return removed
    except Exception:
        return 0
