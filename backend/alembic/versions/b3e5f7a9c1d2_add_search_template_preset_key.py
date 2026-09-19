"""add search_templates.preset_key (bilingual system preset identity)

【可回滚】纯增量加列 + 索引；downgrade 仅 drop 索引与列，不动名称数据。
回填（一次性迁移辅助，符合 P0 冻结结论 PLANS/bilingual/system-content.md §1）：
- 仅对 is_default=1 且 preset_key IS NULL 且 name 精确等于已知预设中文名的行回填；
- 命中 0 行或 >1 行（歧义，如人工复制出的同名预设）不猜：保持 NULL 并记日志
  （B02 用户数据保护）；
- 中文名称此后仅作历史迁移证据，不再作为运行时身份或翻译索引。

Revision ID: b3e5f7a9c1d2
Revises: c1d2e3f4a5b6
Create Date: 2026-09-21 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3e5f7a9c1d2"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMN = "preset_key"
_TABLE = "search_templates"
_INDEX = "idx_search_templates_preset_key"

# 已知系统预设中文名 → 稳定身份键（与 app/data/default_search_templates.py 同源；
# 字面常量仅用于本次一次性回填，禁止在运行时代码中复用做匹配）
_LEGACY_PRESET_NAMES = {
    "活跃种子": "active_torrents",
    "错误状态": "error_status",
    "已暂停": "paused",
    "大文件": "large_files",
}


def _column_names(bind: sa.engine.Connection) -> set:
    return {str(column["name"]) for column in sa.inspect(bind).get_columns(_TABLE)}


def _index_names(bind: sa.engine.Connection) -> set:
    return {str(index["name"]) for index in sa.inspect(bind).get_indexes(_TABLE)}


def _backfill_preset_key(bind: sa.engine.Connection) -> None:
    """按中文名一次性回填 preset_key；命中数 != 1 的记录保持 NULL（不猜）。"""
    for name, key in _LEGACY_PRESET_NAMES.items():
        row = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM search_templates " "WHERE is_default = 1 AND preset_key IS NULL AND name = :name"
            ),
            {"name": name},
        ).scalar_one()
        count = int(row or 0)
        if count == 1:
            bind.execute(
                sa.text(
                    "UPDATE search_templates SET preset_key = :key "
                    "WHERE is_default = 1 AND preset_key IS NULL AND name = :name"
                ),
                {"key": key, "name": name},
            )
        elif count > 1:
            # 歧义（人工复制/同名预设）：保持 NULL，留给运营甄别，不猜测覆盖（B02）
            print(f"[preset_key] ambiguous legacy preset rows for name={name!r}: {count} rows left NULL")
        else:
            # 0 行：旧库从未初始化该预设（后续 init 按键插入）或已被人工删除
            pass


def upgrade() -> None:
    """Upgrade schema: 加 preset_key 列 + 索引 + 一次性中文名回填。"""
    bind = op.get_bind()

    if _COLUMN not in _column_names(bind):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(length=64), nullable=True, comment="系统预设稳定身份键"),
        )

    if _INDEX not in _index_names(bind):
        op.create_index(_INDEX, _TABLE, [_COLUMN], unique=False)

    _backfill_preset_key(bind)


def downgrade() -> None:
    """Downgrade schema: 【可回滚】drop 索引与列（不清除已回填数据以外的任何内容）。"""
    bind = op.get_bind()

    if _INDEX in _index_names(bind):
        op.drop_index(_INDEX, table_name=_TABLE)

    if _COLUMN in _column_names(bind):
        op.drop_column(_TABLE, _COLUMN)
