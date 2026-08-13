"""orphan scan background state and stable current detail

【受限回滚】downgrade 会移除后台扫描统计、超量人工复核记录与稳定明细指针；
表结构可回退，但这些升级后产生的治理元数据无法还原。

Revision ID: 7b2c9d4e6f10
Revises: 4c1d8e7a2b90
Create Date: 2026-08-13 18:00:00.000000

孤儿扫描在大批量场景下改为后台执行，并把当前候选绑定到一条稳定明细：

* ``orphan_scan_result.details_mode`` 区分旧的逐扫描快照与新的 current 模式；
* 记录新增/复用/resolved 数量，便于确认增量扫描是否生效；
* 超护栏扫描持久化复核门禁。迁移会把历史上超过 50000 条的成功扫描锁定，
  避免升级后误把现有 120100 条视为可清理；
* ``orphan_current_candidate.current_detail_id`` 指向当前稳定明细，后续成功扫描
  只推进生命周期，不再为同一路径重复插入 ``orphan_file`` 历史行。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7b2c9d4e6f10"
down_revision: Union[str, Sequence[str], None] = "4c1d8e7a2b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HISTORICAL_GUARDRAIL_THRESHOLD = 50_000


def _column_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("orphan_scan_result"):
        columns = _column_names(bind, "orphan_scan_result")
        additions = [
            ("details_mode", sa.String(length=16), False, sa.text("'snapshot'")),
            ("new_orphans", sa.Integer(), False, sa.text("0")),
            ("known_orphans", sa.Integer(), False, sa.text("0")),
            ("resolved_orphans", sa.Integer(), False, sa.text("0")),
            ("cleanup_review_required", sa.Boolean(), False, sa.text("0")),
            ("cleanup_reviewed_at", sa.DateTime(), True, None),
            ("cleanup_reviewed_by", sa.String(length=100), True, None),
            ("cleanup_review_note", sa.Text(), True, None),
        ]
        for name, type_, nullable, server_default in additions:
            if name in columns:
                continue
            with op.batch_alter_table("orphan_scan_result") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        name,
                        type_,
                        nullable=nullable,
                        server_default=server_default,
                    )
                )

        # 数据安全迁移：历史超阈值成功批次一律要求人工核查路径映射与样本。
        bind.execute(
            sa.text("""
                UPDATE orphan_scan_result
                   SET cleanup_review_required = 1,
                       cleanup_reviewed_at = NULL,
                       cleanup_reviewed_by = NULL,
                       cleanup_review_note = NULL
                 WHERE status = 'completed'
                   AND total_orphans > :threshold
                """),
            {"threshold": _HISTORICAL_GUARDRAIL_THRESHOLD},
        )

    if inspector.has_table("orphan_current_candidate"):
        columns = _column_names(bind, "orphan_current_candidate")
        if "current_detail_id" not in columns:
            with op.batch_alter_table("orphan_current_candidate") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "current_detail_id",
                        sa.Integer(),
                        sa.ForeignKey(
                            "orphan_file.id",
                            name="fk_orphan_candidate_current_detail",
                        ),
                        nullable=True,
                    )
                )

        # 优先绑定 last_seen_scan_id 对应明细；若存量数据不完整，再回退同路径最新行。
        if inspector.has_table("orphan_file"):
            bind.execute(sa.text("""
                    UPDATE orphan_current_candidate
                       SET current_detail_id = COALESCE(
                           (
                               SELECT detail.id
                                 FROM orphan_file AS detail
                                WHERE detail.canonical_path = orphan_current_candidate.canonical_path
                                  AND detail.scan_id = orphan_current_candidate.last_seen_scan_id
                                ORDER BY detail.id DESC
                                LIMIT 1
                           ),
                           (
                               SELECT fallback.id
                                 FROM orphan_file AS fallback
                                WHERE fallback.canonical_path = orphan_current_candidate.canonical_path
                                ORDER BY fallback.id DESC
                                LIMIT 1
                           )
                       )
                     WHERE current_detail_id IS NULL
                    """))

        # 若历史超量批次之后已有较小成功扫描且仍有活跃候选，则沿成功
        # 批次时间线把未复核门禁传递到最新 completed，避免升级瞬间绕过。
        # 相关子查询取“最新成功批次之前最近的未复核护栏批次”，不依赖
        # candidate.last_seen_scan_id（它可能已被较小后续扫描刷新）。
        if inspector.has_table("orphan_scan_result"):
            bind.execute(sa.text("""
                    UPDATE orphan_scan_result
                       SET cleanup_review_required = 1,
                           cleanup_reviewed_at = NULL,
                           cleanup_reviewed_by = NULL,
                           cleanup_review_note = NULL
                     WHERE scan_id = (
                               SELECT latest.scan_id
                                 FROM orphan_scan_result AS latest
                                WHERE latest.status = 'completed'
                                ORDER BY latest.scan_time DESC,
                                         latest.created_at DESC,
                                         latest.scan_id DESC
                                LIMIT 1
                           )
                       AND EXISTS (
                               SELECT 1
                                 FROM orphan_current_candidate AS candidate
                                WHERE candidate.status <> 'resolved'
                           )
                       AND EXISTS (
                               SELECT 1
                                 FROM orphan_scan_result AS guarded
                                WHERE guarded.status = 'completed'
                                  AND guarded.cleanup_review_required = 1
                                  AND guarded.cleanup_reviewed_at IS NULL
                                  AND guarded.scan_time < (
                                          SELECT latest_time.scan_time
                                            FROM orphan_scan_result AS latest_time
                                           WHERE latest_time.status = 'completed'
                                           ORDER BY latest_time.scan_time DESC,
                                                    latest_time.created_at DESC,
                                                    latest_time.scan_id DESC
                                           LIMIT 1
                                      )
                           )
                    """))

        indexes = {str(index["name"]) for index in sa.inspect(bind).get_indexes("orphan_current_candidate")}
        if "ux_orphan_candidate_current_detail_id" not in indexes:
            op.create_index(
                "ux_orphan_candidate_current_detail_id",
                "orphan_current_candidate",
                ["current_detail_id"],
                unique=True,
            )
        if "ix_orphan_candidate_last_scan_status" not in indexes:
            op.create_index(
                "ix_orphan_candidate_last_scan_status",
                "orphan_current_candidate",
                ["last_seen_scan_id", "status"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("orphan_current_candidate"):
        indexes = {str(index["name"]) for index in inspector.get_indexes("orphan_current_candidate")}
        if "ix_orphan_candidate_last_scan_status" in indexes:
            op.drop_index(
                "ix_orphan_candidate_last_scan_status",
                table_name="orphan_current_candidate",
            )
        if "ux_orphan_candidate_current_detail_id" in indexes:
            op.drop_index(
                "ux_orphan_candidate_current_detail_id",
                table_name="orphan_current_candidate",
            )
        if "current_detail_id" in _column_names(bind, "orphan_current_candidate"):
            with op.batch_alter_table("orphan_current_candidate") as batch_op:
                batch_op.drop_column("current_detail_id")

    if inspector.has_table("orphan_scan_result"):
        columns = _column_names(bind, "orphan_scan_result")
        for name in (
            "cleanup_review_note",
            "cleanup_reviewed_by",
            "cleanup_reviewed_at",
            "cleanup_review_required",
            "resolved_orphans",
            "known_orphans",
            "new_orphans",
            "details_mode",
        ):
            if name in columns:
                with op.batch_alter_table("orphan_scan_result") as batch_op:
                    batch_op.drop_column(name)
