# -*- coding: utf-8 -*-
"""速度时间采样模型（统计报表 W1，PLANS/statistics-reports.md §3.1）。

两张 append-only 时序表：
- ``downloader_speed_sample``：60s 原始采样，保留 14 天；
- ``downloader_speed_hourly``：整点聚合（avg 分母 = online_count），保留 730 天。

口径说明：
- 速度单位 bytes/s（缓存 KB/s × 1024，对齐 dashboard_service 写法）；
- ``online`` 取缓存对象 ``is_online`` 标记（downloader_status_polling_task 经
  ``_set_online_status`` 维护）；``fail_time`` 为过时字段，禁止作为采样依据
  （断网时可能仍为 0）；
- 下载器删除后历史行保留（报表侧 LEFT JOIN 昵称，取不到回退 ID 标"已移除"）。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DownloaderSpeedSample(Base):
    """下载器速度原始采样行（每下载器每分钟一行）。"""

    __tablename__ = "downloader_speed_sample"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    downloader_id: Mapped[str] = mapped_column(String, nullable=False, comment="所属下载器主键")
    sampled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="采样时间（naive 本地）")
    download_speed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="下行 bytes/s（在线时缓存 KB/s × 1024，离线恒 0）"
    )
    upload_speed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="上行 bytes/s（在线时缓存 KB/s × 1024，离线恒 0）"
    )
    online: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="采样时是否在线（is_online，非 fail_time）"
    )

    __table_args__ = (Index("idx_speed_sample_dl_time", "downloader_id", "sampled_at"),)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<DownloaderSpeedSample id={self.id} dl={self.downloader_id} "
            f"at={self.sampled_at} down={self.download_speed} up={self.upload_speed} online={self.online}>"
        )


class DownloaderSpeedHourly(Base):
    """下载器速度整点聚合行（avg 分母 = online_count，online_count=0 时 avg 输出 0）。"""

    __tablename__ = "downloader_speed_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    downloader_id: Mapped[str] = mapped_column(String, nullable=False, comment="所属下载器主键")
    stat_hour: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="统计小时（整点截断，naive 本地）")
    avg_download_speed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="下行均值 bytes/s（在线样本均值；online_count=0 记 0）"
    )
    max_download_speed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="下行峰值 bytes/s")
    avg_upload_speed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="上行均值 bytes/s（在线样本均值；online_count=0 记 0）"
    )
    max_upload_speed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="上行峰值 bytes/s")
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="该小时样本总数（含离线行）")
    online_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="该小时在线样本数（onlineRatio = online_count/sample_count）"
    )

    __table_args__ = (UniqueConstraint("downloader_id", "stat_hour", name="uq_speed_hourly_dl_hour"),)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<DownloaderSpeedHourly id={self.id} dl={self.downloader_id} "
            f"hour={self.stat_hour} samples={self.sample_count} online={self.online_count}>"
        )
