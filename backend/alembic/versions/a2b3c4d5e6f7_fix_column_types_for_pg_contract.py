"""fix column types to match real data (PG contract)

【四列类型修正 2026-11-10】SQLite 类型声明非强制，历史数据与模型声明脱节：
1. ``orphan_hardlink_copy_result.inode_id``：Integer→BigInteger——Linux 大存储池
   inode 号超 int32 属常态（生产 17897 行 92% 超限，max≈3.1e10 < 2^63）
2. ``orphan_purge_job.total_size``：Integer→BigInteger——文件字节计数超 int32
   （max≈87GB 字节数）
3. ``seed_transfer_audit_log.source/target_downloader_id``：Integer→String(36)——
   真实数据即下载器 UUID 文本（21 行全部 typeof=text；对齐
   ``bt_downloaders.downloader_id`` String(36) 契约与 rss_subscription 先例）
4. ``task_logs.log_detail``：VARCHAR(2000)→Text——脚本执行日志可超 2000
   （生产 15 行最长 64K；写入侧配套 8000 字符统一截断）

PostgreSQL 目标 schema 由 ORM 模型经 squash 基线生成（PG 空库自动获得新类型）；
存量 PG 库与本 SQLite 链经本迁移对齐。batch recreate 双方言通用（值域增宽/
int→text 均无损，无需 USING）。downgrade 逆向收窄存在不可无损转换的值时拒绝
执行（沿用 b6e1c4d9a2f7 受限回滚先例），需从 pre-migration 备份恢复。

Revision ID: a2b3c4d5e6f7
Revises: e9f0a1b2c3d4
Create Date: 2026-11-10 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INT32_MAX = 2147483647
_INT32_MIN = -2147483648
_LOG_DETAIL_MAX = 2000

# (table, column, 新类型, 旧类型, nullable)
_SPECS: list[tuple[str, str, sa.types.TypeEngine, sa.types.TypeEngine, bool]] = [
    (
        "orphan_hardlink_copy_result",
        "inode_id",
        sa.BigInteger(),
        sa.Integer(),
        False,
    ),
    (
        "orphan_purge_job",
        "total_size",
        sa.BigInteger(),
        sa.Integer(),
        False,
    ),
    (
        "seed_transfer_audit_log",
        "source_downloader_id",
        sa.String(length=36),
        sa.Integer(),
        True,
    ),
    (
        "seed_transfer_audit_log",
        "target_downloader_id",
        sa.String(length=36),
        sa.Integer(),
        True,
    ),
    (
        "task_logs",
        "log_detail",
        sa.Text(),
        sa.String(length=2000),
        True,
    ),
]


def _recover_stale_batch_table(bind: sa.engine.Connection, table: str) -> None:
    """处理 SQLite batch 迁移中断留下的可重建临时表（b6e1c4d9a2f7 先例）。"""
    tmp_name = f"_alembic_tmp_{table}"
    inspector = sa.inspect(bind)
    if not inspector.has_table(tmp_name):
        return
    if not inspector.has_table(table):
        raise RuntimeError(
            f"检测到未完成的 SQLite batch 迁移：{tmp_name} 存在但 "
            f"{table} 缺失；请从已验证的 pre-migration 备份恢复后重试"
        )
    bind.exec_driver_sql(f'DROP TABLE "{tmp_name}"')


def _column_type(bind: sa.engine.Connection, table: str, column: str) -> sa.types.TypeEngine | None:
    if not sa.inspect(bind).has_table(table):
        return None
    for col in sa.inspect(bind).get_columns(table):
        if col["name"] == column:
            return col["type"]
    return None


def _is_lossless_integer_text(text: str) -> bool:
    """判断文本值转 Integer 是否无损（UUID 等非数字文本返回 False）。"""
    try:
        return str(int(text)) == text
    except ValueError:
        return False


def _assert_int32_safe(bind: sa.engine.Connection, table: str, column: str) -> None:
    """收窄到 Integer 前校验无超 int32 范围的值（数值列）。"""
    result = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE {column} IS NOT NULL AND ({column} > {_INT32_MAX} OR {column} < {_INT32_MIN})"
        )
    )
    overflow = result.scalar_one()
    if overflow:
        raise RuntimeError(
            f"{table}.{column} 含 {overflow} 行超 int32 范围的值；"
            "收窄回 Integer 会丢数据，拒绝自动回滚，请从已验证的 pre-migration 备份恢复"
        )


def _assert_lossless_integer_text(bind: sa.engine.Connection, table: str, column: str) -> None:
    """收窄到 Integer 前校验文本值全部可无损转整型（UUID 文本不可转）。"""
    result = bind.execute(sa.text(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"))
    lossy = [str(v) for (v,) in result if not _is_lossless_integer_text(str(v))]
    if lossy:
        raise RuntimeError(
            f"{table}.{column} 含不可无损转换为整数的值（示例: {lossy[:3]}）；"
            "恢复 Integer 列会经 SQLite 数值亲和力截断文本，拒绝自动回滚，"
            "请从已验证的 pre-migration 备份恢复"
        )


def _assert_log_detail_length(bind: sa.engine.Connection) -> None:
    """收窄到 VARCHAR(2000) 前校验无超长值。"""
    result = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM task_logs WHERE log_detail IS NOT NULL AND LENGTH(log_detail) > {_LOG_DETAIL_MAX}"
        )
    )
    overflow = result.scalar_one()
    if overflow:
        raise RuntimeError(
            f"task_logs.log_detail 含 {overflow} 行超 {_LOG_DETAIL_MAX} 字符；"
            "收窄回 VARCHAR(2000) 会丢数据，拒绝自动回滚，请从已验证的 pre-migration 备份恢复"
        )


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, new_type, _old_type, nullable in _SPECS:
        _recover_stale_batch_table(bind, table)
        current = _column_type(bind, table, column)
        if current is None:
            continue
        if isinstance(current, type(new_type)) or type(current) is type(new_type):
            # 已是新类型（重复执行/部分完成的幂等保护）
            continue
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.alter_column(column, existing_type=_old_type, type_=new_type, existing_nullable=nullable)


def downgrade() -> None:
    bind = op.get_bind()
    # 数据性收窄前置校验：任一不可无损即整体拒绝（不做部分回退）
    _assert_int32_safe(bind, "orphan_hardlink_copy_result", "inode_id")
    _assert_int32_safe(bind, "orphan_purge_job", "total_size")
    _assert_lossless_integer_text(bind, "seed_transfer_audit_log", "source_downloader_id")
    _assert_lossless_integer_text(bind, "seed_transfer_audit_log", "target_downloader_id")
    _assert_log_detail_length(bind)

    for table, column, _new_type, old_type, nullable in reversed(_SPECS):
        _recover_stale_batch_table(bind, table)
        current = _column_type(bind, table, column)
        if current is None:
            continue
        if isinstance(current, type(old_type)) or type(current) is type(old_type):
            continue
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.alter_column(column, existing_type=_new_type, type_=old_type, existing_nullable=nullable)
