"""fix torrent backup downloader id type

【受限回滚】把 ``torrent_file_backup.downloader_id`` 从错误的 Integer 改为
与 ``bt_downloaders.downloader_id`` 一致的 String(36)。downgrade 恢复 Integer
列声明；但 UUID 文本经 SQLite INTEGER 亲和力会被截断成前导数字
（如 ``550e8400-…`` → ``550``），存在不可无损转换的值时 downgrade 拒绝执行，
需从已验证的 pre-migration 备份恢复。

Revision ID: b6e1c4d9a2f7
Revises: 7b2c9d4e6f10
Create Date: 2026-08-14 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b6e1c4d9a2f7"
down_revision: Union[str, Sequence[str], None] = "7b2c9d4e6f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAME = "torrent_file_backup"
_BATCH_TABLE_NAME = f"_alembic_tmp_{_TABLE_NAME}"


def _recover_stale_batch_table(bind: sa.engine.Connection) -> None:
    """处理 SQLite batch 迁移中断留下的可重建临时表。"""
    inspector = sa.inspect(bind)
    if not inspector.has_table(_BATCH_TABLE_NAME):
        return
    if not inspector.has_table(_TABLE_NAME):
        raise RuntimeError(
            f"检测到未完成的 SQLite batch 迁移：{_BATCH_TABLE_NAME} 存在但 "
            f"{_TABLE_NAME} 缺失；请从已验证的 pre-migration 备份恢复后重试"
        )
    bind.exec_driver_sql(f'DROP TABLE "{_BATCH_TABLE_NAME}"')


def _downloader_id_type(bind: sa.engine.Connection) -> sa.types.TypeEngine | None:
    if not sa.inspect(bind).has_table(_TABLE_NAME):
        return None
    for column in sa.inspect(bind).get_columns(_TABLE_NAME):
        if column["name"] == "downloader_id":
            return column["type"]
    return None


def upgrade() -> None:
    bind = op.get_bind()
    _recover_stale_batch_table(bind)
    current_type = _downloader_id_type(bind)
    if current_type is None or isinstance(current_type, sa.String):
        return

    with op.batch_alter_table(_TABLE_NAME, recreate="always") as batch_op:
        batch_op.alter_column(
            "downloader_id",
            existing_type=sa.Integer(),
            type_=sa.String(length=36),
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    _recover_stale_batch_table(bind)
    current_type = _downloader_id_type(bind)
    if current_type is None or isinstance(current_type, sa.Integer):
        return

    result = bind.execute(
        sa.text("SELECT DISTINCT downloader_id FROM torrent_file_backup " "WHERE downloader_id IS NOT NULL")
    )
    lossy_samples = [str(value) for (value,) in result if not _is_lossless_integer_text(str(value))]
    if lossy_samples:
        raise RuntimeError(
            "torrent_file_backup.downloader_id 含不可无损转换为整数的值"
            f"（示例: {lossy_samples[:3]}）；恢复 Integer 列会经 SQLite 数值亲和力"
            "截断 UUID 文本，拒绝自动回滚，请从已验证的 pre-migration 备份恢复"
        )

    with op.batch_alter_table(_TABLE_NAME, recreate="always") as batch_op:
        batch_op.alter_column(
            "downloader_id",
            existing_type=sa.String(length=36),
            type_=sa.Integer(),
            existing_nullable=True,
        )


def _is_lossless_integer_text(text: str) -> bool:
    """判断文本值转 Integer 是否无损（``'550e8400-…'`` 这类 UUID 会失败）。"""
    try:
        return str(int(text)) == text
    except ValueError:
        return False
