"""tracker_info 去重键收敛迁移（d5e6f7a8b9c0）回归。

保护点：
1. 确定性主键回填：同 (torrent_info_id, tracker_url) 对必得同一 id；
2. 同对 dr=1 残留行删除（与原唯一索引语义一致）；
3. 长值（930KB 实测形态）无损保留——列本身不受索引退场影响；
4. 未配对行（可空部件）保留原 uuid id；
5. 5 个索引退场（4 普通索引 + 部分唯一）+ PK 冗余索引一并清理；
6. 重放安全：upgrade 幂等（stamp 回旧版本重放场景）。
"""

import hashlib
import sqlite3

import pytest
from alembic import command

from app.torrents.models import make_tracker_id

_TARGET = "d5e6f7a8b9c0"
_DROPPED = (
    "ix_tracker_info_tracker_url",
    "ix_tracker_info_tracker_name",
    "ix_tracker_info_last_announce_msg",
    "ix_tracker_info_last_scrape_msg",
    "ix_tracker_info_tracker_id",
    "idx_tracker_unique_url",
)


def _existing_indexes(db) -> set:
    conn = sqlite3.connect(str(db))
    try:
        return {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tracker_info'"
            ).fetchall()
        }
    finally:
        conn.close()


@pytest.fixture
def pre_migration_db(tmp_path):
    """建到 a2b3（tracker_info 就位、旧索引在）并播种四类行。"""
    from tests.core.test_column_types_migration import build_alembic_config

    db = tmp_path / "tracker-dedup.db"
    cfg = build_alembic_config(db_path=str(db))
    command.upgrade(cfg, "a2b3c4d5e6f7")
    conn = sqlite3.connect(str(db))
    with conn:
        # 1) dr=0 配对行（回填目标）
        conn.execute(
            "INSERT INTO tracker_info(tracker_id,torrent_info_id,tracker_name,tracker_url,dr) "
            "VALUES('uuid-a','ti-1','n','https://t1/announce?passkey=long',0)"
        )
        # 2) 同对 dr=1 残留（应删除）
        conn.execute(
            "INSERT INTO tracker_info(tracker_id,torrent_info_id,tracker_name,tracker_url,dr) "
            "VALUES('uuid-b','ti-1','n','https://t1/announce?passkey=long',1)"
        )
        # 3) 长值行（930KB 实测形态，dr=0）
        long_url = "https://t2/announce?" + "x" * 950_000
        conn.execute(
            "INSERT INTO tracker_info(tracker_id,torrent_info_id,tracker_name,tracker_url,dr) "
            "VALUES('uuid-c','ti-2','long',?,0)",
            (long_url,),
        )
        # 4) 未配对行（url NULL，保留原 uuid）
        conn.execute(
            "INSERT INTO tracker_info(tracker_id,torrent_info_id,tracker_name,tracker_url,dr) "
            "VALUES('uuid-d','ti-3','n',NULL,0)"
        )
    yield db, cfg, long_url


def test_backfill_dedup_and_index_drops(pre_migration_db):
    db, cfg, long_url = pre_migration_db

    command.upgrade(cfg, _TARGET)

    conn = sqlite3.connect(str(db))
    try:
        # 1) dr=0 配对行 → 确定性 id
        got = conn.execute("SELECT tracker_id FROM tracker_info WHERE torrent_info_id='ti-1' AND dr=0").fetchone()[0]
        assert got == hashlib.md5(b"ti-1|https://t1/announce?passkey=long").hexdigest()
        # 2) 同对 dr=1 残留已删
        assert (
            conn.execute("SELECT COUNT(*) FROM tracker_info WHERE torrent_info_id='ti-1' AND dr=1").fetchone()[0] == 0
        )
        # 3) 长值行保留且 id=确定性派生（数据无损）
        cnt = conn.execute(
            "SELECT COUNT(*) FROM tracker_info WHERE tracker_id=? AND LENGTH(tracker_url)>900000",
            (hashlib.md5(b"ti-2|" + long_url.encode()).hexdigest(),),
        ).fetchone()[0]
        assert cnt == 1
        # 4) 未配对行保留原 uuid
        assert (
            conn.execute("SELECT tracker_id FROM tracker_info WHERE torrent_info_id='ti-3'").fetchone()[0] == "uuid-d"
        )
        # 5) 索引退场
        assert _existing_indexes(db).isdisjoint(_DROPPED)
    finally:
        conn.close()


def test_upgrade_replay_safe(pre_migration_db):
    """stamp 回旧版本重放迁移（startup_gates T01 模式）：upgrade 幂等。"""
    db, cfg, _ = pre_migration_db

    command.upgrade(cfg, _TARGET)
    command.upgrade(cfg, "a2b3c4d5e6f7", True) if False else None
    # 手动 stamp 回 a2b3 后重放（索引已在 upgrade 被删——重放必须幂等）

    # 模拟：先 upgrade（删索引）→ stamp a2b3 → 再 upgrade head
    command.stamp(cfg, "a2b3c4d5e6f7", purge=True)
    command.upgrade(cfg, _TARGET)  # 重放：索引已不存在，不炸

    assert _existing_indexes(db).isdisjoint(_DROPPED)


def test_downgrade_recreates_indexes_and_rerandomizes(pre_migration_db):
    db, cfg, _ = pre_migration_db
    command.upgrade(cfg, _TARGET)
    conn = sqlite3.connect(str(db))
    with conn:
        conn.execute("UPDATE tracker_info SET tracker_id='fixed-x' WHERE torrent_info_id='ti-3'")
    conn.close()

    command.downgrade(cfg, "-1")

    # 索引重建 + id 重随机化（不再等于确定性 id / 不再是回填前原值）
    assert "idx_tracker_unique_url" in _existing_indexes(db)
    conn = sqlite3.connect(str(db))
    try:
        got = conn.execute("SELECT tracker_id FROM tracker_info WHERE torrent_info_id='ti-3'").fetchone()[0]
    finally:
        conn.close()
    assert got not in ("uuid-d", "fixed-x")
    # 再 upgrade（round trip）不炸
    command.upgrade(cfg, _TARGET)


def test_make_tracker_id_semantics():
    """确定性派生 + 未配对回退 uuid。"""
    a = make_tracker_id("ti-1", "https://x")
    b = make_tracker_id("ti-1", "https://x")
    c = make_tracker_id("ti-2", "https://x")
    d = make_tracker_id("ti-1", "https://y")
    assert a == b  # 同对同 id（去重键=主键）
    assert a != c and a != d  # 异种子/异 URL 异 id
    e = make_tracker_id(None, None)
    f = make_tracker_id(None, None)
    assert e != f  # 未配对回退 uuid（互异）
    assert len(a) == 32  # md5 hex
