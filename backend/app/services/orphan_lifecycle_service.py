# -*- coding: utf-8 -*-
"""
孤儿文件生命周期服务（v1.0.6+ 语义重做）

管理 OrphanCurrentCandidate 表的生命周期推进：
- 只有完整成功扫描才能推进候选状态（reconcile_candidates）
- 新发现 → insert candidate（first_seen_at=now，count=1）
- 已存在 → 更新 last_seen/count/status=candidate
- 未出现在新清单中的旧 candidate → status=resolved
- failed 扫描不调用此方法（不修改候选生命周期）

自动清理依据「连续成为孤儿的时间」（last_seen_at - first_seen_at），
不再依据文件 mtime。

@file: orphan_lifecycle_service.py
@time: 2026-07-11
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orphan_file import OrphanCurrentCandidate

logger = logging.getLogger(__name__)


class OrphanLifecycleService:
    """孤儿文件生命周期服务（异步）

    用法：
        service = OrphanLifecycleService(db)
        await service.reconcile_candidates(scan_id, scan_time, orphans)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def reconcile_candidates(
        self,
        scan_id: str,
        scan_time: datetime,
        orphans: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """对账候选状态（仅在完整成功扫描后调用）。

        语义：
        - 新发现的孤儿路径 → insert candidate
        - 已存在的 candidate → 更新 last_seen_at + scan_id + count+1 + status=candidate
        - 未出现在本次清单中的旧 candidate（status=candidate）→ status=resolved

        Args:
            scan_id: 本次扫描批次 ID
            scan_time: 本次扫描时间
            orphans: 本次扫描发现的孤儿列表，每项含 canonical_path/downloader_id/file_size/mtime_ns

        Returns:
            {"inserted": int, "updated": int, "resolved": int}
        """
        seen_paths = {o["canonical_path"] for o in orphans}

        # 查询所有当前 candidate/resolved 状态的候选（非 quarantined/purged）
        result = await self.db.execute(
            select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.status.in_(["candidate", "resolved"]))
        )
        existing = {c.canonical_path: c for c in result.scalars().all()}

        inserted = 0
        updated = 0
        resolved = 0

        # 处理本次发现的孤儿
        for orphan in orphans:
            path = orphan["canonical_path"]
            existing_cand = existing.get(path)
            if existing_cand is None:
                # 新发现 → insert（first_seen_at 用 scan_time，反映实际首次发现时间）
                candidate = OrphanCurrentCandidate(
                    canonical_path=path,
                    downloader_id=orphan.get("downloader_id", ""),
                    first_seen_at=scan_time,
                    last_seen_at=scan_time,
                    last_seen_scan_id=scan_id,
                    consecutive_scan_count=1,
                    status="candidate",
                    file_size=orphan.get("file_size", 0),
                    mtime_ns=orphan.get("mtime_ns"),
                    device_id=orphan.get("device_id"),
                    inode=orphan.get("inode"),
                )
                self.db.add(candidate)
                inserted += 1
            else:
                # 已存在 → 更新（重新确认为孤儿，如果是 resolved 则复活为 candidate）
                existing_cand.last_seen_at = scan_time
                existing_cand.last_seen_scan_id = scan_id
                existing_cand.consecutive_scan_count = existing_cand.consecutive_scan_count + 1
                existing_cand.status = "candidate"
                existing_cand.file_size = orphan.get("file_size", existing_cand.file_size)
                if orphan.get("mtime_ns") is not None:
                    existing_cand.mtime_ns = orphan["mtime_ns"]
                updated += 1

        # 处理未出现在本次清单中的旧 candidate → resolved
        for path, cand in existing.items():
            if path not in seen_paths and cand.status == "candidate":
                cand.status = "resolved"
                resolved += 1

        await self.db.commit()

        logger.info(
            f"[孤儿生命周期] scan_id={scan_id} 对账完成: " f"新增 {inserted}，更新 {updated}，标记 resolved {resolved}"
        )
        return {"inserted": inserted, "updated": updated, "resolved": resolved}

    async def get_purgeable_candidates(self, days_threshold: int) -> List[OrphanCurrentCandidate]:
        """获取满足清理条件的候选（连续成为孤儿的时间 > days_threshold 天）。

        清理依据「连续成为孤儿的时间」（last_seen_at - first_seen_at），不再依据 mtime。
        只返回 status=candidate 的候选。

        Args:
            days_threshold: 连续孤儿天数阈值

        Returns:
            满足条件的候选列表
        """
        cutoff = datetime.utcnow() - timedelta(days=days_threshold)
        result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.status == "candidate",
                OrphanCurrentCandidate.first_seen_at < cutoff,
            )
        )
        candidates = result.scalars().all()
        # 二次校验：last_seen_at - first_seen_at >= days_threshold
        purgeable = []
        for c in candidates:
            duration = (c.last_seen_at - c.first_seen_at).total_seconds() / 86400
            if duration >= days_threshold:
                purgeable.append(c)
        return purgeable

    async def mark_quarantined(
        self,
        canonical_path: str,
        quarantine_path: str,
        purge_after: datetime,
    ) -> bool:
        """标记候选为已隔离。

        Args:
            canonical_path: 规范化路径
            quarantine_path: 隔离区路径
            purge_after: 允许物理删除时间

        Returns:
            是否成功更新
        """
        now = datetime.utcnow()
        result = await self.db.execute(
            update(OrphanCurrentCandidate)
            .where(OrphanCurrentCandidate.canonical_path == canonical_path)
            .values(
                status="quarantined",
                quarantine_path=quarantine_path,
                quarantined_at=now,
                purge_after=purge_after,
            )
        )
        await self.db.commit()
        return result.rowcount > 0

    async def mark_purged(self, canonical_path: str) -> bool:
        """标记候选为已物理删除。"""
        result = await self.db.execute(
            update(OrphanCurrentCandidate)
            .where(OrphanCurrentCandidate.canonical_path == canonical_path)
            .values(status="purged")
        )
        await self.db.commit()
        return result.rowcount > 0

    async def get_latest_scan_status(self) -> Optional[Dict[str, Any]]:
        """获取最新扫描批次的状态（用于清理门禁判断）。"""
        from app.models.orphan_file import OrphanScanResult

        result = await self.db.execute(select(OrphanScanResult).order_by(OrphanScanResult.scan_time.desc()).limit(1))
        record = result.scalar_one_or_none()
        if not record:
            return None
        return {
            "scan_id": record.scan_id,
            "status": record.status,
            "scan_time": record.scan_time,
        }
