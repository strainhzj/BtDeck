"""speed_samples

【可回滚】速度时间采样两表（统计报表 W1，PLANS/statistics-reports.md §3.1）：
- ``downloader_speed_sample``：60s 原始采样（保留 14 天，采样任务每日清理）；
- ``downloader_speed_hourly``：整点聚合（保留 730 天）。

append-only 时序数据，无存量回填需求；幂等守卫（表已存在跳过）兼容
版本戳回退后的重升级 no-op 场景。

Revision ID: b7d8e9f0a1c2
Revises: d4a7f1c9e2b6
Create Date: 2026-09-24

（合并 feature/reports 入 dev 时自 a1f7c9e3d2b4 重挂至 d4a7f1c9e2b6，
保持单 head：a1f7c9e3d2b4 → 8fabba8687b0 → d4a7f1c9e2b6 → b7d8e9f0a1c2）

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d8e9f0a1c2"
down_revision: Union[str, Sequence[str], None] = "d4a7f1c9e2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """建速度采样两表（幂等：表已存在时跳过）。"""
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("downloader_speed_sample"):
        op.create_table(
            "downloader_speed_sample",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("downloader_id", sa.String(), nullable=False, comment="所属下载器主键"),
            sa.Column("sampled_at", sa.DateTime(), nullable=False, comment="采样时间（naive 本地）"),
            sa.Column(
                "download_speed",
                sa.Integer(),
                nullable=False,
                comment="下行 bytes/s（在线时缓存 KB/s × 1024，离线恒 0）",
            ),
            sa.Column(
                "upload_speed",
                sa.Integer(),
                nullable=False,
                comment="上行 bytes/s（在线时缓存 KB/s × 1024，离线恒 0）",
            ),
            sa.Column("online", sa.Boolean(), nullable=False, comment="采样时是否在线（is_online，非 fail_time）"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_speed_sample_dl_time", "downloader_speed_sample", ["downloader_id", "sampled_at"])

    if not inspector.has_table("downloader_speed_hourly"):
        op.create_table(
            "downloader_speed_hourly",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("downloader_id", sa.String(), nullable=False, comment="所属下载器主键"),
            sa.Column("stat_hour", sa.DateTime(), nullable=False, comment="统计小时（整点截断，naive 本地）"),
            sa.Column(
                "avg_download_speed",
                sa.Integer(),
                nullable=False,
                comment="下行均值 bytes/s（在线样本均值；online_count=0 记 0）",
            ),
            sa.Column("max_download_speed", sa.Integer(), nullable=False, comment="下行峰值 bytes/s"),
            sa.Column(
                "avg_upload_speed",
                sa.Integer(),
                nullable=False,
                comment="上行均值 bytes/s（在线样本均值；online_count=0 记 0）",
            ),
            sa.Column("max_upload_speed", sa.Integer(), nullable=False, comment="上行峰值 bytes/s"),
            sa.Column("sample_count", sa.Integer(), nullable=False, comment="该小时样本总数（含离线行）"),
            sa.Column(
                "online_count",
                sa.Integer(),
                nullable=False,
                comment="该小时在线样本数（onlineRatio = online_count/sample_count）",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("downloader_id", "stat_hour", name="uq_speed_hourly_dl_hour"),
        )


def downgrade() -> None:
    """回滚：drop 速度采样两表（append-only 观测数据，可安全丢弃）。"""
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("downloader_speed_hourly"):
        op.drop_table("downloader_speed_hourly")
    if inspector.has_table("downloader_speed_sample"):
        op.drop_index("idx_speed_sample_dl_time", table_name="downloader_speed_sample")
        op.drop_table("downloader_speed_sample")
