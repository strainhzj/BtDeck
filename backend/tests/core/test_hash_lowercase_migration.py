# -*- coding: utf-8 -*-
"""
hash 小写口径归一迁移测试（P0-D，rTorrent 接入前置）

验证目标：
1. 迁移归一：torrent_info.hash / torrent_file_backup.info_hash /
   sync_checkpoints.cursor_value 存量大写值一次性 lower()；
2. 已是小写的值不受影响（qB 路径数据零扰动）；
3. 幂等：重复 upgrade 不报错、不改变结果；
4. 缺表容错：漂移形态库（部分业务表缺失）升级不中断
   （该场景已由 test_orphan_schema_repair_migration 覆盖，本文件聚焦数据归一本身）。
"""

import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from tests.core.alembic_head import current_head  # noqa: F401 - 断言 head 前移用

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

# 历史锚点：hash 归一迁移的直接前驱（非 head；head 一律 current_head() 动态读取）
HASH_NORM_PREV = "053003337878"
HASH_NORM_REV = "a1f7c9e3d2b4"


def _make_alembic_config(db_path: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    os.environ["DATABASE_PATH"] = str(db_path)
    return cfg


def _seed_legacy_rows(db_path: Path) -> None:
    """在归一迁移前的 schema 上插入大小写混合的存量数据。"""
    conn = sqlite3.connect(db_path)
    try:
        # TR 大写形态 + qB 小写形态（同一 hash 跨下载器两套身份——正是本迁移要消除的形态）
        conn.executemany(
            "INSERT INTO torrent_info (info_id, downloader_id, downloader_name, hash, name, has_tracker_error) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            [
                ("id-tr-1", "dl-tr", "TR节点", "ABCDEF0123ABCDEF0123ABCDEF0123ABCDEF0123", "tr-torrent"),
                ("id-qb-1", "dl-qb", "QB节点", "abcdef0123abcdef0123abcdef0123abcdef0123", "qb-torrent"),
            ],
        )
        conn.execute(
            "INSERT INTO torrent_file_backup "
            "(info_hash, downloader_id, file_path, use_count, is_deleted, created_at, updated_at) "
            "VALUES ('ABCDEF0123ABCDEF0123ABCDEF0123ABCDEF0123', 'dl-tr', '/backup/a.torrent', 0, 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO sync_checkpoints "
            "(downloader_id, sync_type, cursor_value, cycle_started_at, last_attempt_at, created_at, updated_at) "
            "VALUES ('dl-tr', 'info', 'ABCDEF0123ABCDEF0123ABCDEF0123ABCDEF0123', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_all(db_path: Path, sql: str) -> list:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


class TestHashLowercaseNormalization:
    """a1f7c9e3d2b4：存量 hash 一次性小写归一。"""

    def test_upgrade_normalizes_uppercase_hashes(self, tmp_path):
        """TR 大写 hash/info_hash/cursor 全部 lower()；qB 小写值原样保留。"""
        db_path = tmp_path / "hash-norm.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, HASH_NORM_PREV)
        _seed_legacy_rows(db_path)

        command.upgrade(cfg, "head")

        hashes = {row[0] for row in _fetch_all(db_path, "SELECT hash FROM torrent_info")}
        assert hashes == {"abcdef0123abcdef0123abcdef0123abcdef0123"}
        assert _fetch_all(db_path, "SELECT info_hash FROM torrent_file_backup") == [
            ("abcdef0123abcdef0123abcdef0123abcdef0123",)
        ]
        assert _fetch_all(db_path, "SELECT cursor_value FROM sync_checkpoints") == [
            ("abcdef0123abcdef0123abcdef0123abcdef0123",)
        ]

    def test_upgrade_is_idempotent(self, tmp_path):
        """重复执行归一（stamp 回前驱再 upgrade）不报错、数据不变。"""
        db_path = tmp_path / "hash-norm-idem.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, HASH_NORM_PREV)
        _seed_legacy_rows(db_path)

        command.upgrade(cfg, "head")
        # 幂等复跑：降级 no-op 后再升级，数据保持小写且唯一
        command.downgrade(cfg, HASH_NORM_PREV)
        command.upgrade(cfg, "head")

        hashes = [row[0] for row in _fetch_all(db_path, "SELECT hash FROM torrent_info ORDER BY info_id")]
        assert len(hashes) == 2 and all(h == h.lower() for h in hashes)

    def test_hash_norm_revision_in_chain(self):
        """hash 归一迁移在链上且前驱不变（防误挂链；head 一律 current_head() 动态读取）。

        2026-09-24 统计报表 W1 新增 b7d8e9f0a1c2 后 head 前移，本文件遵循
        "head 一律 current_head() 动态读取"约定（见文首注释），断言改为
        链成员校验：HASH_NORM_REV 在链上、且其 down_revision 仍为 HASH_NORM_PREV
        （若有人重挂链导致前驱变化，此断言红）。合并 feature/reports 入 dev
        后 RSS 两迁移仍在本迁移之后，前驱不受影响。
        """
        from alembic.script import ScriptDirectory

        sd = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
        revisions = {r.revision: r for r in sd.walk_revisions()}
        assert HASH_NORM_REV in revisions, "hash 归一迁移应仍在迁移链上"
        assert (
            revisions[HASH_NORM_REV].down_revision == HASH_NORM_PREV
        ), f"hash 归一迁移前驱应保持 {HASH_NORM_PREV}，实际 {revisions[HASH_NORM_REV].down_revision}"
