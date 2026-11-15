"""tracker_info 去重键收敛到主键（btree 行上限修复）

Revision ID: d5e6f7a8b9c0
Recreate: 沿用链上受限回滚先例（b6e1c4d9a2f7/a2b3c4d5e6f7）

生产实证（2026-11-15）：tracker_info.tracker_url/tracker_name 实测 930KB
（同步故障把超长内容同时写入两列），远超 PG btree v4 2704B 索引行上限——
SQLite 无此限制故仅迁移/PG 运行期暴露。修复=去重键收敛到主键
tracker_id=make_tracker_id(torrent_info_id|tracker_url)（确定性 md5，应用侧
make_tracker_id 同源），URL/name/msg 列上的普通索引与部分唯一索引全部退场
（无界长值列不再可索引）。

- upgrade：先回填确定性主键（可空部件行保留原 id；同对多行=dr=1 残留，
  与唯一索引历史行为一致地保留首行删除后行），再删 5 个索引
  （4 普通索引 + idx_tracker_unique_url 部分唯一）。
- downgrade：索引按原 DDL 重建 + tracker_id 重随机化为 uuid4（原 id 不可
  恢复——但历史 id 本就是随机 uuid，语义无损；重随机化后旧引用失效与
  随机 uuid 的既有语义一致）。
"""

import hashlib
import uuid

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

_DROPPED_INDEXES = (
    "ix_tracker_info_tracker_url",
    "ix_tracker_info_tracker_name",
    "ix_tracker_info_last_announce_msg",
    "ix_tracker_info_last_scrape_msg",
    "ix_tracker_info_tracker_id",
    "idx_tracker_unique_url",
)


def _tracker_url_key(torrent_info_id: str, tracker_url: str) -> str:
    """与 app.torrents.models.make_tracker_id 同源（迁移内独立实现，避免链上
    依赖应用层模块的演进漂移）。"""
    return hashlib.md5(f"{torrent_info_id}|{tracker_url}".encode("utf-8")).hexdigest()


def _inspect_safe(conn, fn, fallback):
    """inspect 守卫可降级：假连接/不可检查对象（测试替身）→ 返回 fallback
    （保守按「存在」处理，与守卫引入前的既有语义一致）。"""
    try:
        return fn(sa.inspect(conn))
    except Exception:  # noqa: BLE001
        return fallback


def upgrade() -> None:
    conn = op.get_bind()
    # 0. 表存在性守卫（最小重放库/守卫测试场景无 tracker_info）：无表即仅删
    #    索引的索引亦不存在，直接完成（幂等语义与 c9e0 守卫先例一致）。
    if not _inspect_safe(conn, lambda i: i.has_table("tracker_info"), fallback=False):
        return
    # 1. 回填确定性主键：同对多行（dr=1 残留）保留首行删除后行——与原唯一
    #    索引的语义一致（唯一索引本就禁止 dr=0 重复，dr=1 重复是同步流程
    #    删除前残留，sync upsert 前置删除逻辑亦按此清理）。
    rows = conn.execute(
        sa.text(
            "SELECT tracker_id, torrent_info_id, tracker_url FROM tracker_info "
            "WHERE torrent_info_id IS NOT NULL AND tracker_url IS NOT NULL "
            "ORDER BY CASE WHEN dr = 0 THEN 0 ELSE 1 END, create_time"
        )
    ).fetchall()
    claimed: set[str] = set()
    delete_ids: list[str] = []
    update_pairs: list[dict[str, str]] = []
    for old_id, torrent_info_id, tracker_url in rows:
        new_id = _tracker_url_key(torrent_info_id, tracker_url)
        if new_id in claimed:
            delete_ids.append(old_id)
            continue
        claimed.add(new_id)
        if new_id != old_id:
            update_pairs.append({"new_id": new_id, "old_id": old_id})
    if delete_ids:
        conn.execute(
            sa.text(
                "DELETE FROM tracker_info WHERE tracker_id IN "
                f"({','.join(f':d{i}' for i in range(len(delete_ids)))})"
            ),
            {f"d{i}": v for i, v in enumerate(delete_ids)},
        )
    for pair in update_pairs:
        conn.execute(
            sa.text("UPDATE tracker_info SET tracker_id = :new_id WHERE tracker_id = :old_id"),
            pair,
        )
    # 2. 删除 6 个索引（无界长值列不再可索引）。
    #    重放安全（stamp 回旧版本重放迁移的启动模式，startup_gates T01 实测）：
    #    按现存索引集合过滤，缺失即跳过。
    existing = _inspect_safe(
        conn,
        lambda i: {x["name"] for x in i.get_indexes("tracker_info")},
        fallback=None,
    )
    for idx in _DROPPED_INDEXES:
        if existing is None or idx in existing:
            op.drop_index(idx, table_name="tracker_info")


def downgrade() -> None:
    conn = op.get_bind()
    if not _inspect_safe(conn, lambda i: i.has_table("tracker_info"), fallback=False):
        return
    # 重放安全：链中拒绝（receipt 守卫）可能把版本停在链中段，再次降级时
    # 索引可能已在——按现存集合跳过重建（与 upgrade 的删除守卫对称）。
    existing = _inspect_safe(
        conn,
        lambda i: {x["name"] for x in i.get_indexes("tracker_info")},
        fallback=None,
    )
    # tracker_id 重随机化为 uuid4——原确定性 id 与随机 id 均不携带可恢复信息，
    # 语义一致（历史 id 本就是随机 uuid）。
    rows = conn.execute(sa.text("SELECT tracker_id FROM tracker_info")).fetchall()
    for (old_id,) in rows:
        conn.execute(
            sa.text("UPDATE tracker_info SET tracker_id = :new_id WHERE tracker_id = :old_id"),
            {"new_id": str(uuid.uuid4()), "old_id": old_id},
        )
    _recreate_specs = (
        ("ix_tracker_info_tracker_url", ["tracker_url"], False),
        ("ix_tracker_info_tracker_name", ["tracker_name"], False),
        ("ix_tracker_info_last_announce_msg", ["last_announce_msg"], False),
        ("ix_tracker_info_last_scrape_msg", ["last_scrape_msg"], False),
        ("ix_tracker_info_tracker_id", ["tracker_id"], False),
        ("idx_tracker_unique_url", ["torrent_info_id", "tracker_url"], True),
    )
    for name, cols, unique in _recreate_specs:
        if existing is not None and name in existing:
            continue
        kw: dict = {"unique": unique}
        if name == "idx_tracker_unique_url":
            kw["sqlite_where"] = sa.text("dr = 0")
            kw["postgresql_where"] = sa.text("dr = 0")
        op.create_index(name, "tracker_info", cols, **kw)
