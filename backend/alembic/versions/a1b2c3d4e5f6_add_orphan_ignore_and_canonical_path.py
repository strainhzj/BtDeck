"""add orphan ignore flag and orphan_file.canonical_path

Revision ID: a1b2c3d4e5f6
Revises: f2a7c91b4d6e
Create Date: 2026-07-31 20:00:00.000000

孤儿文件管理增强：
1. ``orphan_current_candidate`` 增加 ``is_ignored`` / ``ignored_at`` /
   ``ignored_by`` 三列——被忽视的孤儿受保护，定时任务不自动删除，
   但仍可在列表查询到。
2. ``orphan_file`` 明细表增加冗余列 ``canonical_path``（normcase+normpath
   的规范化路径）并建索引。明细 ``file_path`` 是外部绝对路径，规范化逻辑
   （``normalize_path``）是 Python 函数无法下推到 SQL；冗余存一列后，
   "已忽视"筛选可在 SQL 层用 ``canonical_path IN (SELECT ... candidate
   WHERE is_ignored=1)`` 直接过滤与分页，避免全量 Python 端比对。
   同时回填存量明细（file_path 已是绝对路径，``abspath`` 幂等安全）。

【可回滚】纯加列 + 加索引 + 存量数据回填，downgrade 仅 drop 列与索引，
回填数据可丢弃（canonical_path 是可从 file_path 重新计算的派生值）。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f2a7c91b4d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_canonical_path(bind) -> None:
    """回填存量 orphan_file.canonical_path。

    normalize_path = os.path.normcase(os.path.normpath(os.path.abspath(path)))；
    file_path 落库时已是绝对路径，abspath 幂等，回填安全确定。
    """
    from app.services.orphan_manifest import normalize_path

    rows = bind.execute(sa.text("SELECT id, file_path FROM orphan_file WHERE canonical_path IS NULL")).fetchall()
    for row_id, file_path in rows:
        if not file_path:
            continue
        bind.execute(
            sa.text("UPDATE orphan_file SET canonical_path = :cp WHERE id = :rid"),
            {"cp": normalize_path(file_path), "rid": row_id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ---- 1. orphan_file.canonical_path（冗余列 + 索引 + 回填）----
    if inspector.has_table("orphan_file"):
        existing = {c["name"] for c in inspector.get_columns("orphan_file")}
        if "canonical_path" not in existing:
            with op.batch_alter_table("orphan_file") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "canonical_path",
                        sa.String(length=600),
                        nullable=True,
                        comment="规范化路径（normcase+normpath，用于忽略态 SQL 联表过滤）",
                    )
                )
        existing_idx = {i["name"] for i in inspector.get_indexes("orphan_file")}
        if "ix_orphan_file_canonical_path" not in existing_idx:
            op.create_index(
                "ix_orphan_file_canonical_path",
                "orphan_file",
                ["canonical_path"],
            )
        # 回填存量明细（幂等：已填的跳过）
        _backfill_canonical_path(bind)

    # ---- 2. orphan_current_candidate 忽视态三列 ----
    if inspector.has_table("orphan_current_candidate"):
        existing = {c["name"] for c in inspector.get_columns("orphan_current_candidate")}
        if "is_ignored" not in existing:
            with op.batch_alter_table("orphan_current_candidate") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "is_ignored",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.text("0"),
                        comment="是否被用户忽视（受保护，定时任务不自动删除）",
                    )
                )
        if "ignored_at" not in existing:
            with op.batch_alter_table("orphan_current_candidate") as batch_op:
                batch_op.add_column(sa.Column("ignored_at", sa.DateTime(), nullable=True, comment="忽视时间"))
        if "ignored_by" not in existing:
            with op.batch_alter_table("orphan_current_candidate") as batch_op:
                batch_op.add_column(sa.Column("ignored_by", sa.String(length=100), nullable=True, comment="忽视操作者"))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("orphan_current_candidate"):
        existing = {c["name"] for c in inspector.get_columns("orphan_current_candidate")}
        for col in ("ignored_by", "ignored_at", "is_ignored"):
            if col in existing:
                with op.batch_alter_table("orphan_current_candidate") as batch_op:
                    batch_op.drop_column(col)

    if inspector.has_table("orphan_file"):
        existing_idx = {i["name"] for i in inspector.get_indexes("orphan_file")}
        if "ix_orphan_file_canonical_path" in existing_idx:
            op.drop_index("ix_orphan_file_canonical_path", table_name="orphan_file")
        existing = {c["name"] for c in inspector.get_columns("orphan_file")}
        if "canonical_path" in existing:
            with op.batch_alter_table("orphan_file") as batch_op:
                batch_op.drop_column("canonical_path")
