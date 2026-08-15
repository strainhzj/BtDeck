# -*- coding: utf-8 -*-
"""
孤儿文件管理服务（v1.0.6+ 语义重做）

提供孤儿文件查询、清理预览、手动清理、自动清理超期等功能。

语义重做：
- 最新扫描 running/failed 时禁止清理（preview 与 cleanup 相同新鲜度规则）
- 旧 scan_id 禁止预览和清理（stale ID 返回明确拒绝原因）
- 手动清理删除前重建实时 manifest 复核文件身份（size/mtime_ns/inode/路径逃逸/符号链接）
- 自动清理先移入隔离区（不直接删除），保留期到期后独立任务物理删除
- 不提供 force 绕过

@file: orphan_file_service.py
@time: 2026-07-10
"""

import asyncio
import logging
import os
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Sequence, TypeVar, cast

from sqlalchemy import and_, case, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.services.orphan_folder_grouping import orphan_parent_dir
from app.services.orphan_lifecycle_service import OrphanLifecycleService
from app.services.orphan_manifest import (
    ManifestSnapshot,
    TorrentManifestBuilder,
    normalize_path,
)
from app.services.orphan_purge_job_service import (
    active_cleanup_orphan_ids_query,
    active_purge_canonical_paths_query,
)
from app.services.orphan_quarantine import (
    build_quarantine_path,
    compute_purge_after,
    collect_runtime_accessible_roots,
    find_hardlink_copies,
    find_hardlink_paths,
    get_hardlink_copy_count,
    prune_empty_quarantine_parents,
    prune_recorded_quarantine_root,
    quarantine_file,
    resolve_quarantine_root,
    verify_file_identity,
)
from app.tasks.resource_guard import admission_controller
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType
from app.core.config import settings

logger = logging.getLogger(__name__)

SelectionValue = TypeVar("SelectionValue")
ORPHAN_QUERY_CHUNK_SIZE = 500
ORPHAN_PREVIEW_ITEM_LIMIT = 200


class HardlinkCopyError(Exception):
    """到期删除遇硬链接副本时抛出，由上层捕获以跳过删除（安全优先）。

    attributes:
        canonical_path: 候选规范化路径
        quarantine_path: 隔离区物理路径
        copies: 已检测到的副本列表（path + is_seed）；枚举失败时为空
        reason: 跳过原因（供 failed_list 展示）
    """

    def __init__(
        self,
        canonical_path: str,
        quarantine_path: Optional[str],
        copies: List[Dict[str, Any]],
        *,
        reason: str,
    ) -> None:
        super().__init__(reason)
        self.canonical_path = canonical_path
        self.quarantine_path = quarantine_path
        self.copies = copies
        self.reason = reason


def _chunk_values(values: Sequence[SelectionValue]) -> Iterator[Sequence[SelectionValue]]:
    """按保守的 SQLite 绑定变量数量切分查询参数。"""
    for start in range(0, len(values), ORPHAN_QUERY_CHUNK_SIZE):
        yield values[start : start + ORPHAN_QUERY_CHUNK_SIZE]


