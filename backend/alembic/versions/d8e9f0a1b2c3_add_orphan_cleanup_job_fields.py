"""extend orphan purge jobs for asynchronous manual cleanup

The existing ``orphan_purge_job`` table is reused for manual orphan cleanup
so both long-running operations have the same durable lifecycle and result
notification guarantees.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "orphan_purge_job"
_INDEX_OPERATION_TYPE = "ix_orphan_purge_job_operation_type"
_INDEX_SCAN_ID = "ix_orphan_purge_job_scan_id"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return

    existing_columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    additions = [
        (
            "operation_type",
            sa.Column(
                "operation_type",
                sa.String(length=20),
                nullable=False,
                server_default="purge",
                comment="purge/cleanup",
            ),
        ),
        (
            "scan_id",
            sa.Column("scan_id", sa.String(length=36), nullable=True, comment="主动清理绑定的扫描批次"),
        ),
        (
            "orphan_ids_json",
            sa.Column("orphan_ids_json", sa.Text(), nullable=True, comment="主动清理的孤儿文件 ID JSON 数组"),
        ),
        (
            "total_size",
            sa.Column(
                "total_size",
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="成功处理的文件总大小",
            ),
        ),
    ]
    missing = [column for name, column in additions if name not in existing_columns]
    if missing:
        with op.batch_alter_table(_TABLE) as batch_op:
            for column in missing:
                batch_op.add_column(column)

    existing_indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(_TABLE)}
    if _INDEX_OPERATION_TYPE not in existing_indexes:
        op.create_index(_INDEX_OPERATION_TYPE, _TABLE, ["operation_type"], unique=False)
    if _INDEX_SCAN_ID not in existing_indexes:
        op.create_index(_INDEX_SCAN_ID, _TABLE, ["scan_id"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return

    existing_indexes = {item["name"] for item in inspector.get_indexes(_TABLE)}
    if _INDEX_SCAN_ID in existing_indexes:
        op.drop_index(_INDEX_SCAN_ID, table_name=_TABLE)
    if _INDEX_OPERATION_TYPE in existing_indexes:
        op.drop_index(_INDEX_OPERATION_TYPE, table_name=_TABLE)

    existing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}
    removable = [
        name for name in ("total_size", "orphan_ids_json", "scan_id", "operation_type") if name in existing_columns
    ]
    if removable:
        with op.batch_alter_table(_TABLE) as batch_op:
            for name in removable:
                batch_op.drop_column(name)
