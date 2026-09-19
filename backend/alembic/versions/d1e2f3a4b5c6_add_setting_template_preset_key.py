"""add setting_templates.preset_key (bilingual system preset identity)

【可回滚】纯增量加列 + 索引；downgrade 仅 drop 索引与列，不动名称数据。

回填（一次性迁移辅助，符合 P0 冻结结论 PLANS/bilingual/system-content.md §2）：
- 仅对 is_default=1 且 preset_key IS NULL 且 name 精确等于已知预设中文名的行回填；
- 命中 0 行或 >1 行（歧义，如人工复制出的同名模板）不猜：保持 NULL 并记日志（B02 用户数据保护）；
- 中文名称此后仅作历史迁移证据，不再作为运行时身份或翻译索引。

Revision ID: d1e2f3a4b5c6
Revises: b3e5f7a9c1d2
Create Date: 2026-09-19 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "b3e5f7a9c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMN = "preset_key"
_TABLE = "setting_templates"
_INDEX = "idx_setting_templates_preset_key"

# 已知系统预设中文名 → 稳定身份键（与 app/data/default_templates.py 同源；
# 字面常量仅用于本次一次性回填，禁止在运行时代码中复用做匹配）
_LEGACY_PRESET_NAMES = {
    "qBittorrent标准模板": "qb_standard",
    "qBittorrent高性能模板": "qb_highperf",
    "Transmission标准模板": "tr_standard",
    "Transmission高性能模板": "tr_highperf",
    "夜间不限速模板": "night_unlimited",
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
                "SELECT COUNT(*) FROM setting_templates " "WHERE is_system_default = 1 AND preset_key IS NULL AND name = :name"
            ),
            {"name": name},
        ).scalar_one()
        count = int(row or 0)
        if count == 1:
            bind.execute(
                sa.text(
                    "UPDATE setting_templates SET preset_key = :key "
                    "WHERE is_system_default = 1 AND preset_key IS NULL AND name = :name"
                ),
                {"key": key, "name": name},
            )
        elif count > 1:
            # 歧义（人工复制/同名）：不猜，保持 NULL（B02）
            print(f"[migration] setting_templates 中文名 {name} 存在 {count} 行歧义，保持 preset_key 为 NULL")


def upgrade() -> None:
    bind = op.get_bind()
    if _COLUMN not in _column_names(bind):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=64), nullable=True))
    if _INDEX not in _index_names(bind):
        op.create_index(_INDEX, _TABLE, [_COLUMN], unique=False)
    _backfill_preset_key(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if _INDEX in _index_names(bind):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in _column_names(bind):
        op.drop_column(_TABLE, _COLUMN)
