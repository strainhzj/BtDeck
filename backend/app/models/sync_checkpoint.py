# -*- coding: utf-8 -*-
"""
持久化同步检查点模型（W3-2，PLANS/sync-database-blocking-remediation.md）

覆盖问题：P1-03（全量同步状态仅在内存，重启后重复工作）。

游标、周期开始、最近完整同步和部分结果只存在于内存或日志文本中，重启、
取消或部署后无法可靠续跑和判断新鲜度。本表按 (downloader_id, sync_type)
持久化同步进度，使中断/重启后的同步能从最后一个 durable checkpoint 继续。

设计约束：
1. detail_json 只存聚合统计（scanned/changed/committed/batches/retries/
   duration_ms/version_conflicts 白名单），禁止种子 hash、Tracker URL、
   下载器凭据等敏感数据（sanitize_detail_json 落库前强制清洗）。
2. version 为乐观锁版本：更新一律走 ``UPDATE ... WHERE id=? AND version=?``，
   受影响行数=0 即并发冲突，由 SyncCoordinator 侧按“不倒退”策略重试。
3. outcome 六态与 SyncResult / W3-4 任务结果语义对齐：
   success / partial / skipped / failed / no_action / cancelled。
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.datetime_utils import serialize_utc_datetime

# =============================================================================
# outcome 常量（与 SyncResult / W3-4 统一枚举对齐）
# =============================================================================

OUTCOME_SUCCESS = "success"
OUTCOME_PARTIAL = "partial"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"
OUTCOME_NO_ACTION = "no_action"
OUTCOME_CANCELLED = "cancelled"

# 终态 outcome 集合：并发冲突合并时不允许被进行中状态降级覆盖
TERMINAL_OUTCOMES = frozenset({OUTCOME_SUCCESS, OUTCOME_FAILED, OUTCOME_SKIPPED, OUTCOME_NO_ACTION, OUTCOME_CANCELLED})

# detail_json 白名单：只存聚合统计，禁止种子 hash / Tracker URL / 下载器凭据。
# 新增 key 必须经 W3-4 / 安全评审确认无敏感信息后才能加入。
DETAIL_WHITELIST_KEYS = frozenset(
    {"scanned", "changed", "committed", "batches", "retries", "duration_ms", "version_conflicts"}
)


def sanitize_detail_json(detail: Optional[Dict[str, Any]]) -> Optional[str]:
    """清洗聚合统计 dict 到白名单 key 并序列化为 JSON 文本。

    - 非白名单 key 一律丢弃（敏感 key 不可能落库）；
    - 白名单 key 的值只接受数值（int/float/bool/None 或可转数值的字符串），
      其余类型丢弃，保证 detail_json 只是纯聚合数字；
    - 空结果返回 None（不落空串）。

    Args:
        detail: 调用方传入的聚合统计 dict（可能混入任意 key）。

    Returns:
        白名单清洗后的 JSON 文本；无有效内容返回 None。
    """
    if not detail:
        return None
    cleaned: Dict[str, Any] = {}
    for key, value in detail.items():
        if key not in DETAIL_WHITELIST_KEYS:
            continue
        if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
            cleaned[key] = value
            continue
        if isinstance(value, str):
            try:
                cleaned[key] = float(value)
            except (TypeError, ValueError):
                continue
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


class SyncCheckpoint(Base):
    """持久化同步检查点：按 (downloader_id, sync_type) 记录同步续跑进度。

    一行对应一个下载器 + 一种同步类型的进度状态；更新走 version 乐观锁，
    SyncCoordinator 在运行前读取、运行中（批次 durable commit 后）推进、
    运行后按最终 outcome 落终态。
    """

    __tablename__ = "sync_checkpoints"
    __table_args__ = (UniqueConstraint("downloader_id", "sync_type", name="uq_sync_checkpoints_downloader_sync_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    downloader_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="下载器标识")
    sync_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="同步类型：info/tracker/full"
    )
    cursor_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="透明游标字符串/JSON 文本（W3-1 起真正使用）"
    )
    cycle_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="当前周期开始时间")
    last_full_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近完整覆盖时间")
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近成功提交时间")
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最近尝试时间")
    outcome: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="success/partial/skipped/failed/no_action/cancelled（None=尚无完成记录）",
    )
    detail_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="聚合统计 JSON（白名单 key，不含敏感数据）"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="乐观锁版本")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )

    @property
    def detail(self) -> Dict[str, Any]:
        """解析聚合统计；坏数据按空 dict fail-closed。"""
        if not self.detail_json:
            return {}
        try:
            value = json.loads((self.detail_json))
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为 API/日志友好 dict（datetime 统一 UTC ISO 字符串）。"""

        # 注：ORM Column 属性在 mypy 下类型为 Column[datetime]，实例取值实为
        # datetime（可空列可能为 None），用 cast 显式收窄（与仓库基线一致）。
        def _fmt(value: Any) -> Optional[str]:
            return serialize_utc_datetime(value if isinstance(value, datetime) else None)

        return {
            "id": self.id,
            "downloader_id": self.downloader_id,
            "sync_type": self.sync_type,
            "cursor": self.cursor_value,
            "cycle_started_at": _fmt(self.cycle_started_at),
            "last_full_sync_at": _fmt(self.last_full_sync_at),
            "last_success_at": _fmt(self.last_success_at),
            "last_attempt_at": _fmt(self.last_attempt_at),
            "outcome": self.outcome,
            "detail": self.detail,
            "version": self.version,
            "created_at": _fmt(self.created_at),
            "updated_at": _fmt(self.updated_at),
        }
