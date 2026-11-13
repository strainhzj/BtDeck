# -*- coding: utf-8 -*-
"""a2b3c4d5e6f7 四列类型修正迁移回归（2026-11-11 审查补）。

锚定缺陷：downgrade 幂等判据误用单向 isinstance——BigInteger/Text 是
Integer/String 的子类，已升级列被误判为「已是旧类型」而静默跳过，downgrade
返回成功但 inode_id/total_size/log_detail 列 schema 未回退、alembic_version
已退 → 版本与 schema 漂移。本文件用真实迁移链（临时库）钉死：
- upgrade 拓宽类型落地（BIGINT/VARCHAR(36)/TEXT）；
- downgrade 真实回退列类型 + 数值无损；
- 数据性收窄 fail-closed（不可无损即拒绝，版本不前移）。
"""

from __future__ import annotations

import os
import sqlite3

import pytest
from alembic import command

from tests.core.alembic_head import build_alembic_config, current_head

# 历史锚点（a2b3c4d5e6f7 的 down_revision），非当前 head——写死需注释说明
# （tests/core/alembic_head.py 约定）
BASE_AT = "e9f0a1b2c3d4"


@pytest.fixture(autouse=True)
def _clean_database_path_env():
    """自动清理 DATABASE_PATH 环境变量，防止跨测试污染（同 test_db_migration）。"""
    old = os.environ.pop("DATABASE_PATH", None)
    yield
    if old is not None:
        os.environ["DATABASE_PATH"] = old
    else:
        os.environ.pop("DATABASE_PATH", None)


def _column_decls(db_path, table: str) -> dict[str, str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


class TestColumnTypesRoundtrip:
    def test_upgrade_widens_and_downgrade_restores(self, tmp_path):
        db = tmp_path / "mig.db"
        cfg = build_alembic_config(db_path=str(db))
        command.upgrade(cfg, BASE_AT)

        conn = sqlite3.connect(str(db))
        with conn:
            conn.execute(
                "INSERT INTO orphan_hardlink_copy_result(device_id,inode_id,copy_count,found_count,"
                "copies_json,truncated,scanned_at,created_at,updated_at) "
                "VALUES('2051',100,1,1,'[]',0,'2026-11-11 00:00:00','2026-11-11 00:00:00','2026-11-11 00:00:00')"
            )
            conn.execute(
                "INSERT INTO orphan_purge_job(task_id,status,operation_type,canonical_paths_json,operator,"
                "total_count,purged_count,failed_count,total_size,created_at,updated_at) "
                "VALUES('t1','completed','purge','[]','admin',1,1,0,123,"
                "'2026-11-11 00:00:00','2026-11-11 00:00:00')"
            )
            conn.execute(
                "INSERT INTO seed_transfer_audit_log(user_id,operation_type,source_downloader_id,"
                "target_downloader_id,torrent_name,transfer_status,operation_time,delete_source,created_at) "
                "VALUES(1,'transfer','123','456','t','success','2026-11-11 00:00:00',0,'2026-11-11 00:00:00')"
            )
            conn.execute(
                "INSERT INTO task_logs(task_id,task_name,task_type,start_time,end_time,duration,success,"
                "log_detail,dr) VALUES(1,'t',0,'2026-11-11 00:00:00','2026-11-11 00:00:01',1,1,'ok',0)"
            )
        conn.close()

        command.upgrade(cfg, "head")
        assert _column_decls(db, "orphan_hardlink_copy_result")["inode_id"] == "BIGINT"
        assert _column_decls(db, "orphan_purge_job")["total_size"] == "BIGINT"
        assert _column_decls(db, "seed_transfer_audit_log")["source_downloader_id"].upper().startswith("VARCHAR")
        assert _column_decls(db, "task_logs")["log_detail"] == "TEXT"

        # 回归锚点：downgrade 必须真实回退列类型（修复前误跳过仍报成功，
        # 版本已退而 BIGINT/TEXT 残留 → schema 漂移）
        command.downgrade(cfg, "-1")
        assert _column_decls(db, "orphan_hardlink_copy_result")["inode_id"] == "INTEGER"
        assert _column_decls(db, "orphan_purge_job")["total_size"] == "INTEGER"
        assert _column_decls(db, "seed_transfer_audit_log")["source_downloader_id"] == "INTEGER"
        assert _column_decls(db, "task_logs")["log_detail"] == "VARCHAR(2000)"

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            total = conn.execute("SELECT total_size FROM orphan_purge_job").fetchone()[0]
            src = conn.execute("SELECT source_downloader_id FROM seed_transfer_audit_log").fetchone()[0]
            detail_len = conn.execute("SELECT LENGTH(log_detail) FROM task_logs").fetchone()[0]
        finally:
            conn.close()
        assert version == BASE_AT
        assert total == 123  # 数值无损
        assert src == 123  # 数值文本回退 INTEGER
        assert detail_len == 2  # 'ok' 未截断

    def test_downgrade_refuses_lossy_data(self, tmp_path):
        """不可无损收窄（UUID 文本→Integer）→ downgrade 拒绝且版本不前移。"""
        db = tmp_path / "mig.db"
        cfg = build_alembic_config(db_path=str(db))
        command.upgrade(cfg, BASE_AT)
        command.upgrade(cfg, "head")
        conn = sqlite3.connect(str(db))
        with conn:
            conn.execute(
                "INSERT INTO seed_transfer_audit_log(user_id,operation_type,source_downloader_id,"
                "target_downloader_id,torrent_name,transfer_status,operation_time,delete_source,created_at) "
                "VALUES(1,'transfer','550e8400-e29b-41d4-a716-446655440000',NULL,'t','success',"
                "'2026-11-11 00:00:00',0,'2026-11-11 00:00:00')"
            )
        conn.close()
        with pytest.raises(Exception, match="不可无损转换|拒绝自动回滚"):
            command.downgrade(cfg, "-1")
        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            conn.close()
        assert version == current_head()
