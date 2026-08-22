"""add orphan file tables

新增孤儿文件管理两张表：orphan_scan_result（扫描批次）+ orphan_file（孤儿文件明细）。
【可回滚】upgrade 创建两表，downgrade drop 两表。
回滚说明：两表仅存储扫描结果，drop 不影响业务数据。

Revision ID: c3f1a8b7d902
Revises: 95ef8bd8b47a
Create Date: 2026-07-10 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3f1a8b7d902"
down_revision: Union[str, Sequence[str], None] = "95ef8bd8b47a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 创建 orphan_scan_result + orphan_file 表.

    使用 inspect 守卫：对已有该表的库（手动创建或异常重跑），upgrade 不报错。
    与 95ef8bd8b47a search_templates 迁移风格一致。
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("orphan_scan_result"):
        op.create_table(
            "orphan_scan_result",
            sa.Column("scan_id", sa.String(length=36), nullable=False, comment="扫描批次ID（UUID）"),
            sa.Column("scan_time", sa.DateTime(), nullable=False, comment="扫描开始时间"),
            sa.Column(
                "scan_type", sa.String(length=20), nullable=False, comment="扫描类型：manual=手动，scheduled=定时"
            ),
            sa.Column(
                "total_paths_scanned", sa.Integer(), nullable=False, server_default="0", comment="扫描的路径数量"
            ),
            sa.Column(
                "total_files_scanned", sa.Integer(), nullable=False, server_default="0", comment="扫描的文件总数"
            ),
            sa.Column("total_orphans", sa.Integer(), nullable=False, server_default="0", comment="发现的孤儿文件数量"),
            sa.Column(
                "total_orphan_size",
                sa.BigInteger(),
                nullable=False,
                server_default="0",
                comment="孤儿文件总大小（字节）",
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="running",
                comment="扫描状态：running/completed/failed",
            ),
            sa.Column("error_message", sa.Text(), nullable=True, comment="失败时的错误信息"),
            sa.Column("operator", sa.String(length=100), nullable=True, comment="触发者（用户名或system）"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.PrimaryKeyConstraint("scan_id"),
        )
        op.create_index(op.f("ix_orphan_scan_result_scan_time"), "orphan_scan_result", ["scan_time"], unique=False)

    if not insp.has_table("orphan_file"):
        op.create_table(
            "orphan_file",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True, comment="主键"),
            sa.Column(
                "scan_id",
                sa.String(length=36),
                nullable=False,
                comment="所属扫描批次ID",
            ),
            sa.Column("file_path", sa.String(length=500), nullable=False, comment="文件绝对路径（外部路径）"),
            sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0", comment="文件大小（字节）"),
            sa.Column("mtime", sa.DateTime(), nullable=True, comment="文件修改时间"),
            sa.Column("downloader_id", sa.String(length=36), nullable=True, comment="关联下载器ID"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0"), comment="是否已清理"),
            sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="清理时间"),
            sa.Column("deleted_by", sa.String(length=100), nullable=True, comment="清理操作者"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.ForeignKeyConstraint(["scan_id"], ["orphan_scan_result.scan_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_orphan_file_scan_id"), "orphan_file", ["scan_id"], unique=False)
        op.create_index(op.f("ix_orphan_file_downloader_id"), "orphan_file", ["downloader_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop orphan_file + orphan_scan_result 表."""
    op.drop_index(op.f("ix_orphan_file_downloader_id"), table_name="orphan_file")
    op.drop_index(op.f("ix_orphan_file_scan_id"), table_name="orphan_file")
    op.drop_table("orphan_file")
    op.drop_index(op.f("ix_orphan_scan_result_scan_time"), table_name="orphan_scan_result")
    op.drop_table("orphan_scan_result")
