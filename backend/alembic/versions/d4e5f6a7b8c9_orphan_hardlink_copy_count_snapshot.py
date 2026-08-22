"""orphan_file hardlink copy count snapshot column

【可回滚】给 ``orphan_file`` 新增 ``hardlink_copy_count`` 快照列（扫描发现文件
时 stat 的 ``st_nlink - 1``，列表副本数列与 ``hardlink_copies=located`` 筛选的
数据源），并按 id 分块从既有预扫描结果（``orphan_hardlink_copy_result.copy_count``）
回填当前稳定明细，避免升级后到下一轮扫描前列表显示“未知”。历史 snapshot 模式
批次明细不挂 ``current_detail_id``，保持 NULL（未知）由后续扫描覆盖；回填源为
预扫描快照，与扫描写入值口径一致（均为 ``st_nlink - 1``）。

附带覆盖索引 ``ix_orphan_candidate_current_detail_status``：current 模式
detail_scope 的 ``id IN (SELECT current_detail_id ...)`` 子查询原先对候选表
全表 SCAN（每次列表请求多条语句各扫一遍），改走覆盖索引扫描。回填子查询以
INDEXED BY 强制命中 ``ux_orphan_candidate_current_detail_id`` 唯一索引。

Revision ID: d4e5f6a7b8c9
Revises: c8d9e0f1a2b3
Create Date: 2026-08-16 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BACKFILL_BATCH = 20000

_BACKFILL_SQL = sa.text("""
    UPDATE orphan_file
       SET hardlink_copy_count = (
           SELECT r.copy_count
             FROM orphan_current_candidate AS c
                  INDEXED BY ux_orphan_candidate_current_detail_id
             JOIN orphan_hardlink_copy_result AS r
               ON r.device_id = c.device_id
              AND r.inode_id = CAST(c.inode AS INTEGER)
            WHERE c.current_detail_id = orphan_file.id
              AND c.status <> 'resolved'
       )
     WHERE orphan_file.id > :lo
       AND orphan_file.id <= :hi
       AND orphan_file.hardlink_copy_count IS NULL
    """)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    orphan_file_columns = {str(column["name"]) for column in inspector.get_columns("orphan_file")}
    if "hardlink_copy_count" not in orphan_file_columns:
        op.add_column(
            "orphan_file",
            sa.Column("hardlink_copy_count", sa.Integer(), nullable=True),
        )

    candidate_indexes = {str(index["name"]) for index in inspector.get_indexes("orphan_current_candidate")}
    if "ix_orphan_candidate_current_detail_status" not in candidate_indexes:
        op.create_index(
            "ix_orphan_candidate_current_detail_status",
            "orphan_current_candidate",
            ["current_detail_id", "status"],
        )

    # 幂等回填：只补 NULL 行，可安全重入
    bounds = bind.execute(sa.text("SELECT COALESCE(MIN(id), 0), COALESCE(MAX(id), 0) FROM orphan_file")).one()
    lo, hi = int(bounds[0]), int(bounds[1])
    cursor = lo - 1
    while cursor < hi:
        chunk_hi = min(cursor + _BACKFILL_BATCH, hi)
        bind.execute(_BACKFILL_SQL, {"lo": cursor, "hi": chunk_hi})
        cursor = chunk_hi


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    candidate_indexes = {str(index["name"]) for index in inspector.get_indexes("orphan_current_candidate")}
    if "ix_orphan_candidate_current_detail_status" in candidate_indexes:
        op.drop_index("ix_orphan_candidate_current_detail_status", table_name="orphan_current_candidate")

    orphan_file_columns = {str(column["name"]) for column in inspector.get_columns("orphan_file")}
    if "hardlink_copy_count" in orphan_file_columns:
        with op.batch_alter_table("orphan_file", recreate="always") as batch_op:
            batch_op.drop_column("hardlink_copy_count")
