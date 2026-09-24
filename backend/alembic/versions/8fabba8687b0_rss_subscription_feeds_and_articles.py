"""rss subscription feeds and articles

【可回滚】新增 RSS 订阅两张业务表（feature rss-subscription-2026-09-24 Phase 1）。

- ``bt_rss_feeds``：订阅源（绑定下载器 + 抓取状态投影）；
- ``bt_rss_articles``：订阅文章（(feed_id, guid) 唯一去重 + 推送状态）。

纯新增表，downgrade 对称 drop（软删语义不涉及存量数据，无数据迁移）。

Revision ID: 8fabba8687b0
Revises: a1f7c9e3d2b4
Create Date: 2026-09-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8fabba8687b0"
down_revision: Union[str, Sequence[str], None] = "a1f7c9e3d2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 bt_rss_feeds / bt_rss_articles 两表及索引。

    幂等：表已存在时跳过（兼容版本戳回退后的重升级 no-op 守卫，
    对齐 053003337878 moviepilot 迁移惯例）。
    """
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("bt_rss_feeds"):
        op.create_table(
            "bt_rss_feeds",
            sa.Column("feed_id", sa.String(length=36), nullable=False, comment="订阅源唯一标识符"),
            sa.Column("downloader_id", sa.String(length=36), nullable=False, comment="绑定的下载器ID"),
            sa.Column("name", sa.String(length=200), nullable=False, comment="订阅源名称"),
            sa.Column("url", sa.String(length=1000), nullable=False, comment="订阅源地址"),
            sa.Column("enabled", sa.Integer(), nullable=False, comment="是否启用（1=启用，0=停用）"),
            sa.Column("last_fetch_at", sa.DateTime(), nullable=True, comment="最近抓取时间"),
            sa.Column(
                "last_fetch_status", sa.String(length=20), nullable=False, comment="最近抓取状态：never/ok/failed"
            ),
            sa.Column("last_error", sa.Text(), nullable=True, comment="最近抓取失败原因"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.Column("dr", sa.Integer(), nullable=False, comment="软删除标记"),
            sa.PrimaryKeyConstraint("feed_id"),
            comment="RSS 订阅源表",
        )
        op.create_index(op.f("ix_bt_rss_feeds_feed_id"), "bt_rss_feeds", ["feed_id"], unique=False)
        op.create_index(op.f("ix_bt_rss_feeds_downloader_id"), "bt_rss_feeds", ["downloader_id"], unique=False)

    if not inspector.has_table("bt_rss_articles"):
        op.create_table(
            "bt_rss_articles",
            sa.Column("article_id", sa.String(length=36), nullable=False, comment="文章唯一标识符"),
            sa.Column("feed_id", sa.String(length=36), nullable=False, comment="所属订阅源ID"),
            sa.Column("guid", sa.String(length=500), nullable=False, comment="文章全局标识（去重键）"),
            sa.Column("title", sa.String(length=500), nullable=False, comment="文章标题"),
            sa.Column("link", sa.String(length=2000), nullable=False, comment="种子链接（magnet 或直链 URL）"),
            sa.Column("published_at", sa.DateTime(), nullable=True, comment="发布时间"),
            sa.Column("fetched_at", sa.DateTime(), nullable=False, comment="抓取入库时间"),
            sa.Column("status", sa.String(length=20), nullable=False, comment="状态：pending/added"),
            sa.Column("added_at", sa.DateTime(), nullable=True, comment="推送时间"),
            sa.Column("added_downloader_id", sa.String(length=36), nullable=True, comment="实际推送目标下载器ID"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.PrimaryKeyConstraint("article_id"),
            sa.UniqueConstraint("feed_id", "guid", name="uq_rss_article_feed_guid"),
            comment="RSS 订阅文章表（(feed_id,guid) 唯一去重）",
        )
        op.create_index(op.f("ix_bt_rss_articles_article_id"), "bt_rss_articles", ["article_id"], unique=False)
        op.create_index(op.f("ix_bt_rss_articles_feed_id"), "bt_rss_articles", ["feed_id"], unique=False)
        op.create_index(op.f("ix_bt_rss_articles_status"), "bt_rss_articles", ["status"], unique=False)


def downgrade() -> None:
    """对称回滚：删除两张 RSS 订阅表及索引。"""
    op.drop_index(op.f("ix_bt_rss_articles_status"), table_name="bt_rss_articles")
    op.drop_index(op.f("ix_bt_rss_articles_feed_id"), table_name="bt_rss_articles")
    op.drop_index(op.f("ix_bt_rss_articles_article_id"), table_name="bt_rss_articles")
    op.drop_table("bt_rss_articles")
    op.drop_index(op.f("ix_bt_rss_feeds_downloader_id"), table_name="bt_rss_feeds")
    op.drop_index(op.f("ix_bt_rss_feeds_feed_id"), table_name="bt_rss_feeds")
    op.drop_table("bt_rss_feeds")
