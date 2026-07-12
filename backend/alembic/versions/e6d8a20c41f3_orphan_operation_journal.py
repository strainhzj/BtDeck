"""add orphan filesystem operation journal fields

Revision ID: e6d8a20c41f3
Revises: b075727f7182
Create Date: 2026-07-11 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6d8a20c41f3"
down_revision: Union[str, Sequence[str], None] = "b075727f7182"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("orphan_current_candidate"):
        return
    columns = {
        column["name"]: column
        for column in inspector.get_columns("orphan_current_candidate")
    }
    existing = set(columns)
    additions = [
        (
            "quarantine_root",
            sa.Column("quarantine_root", sa.String(length=600), nullable=True),
        ),
        (
            "operation_state",
            sa.Column(
                "operation_state",
                sa.String(length=30),
                nullable=False,
                server_default="stable",
            ),
        ),
        (
            "operation_target_path",
            sa.Column("operation_target_path", sa.String(length=600), nullable=True),
        ),
        ("operation_error", sa.Column("operation_error", sa.Text(), nullable=True)),
    ]
    missing = [column for name, column in additions if name not in existing]
    identity_type_change = any(
        name in columns and not isinstance(columns[name]["type"], sa.String)
        for name in ("device_id", "inode")
    )
    if missing or identity_type_change:
        with op.batch_alter_table("orphan_current_candidate") as batch_op:
            if identity_type_change:
                for name in ("device_id", "inode"):
                    batch_op.alter_column(
                        name, existing_type=sa.BigInteger(), type_=sa.String(length=32)
                    )
            for column in missing:
                batch_op.add_column(column)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("orphan_current_candidate"):
        return
    existing = {
        column["name"] for column in inspector.get_columns("orphan_current_candidate")
    }
    removable = [
        name
        for name in (
            "operation_error",
            "operation_target_path",
            "operation_state",
            "quarantine_root",
        )
        if name in existing
    ]
    if removable:
        with op.batch_alter_table("orphan_current_candidate") as batch_op:
            for name in removable:
                batch_op.drop_column(name)
            for name in ("device_id", "inode"):
                batch_op.alter_column(
                    name, existing_type=sa.String(length=32), type_=sa.BigInteger()
                )
