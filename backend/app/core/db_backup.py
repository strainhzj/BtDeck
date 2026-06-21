# -*- coding: utf-8 -*-
"""
数据库迁移前备份工具

在 migrate_database() 执行 alembic upgrade 前，备份当前 app.db，
用于版本回滚（Level 2 备份还原策略，见 docs/operations/rollback-guide.md）。

设计要点：
- 用 PRAGMA wal_checkpoint(TRUNCATE) + shutil.copy2，而非 sqlite3.backup()。
  迁移发生在启动初期单进程，无并发连接，checkpoint+cp 与 backup() 同样可靠但更简单。
- 备份失败不阻塞迁移（try/except 降级为告警）。
- 保留最近 N 份，超出自动清理最旧的，避免磁盘膨胀。
"""

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 备份保留份数
BACKUP_KEEP = 3


def backup_before_migration(db_path: str) -> Optional[str]:
    """
    迁移前备份数据库。

    用 PRAGMA wal_checkpoint(TRUNCATE) 强制刷盘 WAL 日志，再 shutil.copy2 复制。
    备份失败不抛异常（返回 None），仅告警——避免备份问题阻塞迁移。

    Args:
        db_path: 数据库文件路径

    Returns:
        备份文件路径；失败返回 None
    """
    try:
        if not Path(db_path).exists():
            return None

        # 强制 WAL 刷盘，确保 -wal 日志合并进主库后再复制
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = f"{db_path}.pre-migration-{ts}"
        shutil.copy2(db_path, backup_path)

        prune_old_backups(db_path, keep=BACKUP_KEEP)

        logger.info(f"迁移前已备份数据库: {backup_path}")
        return backup_path

    except Exception as e:
        # 备份失败不阻塞迁移，仅告警
        logger.warning(f"迁移前备份失败（继续迁移）: {e}")
        return None


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
        prefix = f"{db_path}.pre-migration-"
        parent = Path(db_path).parent
        backups = sorted(
            [p for p in parent.glob(f"{Path(db_path).name}.pre-migration-*") if p.is_file()],
            key=lambda p: p.name,
            reverse=True,  # 新的在前
        )
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
