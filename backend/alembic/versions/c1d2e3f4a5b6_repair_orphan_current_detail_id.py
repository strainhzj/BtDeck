"""repair orphan current-detail schema drift

【受限回滚】本迁移只修复已被历史 head 标记但实际缺列的存量库；健康库为
幂等 no-op。downgrade 保留 ``current_detail_id``，因为它已经属于
``975dad435c03`` 及之前的目标 schema，不能把数据库降级成再次不一致的形态。

Revision ID: c1d2e3f4a5b6
Revises: 975dad435c03
Create Date: 2026-08-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "975dad435c03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CANDIDATE_TABLE = "orphan_current_candidate"
_DETAIL_TABLE = "orphan_file"
_DETAIL_ID_COLUMN = "current_detail_id"
_DETAIL_PATH_INDEX = "ix_orphan_file_canonical_path"
_CURRENT_DETAIL_INDEX = "ux_orphan_candidate_current_detail_id"
_LAST_SCAN_STATUS_INDEX = "ix_orphan_candidate_last_scan_status"


def _column_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(bind).get_columns(table_name)}


def _index_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    return {str(index["name"]) for index in sa.inspect(bind).get_indexes(table_name)}


def _add_current_detail_id(bind: sa.engine.Connection) -> None:
    """补齐历史漂移库缺失的可空稳定明细指针。"""
    if bind.dialect.name == "sqlite":
        # SQLite 的 ADD COLUMN 不支持随后单独 ALTER CONSTRAINT；保持与
        # 7b2c9d4e6f10 一致，直接追加可空 REFERENCES 列。
        bind.exec_driver_sql(
            "ALTER TABLE orphan_current_candidate "
            "ADD COLUMN current_detail_id INTEGER "
            "CONSTRAINT fk_orphan_candidate_current_detail "
            "REFERENCES orphan_file(id)"
        )
        return

    op.add_column(
        _CANDIDATE_TABLE,
        sa.Column(
            _DETAIL_ID_COLUMN,
            sa.Integer(),
            sa.ForeignKey(_DETAIL_TABLE + ".id", name="fk_orphan_candidate_current_detail"),
            nullable=True,
        ),
    )


def _backfill_current_detail_id(bind: sa.engine.Connection) -> None:
    """按稳定路径和最近扫描批次幂等回填当前明细指针。"""
    if _DETAIL_PATH_INDEX not in _index_names(bind, _DETAIL_TABLE):
        op.create_index(_DETAIL_PATH_INDEX, _DETAIL_TABLE, ["canonical_path"])

    bind.execute(
        sa.text(
            """
            UPDATE orphan_current_candidate
               SET current_detail_id = COALESCE(
                   (
                       SELECT detail.id
                         FROM orphan_file AS detail
                              INDEXED BY ix_orphan_file_canonical_path
                        WHERE detail.canonical_path = orphan_current_candidate.canonical_path
                          AND detail.scan_id = orphan_current_candidate.last_seen_scan_id
                        ORDER BY detail.id DESC
                        LIMIT 1
                   ),
                   (
                       SELECT fallback.id
                         FROM orphan_file AS fallback
                              INDEXED BY ix_orphan_file_canonical_path
                        WHERE fallback.canonical_path = orphan_current_candidate.canonical_path
                        ORDER BY fallback.id DESC
                        LIMIT 1
                   )
               )
             WHERE current_detail_id IS NULL
            """
        )
    )


def upgrade() -> None:
    """Repair a database whose Alembic version is ahead of its orphan schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(_CANDIDATE_TABLE):
        # At this point all normal upgrade paths have already created the
        # orphan tables. A head-marked database without this table is not
        # safely repairable by an additive column migration.
        raise RuntimeError(
            "orphan_current_candidate is missing; " "restore a validated database backup before starting"
        )

    if not inspector.has_table(_DETAIL_TABLE):
        raise RuntimeError(
            "orphan_current_candidate exists but orphan_file is missing; "
            "restore a validated database backup before starting"
        )

    detail_columns = _column_names(bind, _DETAIL_TABLE)
    if "canonical_path" not in detail_columns:
        raise RuntimeError(
            "orphan_file.canonical_path is missing; " "restore a validated database backup before starting"
        )

    if _DETAIL_ID_COLUMN not in _column_names(bind, _CANDIDATE_TABLE):
        _add_current_detail_id(bind)

    # Refresh the inspector after ADD COLUMN so subsequent index checks see
    # the repaired table definition on all supported SQLAlchemy/SQLite builds.
    if _DETAIL_ID_COLUMN not in _column_names(bind, _CANDIDATE_TABLE):
        raise RuntimeError("failed to add orphan_current_candidate.current_detail_id")

    _backfill_current_detail_id(bind)

    indexes = _index_names(bind, _CANDIDATE_TABLE)
    if _CURRENT_DETAIL_INDEX not in indexes:
        op.create_index(
            _CURRENT_DETAIL_INDEX,
            _CANDIDATE_TABLE,
            [_DETAIL_ID_COLUMN],
            unique=True,
        )

    if _LAST_SCAN_STATUS_INDEX not in indexes:
        op.create_index(
            _LAST_SCAN_STATUS_INDEX,
            _CANDIDATE_TABLE,
            ["last_seen_scan_id", "status"],
        )


def downgrade() -> None:
    """Keep the repaired column because it belongs to the 975dad435c03 schema."""
    pass
