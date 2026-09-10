"""【可回滚】add moviepilot integration tables

新增 MoviePilot 集成两张表（纯增量，downgrade 安全）：

- ``moviepilot_instance``：握手注册的实例（UUID 身份/版本元数据/下载器映射/
  同步状态可见性）；
- ``moviepilot_transfer_history``：MoviePilot 整理历史只读镜像，
  ``(instance_id, history_id)`` 唯一幂等身份 + 内容哈希变更判定 +
  映射解析冗余列（bt_downloader_id/association_status）。

注意：autogenerate 曾附带检出 env.py 既有漂移（orphan_hardlink_* 未导入、
refresh_tokens/notification/search_templates 的 NULL/索引命名差异）——
与本迁移无关，已剔除，不在本迁移处理。

Revision ID: 053003337878
Revises: c1d2e3f4a5b6
Create Date: 2026-09-08 18:36:44.186900

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "053003337878"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "moviepilot_instance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("instance_id", sa.String(length=64), nullable=False, comment="插件生成的实例 UUID（跨库稳定身份）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="实例展示名（插件侧配置）"),
        sa.Column("enabled", sa.Boolean(), nullable=False, comment="是否允许该实例握手/同步"),
        sa.Column("protocol_version", sa.Integer(), nullable=True, comment="握手携带的集成协议版本"),
        sa.Column("plugin_version", sa.String(length=32), nullable=True, comment="BtDeckBridge 插件版本"),
        sa.Column("moviepilot_version", sa.String(length=64), nullable=True, comment="MoviePilot 宿主版本"),
        sa.Column(
            "downloader_mapping", sa.Text(), nullable=True, comment="MP 下载器名 → BtDeck downloader_id 的 JSON 映射"
        ),
        sa.Column(
            "bound_username", sa.String(length=64), nullable=True, comment="绑定的集成账号（首个握手成功的认证用户）"
        ),
        sa.Column("last_handshake_at", sa.DateTime(), nullable=True, comment="最后握手时间"),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True, comment="最后成功同步批次时间"),
        sa.Column(
            "last_sync_stats",
            sa.Text(),
            nullable=True,
            comment="最后同步批次统计 JSON（inserted/updated/skipped/failed）",
        ),
        sa.Column("synced_history_count", sa.Integer(), nullable=False, comment="已同步整理历史条数（去重后）"),
        sa.Column("last_error", sa.Text(), nullable=True, comment="最后一次握手/同步错误（成功后清空）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_moviepilot_instance_instance_id"), "moviepilot_instance", ["instance_id"], unique=True)

    op.create_table(
        "moviepilot_transfer_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("instance_id", sa.String(length=64), nullable=False, comment="所属 MoviePilot 实例 UUID"),
        sa.Column("history_id", sa.BigInteger(), nullable=False, comment="MoviePilot TransferHistory 主键"),
        sa.Column("src_storage", sa.String(length=32), nullable=True, comment="源存储类型（local/rmt/...）"),
        sa.Column("src_path", sa.String(length=1024), nullable=True, comment="源文件路径（MP 原值）"),
        sa.Column("dest_storage", sa.String(length=32), nullable=True, comment="目标存储类型"),
        sa.Column("dest_path", sa.String(length=1024), nullable=True, comment="目标媒体库路径（MP 原值）"),
        sa.Column(
            "transfer_mode", sa.String(length=32), nullable=True, comment="整理方式（copy/move/link/hardlink/...）"
        ),
        sa.Column("media_type", sa.String(length=16), nullable=True, comment="媒体类型（电影/电视剧）"),
        sa.Column("title", sa.String(length=255), nullable=True, comment="媒体标题"),
        sa.Column("year", sa.String(length=8), nullable=True, comment="年份"),
        sa.Column("seasons", sa.String(length=32), nullable=True, comment="季（Sxx）"),
        sa.Column("episodes", sa.String(length=255), nullable=True, comment="集（Exx，多集逗号分隔）"),
        sa.Column("tmdb_id", sa.Integer(), nullable=True, comment="TMDB ID"),
        sa.Column("douban_id", sa.String(length=32), nullable=True, comment="豆瓣 ID"),
        sa.Column("media_source", sa.String(length=32), nullable=True, comment="MP 统一媒体数据源"),
        sa.Column("media_id", sa.String(length=64), nullable=True, comment="MP 原生媒体 ID"),
        sa.Column("mp_downloader", sa.String(length=128), nullable=True, comment="MoviePilot 侧下载器名（原值）"),
        sa.Column("download_hash", sa.String(length=64), nullable=True, comment="下载 Hash（MP 原值）"),
        sa.Column("bt_downloader_id", sa.String(length=64), nullable=True, comment="映射解析出的 BtDeck downloader_id"),
        sa.Column(
            "association_status", sa.String(length=16), nullable=False, comment="关联状态 linked/unmapped/unassociated"
        ),
        sa.Column("status", sa.Boolean(), nullable=True, comment="MP 侧整理成功状态"),
        sa.Column("errmsg", sa.Text(), nullable=True, comment="MP 侧整理失败信息"),
        sa.Column("mp_recorded_at", sa.String(length=32), nullable=True, comment="MP date 原始字符串"),
        sa.Column("recorded_at", sa.DateTime(), nullable=True, comment="MP date 解析值（解析失败为空）"),
        sa.Column("content_hash", sa.String(length=64), nullable=False, comment="规范字段 SHA-256（幂等变更判定）"),
        sa.Column("raw_snapshot", sa.Text(), nullable=True, comment="关键字段原始 JSON 留档（含 fileitem/files 概要）"),
        sa.Column("first_synced_at", sa.DateTime(), nullable=False, comment="首次同步时间"),
        sa.Column("last_synced_at", sa.DateTime(), nullable=False, comment="最近同步时间（内容变化或新插入）"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id", "history_id", name="uq_moviepilot_history_identity"),
    )
    op.create_index(
        op.f("ix_moviepilot_transfer_history_instance_id"), "moviepilot_transfer_history", ["instance_id"], unique=False
    )
    op.create_index(
        op.f("ix_moviepilot_transfer_history_title"), "moviepilot_transfer_history", ["title"], unique=False
    )
    op.create_index("idx_moviepilot_dest_path", "moviepilot_transfer_history", ["dest_path"], unique=False)
    op.create_index("idx_moviepilot_src_path", "moviepilot_transfer_history", ["src_path"], unique=False)
    op.create_index(
        "idx_moviepilot_hash_dl", "moviepilot_transfer_history", ["download_hash", "bt_downloader_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema：删除两张集成表（镜像数据可由插件重新全量同步重建）。"""
    op.drop_index("idx_moviepilot_hash_dl", table_name="moviepilot_transfer_history")
    op.drop_index("idx_moviepilot_src_path", table_name="moviepilot_transfer_history")
    op.drop_index("idx_moviepilot_dest_path", table_name="moviepilot_transfer_history")
    op.drop_index(op.f("ix_moviepilot_transfer_history_title"), table_name="moviepilot_transfer_history")
    op.drop_index(op.f("ix_moviepilot_transfer_history_instance_id"), table_name="moviepilot_transfer_history")
    op.drop_table("moviepilot_transfer_history")
    op.drop_index(op.f("ix_moviepilot_instance_instance_id"), table_name="moviepilot_instance")
    op.drop_table("moviepilot_instance")