class OrphanFileService:
    """孤儿文件管理服务（异步）"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _detail_canonical_path(detail: OrphanFile) -> str:
        """返回扫描明细的稳定候选身份。"""
        canonical_path = cast(Optional[str], detail.canonical_path)
        return canonical_path or normalize_path(cast(str, detail.file_path))

    @staticmethod
    def _sync_candidate_owner(
        candidate: OrphanCurrentCandidate,
        detail: OrphanFile,
    ) -> bool:
        """在同一候选快照内同步归属下载器，返回是否发生修正。

        canonical_path 是候选表主键；downloader_id 是随扫描范围变化的归属
        元数据。只在候选尚无 last_seen_scan_id，或候选与明细属于同一扫描
        快照时修正，避免旧页面操作覆盖更新扫描已经确认的新归属。
        """
        current_owner = cast(Optional[str], detail.downloader_id) or ""
        if cast(str, candidate.downloader_id) == current_owner:
            return False
        if cast(Optional[str], candidate.last_seen_scan_id) not in (
            None,
            cast(str, detail.scan_id),
        ):
            return False
        setattr(candidate, "downloader_id", current_owner)
        return True

    @staticmethod
    def _current_detail_ids_query(scan_id: str) -> Any:
        """返回增量模式的稳定当前明细 ID 集合。

        ``scan_id`` 用于保持调用契约并由上层校验明细模式；集合本身由候选当前态
        决定。这样批处理写入中途失败后，旧成功扫描仍能只读展示稳定明细，清理
        则由最新扫描非 completed 的门禁继续阻断。
        """
        del scan_id
        return select(OrphanCurrentCandidate.current_detail_id).where(
            OrphanCurrentCandidate.current_detail_id.isnot(None),
            OrphanCurrentCandidate.status != "resolved",
        )

    @staticmethod
    def _build_orphan_conditions(
        scan_id: str,
        *,
        current_mode: bool = False,
        downloader_id: Optional[str] = None,
        min_size: Optional[int] = None,
        include_deleted: bool = False,
        path_like: Optional[str] = None,
        path_prefix: Optional[str] = None,
        status: Optional[str] = None,
        confidence: Optional[str] = None,
    ) -> List[Any]:
        """构建列表与“全选当前筛选”共用的 SQL 条件。"""
        detail_scope = (
            OrphanFile.id.in_(OrphanFileService._current_detail_ids_query(scan_id))
            if current_mode
            else OrphanFile.scan_id == scan_id
        )
        conditions: List[Any] = [
            detail_scope,
            OrphanFile.id.notin_(active_cleanup_orphan_ids_query()),
        ]

        # status 三态互斥（一个文件只可能是 pending/ignored/deleted 之一）：
        # - pending：未删除 且 不在忽视集
        # - ignored：未删除 且 在忽视集
        # - deleted：已删除
        # 支持逗号分隔多值：每个值用 and_() 打包完整条件，多值时用 or_() 取并集。
        # 注意：pending 与 ignored/deleted 组合时，OR 会让 is_deleted/忽视集条件退化为
        # “所有未删除文件”，这是用户明确的“OR 并集”语义（前端会给提示）。
        ignored_paths = select(OrphanCurrentCandidate.canonical_path).where(
            OrphanCurrentCandidate.is_ignored == True  # noqa: E712
        )
        if status:
            statuses = list(dict.fromkeys(s.strip() for s in status.split(",") if s.strip()))
            status_clauses: List[Any] = []
            for s in statuses:
                if s == "deleted":
                    status_clauses.append(OrphanFile.is_deleted == True)  # noqa: E712
                elif s == "ignored":
                    status_clauses.append(
                        and_(
                            OrphanFile.is_deleted == False,  # noqa: E712
                            OrphanFile.canonical_path.in_(ignored_paths),
                        )
                    )
                elif s == "pending":
                    status_clauses.append(
                        and_(
                            OrphanFile.is_deleted == False,  # noqa: E712
                            OrphanFile.canonical_path.notin_(ignored_paths),
                        )
                    )
            if len(status_clauses) == 1:
                conditions.append(status_clauses[0])
            elif status_clauses:
                conditions.append(or_(*status_clauses))
            elif not include_deleted:
                # status 传入但 split 后无有效值（如 ","），回落到默认排除已删除
                conditions.append(OrphanFile.is_deleted == False)  # noqa: E712
        elif not include_deleted:
            # 无 status 筛选时默认排除已删除（与历史行为一致）
            conditions.append(OrphanFile.is_deleted == False)  # noqa: E712

        if downloader_id:
            # 支持多选：逗号分隔的字符串（与 duplicate_torrents 多值过滤范式一致）
            downloader_ids = list(dict.fromkeys(d.strip() for d in downloader_id.split(",") if d.strip()))
            if len(downloader_ids) == 1:
                conditions.append(OrphanFile.downloader_id == downloader_ids[0])
            else:
                conditions.append(OrphanFile.downloader_id.in_(downloader_ids))
        if min_size is not None:
            conditions.append(OrphanFile.file_size >= min_size)
        if confidence:
            # 支持多选：逗号分隔的字符串
            confidences = list(dict.fromkeys(c.strip() for c in confidence.split(",") if c.strip()))
            if len(confidences) == 1:
                conditions.append(OrphanFile.confidence == confidences[0])
            else:
                conditions.append(OrphanFile.confidence.in_(confidences))
        if path_like:
            escaped = path_like.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(OrphanFile.file_path.like(f"%{escaped}%", escape="\\"))
        # 左匹配（前缀）独立于 path_like（包含匹配）：file_path LIKE 'prefix%'。
        # 与 path_like 同样的转义规则，仅尾部追加 %。注：SQLite LIKE 对 ASCII 大小写
        # 不敏感，Windows 盘符 D:\ 与 d:\ 可互通，符合文件系统语义。
        if path_prefix:
            escaped_pfx = path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(OrphanFile.file_path.like(f"{escaped_pfx}%", escape="\\"))
        return conditions

    @staticmethod
    def _orphan_order_columns() -> tuple:
        """构造孤儿文件列表的稳定排序键（confidence_rank, ignored_rank）。

        - confidence_rank：高置信度=0（靠前），低置信度=1。
        - ignored_rank：已忽视=1（沉底），其余=0。

        供 get_orphan_list 与 get_orphan_list_grouped 共用，避免排序逻辑漂移。
        组内最终排序为 ``confidence_rank, ignored_rank, file_size DESC, id ASC``。
        """
        confidence_rank = case(
            (OrphanFile.confidence == "high", 0),
            else_=1,
        )
        ignored_paths_subq = select(OrphanCurrentCandidate.canonical_path).where(
            OrphanCurrentCandidate.is_ignored == True  # noqa: E712
        )
        ignored_rank = case(
            (OrphanFile.canonical_path.in_(ignored_paths_subq), 1),
            else_=0,
        )
        return confidence_rank, ignored_rank

    async def resolve_orphan_selection(
        self,
        *,
        orphan_ids: Sequence[int],
        select_all: bool,
        excluded_orphan_ids: Sequence[int],
        scan_id: Optional[str],
        downloader_id: Optional[str] = None,
        min_size: Optional[int] = None,
        path_like: Optional[str] = None,
        path_prefix: Optional[str] = None,
        status: Optional[str] = None,
        confidence: Optional[str] = None,
    ) -> List[int]:
        """把显式勾选或当前筛选全集解析为稳定的明细 ID 快照。"""
        normalized_ids = list(dict.fromkeys(int(orphan_id) for orphan_id in orphan_ids if int(orphan_id) > 0))
        if not select_all:
            if not normalized_ids:
                raise ValueError("至少需要选择一个孤儿文件")
            return normalized_ids
        if not scan_id:
            raise ValueError("全选当前筛选结果必须绑定扫描批次")

        scan_record = await self._get_scan(scan_id)
        conditions = self._build_orphan_conditions(
            scan_id,
            current_mode=bool(scan_record and scan_record.details_mode == "current"),
            downloader_id=downloader_id,
            min_size=min_size,
            path_like=path_like,
            path_prefix=path_prefix,
            status=status,
            confidence=confidence,
        )
        query = select(OrphanFile.id).order_by(OrphanFile.id.asc())
        for condition in conditions:
            query = query.where(condition)
        result = await self.db.execute(query)
        excluded = {int(orphan_id) for orphan_id in excluded_orphan_ids}
        return [int(orphan_id) for orphan_id in result.scalars().all() if int(orphan_id) not in excluded]

    async def _load_orphan_details(
        self,
        orphan_ids: Sequence[int],
        *,
        scan_id: Optional[str],
        exclude_ignored: bool = False,
        exclude_in_flight: bool = False,
    ) -> List[OrphanFile]:
        """分块加载明细，避免大批量全选触发 SQLite 绑定变量上限。"""
        normalized_ids = list(dict.fromkeys(int(orphan_id) for orphan_id in orphan_ids))
        details_by_id: Dict[int, OrphanFile] = {}
        current_mode = False
        if scan_id:
            scan_record = await self._get_scan(scan_id)
            current_mode = bool(scan_record and scan_record.details_mode == "current")
        for chunk in _chunk_values(normalized_ids):
            conditions: List[Any] = [
                OrphanFile.id.in_(list(chunk)),
                OrphanFile.is_deleted == False,  # noqa: E712
            ]
            if scan_id:
                if current_mode:
                    conditions.append(OrphanFile.id.in_(self._current_detail_ids_query(scan_id)))
                else:
                    conditions.append(OrphanFile.scan_id == scan_id)
            if exclude_ignored:
                conditions.append(
                    OrphanFile.canonical_path.notin_(
                        select(OrphanCurrentCandidate.canonical_path).where(
                            OrphanCurrentCandidate.is_ignored == True  # noqa: E712
                        )
                    )
                )
            if exclude_in_flight:
                conditions.append(OrphanFile.id.notin_(active_cleanup_orphan_ids_query()))
            result = await self.db.execute(select(OrphanFile).where(*conditions))
            for detail in result.scalars().all():
                details_by_id[int(detail.id)] = detail
        return [details_by_id[orphan_id] for orphan_id in normalized_ids if orphan_id in details_by_id]

    async def _load_candidates(
        self,
        canonical_paths: Sequence[str],
        *,
        stable_only: bool = False,
    ) -> Dict[str, OrphanCurrentCandidate]:
        """按规范化路径分块加载候选。"""
        normalized_paths = list(dict.fromkeys(str(path) for path in canonical_paths if path))
        candidates: Dict[str, OrphanCurrentCandidate] = {}
        for chunk in _chunk_values(normalized_paths):
            conditions: List[Any] = [OrphanCurrentCandidate.canonical_path.in_(list(chunk))]
            if stable_only:
                conditions.extend(
                    [
                        OrphanCurrentCandidate.status == "candidate",
                        OrphanCurrentCandidate.operation_state == "stable",
                    ]
                )
            result = await self.db.execute(select(OrphanCurrentCandidate).where(*conditions))
            for candidate in result.scalars().all():
                candidates[cast(str, candidate.canonical_path)] = candidate
        return candidates

    # ==================== 新鲜度门禁 ====================

    async def _get_latest_scan(self, *, status: Optional[str] = None) -> Optional[OrphanScanResult]:
        """按统一稳定顺序获取最新扫描记录。"""
        query = select(OrphanScanResult)
        if status is not None:
            query = query.where(OrphanScanResult.status == status)
        result = await self.db.execute(
            query.order_by(
                OrphanScanResult.scan_time.desc(),
                OrphanScanResult.created_at.desc(),
                OrphanScanResult.scan_id.desc(),
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_scan(self, scan_id: str) -> Optional[OrphanScanResult]:
        result = await self.db.execute(select(OrphanScanResult).where(OrphanScanResult.scan_id == scan_id))
        return result.scalar_one_or_none()

    @staticmethod
    def _evaluate_cleanup_snapshot(
        latest_attempt: Optional[OrphanScanResult],
        scan_id: Optional[str],
    ) -> Dict[str, Any]:
        """纯判定扫描快照是否仍具备清理资格。

        超量扫描字段只用于页面提醒，不再作为清理门禁；清理仍要求最新扫描
        已成功完成，并绑定同一批次的 scan_id。
        """
        if latest_attempt is None:
            return {
                "allowed": False,
                "reason": "无任何扫描记录",
                "latest_scan_id": None,
            }
        if latest_attempt.status != "completed":
            return {
                "allowed": False,
                "reason": (f"最新扫描状态为 {latest_attempt.status}（非 completed），禁止清理"),
                "latest_scan_id": latest_attempt.scan_id,
            }
        if not scan_id:
            return {
                "allowed": False,
                "reason": "scan_id 必填，预览和清理必须绑定明确扫描快照",
                "latest_scan_id": latest_attempt.scan_id,
            }
        if scan_id != latest_attempt.scan_id:
            return {
                "allowed": False,
                "reason": (
                    f"scan_id {scan_id} 不是最新扫描批次" f"（最新为 {latest_attempt.scan_id}），stale ID 拒绝清理"
                ),
                "latest_scan_id": latest_attempt.scan_id,
            }
        return {
            "allowed": True,
            "reason": None,
            "latest_scan_id": latest_attempt.scan_id,
        }

    async def _check_cleanup_allowed(self, scan_id: Optional[str] = None) -> Dict[str, Any]:
        """检查是否允许清理（preview 与 cleanup 共用相同新鲜度规则）。

        规则：
        - 最新扫描必须 status=completed（running/failed 禁止清理）
        - 如提供 scan_id，必须等于最新扫描的 scan_id（stale ID 拒绝）

        Returns:
            {"allowed": bool, "reason": str, "latest_scan_id": str}
        """
        latest = await self._get_latest_scan()
        return self._evaluate_cleanup_snapshot(latest, scan_id)

    async def _build_realtime_manifest(
        self, store: Any, required_downloader_ids: Optional[set] = None
    ) -> Optional[ManifestSnapshot]:
        """重建实时文件清单（用于清理前复核文件是否仍被种子引用）。

        复用 OrphanScanner 的文件清单构建逻辑（不写 DB）。
        返回当前所有种子引用的规范化路径集合。

        Args:
            store: app.state.store

        Returns:
            规范化路径集合（None 表示 manifest 构建失败 → 调用方 fail-closed）
        """
        try:
            return await TorrentManifestBuilder(store).build(required_downloader_ids=required_downloader_ids)
        except Exception as e:
            logger.warning(f"[孤儿清理] 实时 manifest 构建失败: {e}")
            return None

    @staticmethod
    def _identity_complete(candidate: OrphanCurrentCandidate) -> bool:
        return all(
            value is not None
            for value in (
                candidate.file_size,
                candidate.mtime_ns,
                candidate.device_id,
                candidate.inode,
            )
        )

    @staticmethod
    def _candidate_inode(candidate: OrphanCurrentCandidate) -> tuple[int, int]:
        return int(candidate.device_id), int(candidate.inode)

    @staticmethod
    def _path_authorized(candidate: OrphanCurrentCandidate, manifest: ManifestSnapshot) -> bool:
        # 纵深防御：回收站归档路径无条件拒绝清理/隔离，即使扫描侧门禁失效（历史误判
        # 候选仍残留在 orphan_current_candidate 中）也不误处理。隔离区路径同理拒绝。
        # 这保护已写入候选池的 Level3 回收站文件不被定时任务移隔离→物理删除。
        recycle_tag = getattr(settings, "ORPHAN_RECYCLE_BIN_TAG", ".pending_delete") or ""
        if recycle_tag and recycle_tag in candidate.canonical_path:
            logger.warning(
                "[孤儿清理] 拒绝处理 Level3 回收站路径（历史误判候选保护）: %s",
                candidate.canonical_path,
            )
            return False
        quarantine_dir_name = getattr(settings, "ORPHAN_QUARANTINE_DIR_NAME", ".btdeck_quarantine")
        if quarantine_dir_name and quarantine_dir_name in candidate.canonical_path:
            return False
        if candidate.downloader_id not in manifest.downloader_ids:
            return False
        candidate_path = os.path.realpath(candidate.canonical_path)
        for root, owners in manifest.scan_roots:
            # 共享根场景：候选 downloader_id 是该根任一 owner 即授权
            if candidate.downloader_id not in owners:
                continue
            try:
                if os.path.commonpath([candidate_path, os.path.realpath(root)]) == os.path.realpath(root):
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _path_in_quarantine_root(path: Optional[str], quarantine_root: Optional[str]) -> bool:
        """判断一个已记录的隔离路径是否严格位于隔离根内。

        隔离区物理删除只信任数据库中持久化的 ``quarantine_path`` 和
        ``quarantine_root``。这里不使用 downloader 的 scan_root，也不把
        ``canonical_path`` 重新映射成物理路径。符号链接本身拒绝处理，避免
        ``realpath`` 将其解析到隔离根之外后误放行。
        """
        if not path or not quarantine_root:
            return False
        if not os.path.isabs(path) or not os.path.isabs(quarantine_root):
            return False
        if os.path.islink(path) or os.path.islink(quarantine_root):
            return False

        try:
            path_real = os.path.realpath(path)
            root_real = os.path.realpath(quarantine_root)
            if os.path.normcase(path_real) == os.path.normcase(root_real):
                return False
            common_path = os.path.commonpath([path_real, root_real])
            return os.path.normcase(common_path) == os.path.normcase(root_real)
        except ValueError:
            return False

    @staticmethod
    def _quarantine_path_authorized(
        candidate: OrphanCurrentCandidate,
        _manifest: Optional[ManifestSnapshot] = None,
    ) -> bool:
        """校验已隔离文件的物理删除范围。

        ``manifest`` 参数保留为兼容参数，但故意不参与判断。文件一旦完成
        隔离，物理删除对象就是记录中的 ``quarantine_path``；再用下载器的
        原始路径映射或实时 ``downloader_ids`` 授权会把映射异常误判成隔离
        区越权，并再次产生 ``/Downloads/ipan/Downloads/...`` 一类错误路径。
        实时 manifest 只适用于“原始文件是否仍被种子引用”的扫描阶段，不是
        隔离区物理删除的路径来源。
        """
        return OrphanFileService._path_in_quarantine_root(
            candidate.quarantine_path,
            candidate.quarantine_root,
        )

    @staticmethod
    def _quarantine_delete_guard_error(candidate: OrphanCurrentCandidate) -> Optional[str]:
        """返回隔离区物理删除的路径安全校验错误。"""
        if not OrphanFileService._quarantine_path_authorized(candidate):
            return "隔离记录的 quarantine_path 不在 quarantine_root 内，拒绝删除"
        return None

    async def _ensure_quarantine_identity(
        self,
        candidate: OrphanCurrentCandidate,
        file_path: str,
    ) -> Optional[str]:
        """为旧版隔离记录补齐身份字段，并验证已有字段未发生变化。

        ``orphan_current_candidate`` 的身份字段历史上允许为空，旧版本已经
        移入隔离区的记录因此无法通过新的 inode/mtime 安全门禁。此处只对
        已持久化且已通过隔离根校验的文件执行补齐：已存在的字段必须先匹配，
        文件大小也必须匹配；任何不匹配都仍然 fail-closed。补齐后的字段会
        随后续 purge 状态提交持久化，避免每次重试都重新进入兼容分支。
        """
        if self._identity_complete(candidate):
            return None

        try:
            ok, reason = verify_file_identity(
                file_path,
                expected_size=candidate.file_size,
                expected_mtime_ns=candidate.mtime_ns,
            )
            if not ok:
                return f"隔离文件身份复核失败: {reason}"

            stat_info = os.stat(file_path, follow_symlinks=False)
            if candidate.device_id is not None and int(candidate.device_id) != stat_info.st_dev:
                return "隔离文件 device_id 与记录不一致，拒绝删除"
            if candidate.inode is not None and int(candidate.inode) != stat_info.st_ino:
                return "隔离文件 inode 与记录不一致，拒绝删除"

            candidate.file_size = stat_info.st_size
            candidate.mtime_ns = stat_info.st_mtime_ns
            candidate.device_id = str(stat_info.st_dev)
            candidate.inode = str(stat_info.st_ino)
            logger.warning(
                "[隔离删除] 已为旧版隔离记录补齐身份字段 canonical=%s quarantine=%s",
                candidate.canonical_path,
                file_path,
            )
            return None
        except (OSError, TypeError, ValueError) as exc:
            return f"隔离记录身份字段无效，拒绝删除: {exc}"

    @staticmethod
    def _authorize_low_confidence(candidate: OrphanCurrentCandidate, manifest: ManifestSnapshot) -> bool:
        """低置信度候选的授权复核（分流优化）。

        low 候选的 downloader 在扫描时处于离线/降级状态。删除前分两种情况：
        - downloader 已重新上线且精筛成功（在 manifest.downloader_ids）→ 走标准
          _path_authorized，保留「下载器恢复后可清理」的合法路径。
        - downloader 仍降级/离线（不在 manifest.downloader_ids）→ 用 manifest 的
          directory_whitelist（降级种子目录 + DB 种子目录）做目录级复核：候选文件
          不落在任何已知种子目录下才放行，与扫描期目录粗筛语义一致（fail-closed）。

        安全底线：目录白名单兜底仍是 fail-closed——文件若落在任一已知种子目录则拒绝。
        verify_file_identity（size/mtime_ns/inode）在调用方照常执行，不受此复核影响。
        """
        if candidate.downloader_id in manifest.downloader_ids:
            return OrphanFileService._path_authorized(candidate, manifest)
        # downloader 仍离线：目录白名单兜底（文件不被任何已知种子目录覆盖才可清理）
        try:
            norm_path = normalize_path(candidate.canonical_path)
        except (ValueError, OSError):
            return False
        for directory in manifest.directory_whitelist:
            try:
                # 白名单目录统一用 normalize_path 规范化，与候选路径同口径
                # （Windows normcase 小写化 + normpath），确保 commonpath 比较正确。
                norm_dir = normalize_path(directory)
                if os.path.commonpath([norm_path, norm_dir]) == norm_dir:
                    # 落在已知种子目录内 → 可能被引用，拒绝（fail-closed）
                    return False
            except (ValueError, OSError):
                continue
        return True

    @staticmethod
    def _owning_root(candidate: OrphanCurrentCandidate, manifest: ManifestSnapshot) -> Optional[str]:
        matches = []
        candidate_path = os.path.realpath(candidate.canonical_path)
        for root, owners in manifest.scan_roots:
            if candidate.downloader_id not in owners:
                continue
            try:
                if os.path.commonpath([candidate_path, os.path.realpath(root)]) == os.path.realpath(root):
                    matches.append(root)
            except ValueError:
                continue
        return max(matches, key=len) if matches else None

    # ==================== 查询 ====================

    async def get_latest_scan_result(self) -> Optional[Dict[str, Any]]:
        """获取最新扫描批次结果"""
        record = await self._get_latest_scan()
        if not record:
            return None
        return record.to_dict()

    @staticmethod
    def _inspect_hardlink_sources(targets: Sequence[tuple[int, str]]) -> List[Dict[str, Any]]:
        """顺序读取源文件 inode/nlink；由调用方放入线程，避免阻塞事件循环。"""
        inspected: List[Dict[str, Any]] = []
        for orphan_id, file_path in targets:
            try:
                stat_result = os.stat(file_path)
            except OSError:
                inspected.append(
                    {
                        "orphan_id": orphan_id,
                        "file_path": file_path,
                        "identity": None,
                        "copy_count": None,
                        "error": "源文件不可访问，无法重新核对副本位置",
                    }
                )
                continue
            inspected.append(
                {
                    "orphan_id": orphan_id,
                    "file_path": file_path,
                    "identity": (int(stat_result.st_dev), int(stat_result.st_ino)),
                    "copy_count": max(int(stat_result.st_nlink) - 1, 0),
                    "error": None,
                }
            )
        return inspected

    async def get_hardlink_copy_locations(self, orphan_ids: Sequence[int]) -> Dict[str, Any]:
        """按需定位孤儿文件在当前运行环境可访问目录内的其它硬链接路径。

        ``st_nlink - 1`` 仍是副本总数的权威口径；具体位置只能通过目录遍历反查。
        本方法收集当前进程可访问、与目标 inode 同文件系统的挂载根，并对多个目标
        合并为一轮扫描。无权限或未挂载目录中的链接会计入 ``unlocated_count``。
        """
        normalized_ids = list(dict.fromkeys(int(orphan_id) for orphan_id in orphan_ids))
        if not normalized_ids:
            raise ValueError("至少需要一个孤儿文件 ID")

        details = await self._load_orphan_details(
            normalized_ids,
            scan_id=None,
            exclude_in_flight=False,
        )
        detail_ids = {int(detail.id) for detail in details}
        missing_orphan_ids = [orphan_id for orphan_id in normalized_ids if orphan_id not in detail_ids]
        targets = [(int(detail.id), cast(str, detail.file_path)) for detail in details]
        inspected = await asyncio.to_thread(self._inspect_hardlink_sources, targets)

        target_inodes = {
            cast(tuple[int, int], item["identity"])
            for item in inspected
            if item["identity"] is not None and int(item["copy_count"] or 0) > 0
        }
        scan_roots: List[str] = []
        paths_by_inode: Dict[tuple[int, int], List[str]] = {}
        search_error: Optional[str] = None
        if target_inodes:
            try:
                source_paths = [
                    cast(str, item["file_path"])
                    for item in inspected
                    if item["identity"] is not None and int(item["copy_count"] or 0) > 0
                ]
                scan_roots = await asyncio.to_thread(
                    collect_runtime_accessible_roots,
                    target_inodes,
                    source_paths,
                )
                paths_by_inode = await asyncio.to_thread(
                    find_hardlink_paths,
                    target_inodes,
                    scan_roots,
                )
            except Exception as exc:
                search_error = "当前运行环境可访问目录扫描失败，未能完整定位副本位置"
                logger.warning("[孤儿列表] 硬链接副本位置扫描失败: %s", exc)

        items: List[Dict[str, Any]] = []
        for inspected_item in inspected:
            source_path = cast(str, inspected_item["file_path"])
            copy_count = cast(Optional[int], inspected_item["copy_count"])
            identity = cast(Optional[tuple[int, int]], inspected_item["identity"])
            copies: List[str] = []
            if identity is not None and copy_count is not None and copy_count > 0:
                source_key = os.path.normcase(os.path.realpath(os.path.abspath(source_path)))
                copies = [
                    path
                    for path in paths_by_inode.get(identity, [])
                    if os.path.normcase(os.path.realpath(path)) != source_key
                ]
            found_count = len(copies)
            unlocated_count = max(copy_count - found_count, 0) if copy_count is not None else None
            item_error = cast(Optional[str], inspected_item["error"])
            if item_error is None and search_error is not None and copy_count:
                item_error = search_error
            items.append(
                {
                    "orphan_id": inspected_item["orphan_id"],
                    "file_path": source_path,
                    "copy_count": copy_count,
                    "found_count": found_count,
                    "unlocated_count": unlocated_count,
                    "copies": copies,
                    "error": item_error,
                }
            )

        known_items = [item for item in items if item["copy_count"] is not None]
        return {
            "requested_count": len(normalized_ids),
            "resolved_count": len(details),
            "missing_orphan_ids": missing_orphan_ids,
            "total_copy_count": sum(int(item["copy_count"]) for item in known_items),
            "total_found_count": sum(int(item["found_count"]) for item in items),
            "total_unlocated_count": sum(int(item["unlocated_count"] or 0) for item in known_items),
            "unknown_count": len(items) - len(known_items),
            "searched_root_count": len(scan_roots),
            "search_error": search_error,
            "items": items,
        }

    async def get_orphan_list(
        self,
        page: int = 1,
        page_size: int = 20,
        downloader_id: Optional[str] = None,
        min_size: Optional[int] = None,
        include_deleted: bool = False,
        path_like: Optional[str] = None,
        path_prefix: Optional[str] = None,
        status: Optional[str] = None,
        confidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询孤儿文件列表与同一批次的页面扫描上下文。

        Args:
            path_like: 文件路径模糊匹配（LIKE %path_like%）。
            path_prefix: 文件路径左匹配（LIKE prefix%），与 path_like 独立叠加（AND）。
            status: 状态筛选——pending=待清理（默认，未删除未忽视）、
                ignored=已忽视（联表候选 is_ignored=1）、deleted=已清理。
                None 时等价 pending+deleted 由 include_deleted 控制（兼容旧调用）。
            confidence: 置信度筛选——high=高置信度，low=低置信度。

        Returns:
            分页字段与 scan_context。扫描原始量保留在 display_scan，
            remaining_* 表示该展示批次尚未清理的全量。
        """
        latest_attempt = await self._get_latest_scan()
        display_scan: Optional[OrphanScanResult] = None
        if latest_attempt is not None:
            if latest_attempt.status == "completed":
                display_scan = latest_attempt
            elif latest_attempt.status == "failed":
                display_scan = await self._get_latest_scan(status="completed")

        gate = self._evaluate_cleanup_snapshot(
            latest_attempt,
            display_scan.scan_id if display_scan is not None else None,
        )
        scan_context: Dict[str, Any] = {
            "latest_attempt": latest_attempt.to_dict() if latest_attempt is not None else None,
            "display_scan": display_scan.to_dict() if display_scan is not None else None,
            "remaining_count": 0,
            "remaining_size": 0,
            "ignored_count": 0,
            "cleanup_allowed": gate["allowed"],
            "cleanup_block_reason": gate["reason"],
        }
        if display_scan is None:
            return {
                "total": 0,
                "page": page,
                "pageSize": page_size,
                "list": [],
                "scan_context": scan_context,
            }

        current_mode = str(display_scan.details_mode or "snapshot") == "current"
        detail_scope = (
            OrphanFile.id.in_(self._current_detail_ids_query(cast(str, display_scan.scan_id)))
            if current_mode
            else OrphanFile.scan_id == display_scan.scan_id
        )

        remaining_result = await self.db.execute(
            select(
                func.count(OrphanFile.id),
                func.coalesce(func.sum(OrphanFile.file_size), 0),
            ).where(
                detail_scope,
                OrphanFile.is_deleted == False,  # noqa: E712
                OrphanFile.id.notin_(active_cleanup_orphan_ids_query()),
            )
        )
        remaining_count, remaining_size = remaining_result.one()
        scan_context["remaining_count"] = int(remaining_count or 0)
        scan_context["remaining_size"] = int(remaining_size or 0)

        # 本展示批次中对应候选被忽视的数量（与 remaining_* 同口径，基于 display_scan.scan_id）
        ignored_count_result = await self.db.execute(
            select(func.count(OrphanFile.id)).where(
                detail_scope,
                OrphanFile.is_deleted == False,  # noqa: E712
                OrphanFile.id.notin_(active_cleanup_orphan_ids_query()),
                OrphanFile.canonical_path.in_(
                    select(OrphanCurrentCandidate.canonical_path).where(
                        OrphanCurrentCandidate.is_ignored == True  # noqa: E712
                    )
                ),
            )
        )
        scan_context["ignored_count"] = int(ignored_count_result.scalar() or 0)

        # 列表与“全选当前筛选”必须共用完全相同的过滤语义。
        conditions = self._build_orphan_conditions(
            cast(str, display_scan.scan_id),
            current_mode=current_mode,
            downloader_id=downloader_id,
            min_size=min_size,
            include_deleted=include_deleted,
            path_like=path_like,
            path_prefix=path_prefix,
            status=status,
            confidence=confidence,
        )

        # 总数
        count_query = select(func.count(OrphanFile.id))
        for cond in conditions:
            count_query = count_query.where(cond)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 排序：高置信度优先，其次被忽视的孤儿文件优先级最低（沉底），
        # 组内再按文件大小降序和 ID 升序保持稳定。
        confidence_rank, ignored_rank = self._orphan_order_columns()
        list_query = select(OrphanFile).order_by(
            confidence_rank.asc(),
            ignored_rank.asc(),
            OrphanFile.file_size.desc(),
            OrphanFile.id.asc(),
        )
        for cond in conditions:
            list_query = list_query.where(cond)
        offset = (page - 1) * page_size
        list_query = list_query.offset(offset).limit(page_size)

        result = await self.db.execute(list_query)
        items = result.scalars().all()
        item_dicts = [item.to_dict() for item in items]

        # 下载器别名（nickname）解析 + 忽视态注入：批量查询避免 N+1。
        await self._enrich_items(item_dicts)

        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "list": item_dicts,
            "scan_context": scan_context,
        }

    async def get_orphan_list_grouped(
        self,
        page: int = 1,
        page_size: int = 20,
        downloader_id: Optional[str] = None,
        min_size: Optional[int] = None,
        include_deleted: bool = False,
        path_like: Optional[str] = None,
        path_prefix: Optional[str] = None,
        status: Optional[str] = None,
        confidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按直接父目录聚合分页查询孤儿文件列表。

        与 ``get_orphan_list`` 共用相同的 scan_context / remaining / ignored 统计口径
        （文件级），区别仅在列表数据形态：本方法把同一直接父目录下的文件聚合。

        - cnt >= 2 的组 → 仅返回聚合父行（children 初始为空，展开后独立分页）
        - cnt == 1 的组 → 直接返回该 OrphanFileItem（保持原样，单文件不折叠）
        - 分页单位为"文件夹组"，``total`` = 组数
        - 组间排序：组内最大文件大小降序、父目录路径字典序升序
        - 子项排序：懒加载接口复用 _orphan_order_columns（confidence/ignored/file_size/id）

        父目录计算由注册到 SQLite 连接的 ``bt_orphan_parent_dir`` 自定义函数完成，
        支持 ``/`` 与 ``\\`` 分隔符统一处理。
        """
        # aiosqlite 下 connect 事件不生效，需在查询前显式注册自定义函数。
        # driver_connection 是 aiosqlite.Connection，其 create_function 为协程，
        # 会安全转发到 worker 线程注册到真实 sqlite3 连接。
        try:
            sa_conn = await self.db.connection()
            raw_conn = await sa_conn.get_raw_connection()
            aio_conn = raw_conn.driver_connection
            if aio_conn is not None and hasattr(aio_conn, "create_function"):
                await aio_conn.create_function("bt_orphan_parent_dir", 1, orphan_parent_dir)
        except (AttributeError, TypeError):
            pass
        latest_attempt = await self._get_latest_scan()
        display_scan: Optional[OrphanScanResult] = None
        if latest_attempt is not None:
            if latest_attempt.status == "completed":
                display_scan = latest_attempt
            elif latest_attempt.status == "failed":
                display_scan = await self._get_latest_scan(status="completed")

        gate = self._evaluate_cleanup_snapshot(
            latest_attempt,
            display_scan.scan_id if display_scan is not None else None,
        )
        scan_context: Dict[str, Any] = {
            "latest_attempt": latest_attempt.to_dict() if latest_attempt is not None else None,
            "display_scan": display_scan.to_dict() if display_scan is not None else None,
            "remaining_count": 0,
            "remaining_size": 0,
            "ignored_count": 0,
            "cleanup_allowed": gate["allowed"],
            "cleanup_block_reason": gate["reason"],
        }
        if display_scan is None:
            return {
                "total": 0,
                "page": page,
                "pageSize": page_size,
                "list": [],
                "scan_context": scan_context,
            }

        current_mode = str(display_scan.details_mode or "snapshot") == "current"
        detail_scope = (
            OrphanFile.id.in_(self._current_detail_ids_query(cast(str, display_scan.scan_id)))
            if current_mode
            else OrphanFile.scan_id == display_scan.scan_id
        )

        remaining_result = await self.db.execute(
            select(
                func.count(OrphanFile.id),
                func.coalesce(func.sum(OrphanFile.file_size), 0),
            ).where(
                detail_scope,
                OrphanFile.is_deleted == False,  # noqa: E712
                OrphanFile.id.notin_(active_cleanup_orphan_ids_query()),
            )
        )
        remaining_count, remaining_size = remaining_result.one()
        scan_context["remaining_count"] = int(remaining_count or 0)
        scan_context["remaining_size"] = int(remaining_size or 0)

        ignored_count_result = await self.db.execute(
            select(func.count(OrphanFile.id)).where(
                detail_scope,
                OrphanFile.is_deleted == False,  # noqa: E712
                OrphanFile.id.notin_(active_cleanup_orphan_ids_query()),
                OrphanFile.canonical_path.in_(
                    select(OrphanCurrentCandidate.canonical_path).where(
                        OrphanCurrentCandidate.is_ignored == True  # noqa: E712
                    )
                ),
            )
        )
        scan_context["ignored_count"] = int(ignored_count_result.scalar() or 0)

        conditions = self._build_orphan_conditions(
            cast(str, display_scan.scan_id),
            current_mode=current_mode,
            downloader_id=downloader_id,
            min_size=min_size,
            include_deleted=include_deleted,
            path_like=path_like,
            path_prefix=path_prefix,
            status=status,
            confidence=confidence,
        )

        # 父目录自定义函数表达式（GROUP BY / WHERE IN 共用同一实例）
        parent_dir_func = func.bt_orphan_parent_dir(OrphanFile.file_path)
        ignored_paths = select(OrphanCurrentCandidate.canonical_path).where(
            OrphanCurrentCandidate.is_ignored == True  # noqa: E712
        )
        ignored_flag = case(
            (
                and_(
                    OrphanFile.is_deleted == False,  # noqa: E712
                    OrphanFile.canonical_path.in_(ignored_paths),
                ),
                1,
            ),
            else_=0,
        )
        pending_flag = case(
            (
                and_(
                    OrphanFile.is_deleted == False,  # noqa: E712
                    OrphanFile.canonical_path.notin_(ignored_paths),
                ),
                1,
            ),
            else_=0,
        )

        # 父列表仅做 SQL 聚合；不拉取文件夹全部子项，也不对其执行实时 stat。
        group_query = (
            select(
                parent_dir_func.label("pdir"),
                func.count().label("cnt"),
                func.min(OrphanFile.id).label("singleton_id"),
                func.max(OrphanFile.file_size).label("max_size"),
                func.coalesce(func.sum(OrphanFile.file_size), 0).label("total_size"),
                func.max(OrphanFile.mtime).label("latest_mtime"),
                func.sum(case((OrphanFile.is_deleted == True, 1), else_=0)).label("deleted_count"),  # noqa: E712
                func.sum(ignored_flag).label("ignored_count"),
                func.sum(pending_flag).label("pending_count"),
                func.sum(case((OrphanFile.confidence == "low", 1), else_=0)).label("low_count"),
            )
            .where(*conditions)
            .group_by(parent_dir_func)
        )

        # total = 组数（子查询计数）
        count_result = await self.db.execute(select(func.count()).select_from(group_query.subquery()))
        total = int(count_result.scalar() or 0)

        # 本页组：组内最大文件降序、父目录字典序升序
        page_query = (
            group_query.order_by(
                text("max_size DESC"),
                text("pdir ASC"),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        page_result = await self.db.execute(page_query)
        page_groups = page_result.all()

        if not page_groups:
            return {
                "total": total,
                "page": page,
                "pageSize": page_size,
                "list": [],
                "scan_context": scan_context,
            }

        # 单文件组无需展开，最多只加载父页 page_size 条；实时硬链接统计仍只覆盖可见项。
        singleton_ids = [int(group.singleton_id) for group in page_groups if int(group.cnt) == 1]
        singleton_map: Dict[int, Dict[str, Any]] = {}
        if singleton_ids:
            singleton_result = await self.db.execute(select(OrphanFile).where(OrphanFile.id.in_(singleton_ids)))
            singleton_dicts = [detail.to_dict() for detail in singleton_result.scalars().all()]
            await self._enrich_items(singleton_dicts)
            singleton_map = {int(item["id"]): item for item in singleton_dicts}

        item_list: List[Dict[str, Any]] = []
        for group in page_groups:
            if int(group.cnt) == 1:
                singleton = singleton_map.get(int(group.singleton_id))
                if singleton is not None:
                    item_list.append(singleton)
            else:
                count = int(group.cnt)
                latest_mtime = group.latest_mtime
                item_list.append(
                    {
                        "_is_folder": True,
                        "folder_key": "folder:" + str(group.pdir),
                        "folder_path": str(group.pdir),
                        "child_count": count,
                        "children": [],
                        "child_ids": [],
                        "children_loaded": False,
                        "children_loading": False,
                        "child_page": 1,
                        "child_page_size": 20,
                        "child_total": count,
                        "total_size": int(group.total_size or 0),
                        "latest_mtime": (latest_mtime.isoformat() if latest_mtime is not None else None),
                        "downloader_name": None,
                        "all_pending": int(group.pending_count or 0) == count,
                        "all_ignored": int(group.ignored_count or 0) == count,
                        "all_deleted": int(group.deleted_count or 0) == count,
                        "has_low_confidence": int(group.low_count or 0) > 0,
                        # 文件夹未展开时不读取任何子文件 inode；当前可见子页单独统计。
                        "hardlink_copy_count": None,
                    }
                )

        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "list": item_list,
            "scan_context": scan_context,
        }

    async def get_orphan_folder_children(
        self,
        folder_path: str,
        *,
        page: int = 1,
        page_size: int = 20,
        downloader_id: Optional[str] = None,
        min_size: Optional[int] = None,
        path_like: Optional[str] = None,
        path_prefix: Optional[str] = None,
        status: Optional[str] = None,
        confidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        """展开文件夹后按独立页加载子项；硬链接统计仅覆盖返回页。"""
        try:
            sa_conn = await self.db.connection()
            raw_conn = await sa_conn.get_raw_connection()
            aio_conn = raw_conn.driver_connection
            if aio_conn is not None and hasattr(aio_conn, "create_function"):
                await aio_conn.create_function("bt_orphan_parent_dir", 1, orphan_parent_dir)
        except (AttributeError, TypeError):
            pass

        latest_attempt = await self._get_latest_scan()
        display_scan: Optional[OrphanScanResult] = None
        if latest_attempt is not None:
            if latest_attempt.status == "completed":
                display_scan = latest_attempt
            elif latest_attempt.status == "failed":
                display_scan = await self._get_latest_scan(status="completed")
        if display_scan is None:
            return {"total": 0, "page": page, "pageSize": page_size, "list": []}

        conditions = self._build_orphan_conditions(
            cast(str, display_scan.scan_id),
            current_mode=str(display_scan.details_mode or "snapshot") == "current",
            downloader_id=downloader_id,
            min_size=min_size,
            path_like=path_like,
            path_prefix=path_prefix,
            status=status,
            confidence=confidence,
        )
        parent_dir_func = func.bt_orphan_parent_dir(OrphanFile.file_path)
        conditions.append(parent_dir_func == folder_path)
        count_result = await self.db.execute(select(func.count(OrphanFile.id)).where(*conditions))
        total = int(count_result.scalar() or 0)

        confidence_rank, ignored_rank = self._orphan_order_columns()
        result = await self.db.execute(
            select(OrphanFile)
            .where(*conditions)
            .order_by(
                confidence_rank.asc(),
                ignored_rank.asc(),
                OrphanFile.file_size.desc(),
                OrphanFile.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        item_dicts = [detail.to_dict() for detail in result.scalars().all()]
        await self._enrich_items(item_dicts)
        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "list": item_dicts,
        }

    @staticmethod
    def _enrich_hardlink_copy_counts(item_dicts: List[Dict[str, Any]]) -> None:
        """在线读取每个孤儿文件的硬链接副本数；不可访问时标记为未知。"""
        unavailable_count = 0
        for item in item_dicts:
            file_path = item.get("file_path")
            if not isinstance(file_path, str) or not file_path:
                item["hardlink_copy_count"] = None
                unavailable_count += 1
                continue
            try:
                item["hardlink_copy_count"] = get_hardlink_copy_count(file_path)
            except OSError:
                item["hardlink_copy_count"] = None
                unavailable_count += 1
        if unavailable_count:
            logger.debug("[孤儿列表] %d 个文件无法读取硬链接数量", unavailable_count)

    async def _enrich_items(self, item_dicts: List[Dict[str, Any]]) -> None:
        """为本页明细批量注入硬链接数、downloader_name（别名）与忽视态字段。

        - hardlink_copy_count：实时 ``st_nlink - 1``；文件不可访问时为 None。
        - downloader_name：JOIN bt_downloaders.nickname，nickname 为空回退掩码 ID。
        - is_ignored/ignored_at/ignored_by：按 canonical_path 批量查候选。
        """
        if not item_dicts:
            return

        # 文件系统 stat 可能命中网络盘，统一移出事件循环并顺序读取，避免并发打满 NAS。
        await asyncio.to_thread(self._enrich_hardlink_copy_counts, item_dicts)

        # 下载器别名
        downloader_ids = {d["downloader_id"] for d in item_dicts if d.get("downloader_id")}
        nickname_map: Dict[str, str] = {}
        if downloader_ids:
            from app.downloader.models import BtDownloaders

            dl_result = await self.db.execute(
                select(BtDownloaders.downloader_id, BtDownloaders.nickname).where(
                    BtDownloaders.downloader_id.in_(downloader_ids)
                )
            )
            nickname_map = {row[0]: row[1] for row in dl_result.all() if row[1]}

        # 忽视态：按 canonical_path 批量查候选
        canonical_paths = [d["canonical_path"] for d in item_dicts if d.get("canonical_path")]
        ignore_map: Dict[str, Dict[str, Any]] = {}
        if canonical_paths:
            cand_result = await self.db.execute(
                select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path.in_(canonical_paths))
            )
            for cand in cand_result.scalars().all():
                ignore_map[cand.canonical_path] = {
                    "is_ignored": bool(cand.is_ignored),
                    "ignored_at": cand.ignored_at.isoformat() if cand.ignored_at else None,
                    "ignored_by": cand.ignored_by,
                }

        for d in item_dicts:
            dl_id = d.get("downloader_id")
            d["downloader_name"] = nickname_map.get(dl_id) if dl_id else None
            ignore_info = ignore_map.get(d.get("canonical_path"))
            if ignore_info:
                d["is_ignored"] = ignore_info["is_ignored"]
                d["ignored_at"] = ignore_info["ignored_at"]
                d["ignored_by"] = ignore_info["ignored_by"]
            else:
                d.setdefault("is_ignored", False)
                d.setdefault("ignored_at", None)
                d.setdefault("ignored_by", None)

    async def reconcile_stable_candidate_details(self) -> Dict[str, int]:
        """幂等补齐历史 stable 隔离候选对应的扫描明细。

        仅按候选的 last_seen_scan_id、下载器身份和规范化路径更新该批次仍未
        清理的 OrphanFile；无法匹配时只记录诊断，不跨批次猜测。候选查询、
        明细匹配、更新和提交按 keyset 分页统一进入 ``db_write_scope``，避免
        启动时一次加载大批候选或持有长写事务。
        """
        batch_size = max(1, int(settings.ORPHAN_SCAN_COMMIT_BATCH_SIZE))
        cursor: Optional[str] = None
        candidate_count = 0
        updated_count = 0
        unmatched_count = 0
        reconciliation_time = datetime.utcnow()
        suppressed_unmatched_logs = 0

        while True:
            page: List[OrphanCurrentCandidate] = []
            try:
                async with admission_controller.db_write_scope():
                    candidate_query = select(OrphanCurrentCandidate).where(
                        OrphanCurrentCandidate.status.in_(["quarantined", "purged"]),
                        OrphanCurrentCandidate.operation_state == "stable",
                        OrphanCurrentCandidate.last_seen_scan_id.isnot(None),
                    )
                    if cursor is not None:
                        candidate_query = candidate_query.where(OrphanCurrentCandidate.canonical_path > cursor)
                    candidate_result = await self.db.execute(
                        candidate_query.order_by(OrphanCurrentCandidate.canonical_path.asc()).limit(batch_size)
                    )
                    page = list(candidate_result.scalars().all())
                    candidate_count += len(page)

                    pointer_ids = [
                        int(candidate.current_detail_id)
                        for candidate in page
                        if candidate.current_detail_id is not None
                    ]
                    live_pointer_ids: set[int] = set()
                    if pointer_ids:
                        pointer_result = await self.db.execute(
                            select(OrphanFile.id).where(
                                OrphanFile.id.in_(pointer_ids),
                                OrphanFile.is_deleted == False,  # noqa: E712
                            )
                        )
                        live_pointer_ids = {int(detail_id) for detail_id in pointer_result.scalars().all()}

                    # 仅迁移前没有 current_detail_id 的候选需要复合键回退；
                    # 一页合并为一条 SQL，避免启动修复出现逐候选 N+1 查询。
                    fallback_candidates = [candidate for candidate in page if candidate.current_detail_id is None]
                    fallback_ids: Dict[tuple[str, str, str], List[int]] = {}
                    if fallback_candidates:
                        fallback_conditions = []
                        for candidate in fallback_candidates:
                            downloader_id = str(candidate.downloader_id or "")
                            downloader_condition = (
                                OrphanFile.downloader_id == downloader_id
                                if downloader_id
                                else or_(
                                    OrphanFile.downloader_id.is_(None),
                                    OrphanFile.downloader_id == "",
                                )
                            )
                            fallback_conditions.append(
                                and_(
                                    OrphanFile.scan_id == candidate.last_seen_scan_id,
                                    downloader_condition,
                                    OrphanFile.canonical_path == candidate.canonical_path,
                                )
                            )
                        detail_result = await self.db.execute(
                            select(
                                OrphanFile.id,
                                OrphanFile.scan_id,
                                OrphanFile.downloader_id,
                                OrphanFile.canonical_path,
                            ).where(
                                OrphanFile.is_deleted == False,  # noqa: E712
                                or_(*fallback_conditions),
                            )
                        )
                        for row in detail_result.all():
                            key = (
                                str(row.scan_id),
                                str(row.downloader_id or ""),
                                str(row.canonical_path),
                            )
                            fallback_ids.setdefault(key, []).append(int(row.id))

                    for candidate in page:
                        if candidate.current_detail_id is not None:
                            detail_id = int(candidate.current_detail_id)
                            matching_ids = [detail_id] if detail_id in live_pointer_ids else []
                        else:
                            matching_ids = fallback_ids.get(
                                (
                                    str(candidate.last_seen_scan_id),
                                    str(candidate.downloader_id or ""),
                                    str(candidate.canonical_path),
                                ),
                                [],
                            )
                        if not matching_ids:
                            unmatched_count += 1
                            if unmatched_count <= 10:
                                logger.warning(
                                    "[孤儿存量对账] 未找到明细: scan_id=%s downloader_id=%s path=%s",
                                    candidate.last_seen_scan_id,
                                    candidate.downloader_id,
                                    candidate.canonical_path,
                                )
                            else:
                                suppressed_unmatched_logs += 1
                            continue

                        update_result = await self.db.execute(
                            update(OrphanFile)
                            .where(
                                OrphanFile.id.in_(matching_ids),
                                OrphanFile.is_deleted == False,  # noqa: E712
                            )
                            .values(
                                is_deleted=True,
                                deleted_at=candidate.quarantined_at or reconciliation_time,
                                deleted_by="system:reconciliation",
                            )
                        )
                        updated_count += int(update_result.rowcount or 0)
                    await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise

            if not page:
                break
            cursor = str(page[-1].canonical_path)

        if suppressed_unmatched_logs:
            logger.warning(
                "[孤儿存量对账] 另有 %d 条未匹配诊断已合并，避免大批量日志放大",
                suppressed_unmatched_logs,
            )

        logger.info(
            "[孤儿存量对账] candidates=%d updated=%d unmatched=%d",
            candidate_count,
            updated_count,
            unmatched_count,
        )
        return {
            "candidate_count": candidate_count,
            "updated_count": updated_count,
            "unmatched_count": unmatched_count,
        }

    # ==================== 清理预览 ====================

    async def prefix_match_preview(self, path_prefix: str, scan_id: str) -> Dict[str, Any]:
        """左匹配预览：统计以 path_prefix 开头的“待清理”孤儿文件数与大小。

        与 cleanup 共用新鲜度门禁：最新扫描必须 completed 且 scan_id 必须最新，
        否则返回 rejected=True（避免对过期数据给出误导性的“将影响 N 个”）。
        范围严格限定 status=pending（排除已忽视 / 已清理），与前端快捷操作语义一致。
        """
        gate = await self._check_cleanup_allowed(scan_id)
        if not gate["allowed"]:
            return {
                "rejected": True,
                "reason": gate["reason"],
                "count": 0,
                "total_size": 0,
                "low_confidence_count": 0,
                "sample_paths": [],
            }

        conditions = self._build_orphan_conditions(
            scan_id,
            current_mode=bool((scan_record := await self._get_scan(scan_id)) and scan_record.details_mode == "current"),
            path_prefix=path_prefix,
            status="pending",  # 强制仅待清理
        )
        query = select(
            OrphanFile.id,
            OrphanFile.file_size,
            OrphanFile.confidence,
            OrphanFile.file_path,
        )
        for condition in conditions:
            query = query.where(condition)
        result = await self.db.execute(query)
        rows = result.all()
        return {
            "count": len(rows),
            "total_size": sum(int(row.file_size or 0) for row in rows),
            "low_confidence_count": sum(1 for row in rows if row.confidence != "high"),
            "sample_paths": [row.file_path for row in rows[:10]],
        }

    async def cleanup_preview(self, orphan_ids: List[int], scan_id: Optional[str] = None) -> Dict[str, Any]:
        """清理预览（返回文件数 + 总大小）。

        新鲜度门禁：最新扫描必须 completed；scan_id 必须是最新批次（否则 stale 拒绝）。
        """
        gate = await self._check_cleanup_allowed(scan_id)
        if not gate["allowed"]:
            return {
                "rejected": True,
                "reason": gate["reason"],
                "error": gate["reason"],
                "total_count": 0,
                "total_size": 0,
                "items": [],
            }

        items = await self._load_orphan_details(
            orphan_ids,
            scan_id=scan_id,
            exclude_ignored=True,
            exclude_in_flight=True,
        )

        # 手动清理放行低置信度文件：low confidence（离线降级目录粗筛产出）有误判风险，
        # 但用户可在前端警告确认后主动删除。仅自动清理（get_purgeable_candidates）仍排除 low。
        # 统计 low 数量供前端弹出"含低置信度，有误判风险"警告。
        low_confidence_count = sum(1 for item in items if item.confidence != "high")
        total_size = sum(item.file_size for item in items)
        return {
            "total_count": len(items),
            "total_size": total_size,
            "low_confidence_count": low_confidence_count,
            "items": [
                {
                    "id": item.id,
                    "file_path": item.file_path,
                    "file_size": item.file_size,
                    "confidence": item.confidence,
                }
                for item in items[:ORPHAN_PREVIEW_ITEM_LIMIT]
            ],
            "items_truncated": len(items) > ORPHAN_PREVIEW_ITEM_LIMIT,
        }

    # ==================== 手动清理 ====================

    async def cleanup_orphans(
        self,
        orphan_ids: List[int],
        operator: str,
        audit_service: Any = None,
        store: Any = None,
        scan_id: Optional[str] = None,
        _lease_acquired: bool = False,
        _lease_handle: Any = None,
    ) -> Dict[str, Any]:
        """手动清理选中的孤儿文件（安全隔离 + 标记 + 审计日志）。

        语义重做：
        - 新鲜度门禁：最新扫描必须 completed；scan_id 必须最新（stale 拒绝）
        - 删除前实时复核文件身份（size/mtime_ns/inode/符号链接/路径逃逸）
        - 不提供 force 绕过

        Args:
            orphan_ids: 孤儿文件 ID 列表
            operator: 操作者用户名
            audit_service: 审计日志服务（可选）
            store: app.state.store（用于实时 manifest 复核）
            scan_id: 调用方传入的 scan_id（stable ID 校验）

        Returns:
            {"success_count": int, "failed_count": int, "failed_list": [...]}
        """
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("manual_cleanup", db=self.db) as lease_handle:
                    return await self.cleanup_orphans(
                        orphan_ids=orphan_ids,
                        operator=operator,
                        audit_service=audit_service,
                        store=store,
                        scan_id=scan_id,
                        _lease_acquired=True,
                        _lease_handle=lease_handle,
                    )
            except OrphanLeaseBusyError as exc:
                return {
                    "success_count": 0,
                    "failed_count": len(orphan_ids),
                    "failed_list": [{"id": oid, "reason": str(exc)} for oid in orphan_ids],
                    "rejected": True,
                    "error": str(exc),
                    "total_size": 0,
                }

        # 新鲜度门禁
        gate = await self._check_cleanup_allowed(scan_id)
        if not gate["allowed"]:
            return {
                "success_count": 0,
                "failed_count": len(orphan_ids),
                "failed_list": [{"id": oid, "reason": gate["reason"]} for oid in orphan_ids],
                "rejected": True,
                "error": gate["reason"],
                "total_size": 0,
            }

        await self._recover_interrupted_operations(
            store=store,
            lease_handle=_lease_handle,
        )

        # 恢复可能已经最终化选中项，必须重新读取当前工作集。
        items = await self._load_orphan_details(
            orphan_ids,
            scan_id=scan_id,
        )

        success_count = 0
        failed_list: List[Dict[str, Any]] = []
        deleted_size = 0
        cleaned_names: List[str] = []  # 成功清理的文件/目录 basename（供审计日志展示）
        hardlink_notes: List[Dict[str, Any]] = []

        # 实时 manifest 复核：store 提供时必须成功构建（fail-closed）
        # manifest 构建失败 → 无法确认文件是否仍被种子引用 → 拒绝所有清理
        candidates = await self._load_candidates(
            [self._detail_canonical_path(item) for item in items],
            stable_only=True,
        )
        owner_reassigned = 0
        for item in items:
            candidate = candidates.get(self._detail_canonical_path(item))
            if candidate is not None and self._sync_candidate_owner(candidate, item):
                owner_reassigned += 1
        if owner_reassigned:
            logger.info(
                "[孤儿清理] 按 canonical_path 修正候选归属 owner_reassigned=%d",
                owner_reassigned,
            )
        # 分流优化：manifest 精筛复核范围只放 high 候选所属下载器。
        # low 候选（离线降级目录粗筛产出）的 downloader 大概率仍离线，为其拉取整下载器
        # 逐种子清单既慢又常因 downloader 降级被拒绝（纯浪费）。low 候选改走目录白名单
        # 兜底复核（见循环内 _authorize_low_confidence），不触发全量 manifest 拉取。
        high_downloader_ids = {
            cand.downloader_id for cand in candidates.values() if (cand.confidence or "high") == "high"
        }
        _manifest_started = time.monotonic()
        manifest = await self._build_realtime_manifest(store, high_downloader_ids)
        logger.info(
            "[孤儿清理] manifest 复核完成 耗时=%.2fs high下载器=%d/%d 总候选=%d",
            time.monotonic() - _manifest_started,
            len(high_downloader_ids),
            len({c.downloader_id for c in candidates.values()}),
            len(candidates),
        )
        if manifest is None:
            reason = "实时 manifest 构建失败，无法确认文件是否仍被种子引用（fail-closed）"
            logger.warning(f"[孤儿清理] {reason}")
            return {
                "success_count": 0,
                "failed_count": len(items),
                "failed_list": [{"id": i.id, "file_path": i.file_path, "reason": reason} for i in items],
                "total_size": 0,
            }

        _loop_started = time.monotonic()
        logger.info("[孤儿清理] 删除循环开始 items=%d", len(items))
        for item in items:
            try:
                canonical = self._detail_canonical_path(item)
                if canonical in manifest.expected_paths:
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "文件当前已被种子引用",
                        }
                    )
                    continue

                candidate = candidates.get(canonical)
                if candidate is None:
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "当前候选状态不存在或已失效",
                        }
                    )
                    continue

                # 授权复核：high 候选走标准精筛授权；low 候选走分流复核（下载器在线则
                # 精筛授权，仍离线则目录白名单兜底）。两者均为 fail-closed。
                if (candidate.confidence or "high") == "high":
                    authorized = self._path_authorized(candidate, manifest)
                else:
                    authorized = self._authorize_low_confidence(candidate, manifest)
                if not authorized:
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "文件不属于实时 manifest 授权扫描根",
                        }
                    )
                    continue
                # 忽视态保护：被用户忽视的孤儿受保护，需先取消忽视才能清理。
                # 注：手动清理放行低置信度文件（low 有误判风险，由前端警告确认后删除）；
                # 仅自动清理（get_purgeable_candidates）仍排除 low。清理安全底线不变——
                # 实时 manifest 复核（expected_paths/_path_authorized/verify_file_identity）照常拦截。
                if getattr(candidate, "is_ignored", False):
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "已忽视的孤儿受保护，需先取消忽视才能清理",
                        }
                    )
                    continue
                if not self._identity_complete(candidate):
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "候选文件身份字段不完整，需重新扫描",
                        }
                    )
                    continue

                # 删除前实时复核文件身份（fail-closed：不匹配则拒绝删除）
                ok, reason = verify_file_identity(
                    item.file_path,
                    expected_size=item.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    failed_list.append({"id": item.id, "file_path": item.file_path, "reason": reason})
                    logger.warning(f"[孤儿清理] 文件身份复核失败，拒绝删除: {reason}")
                    continue

                # 手动清理同样进入隔离区，避免不可逆 TOCTOU 删除。
                actual_path = item.file_path
                if not os.path.exists(actual_path):
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "文件不存在",
                        }
                    )
                    continue
                owning_root = self._owning_root(candidate, manifest)
                quarantine_root = resolve_quarantine_root(owning_root, scan_id=scan_id)
                # 清理预警（不阻断）：原文件若存在硬链接副本，隔离前记录诊断，
                # 让用户在后续彻底删除前知情。隔离本身可恢复，故不拒绝。
                cleanup_note = await self._detect_hardlink_copies(
                    candidate, cast(str, actual_path), manifest, "cleanup_warn"
                )
                await self._quarantine_candidate(
                    candidate,
                    actual_path,
                    quarantine_root,
                    scan_id=scan_id,
                    operator=operator,
                    lease_handle=_lease_handle,
                )

                deleted_size += item.file_size
                success_count += 1
                cleaned_names.append(os.path.basename(actual_path))
                if cleanup_note is not None:
                    hardlink_notes.append(cleanup_note)

            except Exception as e:
                logger.error(f"[孤儿清理] 隔离文件失败 {item.file_path}: {e}")
                failed_list.append({"id": item.id, "file_path": item.file_path, "reason": str(e)})

        # 审计日志
        if audit_service and success_count > 0:
            try:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ORPHAN_CLEANUP.value,
                    operator=operator,
                    operation_detail={
                        "action": "manual_cleanup",
                        "success_count": success_count,
                        "failed_count": len(failed_list),
                        "total_size": deleted_size,
                        "cleaned_files": cleaned_names,
                    },
                    operation_result=AuditOperationResult.SUCCESS if not failed_list else AuditOperationResult.PARTIAL,
                    error_message=f"失败 {len(failed_list)} 个" if failed_list else None,
                )
            except Exception as e:
                logger.warning(f"[孤儿清理] 审计日志记录失败: {e}")

        logger.info(
            "[孤儿清理] 完成 success=%d failed=%d total_size=%d 循环耗时=%.2fs",
            success_count,
            len(failed_list),
            deleted_size,
            time.monotonic() - _loop_started,
        )
        return {
            "success_count": success_count,
            "failed_count": len(failed_list),
            "failed_list": failed_list,
            "total_size": deleted_size,
            "hardlink_notes": hardlink_notes,
        }

    # ==================== 忽视管理 ====================

    async def set_ignored(
        self,
        orphan_ids: List[int],
        ignored: bool,
        operator: str,
        scan_id: Optional[str] = None,
        audit_service: Any = None,
    ) -> Dict[str, Any]:
        """设置/取消孤儿文件的忽视态（保护标志，存候选表，跨扫描持久）。

        被忽视的孤儿：定时任务不自动删除，手动清理也被拒绝，但仍可在列表查询。
        取消忽视后恢复可清理。

        仅对 status=candidate 且 operation_state=stable 的候选生效（已进入
        清理流水线 quarantined/purged 的候选不再可忽视）。映射键为明细的
        canonical_path；downloader_id 仅为当前扫描归属元数据。

        Returns:
            {"success_count": int, "failed_count": int, "failed_list": [...]}
        """
        if not orphan_ids:
            return {"success_count": 0, "failed_count": 0, "failed_list": []}

        logger.info(
            "[孤儿忽视] 开始 operator=%s ignored=%s scan_id=%s requested=%d",
            operator,
            ignored,
            scan_id,
            len(orphan_ids),
        )

        # 取明细（限定 scan_id 调用方绑定的批次，避免跨批次误操作）。
        # 分块查询同时支持“全选当前筛选”产生的大规模 ID 快照。
        details = await self._load_orphan_details(
            orphan_ids,
            scan_id=scan_id,
            exclude_in_flight=True,
        )

        if not details:
            logger.warning(
                "[孤儿忽视] 未找到扫描明细 operator=%s ignored=%s scan_id=%s requested_ids=%s",
                operator,
                ignored,
                scan_id,
                orphan_ids[:20],
            )
            return {
                "success_count": 0,
                "failed_count": len(orphan_ids),
                "failed_list": [{"id": oid, "reason": "未找到对应的孤儿明细"} for oid in orphan_ids],
            }

        # canonical_path 是候选表主键和列表忽视态的统一身份；downloader_id
        # 仅是当前扫描归属元数据，不能参与候选是否存在的判定。
        canonical_paths = [self._detail_canonical_path(detail) for detail in details]
        candidates = await self._load_candidates(canonical_paths)

        now = datetime.utcnow()
        success_count = 0
        failed_list: List[Dict[str, Any]] = []
        owner_reassigned = 0
        details_by_id = {int(detail.id): detail for detail in details}

        for orphan_id in orphan_ids:
            detail = details_by_id.get(orphan_id)
            if detail is None:
                failed_list.append({"id": orphan_id, "reason": "未找到对应的孤儿明细"})
                continue

            canonical_path = self._detail_canonical_path(detail)
            candidate = candidates.get(canonical_path)
            if candidate is None:
                failed_list.append(
                    {"id": orphan_id, "file_path": detail.file_path, "reason": "当前候选状态不存在或已失效"}
                )
                continue
            if candidate.status != "candidate" or candidate.operation_state != "stable":
                failed_list.append(
                    {
                        "id": orphan_id,
                        "file_path": detail.file_path,
                        "reason": (
                            "候选已进入清理流程"
                            f"（status={candidate.status}, operation_state={candidate.operation_state}），不可忽视"
                        ),
                    }
                )
                continue
            if self._sync_candidate_owner(candidate, detail):
                owner_reassigned += 1
            candidate.is_ignored = bool(ignored)
            candidate.ignored_at = now if ignored else None
            candidate.ignored_by = operator if ignored else None
            success_count += 1

        try:
            async with admission_controller.db_write_scope():
                await self.db.flush()
                await self.db.commit()
        except Exception as exc:
            await self.db.rollback()
            logger.exception(
                "[孤儿忽视] 数据库提交失败 operator=%s ignored=%s scan_id=%s requested=%d error=%s",
                operator,
                ignored,
                scan_id,
                len(orphan_ids),
                exc,
            )
            reason = "数据库提交失败，请查看后端日志"
            return {
                "success_count": 0,
                "failed_count": len(orphan_ids),
                "failed_list": [{"id": oid, "reason": reason} for oid in orphan_ids],
            }

        if failed_list:
            reason_counts = Counter(str(item.get("reason") or "未知原因") for item in failed_list)
            logger.warning(
                "[孤儿忽视] 存在失败 operator=%s ignored=%s scan_id=%s failed_reasons=%s samples=%s",
                operator,
                ignored,
                scan_id,
                dict(reason_counts),
                failed_list[:5],
            )

        # 审计日志：用独立 session，避免污染主事务（参考 auto_cleanup_expired 模式）
        try:
            from app.database import AsyncSessionLocal
            from app.services.audit_service import AuditLogService

            async with AsyncSessionLocal() as audit_db:
                audit_svc = audit_service or AuditLogService(audit_db)
                # 若调用方传入了 audit_service（共享主 session），用它；否则独立 session
                await audit_svc.log_operation(
                    operation_type=AuditOperationType.ORPHAN_IGNORE.value,
                    operator=operator,
                    operation_detail={
                        "action": "ignore" if ignored else "unignore",
                        "success_count": success_count,
                        "failed_count": len(failed_list),
                    },
                    operation_result=AuditOperationResult.SUCCESS if not failed_list else AuditOperationResult.PARTIAL,
                    error_message=f"失败 {len(failed_list)} 个" if failed_list else None,
                )
                await audit_db.commit()
        except Exception as e:
            logger.warning(f"[孤儿忽视] 审计日志记录失败: {e}")

        logger.info(
            "[孤儿忽视] 完成 operator=%s ignored=%s success=%d failed=%d owner_reassigned=%d",
            operator,
            ignored,
            success_count,
            len(failed_list),
            owner_reassigned,
        )
        return {
            "success_count": success_count,
            "failed_count": len(failed_list),
            "failed_list": failed_list,
        }

    # ==================== 自动清理超期（移入隔离区） ====================

    async def auto_cleanup_expired(
        self,
        days_threshold: int,
        operator: str = "system",
        store: Any = None,
        scan_id: Optional[str] = None,
        _lease_acquired: bool = False,
        _lease_handle: Any = None,
    ) -> Dict[str, Any]:
        """自动清理超期孤儿文件（定时任务调用）。

        语义重做：
        - 按 OrphanCurrentCandidate 的「连续成为孤儿的时间」筛选（不再用 mtime）
        - 先移入隔离区（不直接删除），记录 quarantine_path + purge_after
        - 独立的 purge_expired_quarantine 负责到期物理删除

        Args:
            days_threshold: 连续孤儿天数阈值
            operator: 操作者（默认 system）
            store: app.state.store
            scan_id: 本次扫描 ID（必须传入）

        Returns:
            {"quarantined_count": int, "failed_count": int, "total_size": int}
        """
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("auto_cleanup", db=self.db) as lease_handle:
                    return await self.auto_cleanup_expired(
                        days_threshold=days_threshold,
                        operator=operator,
                        store=store,
                        scan_id=scan_id,
                        _lease_acquired=True,
                        _lease_handle=lease_handle,
                    )
            except OrphanLeaseBusyError as exc:
                return {
                    "quarantined_count": 0,
                    "failed_count": 0,
                    "total_size": 0,
                    "rejected": True,
                    "error": str(exc),
                }

        lifecycle = OrphanLifecycleService(self.db)
        gate = await self._check_cleanup_allowed(scan_id)
        if not gate["allowed"]:
            return {
                "quarantined_count": 0,
                "failed_count": 0,
                "total_size": 0,
                "rejected": True,
                "error": gate["reason"],
            }

        await self._recover_interrupted_operations(
            store=store,
            lease_handle=_lease_handle,
        )

        # 恢复会改变候选状态，必须在恢复后获取可清理集合。
        purgeable = await lifecycle.get_purgeable_candidates(days_threshold)
        _manifest_started = time.monotonic()
        manifest = await self._build_realtime_manifest(store, {candidate.downloader_id for candidate in purgeable})
        logger.info(
            "[孤儿自动清理] manifest 构建完成 耗时=%.2fs 候选=%d 下载器=%d",
            time.monotonic() - _manifest_started,
            len(purgeable),
            len({c.downloader_id for c in purgeable}),
        )
        if manifest is None:
            return {
                "quarantined_count": 0,
                "failed_count": 0,
                "total_size": 0,
                "rejected": True,
                "error": "实时 manifest 构建失败",
            }

        if not purgeable:
            logger.info(f"[孤儿自动清理] 无满足 {days_threshold} 天条件的候选")
            return {"quarantined_count": 0, "failed_count": 0, "total_size": 0}

        logger.info(f"[孤儿自动清理] 发现 {len(purgeable)} 个满足条件的候选，移入隔离区")

        quarantined_count = 0
        failed_count = 0
        total_size = 0
        hardlink_notes: List[Dict[str, Any]] = []
        _loop_started = time.monotonic()

        for candidate in purgeable:
            try:
                # 忽视态保护（防御纵深）：即使因 SQL 过滤被旁路（如 is_ignored 子句被
                # 误删或候选被直接注入），被忽视的孤儿也绝不能进入隔离/删除流水线。
                # 这是数据安全底线：忽视=保护，定时任务不得删除被忽视的文件。
                if getattr(candidate, "is_ignored", False):
                    logger.warning(f"[孤儿自动清理] 候选被忽视受保护，跳过: {candidate.canonical_path}")
                    failed_count += 1
                    continue
                if normalize_path(candidate.canonical_path) in manifest.expected_paths:
                    logger.warning(f"[孤儿自动清理] 文件已被种子引用，跳过: {candidate.canonical_path}")
                    failed_count += 1
                    continue
                if not self._path_authorized(candidate, manifest) or not self._identity_complete(candidate):
                    logger.warning(f"[孤儿自动清理] 路径未授权或身份字段不完整: {candidate.canonical_path}")
                    failed_count += 1
                    continue
                # 推导扫描根（canonical_path 所在的下载器扫描根）
                scan_root = self._owning_root(candidate, manifest)
                quarantine_root = resolve_quarantine_root(scan_root, scan_id=scan_id)

                # 隔离前复核文件身份
                ok, reason = verify_file_identity(
                    candidate.canonical_path,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    failed_count += 1
                    logger.warning(f"[孤儿自动清理] 复核失败，跳过: {reason}")
                    continue

                # 清理预警（不阻断）：原文件若存在硬链接副本，隔离前记录诊断。
                auto_note = await self._detect_hardlink_copies(
                    candidate,
                    cast(str, candidate.canonical_path),
                    manifest,
                    "cleanup_warn",
                )
                # 移入隔离区
                await self._quarantine_candidate(
                    candidate,
                    candidate.canonical_path,
                    quarantine_root,
                    scan_id=scan_id,
                    operator=operator,
                    lease_handle=_lease_handle,
                )

                quarantined_count += 1
                total_size += candidate.file_size
                if auto_note is not None:
                    hardlink_notes.append(auto_note)

            except Exception as e:
                logger.error(f"[孤儿自动清理] 隔离失败 {candidate.canonical_path}: {e}")
                failed_count += 1

        # 审计日志
        try:
            from app.services.audit_service import AuditLogService
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as audit_db:
                audit_service = AuditLogService(audit_db)
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ORPHAN_AUTO_CLEANUP.value,
                    operator=operator,
                    operation_detail={
                        "action": "auto_cleanup_to_quarantine",
                        "days_threshold": days_threshold,
                        "quarantined_count": quarantined_count,
                        "failed_count": failed_count,
                        "total_size": total_size,
                    },
                    operation_result=(
                        AuditOperationResult.SUCCESS if not failed_count else AuditOperationResult.PARTIAL
                    ),
                    error_message=f"失败 {failed_count} 个" if failed_count else None,
                )
                await audit_db.commit()
        except Exception as e:
            logger.warning(f"[孤儿自动清理] 审计日志记录失败: {e}")

        logger.info(
            f"[孤儿自动清理] 完成: 隔离 {quarantined_count}，失败 {failed_count}，"
            f"共 {total_size / (1024**2):.2f} MB，循环耗时={time.monotonic() - _loop_started:.2f}s"
        )

        return {
            "quarantined_count": quarantined_count,
            "success_count": quarantined_count,  # 向后兼容字段
            "failed_count": failed_count,
            "total_size": total_size,
            "hardlink_notes": hardlink_notes,
        }

    # ==================== 隔离区到期物理删除 ====================

    async def purge_expired_quarantine(
        self,
        store: Any = None,
        _lease_acquired: bool = False,
        _lease_handle: Any = None,
    ) -> Dict[str, Any]:
        """物理删除隔离保留期到期的文件（独立清理任务）。

        只删 status=quarantined AND purge_after < now AND 路径仍在隔离区内的文件。
        """
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("quarantine_purge", db=self.db) as lease_handle:
                    return await self.purge_expired_quarantine(
                        store=store, _lease_acquired=True, _lease_handle=lease_handle
                    )
            except OrphanLeaseBusyError as exc:
                return {
                    "purged_count": 0,
                    "failed_count": 0,
                    "rejected": True,
                    "error": str(exc),
                }

        now = datetime.utcnow()
        await self._recover_interrupted_operations(
            store=store,
            lease_handle=_lease_handle,
        )

        # 恢复可能已物理删除或回退候选，后续只处理最新工作集。
        result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.status == "quarantined",
                OrphanCurrentCandidate.operation_state == "stable",
                OrphanCurrentCandidate.purge_after.isnot(None),
                OrphanCurrentCandidate.purge_after < now,
            )
        )
        candidates = result.scalars().all()
        purged_count = 0
        failed_count = 0
        skipped_hardlink: List[Dict[str, Any]] = []
        # 隔离区物理删除不依赖下载器 manifest；保留统计字段以兼容已有日志/调用方。
        _in_loop_manifest_builds = 0
        _in_loop_manifest_total_time = 0.0
        _loop_started = time.monotonic()

        for candidate in candidates:
            tombstone_path: Optional[str] = None
            try:
                qpath = candidate.quarantine_path
                if not qpath or not os.path.exists(qpath):
                    # 文件已不在隔离区（可能已被手动清理）
                    await self._mark_purged(candidate.canonical_path)
                    prune_empty_quarantine_parents(qpath, candidate.quarantine_root)
                    continue

                guard_error = self._quarantine_delete_guard_error(candidate)
                if guard_error:
                    logger.warning("[隔离清理] 安全校验失败，跳过 %s: %s", qpath, guard_error)
                    failed_count += 1
                    continue
                identity_error = await self._ensure_quarantine_identity(candidate, qpath)
                if identity_error:
                    logger.warning("[隔离清理] 身份校验失败，跳过 %s: %s", qpath, identity_error)
                    failed_count += 1
                    continue

                # 二次验证：路径仍在预写的精确隔离根内（防路径篡改）。
                quarantine_root = candidate.quarantine_root
                if not self._path_in_quarantine_root(qpath, quarantine_root):
                    logger.warning("[隔离清理] 路径不在隔离区内，跳过: %s", qpath)
                    failed_count += 1
                    continue

                ok, reason = verify_file_identity(
                    qpath,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    logger.warning(f"[隔离清理] 文件身份变化，跳过: {reason}")
                    failed_count += 1
                    continue

                # 硬链接副本保护：到期删除遇副本必须跳过（安全优先），避免删了
                # 隔离副本却因其它链接（如种子/媒体库）未释放空间。删除前抓取
                # inode（删除后失效）；nlink>1 时跳过。副本路径枚举需要 manifest
                # 推导 scan_roots，但到期删除不主动构建下载器 manifest（隔离后
                # 下载器可能已降级）；manifest 为 None 时仅按 nlink 跳过、无法
                # 列出具体副本路径（reason 标注）。
                try:
                    await self._detect_hardlink_copies(candidate, cast(str, qpath), None, mode="purge_expired")
                except HardlinkCopyError as he:
                    # 延后 purge_after，打破「每日重试循环」：跳过后 purge_after 不变，
                    # 次日任务会再次选中→再次跳过。延后 N 天后副本若仍存在继续延后
                    # （无上限），副本被清除后 purge_after 到期仍会正常删除。
                    new_purge_after = compute_purge_after(datetime.utcnow(), settings.ORPHAN_HARDLINK_PURGE_DELAY_DAYS)
                    # 计数用 SQL 表达式原子递增（并入同一次 UPDATE，避免 commit 后
                    # ORM 对象过期/StaleData 陷阱与 read-modify-write 丢计数）。
                    await self._commit_candidate_state(
                        cast(str, candidate.canonical_path),
                        purge_after=new_purge_after,
                        purge_delay_count=OrphanCurrentCandidate.purge_delay_count + 1,
                    )
                    logger.warning(
                        "[隔离清理] %s: %s (purge_after 已延后至 %s, 累计延后次数+1)",
                        qpath,
                        he.reason,
                        new_purge_after,
                    )
                    failed_count += 1
                    skipped_hardlink.append(
                        {
                            "canonical_path": he.canonical_path,
                            "quarantine_path": he.quarantine_path,
                            "reason": he.reason,
                            "copies": he.copies,
                        }
                    )
                    continue
                except Exception as he:
                    logger.warning("[隔离清理] 硬链接检测异常，保守跳过 %s: %s", qpath, he)
                    failed_count += 1
                    continue

                tombstone_path = build_quarantine_path(qpath, quarantine_root)
                await self._commit_candidate_state(
                    candidate.canonical_path,
                    operation_state="purge_pending",
                    operation_target_path=tombstone_path,
                    operation_error=None,
                )
                await _lease_handle.assert_owned()
                quarantine_file(
                    qpath,
                    quarantine_root,
                    dest_path=tombstone_path,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                await _lease_handle.assert_owned()
                prune_empty_quarantine_parents(qpath, quarantine_root)
                if not self._path_in_quarantine_root(tombstone_path, quarantine_root):
                    raise OSError("tombstone 路径越过 quarantine_root，拒绝删除")
                ok, reason = verify_file_identity(
                    tombstone_path,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    raise OSError(reason)
                await _lease_handle.assert_owned()
                os.remove(tombstone_path)
                await _lease_handle.assert_owned()
                prune_empty_quarantine_parents(tombstone_path, quarantine_root)
                await self._mark_purged(candidate.canonical_path)
                purged_count += 1
                logger.info(f"[隔离清理] 物理删除: {qpath}")

            except Exception as e:
                if tombstone_path and candidate.quarantine_root and not os.path.exists(tombstone_path):
                    prune_empty_quarantine_parents(tombstone_path, candidate.quarantine_root)
                logger.error(f"[隔离清理] 删除失败 {candidate.quarantine_path}: {e}")
                failed_count += 1

        logger.info(
            "[隔离清理] 完成: 物理删除=%d 失败=%d 跳过硬链接=%d 候选=%d 循环内manifest构建=%d次(耗时=%.2fs) 循环总耗时=%.2fs",
            purged_count,
            failed_count,
            len(skipped_hardlink),
            len(candidates),
            _in_loop_manifest_builds,
            _in_loop_manifest_total_time,
            time.monotonic() - _loop_started,
        )
        return {
            "purged_count": purged_count,
            "failed_count": failed_count,
            "skipped_hardlink": skipped_hardlink,
        }

    # ==================== 隔离区管理（恢复 / 立即彻底删除 / 列表） ====================

    async def get_quarantine_list(
        self,
        page: int = 1,
        page_size: int = 20,
        downloader_id: Optional[str] = None,
        path_like: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询隔离区文件列表（status=quarantined 的候选）。

        只读，无需 lease。返回 candidate 的隔离元数据 + 下载器昵称。
        """
        conditions = [
            OrphanCurrentCandidate.status == "quarantined",
            OrphanCurrentCandidate.operation_state == "stable",
            OrphanCurrentCandidate.canonical_path.notin_(active_purge_canonical_paths_query()),
        ]
        if downloader_id:
            conditions.append(OrphanCurrentCandidate.downloader_id == downloader_id)
        if path_like:
            conditions.append(OrphanCurrentCandidate.canonical_path.like(f"%{path_like}%"))

        total_result = await self.db.execute(
            select(func.count()).select_from(OrphanCurrentCandidate).where(*conditions)
        )
        total = int(total_result.scalar() or 0)

        list_query = (
            select(OrphanCurrentCandidate)
            .where(*conditions)
            .order_by(OrphanCurrentCandidate.purge_after.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(list_query)
        candidates = result.scalars().all()

        # 批量补下载器昵称
        downloader_ids = {c.downloader_id for c in candidates if c.downloader_id}
        nickname_map: Dict[str, str] = {}
        if downloader_ids:
            from app.downloader.models import BtDownloaders

            dl_result = await self.db.execute(
                select(BtDownloaders.downloader_id, BtDownloaders.nickname).where(
                    BtDownloaders.downloader_id.in_(downloader_ids)
                )
            )
            nickname_map = {row[0]: row[1] for row in dl_result.all() if row[1]}

        item_list = []
        for c in candidates:
            item_list.append(
                {
                    "canonical_path": c.canonical_path,
                    "downloader_id": c.downloader_id,
                    "downloader_name": nickname_map.get(c.downloader_id) if c.downloader_id else None,
                    "quarantine_path": c.quarantine_path,
                    "quarantine_root": c.quarantine_root,
                    "mtime": (
                        datetime.utcfromtimestamp(c.mtime_ns / 1_000_000_000).isoformat() if c.mtime_ns else None
                    ),
                    "quarantined_at": c.quarantined_at.isoformat() if c.quarantined_at else None,
                    "purge_after": c.purge_after.isoformat() if c.purge_after else None,
                    "purge_delay_count": c.purge_delay_count,
                    "file_size": c.file_size,
                    "confidence": c.confidence,
                }
            )

        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "list": item_list,
        }

    async def prune_recorded_empty_quarantine_dirs(
        self,
        _lease_acquired: bool = False,
    ) -> Dict[str, int]:
        """清理候选记录可追溯的历史空 UUID 目录和空 scan_id 根目录。"""
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("quarantine_dir_prune", db=self.db):
                    return await self.prune_recorded_empty_quarantine_dirs(
                        _lease_acquired=True,
                    )
            except OrphanLeaseBusyError:
                # 不与正在创建操作目录的 quarantine/purge 竞争；
                # 后续任务或下次启动会再次尝试历史清理。
                logger.info("[隔离区] 孤儿维护租约忙，跳过本次历史空目录清理")
                return {"root_count": 0, "removed_dir_count": 0}

        result = await self.db.execute(
            select(OrphanCurrentCandidate.quarantine_root)
            .where(OrphanCurrentCandidate.quarantine_root.isnot(None))
            .distinct()
        )
        roots = [str(root) for root in result.scalars().all() if root]

        def _prune_all() -> int:
            return sum(prune_recorded_quarantine_root(root) for root in roots)

        removed_count = await asyncio.to_thread(_prune_all) if roots else 0
        if removed_count:
            logger.info(
                "[隔离区] 历史空目录清理完成 roots=%d removed=%d",
                len(roots),
                removed_count,
            )
        return {"root_count": len(roots), "removed_dir_count": removed_count}

    async def restore_quarantined(
        self,
        canonical_paths: List[str],
        operator: str,
        audit_service: Any = None,
        _lease_acquired: bool = False,
        _lease_handle: Any = None,
    ) -> Dict[str, Any]:
        """从隔离区恢复文件到原位置（mark_quarantined 的逆操作）。

        安全检查：
        - operation_state 必须为 stable（避免与崩溃恢复冲突）
        - quarantine_path 必须存在；canonical_path 原位必须不存在（防 Windows rename 覆盖）
        - quarantine_path 必须仍在 quarantine_root 内（防路径篡改）
        - verify_file_identity 身份复核（size/mtime_ns/inode）
        """
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("manual_restore", db=self.db) as lease_handle:
                    return await self.restore_quarantined(
                        canonical_paths=canonical_paths,
                        operator=operator,
                        audit_service=audit_service,
                        _lease_acquired=True,
                        _lease_handle=lease_handle,
                    )
            except OrphanLeaseBusyError as exc:
                return {
                    "restored_count": 0,
                    "failed_count": len(canonical_paths),
                    "failed_list": [{"canonical_path": p, "reason": str(exc)} for p in canonical_paths],
                    "rejected": True,
                    "error": str(exc),
                }

        _loop_started = time.monotonic()
        logger.info("[隔离恢复] 开始 canonical_paths=%d operator=%s", len(canonical_paths), operator)

        result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.canonical_path.in_(canonical_paths),
                OrphanCurrentCandidate.status == "quarantined",
                OrphanCurrentCandidate.operation_state == "stable",
                OrphanCurrentCandidate.canonical_path.notin_(active_purge_canonical_paths_query()),
            )
        )
        candidates = result.scalars().all()

        restored_count = 0
        failed_list: List[Dict[str, Any]] = []

        for candidate in candidates:
            try:
                qpath = candidate.quarantine_path
                canonical = candidate.canonical_path
                # 安全检查：隔离文件存在
                if not qpath or not os.path.exists(qpath):
                    failed_list.append({"canonical_path": canonical, "reason": "隔离区文件不存在"})
                    continue
                # 安全检查：原位不存在（防 Windows os.rename 覆盖其它文件）
                if os.path.exists(canonical):
                    failed_list.append({"canonical_path": canonical, "reason": "原位置已被占用，拒绝恢复（避免覆盖）"})
                    continue
                # 安全检查：路径仍在隔离区内（防路径篡改）
                qroot = candidate.quarantine_root
                if qroot:
                    try:
                        if os.path.commonpath([os.path.realpath(qpath), os.path.realpath(qroot)]) != os.path.realpath(
                            qroot
                        ):
                            failed_list.append({"canonical_path": canonical, "reason": "隔离路径逃逸，拒绝恢复"})
                            continue
                    except ValueError:
                        failed_list.append({"canonical_path": canonical, "reason": "隔离路径跨驱动器，拒绝恢复"})
                        continue
                # 身份复核
                ok, reason = verify_file_identity(
                    qpath,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    failed_list.append({"canonical_path": canonical, "reason": f"身份复核失败: {reason}"})
                    continue

                await _lease_handle.assert_owned()
                # 还原到原位（与移入时的 os.rename 互逆）
                os.rename(qpath, canonical)
                await _lease_handle.assert_owned()

                # 回滚候选 + 明细（同一事务）
                await self._finalize_restore(candidate, operator=operator)
                prune_empty_quarantine_parents(qpath, qroot)
                restored_count += 1
                logger.info("[隔离恢复] 已还原: %s -> %s", qpath, canonical)

            except Exception as e:
                logger.error("[隔离恢复] 恢复失败 %s: %s", candidate.canonical_path, e)
                failed_list.append(
                    {
                        "canonical_path": candidate.canonical_path,
                        "quarantine_path": candidate.quarantine_path,
                        "reason": str(e),
                    }
                )

        # 未匹配的 canonical_paths：区分「已恢复（幂等成功）」/「状态不符」/「不存在」。
        # 崩溃恢复重跑场景下，上次执行已还原的候选（status=candidate，mark_restored
        # 把候选从 quarantined 回滚到 candidate）必须视为成功，否则任务被误报 partial
        # 且错误信息误导用户（与 purge_quarantine_now 的三态区分同构）。
        matched = {c.canonical_path for c in candidates}
        for p in canonical_paths:
            if p in matched:
                continue
            row = (
                await self.db.execute(
                    select(OrphanCurrentCandidate.status, OrphanCurrentCandidate.operation_state).where(
                        OrphanCurrentCandidate.canonical_path == p
                    )
                )
            ).first()
            if row is not None and row.status == "candidate":
                logger.info("[隔离恢复] 候选已恢复，幂等成功: %s", p)
                restored_count += 1
                continue
            if row is not None:
                failed_list.append(
                    {
                        "canonical_path": p,
                        "reason": (
                            "候选状态不符"
                            f"（status={row.status}, operation_state={row.operation_state}），"
                            "可能已被删除或仍在处理中"
                        ),
                    }
                )
                continue
            failed_list.append({"canonical_path": p, "reason": "候选不存在（未找到对应记录）"})

        # 审计日志
        if audit_service and restored_count > 0:
            try:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ORPHAN_RESTORE.value,
                    operator=operator,
                    operation_detail={
                        "action": "manual_restore",
                        "restored_count": restored_count,
                        "failed_count": len(failed_list),
                    },
                    operation_result=AuditOperationResult.SUCCESS if not failed_list else AuditOperationResult.PARTIAL,
                    error_message=f"失败 {len(failed_list)} 个" if failed_list else None,
                )
            except Exception as e:
                logger.warning("[隔离恢复] 审计日志记录失败: %s", e)

        logger.info(
            "[隔离恢复] 完成 restored=%d failed=%d 耗时=%.2fs",
            restored_count,
            len(failed_list),
            time.monotonic() - _loop_started,
        )
        return {
            "restored_count": restored_count,
            "failed_count": len(failed_list),
            "failed_list": failed_list,
        }

    async def _finalize_restore(self, candidate: OrphanCurrentCandidate, *, operator: str) -> None:
        """在同一事务中回滚候选（mark_restored）+ 回滚扫描明细（is_deleted=False）。"""
        effective_scan_id = candidate.last_seen_scan_id
        try:
            async with admission_controller.db_write_scope():
                candidate_updated = await OrphanLifecycleService(self.db).mark_restored(
                    canonical_path=candidate.canonical_path,
                    commit=False,
                )
                if not candidate_updated:
                    raise RuntimeError(f"候选不存在，无法最终化恢复: {candidate.canonical_path}")
                # 回滚明细：匹配同批次、同下载器、同路径、已删除的明细
                if effective_scan_id:
                    detail_conditions: List[Any] = [
                        OrphanFile.is_deleted == True,  # noqa: E712
                    ]
                    if candidate.current_detail_id is not None:
                        detail_conditions.append(OrphanFile.id == candidate.current_detail_id)
                    else:
                        detail_conditions.extend(
                            [
                                OrphanFile.scan_id == effective_scan_id,
                                OrphanFile.downloader_id == candidate.downloader_id,
                                OrphanFile.canonical_path == candidate.canonical_path,
                            ]
                        )
                    await self.db.execute(
                        update(OrphanFile)
                        .where(*detail_conditions)
                        .values(is_deleted=False, deleted_at=None, deleted_by=None)
                    )
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def purge_quarantine_now(
        self,
        canonical_paths: List[str],
        operator: str,
        store: Any = None,
        audit_service: Any = None,
        _lease_acquired: bool = False,
        _lease_handle: Any = None,
    ) -> Dict[str, Any]:
        """立即彻底删除隔离区文件（跳过 purge_after 时间门禁，保留全部安全检查）。

        复用 purge_expired_quarantine 的安全检查全套（manifest 复核/路径校验/身份复核/tombstone），
        唯一区别：不要求 purge_after < now。
        """
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("manual_purge", db=self.db) as lease_handle:
                    return await self.purge_quarantine_now(
                        canonical_paths=canonical_paths,
                        operator=operator,
                        store=store,
                        audit_service=audit_service,
                        _lease_acquired=True,
                        _lease_handle=lease_handle,
                    )
            except OrphanLeaseBusyError as exc:
                return {
                    "purged_count": 0,
                    "failed_count": len(canonical_paths),
                    "failed_list": [{"canonical_path": p, "reason": str(exc)} for p in canonical_paths],
                    "rejected": True,
                    "error": str(exc),
                }

        await self._recover_interrupted_operations(store=store, lease_handle=_lease_handle)

        _loop_started = time.monotonic()
        logger.info("[隔离删除] 开始 canonical_paths=%d operator=%s", len(canonical_paths), operator)

        result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.canonical_path.in_(canonical_paths),
                OrphanCurrentCandidate.status == "quarantined",
                OrphanCurrentCandidate.operation_state == "stable",
            )
        )
        candidates = result.scalars().all()

        purged_count = 0
        failed_list: List[Dict[str, Any]] = []
        hardlink_notes: List[Dict[str, Any]] = []

        # manifest 按 downloader 预构建缓存：禁止逐文件重建（N 文件 = 1 次/下载器，
        # 修复前每文件 2 次全量下载器 API 拉取，是"分钟级/文件"的性能放大器）。
        manifest_cache: Dict[str, Optional[ManifestSnapshot]] = {}

        for candidate in candidates:
            try:
                # 候选表 downloader_id 非空；ORM 列类型标注缺失，cast 仅辅助静态检查
                downloader_id = cast(str, candidate.downloader_id)
                if downloader_id not in manifest_cache:
                    manifest_cache[downloader_id] = await self._build_realtime_manifest(store, {downloader_id})
                note = await self._purge_single_candidate(
                    candidate,
                    store,
                    _lease_handle,
                    manifest=manifest_cache[downloader_id],
                    mode="purge_now",
                )
                purged_count += 1
                if note is not None:
                    hardlink_notes.append(note)
            except Exception as e:
                logger.error("[隔离删除] 删除失败 %s: %s", candidate.quarantine_path, e)
                failed_list.append(
                    {
                        "canonical_path": candidate.canonical_path,
                        "quarantine_path": candidate.quarantine_path,
                        "reason": str(e),
                    }
                )

        # 未匹配的 canonical_paths：区分"已删除（幂等成功）"与"真不存在/状态不符"。
        # 崩溃恢复重跑场景下，上次执行已物理删除的候选（status=purged）必须视为
        # 成功，否则任务被误报 partial 且错误信息误导用户。
        matched = {c.canonical_path for c in candidates}
        for p in canonical_paths:
            if p in matched:
                continue
            row = (
                await self.db.execute(
                    select(
                        OrphanCurrentCandidate.status,
                        OrphanCurrentCandidate.operation_state,
                    ).where(OrphanCurrentCandidate.canonical_path == p)
                )
            ).first()
            if row is not None and row.status == "purged":
                logger.info("[隔离删除] 候选已删除，幂等成功: %s", p)
                purged_count += 1
                continue
            if row is not None:
                failed_list.append(
                    {
                        "canonical_path": p,
                        "reason": (
                            "候选状态不符"
                            f"（status={row.status}, operation_state={row.operation_state}），"
                            "可能已被恢复或仍在处理中"
                        ),
                    }
                )
                continue
            failed_list.append({"canonical_path": p, "reason": "候选不存在（未找到对应记录）"})

        # 审计日志
        if audit_service and purged_count > 0:
            try:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ORPHAN_PURGE.value,
                    operator=operator,
                    operation_detail={
                        "action": "manual_purge",
                        "purged_count": purged_count,
                        "failed_count": len(failed_list),
                    },
                    operation_result=AuditOperationResult.SUCCESS if not failed_list else AuditOperationResult.PARTIAL,
                    error_message=f"失败 {len(failed_list)} 个" if failed_list else None,
                )
            except Exception as e:
                logger.warning("[隔离删除] 审计日志记录失败: %s", e)

        logger.info(
            "[隔离删除] 完成 purged=%d failed=%d hardlink_notes=%d 耗时=%.2fs",
            purged_count,
            len(failed_list),
            len(hardlink_notes),
            time.monotonic() - _loop_started,
        )
        return {
            "purged_count": purged_count,
            "failed_count": len(failed_list),
            "failed_list": failed_list,
            "hardlink_notes": hardlink_notes,
        }

    async def _purge_single_candidate(
        self,
        candidate: OrphanCurrentCandidate,
        store: Any,
        _lease_handle: Any,
        manifest: Optional[ManifestSnapshot] = None,
        mode: str = "purge_now",
    ) -> Optional[Dict[str, Any]]:
        """物理删除单个隔离候选（保留 purge_expired_quarantine 的全部安全检查）。

        抽取自 purge_expired_quarantine 循环体，供立即删除与到期删除共享。

        Args:
            manifest: 调用方按 downloader 预构建的实时 manifest（可复用）；为 None
                时降级为逐文件构建（仅作兜底，正常路径由 purge_quarantine_now 提供）。
            mode: ``purge_now``（立即彻底删除）或 ``purge_expired``（到期自动删除）。
                两者对硬链接副本的处理不同：
                - purge_now：照常删除，返回副本诊断（路径 + is_seed）供通知展示；
                - purge_expired：存在副本时抛 ``HardlinkCopyError`` 跳过删除（安全优先）。

        Returns:
            立即删除模式下，若被删文件存在其它硬链接副本，返回 hardlink_note 字典；
            否则返回 None。
        """
        qpath = candidate.quarantine_path
        if not qpath or not os.path.exists(qpath):
            # 文件已不在隔离区（可能已被手动清理），直接标记
            await self._mark_purged(candidate.canonical_path)
            prune_empty_quarantine_parents(qpath, candidate.quarantine_root)
            return None

        # 文件进入隔离区后，物理删除只校验持久化的隔离路径和文件身份。
        # 不再用 manifest 为隔离路径授权；manifest 仅作为可选的原路径引用
        # 复核，不能参与实际删除路径解析。
        if manifest is None:
            manifest = await self._build_realtime_manifest(store, {candidate.downloader_id})
        reference_manifest = manifest
        if (
            reference_manifest is not None
            and normalize_path(candidate.canonical_path) in reference_manifest.expected_paths
        ):
            raise OSError("文件当前已被种子引用，拒绝删除")
        guard_error = self._quarantine_delete_guard_error(candidate)
        if guard_error:
            raise OSError(guard_error)
        identity_error = await self._ensure_quarantine_identity(candidate, qpath)
        if identity_error:
            raise OSError(identity_error)

        # 二次验证：路径仍在隔离区内
        quarantine_root = candidate.quarantine_root
        if not quarantine_root:
            raise OSError("路径不在隔离区内")
        if not self._path_in_quarantine_root(qpath, quarantine_root):
            raise OSError("隔离文件路径越过 quarantine_root，拒绝删除")

        ok, reason = verify_file_identity(
            qpath,
            expected_size=candidate.file_size,
            expected_mtime_ns=candidate.mtime_ns,
            expected_inode=self._candidate_inode(candidate),
        )
        if not ok:
            raise OSError(f"身份复核失败: {reason}")

        # 硬链接副本检测：删除前抓取 inode/nlink（删除后 inode 失效无法反查）。
        # 仅在 nlink>1 时触发副本枚举，限定在候选所属 downloader 的 scan_roots。
        hardlink_note = await self._detect_hardlink_copies(candidate, cast(str, qpath), manifest, mode, store)

        # tombstone 预写 + 物理删除（与 purge_expired_quarantine 一致）
        tombstone_path = build_quarantine_path(qpath, quarantine_root)
        try:
            await self._commit_candidate_state(
                candidate.canonical_path,
                operation_state="purge_pending",
                operation_target_path=tombstone_path,
                operation_error=None,
            )
            await _lease_handle.assert_owned()
            quarantine_file(
                qpath,
                quarantine_root,
                dest_path=tombstone_path,
                expected_size=candidate.file_size,
                expected_mtime_ns=candidate.mtime_ns,
                expected_inode=self._candidate_inode(candidate),
            )
            await _lease_handle.assert_owned()
            prune_empty_quarantine_parents(qpath, quarantine_root)
            # tombstone 仍必须位于同一个持久化隔离根内；下面的 manifest 只做
            # 原路径引用复核，不参与 tombstone 的物理路径解析或授权。
            if not self._path_in_quarantine_root(tombstone_path, quarantine_root):
                raise OSError("tombstone 路径越过 quarantine_root，拒绝删除")
            delete_manifest = (
                manifest
                if manifest is not None
                else await self._build_realtime_manifest(store, {candidate.downloader_id})
            )
            if (
                delete_manifest is not None
                and normalize_path(candidate.canonical_path) in delete_manifest.expected_paths
            ):
                raise OSError("tombstone 删除前原路径已被种子引用")
            ok2, reason2 = verify_file_identity(
                tombstone_path,
                expected_size=candidate.file_size,
                expected_mtime_ns=candidate.mtime_ns,
                expected_inode=self._candidate_inode(candidate),
            )
            if not ok2:
                raise OSError(reason2)
            await _lease_handle.assert_owned()
            os.remove(tombstone_path)
            await _lease_handle.assert_owned()
            prune_empty_quarantine_parents(tombstone_path, quarantine_root)
            await self._mark_purged(candidate.canonical_path)
            logger.info("[隔离删除] 物理删除: %s", qpath)
        except Exception:
            # build_quarantine_path 会先建目录；若文件尚未移入，立即回收该空目录。
            if not os.path.exists(tombstone_path):
                prune_empty_quarantine_parents(tombstone_path, quarantine_root)
            raise
        return hardlink_note

    async def _detect_hardlink_copies(
        self,
        candidate: OrphanCurrentCandidate,
        qpath: str,
        manifest: Optional[ManifestSnapshot],
        mode: str,
        store: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """删除/清理前检测硬链接副本。

        - nlink=1：无副本，返回 None（不触碰 manifest）。
        - nlink>1：需要 manifest 推导 scan_roots 与 is_seed。manifest 为 None 时
          按需构建一次（仅此场景，常规 nlink=1 操作不依赖 manifest）。
          - purge_now（立即删除）/ cleanup_warn（清理预警）：返回 hardlink_note
            字典，操作照常进行（不阻断，因为两者都是可恢复/可后续决策的）。
          - purge_expired（到期删除）：抛 HardlinkCopyError 由上层跳过删除
            （安全优先，到期自动删除不可恢复）。
        - inode 不可靠（网络盘等 stat 失败）：
          - purge_now / cleanup_warn：照常操作，仅缺诊断（记 warning）。
          - purge_expired：保守跳过（抛 HardlinkCopyError，reason 标注不可靠）。
        """
        # ORM 列类型标注缺失，cast 仅辅助静态检查（运行期为真实值）。
        canonical_path = cast(str, candidate.canonical_path)
        try:
            qstat = os.stat(qpath)
        except OSError as exc:
            if mode == "purge_expired":
                raise HardlinkCopyError(
                    canonical_path,
                    qpath,
                    [],
                    reason="隔离文件 inode 不可靠，跳过到期删除",
                ) from exc
            logger.warning("[隔离删除] inode 不可靠，跳过硬链接诊断: %s (%s)", qpath, exc)
            return None

        if qstat.st_nlink <= 1:
            return None

        # nlink>1：按需补建 manifest（仅此场景），用于推导 scan_roots 与 is_seed。
        if manifest is None and store is not None:
            manifest = await self._build_realtime_manifest(store, {candidate.downloader_id})

        scan_roots = self._candidate_scan_roots(candidate, manifest)
        if not scan_roots:
            # manifest 不可用或候选 downloader 不在 scan_roots：无法枚举具体副本路径。
            # 立即删除照常（仅缺诊断）；到期删除仍按 nlink>1 跳过。
            if mode == "purge_expired":
                raise HardlinkCopyError(
                    canonical_path,
                    qpath,
                    [],
                    reason="存在其它硬链接副本（manifest 不可用，无法枚举具体路径），跳过到期删除",
                )
            logger.info("[隔离删除] manifest 不可用，仅按 nlink 检测副本: %s", qpath)
            return None

        try:
            copy_paths = find_hardlink_copies(
                target_inode=(qstat.st_dev, qstat.st_ino),
                scan_roots=scan_roots,
                exclude_path=qpath,
            )
        except OSError as exc:
            if mode == "purge_expired":
                raise HardlinkCopyError(
                    canonical_path,
                    qpath,
                    [],
                    reason="硬链接副本枚举失败，跳过到期删除",
                ) from exc
            logger.warning("[隔离删除] 副本枚举失败，仅缺诊断: %s (%s)", qpath, exc)
            return None

        expected = manifest.expected_paths if manifest is not None else set()
        copies = [{"path": p, "is_seed": normalize_path(p) in expected} for p in copy_paths]
        note = {
            "canonical_path": canonical_path,
            "deleted_path": qpath,
            "remaining_count": len(copies),
            "copies": copies,
        }
        logger.info("[隔离删除] 检测到硬链接副本 path=%s copies=%d", qpath, len(copies))
        if mode == "purge_expired":
            raise HardlinkCopyError(
                canonical_path,
                qpath,
                copies,
                reason=f"存在 {len(copies)} 个其它硬链接副本，跳过到期删除",
            )
        return note

    @staticmethod
    def _candidate_scan_roots(candidate: OrphanCurrentCandidate, manifest: Optional[ManifestSnapshot]) -> List[str]:
        """取候选所属 downloader 在 manifest.scan_roots 中的扫描根列表。"""
        if manifest is None:
            return []
        downloader_id = candidate.downloader_id
        return [root for root, owners in manifest.scan_roots if downloader_id in owners]

    async def _mark_purged(self, canonical_path: str) -> None:
        """标记候选为已物理删除。"""
        try:
            async with admission_controller.db_write_scope():
                updated = await OrphanLifecycleService(self.db).mark_purged(
                    canonical_path,
                    commit=False,
                )
                if not updated:
                    raise RuntimeError(f"候选不存在，无法标记 purged: {canonical_path}")
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def _matching_undeleted_details(
        self,
        candidate: OrphanCurrentCandidate,
        scan_id: str,
    ) -> List[OrphanFile]:
        """按批次、下载器身份和规范化路径定位所有未清理明细。"""
        if candidate.current_detail_id is not None:
            detail_result = await self.db.execute(
                select(OrphanFile).where(
                    OrphanFile.id == candidate.current_detail_id,
                    OrphanFile.is_deleted == False,  # noqa: E712
                )
            )
            return detail_result.scalars().all()

        detail_result = await self.db.execute(
            select(OrphanFile).where(
                OrphanFile.scan_id == scan_id,
                OrphanFile.is_deleted == False,  # noqa: E712
            )
        )
        candidate_downloader = candidate.downloader_id or ""
        candidate_path = normalize_path(candidate.canonical_path)
        return [
            detail
            for detail in detail_result.scalars().all()
            if (detail.downloader_id or "") == candidate_downloader
            and normalize_path(detail.file_path) == candidate_path
        ]

    async def _finalize_quarantine(
        self,
        candidate: OrphanCurrentCandidate,
        *,
        quarantine_path: str,
        quarantine_root: str,
        purge_after: datetime,
        scan_id: Optional[str],
        operator: str,
    ) -> int:
        """在同一最终事务中稳定候选并标记对应扫描明细。"""
        effective_scan_id = scan_id or candidate.last_seen_scan_id
        if not effective_scan_id:
            raise RuntimeError("候选缺少 last_seen_scan_id，无法最终化隔离")

        details = await self._matching_undeleted_details(candidate, effective_scan_id)
        if not details:
            raise RuntimeError("隔离最终化找不到同批次、同下载器、同路径的未清理明细")

        finalized_at = datetime.utcnow()
        detail_ids = [detail.id for detail in details]
        try:
            async with admission_controller.db_write_scope():
                candidate_updated = await OrphanLifecycleService(self.db).mark_quarantined(
                    canonical_path=candidate.canonical_path,
                    quarantine_path=quarantine_path,
                    quarantine_root=quarantine_root,
                    purge_after=purge_after,
                    quarantined_at=finalized_at,
                    commit=False,
                )
                if not candidate_updated:
                    raise RuntimeError(f"候选不存在，无法最终化隔离: {candidate.canonical_path}")
                detail_update = await self.db.execute(
                    update(OrphanFile)
                    .where(
                        OrphanFile.id.in_(detail_ids),
                        OrphanFile.is_deleted == False,  # noqa: E712
                    )
                    .values(
                        is_deleted=True,
                        deleted_at=finalized_at,
                        deleted_by=operator,
                    )
                )
                if int(detail_update.rowcount or 0) != len(detail_ids):
                    raise RuntimeError("隔离最终化期间扫描明细发生并发变化")
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return len(detail_ids)

    async def _commit_candidate_state(self, canonical_path: str, **values: Any) -> None:
        """提交不涉及扫描明细的候选恢复状态。"""
        try:
            async with admission_controller.db_write_scope():
                result = await self.db.execute(
                    update(OrphanCurrentCandidate)
                    .where(OrphanCurrentCandidate.canonical_path == canonical_path)
                    .values(**values)
                )
                if not result.rowcount:
                    raise RuntimeError(f"候选不存在: {canonical_path}")
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def _quarantine_candidate(
        self,
        candidate: OrphanCurrentCandidate,
        source_path: str,
        quarantine_root: str,
        *,
        scan_id: Optional[str],
        operator: str,
        lease_handle: Any,
    ) -> str:
        """用预写操作状态跨越数据库与文件系统之间的崩溃窗口。"""
        if lease_handle is None:
            raise RuntimeError("隔离操作缺少维护租约")
        await lease_handle.assert_owned()

        os.makedirs(quarantine_root, exist_ok=True)
        target_path = build_quarantine_path(source_path, quarantine_root)
        purge_after = compute_purge_after(datetime.utcnow())
        candidate.operation_state = "quarantine_pending"
        candidate.operation_target_path = target_path
        candidate.operation_error = None
        candidate.quarantine_root = quarantine_root
        candidate.purge_after = purge_after
        try:
            async with admission_controller.db_write_scope():
                await self.db.commit()
            quarantine_path = quarantine_file(
                source_path,
                quarantine_root,
                dest_path=target_path,
                expected_size=candidate.file_size,
                expected_mtime_ns=candidate.mtime_ns,
                expected_inode=self._candidate_inode(candidate),
            )
            await lease_handle.assert_owned()
            await self._finalize_quarantine(
                candidate,
                quarantine_path=quarantine_path,
                quarantine_root=quarantine_root,
                purge_after=purge_after,
                scan_id=scan_id,
                operator=operator,
            )
            return quarantine_path
        except Exception:
            await self.db.rollback()
            if not os.path.exists(target_path):
                prune_empty_quarantine_parents(target_path, quarantine_root)
            raise

    async def _recover_interrupted_operations(
        self,
        manifest: Optional[ManifestSnapshot] = None,
        store: Any = None,
        lease_handle: Any = None,
    ) -> Dict[str, int]:
        """恢复上次进程在 rename/remove 与最终 DB 提交之间中断的操作。"""
        result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.operation_state.in_(["quarantine_pending", "purge_pending"])
            )
        )
        candidates = result.scalars().all()
        if not candidates:
            return {"recovered": 0, "failed": 0}

        pending_candidates = [(str(candidate.canonical_path), str(candidate.downloader_id)) for candidate in candidates]
        quarantine_pending_ids = {
            str(candidate.downloader_id)
            for candidate in candidates
            if candidate.operation_state == "quarantine_pending"
        }
        if quarantine_pending_ids and (
            manifest is None or not quarantine_pending_ids.issubset(manifest.downloader_ids)
        ):
            manifest = await self._build_realtime_manifest(
                store,
                quarantine_pending_ids,
            )
        if quarantine_pending_ids and (
            manifest is None or not quarantine_pending_ids.issubset(manifest.downloader_ids)
        ):
            reason = "恢复 manifest 未覆盖全部 quarantine_pending 下载器，保持 pending"
            try:
                async with admission_controller.db_write_scope():
                    await self.db.execute(
                        update(OrphanCurrentCandidate)
                        .where(OrphanCurrentCandidate.operation_state.in_(["quarantine_pending", "purge_pending"]))
                        .values(operation_error=reason)
                    )
                    await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise
            logger.error("[孤儿操作恢复] %s", reason)
            return {"recovered": 0, "failed": len(pending_candidates)}

        recovered = 0
        failed = 0

        for canonical_path, _ in pending_candidates:
            candidate = await self.db.get(OrphanCurrentCandidate, canonical_path)
            if candidate is None or candidate.operation_state not in (
                "quarantine_pending",
                "purge_pending",
            ):
                continue
            try:
                if candidate.operation_state == "purge_pending":
                    original = candidate.quarantine_path
                    target = candidate.operation_target_path
                    root = candidate.quarantine_root
                    original_exists = bool(original and os.path.exists(original))
                    target_exists = bool(target and os.path.exists(target))
                    if original_exists and target_exists:
                        raise OSError("purge 恢复发现原路径和 tombstone 同时存在")
                    if target_exists:
                        guard_error = self._quarantine_delete_guard_error(candidate)
                        if guard_error:
                            raise OSError(guard_error)
                        if not self._path_in_quarantine_root(target, root):
                            raise OSError("purge 恢复的 tombstone 越过 quarantine_root")
                        identity_error = await self._ensure_quarantine_identity(candidate, target)
                        if identity_error:
                            raise OSError(identity_error)
                        ok, reason = verify_file_identity(
                            target,
                            expected_size=candidate.file_size,
                            expected_mtime_ns=candidate.mtime_ns,
                            expected_inode=self._candidate_inode(candidate),
                        )
                        if not ok:
                            raise OSError(reason)
                        if lease_handle is None:
                            raise OSError("purge 恢复缺少维护租约")
                        await lease_handle.assert_owned()
                        os.remove(target)
                        await lease_handle.assert_owned()
                        prune_empty_quarantine_parents(original, root)
                        prune_empty_quarantine_parents(target, root)
                        await self._mark_purged(candidate.canonical_path)
                    elif original_exists:
                        await self._commit_candidate_state(
                            candidate.canonical_path,
                            status="quarantined",
                            operation_state="stable",
                            operation_target_path=None,
                            operation_error=None,
                        )
                        prune_empty_quarantine_parents(target, root)
                    else:
                        await self._mark_purged(candidate.canonical_path)
                        prune_empty_quarantine_parents(original, root)
                        prune_empty_quarantine_parents(target, root)
                    recovered += 1
                    continue

                source = candidate.canonical_path
                target = candidate.operation_target_path
                root = candidate.quarantine_root
                if target and os.path.exists(target):
                    ok, reason = verify_file_identity(
                        target,
                        expected_size=candidate.file_size,
                        expected_mtime_ns=candidate.mtime_ns,
                        expected_inode=self._candidate_inode(candidate),
                    )
                    if not ok:
                        raise OSError(reason)
                    if os.path.exists(source):
                        source_stat = os.stat(source)
                        target_stat = os.stat(target)
                        if (source_stat.st_dev, source_stat.st_ino) == (
                            target_stat.st_dev,
                            target_stat.st_ino,
                        ):
                            if lease_handle is None:
                                raise OSError("硬链接恢复缺少维护租约")
                            await lease_handle.assert_owned()
                            if normalize_path(source) in manifest.expected_paths:
                                os.unlink(target)
                                await lease_handle.assert_owned()
                                prune_empty_quarantine_parents(target, root)
                                await self._commit_candidate_state(
                                    candidate.canonical_path,
                                    status="resolved",
                                    operation_state="stable",
                                    operation_target_path=None,
                                    operation_error=None,
                                )
                                recovered += 1
                                continue
                            os.unlink(source)
                            await lease_handle.assert_owned()
                        else:
                            raise OSError("隔离恢复发现源路径和目标路径身份不同，转人工处理")
                    await self._finalize_quarantine(
                        candidate,
                        quarantine_path=target,
                        quarantine_root=root or os.path.dirname(target),
                        purge_after=candidate.purge_after or compute_purge_after(datetime.utcnow()),
                        scan_id=candidate.last_seen_scan_id,
                        operator="system:recovery",
                    )
                elif normalize_path(source) in manifest.expected_paths and os.path.exists(source):
                    await self._commit_candidate_state(
                        candidate.canonical_path,
                        status="resolved",
                        operation_state="stable",
                        operation_target_path=None,
                        operation_error=None,
                    )
                    prune_empty_quarantine_parents(target, root)
                elif target and root and os.path.exists(source):
                    if not self._path_authorized(candidate, manifest):
                        raise OSError("隔离恢复路径不属于授权扫描根")
                    if lease_handle is None:
                        raise OSError("隔离恢复缺少维护租约")
                    await lease_handle.assert_owned()
                    quarantine_file(
                        source,
                        root,
                        dest_path=target,
                        expected_size=candidate.file_size,
                        expected_mtime_ns=candidate.mtime_ns,
                        expected_inode=self._candidate_inode(candidate),
                    )
                    await lease_handle.assert_owned()
                    await self._finalize_quarantine(
                        candidate,
                        quarantine_path=target,
                        quarantine_root=root,
                        purge_after=candidate.purge_after or compute_purge_after(datetime.utcnow()),
                        scan_id=candidate.last_seen_scan_id,
                        operator="system:recovery",
                    )
                else:
                    raise OSError("隔离恢复时源路径与目标路径均不存在")
                recovered += 1
            except Exception as exc:
                # 保留 pending，后续维护任务继续恢复；错误原因用于诊断。
                await self.db.rollback()
                try:
                    await self._commit_candidate_state(
                        canonical_path,
                        operation_error=str(exc)[:1000],
                    )
                except Exception as error_commit_exc:
                    logger.error(
                        "[孤儿操作恢复] 记录恢复错误失败 %s: %s",
                        canonical_path,
                        error_commit_exc,
                    )
                failed += 1
                logger.error(f"[孤儿操作恢复] {canonical_path}: {exc}")

        return {"recovered": recovered, "failed": failed}
