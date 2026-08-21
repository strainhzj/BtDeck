# -*- coding: utf-8 -*-
"""孤儿文件硬链接副本位置的定时任务预扫描结果。

按 ``(st_dev, st_ino)`` 物理身份唯一存储最近一轮整体查找结果；前端点击副本
数量只读取这里的结果，不再触发实时目录遍历。``orphan_hardlink_scan_state``
是单行 keyset 游标，记录任务下一轮从哪个明细 ID 继续，避免大库每轮从头 stat。
"""

import json
from datetime import datetime
from typing import List, cast

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from app.database import Base


class OrphanHardlinkCopyResult(Base):
    """单个 inode 身份的副本定位结果（定时任务写入，接口只读）。

    ``device_id`` 用字符串存储：Windows 的 ``st_dev`` 是无符号卷序列号，可能
    超出 SQLite 有符号整数范围（与 ``orphan_current_candidate.device_id`` 同惯例）。
    """

    __tablename__ = "orphan_hardlink_copy_result"
    __table_args__ = (UniqueConstraint("device_id", "inode_id", name="uq_orphan_hardlink_identity"),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增主键")
    device_id = Column(String(32), nullable=False, comment="目标文件 st_dev（字符串，Windows 无符号卷号）")
    inode_id = Column(Integer, nullable=False, comment="目标文件 st_ino")
    copy_count = Column(Integer, nullable=False, default=0, comment="扫描时的 st_nlink - 1")
    found_count = Column(Integer, nullable=False, default=0, comment="本轮实际定位到的路径数（含源路径本身）")
    copies_json = Column(
        Text, nullable=False, default="[]", server_default="[]", comment="定位到的物理路径 JSON 数组（可截断）"
    )
    truncated = Column(Integer, nullable=False, default=0, server_default="0", comment="路径数超过存储上限被截断")
    scan_note = Column(String(200), nullable=True, comment="扫描备注（budget_exceeded/partial 等）")
    scanned_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True, comment="本轮结果时间")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )

    @property
    def copies(self) -> List[str]:
        """解析定位路径；坏数据按空列表 fail-closed。"""
        try:
            value = json.loads(cast(str, self.copies_json) or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []


class OrphanHardlinkScanState(Base):
    """副本预扫描任务的 keyset 游标（单行，id 恒为 1）。"""

    __tablename__ = "orphan_hardlink_scan_state"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="恒为 1")
    last_detail_id = Column(Integer, nullable=False, default=0, comment="下一轮起始的孤儿明细 ID（开区间）")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
