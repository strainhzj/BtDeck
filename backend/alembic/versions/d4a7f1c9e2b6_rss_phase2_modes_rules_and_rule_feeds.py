"""rss phase2 modes rules and rule feeds

【可回滚】RSS 订阅 Phase 2 三张新表 + 两列（feature rss-subscription-phase2-2026-09-24）。

- ``bt_rss_modes``：按下载器 RSS 模式（btdeck/qb_native，行惰性创建，无行=btdeck）；
- ``bt_rss_rules``：引擎自动下载规则（关键词 include/exclude + 正则 + 目标下载器）；
- ``bt_rss_rule_feeds``：规则↔源关联（复合主键，空关联=归属下载器全部源）；
- ``bt_rss_articles`` 加列 ``added_rule_id``（自动规则命中事实）；
- ``bt_rss_feeds`` 加列 ``refresh_interval_minutes``（每源刷新间隔覆盖，null=全局节奏）。

纯新增表 + 可空列，downgrade 对称 drop/drop_column（无数据迁移）。

Revision ID: d4a7f1c9e2b6
Revises: 8fabba8687b0
Create Date: 2026-09-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a7f1c9e2b6"
down_revision: Union[str, Sequence[str], None] = "8fabba8687b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind: sa.engine.Connection, table: str) -> set:
    """既有表列名集合（加列幂等守卫用）。"""
    return {col["name"] for col in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    """新增三表 + 两列（全部幂等：已存在时跳过）。

    幂等守卫对齐 8fabba8687b0 惯例（版本戳回退后的重升级 no-op）。
    """
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("bt_rss_modes"):
        op.create_table(
            "bt_rss_modes",
            sa.Column("downloader_id", sa.String(length=36), nullable=False, comment="下载器ID"),
            sa.Column("mode", sa.String(length=20), nullable=False, comment="RSS 模式：btdeck/qb_native"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.PrimaryKeyConstraint("downloader_id"),
            comment="RSS 模式表（按下载器二选一，无行=默认 btdeck）",
        )

    if not inspector.has_table("bt_rss_rules"):
        op.create_table(
            "bt_rss_rules",
            sa.Column("rule_id", sa.String(length=36), nullable=False, comment="规则唯一标识符"),
            sa.Column("downloader_id", sa.String(length=36), nullable=False, comment="归属下载器ID"),
            sa.Column("name", sa.String(length=200), nullable=False, comment="规则名称"),
            sa.Column("enabled", sa.Integer(), nullable=False, comment="是否启用（1=启用，0=停用）"),
            sa.Column("include_keywords", sa.Text(), nullable=False, comment="命中关键词（逗号分隔，任一命中）"),
            sa.Column("exclude_keywords", sa.Text(), nullable=True, comment="排除关键词（逗号分隔，全不命中）"),
            sa.Column("use_regex", sa.Integer(), nullable=False, comment="是否按正则匹配（0=子串，1=re.search）"),
            sa.Column(
                "target_downloader_id",
                sa.String(length=36),
                nullable=True,
                comment="推送目标下载器覆盖（null=归属下载器）",
            ),
            sa.Column("save_path", sa.String(length=500), nullable=True, comment="保存路径"),
            sa.Column("tags", sa.String(length=200), nullable=True, comment="标签（逗号分隔）"),
            sa.Column("match_count", sa.Integer(), nullable=False, comment="累计自动推送数"),
            sa.Column("last_matched_at", sa.DateTime(), nullable=True, comment="最近一次命中推送时间"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.Column("dr", sa.Integer(), nullable=False, comment="软删除标记"),
            sa.PrimaryKeyConstraint("rule_id"),
            comment="RSS 自动下载规则表（BtDeck 引擎）",
        )
        op.create_index(op.f("ix_bt_rss_rules_rule_id"), "bt_rss_rules", ["rule_id"], unique=False)
        op.create_index(op.f("ix_bt_rss_rules_downloader_id"), "bt_rss_rules", ["downloader_id"], unique=False)

    if not inspector.has_table("bt_rss_rule_feeds"):
        op.create_table(
            "bt_rss_rule_feeds",
            sa.Column("rule_id", sa.String(length=36), nullable=False, comment="规则ID"),
            sa.Column("feed_id", sa.String(length=36), nullable=False, comment="订阅源ID"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.PrimaryKeyConstraint("rule_id", "feed_id"),
            comment="RSS 规则↔源关联表（空关联=归属下载器全部源）",
        )

    bind = op.get_bind()

    article_columns = _columns(bind, "bt_rss_articles")
    if "added_rule_id" not in article_columns:
        op.add_column(
            "bt_rss_articles",
            sa.Column(
                "added_rule_id",
                sa.String(length=36),
                nullable=True,
                comment="自动规则命中事实（推送规则ID，手动推送为空）",
            ),
        )

    feed_columns = _columns(bind, "bt_rss_feeds")
    if "refresh_interval_minutes" not in feed_columns:
        op.add_column(
            "bt_rss_feeds",
            sa.Column(
                "refresh_interval_minutes",
                sa.Integer(),
                nullable=True,
                comment="刷新间隔覆盖（分钟，null=跟全局调度节奏）",
            ),
        )


def downgrade() -> None:
    """对称回滚：删两列 + 删三表。"""
    bind = op.get_bind()

    feed_columns = _columns(bind, "bt_rss_feeds")
    if "refresh_interval_minutes" in feed_columns:
        op.drop_column("bt_rss_feeds", "refresh_interval_minutes")

    article_columns = _columns(bind, "bt_rss_articles")
    if "added_rule_id" in article_columns:
        op.drop_column("bt_rss_articles", "added_rule_id")

    inspector = sa.inspect(bind)
    if inspector.has_table("bt_rss_rule_feeds"):
        op.drop_table("bt_rss_rule_feeds")

    if inspector.has_table("bt_rss_rules"):
        op.drop_index(op.f("ix_bt_rss_rules_downloader_id"), table_name="bt_rss_rules")
        op.drop_index(op.f("ix_bt_rss_rules_rule_id"), table_name="bt_rss_rules")
        op.drop_table("bt_rss_rules")

    if inspector.has_table("bt_rss_modes"):
        op.drop_table("bt_rss_modes")
