"""add search_templates table

【可回滚】纯增量加表，downgrade 安全（仅 drop 该表，不影响其他表）。

第四轨归位：search_templates 表原由 advanced_search.py 的 _ensure_table_exists()
用原生 SQL 按需自建，独立于 Alembic。本迁移将其纳入 Alembic 统一管理。

upgrade() 使用 inspect 守卫：对已有该表的库（历史快照初始化或 _ensure_table_exists
建过的库）跳过建表，但补建缺失的索引，确保所有库的 schema 一致。

Revision ID: 95ef8bd8b47a
Revises: a0ada9774936
Create Date: 2026-06-21 15:00:53.549328

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95ef8bd8b47a'
down_revision: Union[str, Sequence[str], None] = 'a0ada9774936'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 索引名约定（与 advanced_search.py:829-830 的 _ensure_table_exists 历史定义一致）
_INDEX_USER_ID = 'idx_search_templates_user_id'
_INDEX_IS_PUBLIC = 'idx_search_templates_is_public'


def upgrade() -> None:
    """Upgrade schema.

    使用 inspect 守卫：
    - 表不存在（fresh alembic 库）→ 建表 + 建索引
    - 表存在但缺索引（历史快照库，schema.sql 不建索引）→ 仅补建索引
    - 表存在且有索引（_ensure_table_exists 建过的库）→ no-op
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table('search_templates'):
        # 字段定义与 server_default 严格匹配原 CREATE TABLE
        # （advanced_search.py:812-824 / production_complete_schema.sql:233-244）
        op.create_table(
            'search_templates',
            sa.Column('id', sa.String(length=36), nullable=False, comment='模板唯一标识（UUID）'),
            sa.Column('user_id', sa.String(length=36), nullable=False, comment='所属用户 ID'),
            sa.Column('name', sa.String(length=100), nullable=False, comment='模板名称'),
            sa.Column('description', sa.String(length=500), nullable=True, comment='模板描述'),
            sa.Column('conditions', sa.Text(), nullable=False, comment='查询条件（JSON 字符串）'),
            sa.Column('is_default', sa.Integer(), nullable=False, server_default='0',
                      comment='是否系统预设：1=预设，0=用户自定义'),
            sa.Column('is_public', sa.Integer(), nullable=False, server_default='0',
                      comment='是否公开可见'),
            sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0',
                      comment='使用次数'),
            sa.Column('created_time', sa.DateTime(), nullable=True,
                      server_default=sa.text('(CURRENT_TIMESTAMP)'), comment='创建时间'),
            sa.Column('updated_time', sa.DateTime(), nullable=True,
                      server_default=sa.text('(CURRENT_TIMESTAMP)'), comment='更新时间'),
            sa.PrimaryKeyConstraint('id')
        )

    # 索引补建（对已存在表但缺索引的库生效）
    existing_indexes = set()
    if insp.has_table('search_templates'):
        existing_indexes = {idx['name'] for idx in insp.get_indexes('search_templates')}

    if _INDEX_USER_ID not in existing_indexes:
        op.create_index(_INDEX_USER_ID, 'search_templates', ['user_id'], unique=False)
    if _INDEX_IS_PUBLIC not in existing_indexes:
        op.create_index(_INDEX_IS_PUBLIC, 'search_templates', ['is_public'], unique=False)


def downgrade() -> None:
    """Downgrade schema. 【可回滚】仅 drop search_templates 表及其索引。"""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    existing_indexes = set()
    if insp.has_table('search_templates'):
        existing_indexes = {idx['name'] for idx in insp.get_indexes('search_templates')}

    if _INDEX_USER_ID in existing_indexes:
        op.drop_index(_INDEX_USER_ID, table_name='search_templates')
    if _INDEX_IS_PUBLIC in existing_indexes:
        op.drop_index(_INDEX_IS_PUBLIC, table_name='search_templates')
    if insp.has_table('search_templates'):
        op.drop_table('search_templates')
