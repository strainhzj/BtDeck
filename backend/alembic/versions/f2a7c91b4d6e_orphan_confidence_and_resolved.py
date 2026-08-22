"""add orphan confidence column and resolve legacy candidates

Revision ID: f2a7c91b4d6e
Revises: 8f4c2d1a9b7e
Create Date: 2026-07-31 19:00:00.000000

Two changes for the cross-downloader shared-directory scan fix:

1. Add ``confidence`` (VARCHAR(8), NOT NULL, default 'high') to both
   ``orphan_file`` and ``orphan_current_candidate``. 'high' = precise filter
   (online downloader file list), 'low' = degraded directory-only filter
   (offline / mapping-missing downloader).

2. Resolve all existing ``orphan_current_candidate`` rows whose status is
   'candidate' to 'resolved'. The pre-fix scan produced a large number of
   false positives under the shared-directory scenario; marking them resolved
   moves them out of the orphan list so the next scan re-judges from scratch
   with the corrected two-layer logic (most will be protected by the
   directory whitelist and never re-appear). Historical ``orphan_file``
   detail rows are preserved as audit records.

DESTRUCTIVE_MIGRATION_ROLLBACK: resolution of legacy candidates is a one-way
state transition driven by the data-correction intent. Downgrade only removes
the confidence column; it cannot re-promote resolved candidates back to
candidate (their original detection was under the buggy logic).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2a7c91b4d6e"
down_revision: Union[str, Sequence[str], None] = "8f4c2d1a9b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ---- 1. orphan_file.confidence ----
    if inspector.has_table("orphan_file"):
        existing = {c["name"] for c in inspector.get_columns("orphan_file")}
        if "confidence" not in existing:
            with op.batch_alter_table("orphan_file") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "confidence",
                        sa.String(length=8),
                        nullable=False,
                        server_default="high",
                    )
                )

    # ---- 2. orphan_current_candidate.confidence ----
    if inspector.has_table("orphan_current_candidate"):
        existing = {c["name"] for c in inspector.get_columns("orphan_current_candidate")}
        if "confidence" not in existing:
            with op.batch_alter_table("orphan_current_candidate") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "confidence",
                        sa.String(length=8),
                        nullable=False,
                        server_default="high",
                    )
                )

    # ---- 3. resolve legacy candidates (move out of orphan list) ----
    # 跨下载器共享目录修复前的存量 candidate 绝大多数是误判；统一标记 resolved，
    # 让下次扫描用新两层逻辑从零重新判定。quarantined/purged 不动（已进入清理流水线）。
    if inspector.has_table("orphan_current_candidate"):
        bind.execute(sa.text("UPDATE orphan_current_candidate SET status = 'resolved' " "WHERE status = 'candidate'"))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("orphan_current_candidate"):
        existing = {c["name"] for c in inspector.get_columns("orphan_current_candidate")}
        if "confidence" in existing:
            with op.batch_alter_table("orphan_current_candidate") as batch_op:
                batch_op.drop_column("confidence")

    if inspector.has_table("orphan_file"):
        existing = {c["name"] for c in inspector.get_columns("orphan_file")}
        if "confidence" in existing:
            with op.batch_alter_table("orphan_file") as batch_op:
                batch_op.drop_column("confidence")
