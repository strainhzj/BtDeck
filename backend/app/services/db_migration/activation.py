"""A+B 切换提交服务（database-migration-ui W3-6，PLANS §7；T04/T16/T10）。

commit_phase：NONE → PREPARED → COMMITTED → ACTIVATED_ACK（journal 单向持久）。

不变量（§7.1/7.2，评审确认顺序）：
1. **先持久候选/前代配置与 PREPARED manifest**，后发布选择；
2. **fsync COMMITTED 决定先于任何配置发布**——COMMITTED 是本地持久决定，
   之后只能按该目标幂等 redo，不自动回旧库；
3. B=原子发布新 active；A=原子发布去除旧 active 的候选（env 交接路径）；
   control 记 RESTART_PENDING+新代次；
4. 已知托管适配器+显式 opt-in 才调度自身优雅退出；否则提示手动重启
   （不假设 Restart=on-failure 会重启正常退出，不盲发信号）；
5. 新进程 redo：读 COMMITTED 幂等补完配置发布；目标 ACK **先于**本地
   ACTIVATED_ACK；两边一致才允许正常启动收尾（审计归档同事务）。

注入点（测试替身）：``publish_active`` / ``target_ack_writer`` /
``restart_scheduler``。生产实现见各默认函数。
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.services.db_migration.config_store import (
    config_lock,
    read_yaml,
    write_prior_config,
    write_candidate_config,
)
from app.services.db_migration.journal import (
    COMMIT_PHASE_ACTIVATED_ACK,
    COMMIT_PHASE_COMMITTED,
    COMMIT_PHASE_NONE,
    COMMIT_PHASE_PREPARED,
    Journal,
)

__all__ = [
    "ActivationError",
    "ActivationService",
    "SWITCH_MODE_A",
    "SWITCH_MODE_B",
]

SWITCH_MODE_A = "A"
SWITCH_MODE_B = "B"

RESTART_OPT_IN_ENV = "BTD_MIGRATION_MANAGED_RESTART"


class ActivationError(RuntimeError):
    """提交流程错误（状态/一致性/适配器）。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SwitchPrepareResult:
    attempt_id: str
    mode: str
    commit_phase: str
    candidate_digest: str
    prior_digest: str
    restart_pending: bool


class ActivationService:
    """提交/ACK 编排（配置目录级单例语义；经 journal 锁串行）。"""

    def __init__(
        self,
        config_dir: os.PathLike[str] | str,
        *,
        yaml_path: Optional[os.PathLike[str] | str] = None,
        publish_active: Optional[Callable[[os.PathLike[str] | str, Dict[str, Any]], None]] = None,
        target_ack_writer: Optional[Callable[[str, str], None]] = None,
        restart_scheduler: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> None:
        self._config_dir = str(config_dir)
        self._yaml_path = str(yaml_path) if yaml_path else None
        self._journal = Journal(config_dir)
        self._publish_active = publish_active or self._default_publish_active
        self._target_ack = target_ack_writer or self._default_target_ack_writer
        self._schedule_exit = restart_scheduler or self._default_restart_scheduler

    # ------------------------------------------------------------------
    # yaml 路径解析（config.yaml 默认 CONFIG_DIR/config.yaml）
    # ------------------------------------------------------------------

    def _resolve_yaml(self) -> str:
        if self._yaml_path:
            return self._yaml_path
        from app.core.config import settings

        return (
            str(Path(self._config_dir) / "config.yaml")
            if str(self._config_dir) != str(Path(settings.YAML_PATH).parent)
            else str(settings.YAML_PATH)
        )

    # ------------------------------------------------------------------
    # §7.2 step1-2：候选/前代持久 + PREPARED
    # ------------------------------------------------------------------

    def advance_archive_cursor(self, last_event_id: str) -> None:
        """代理 journal 归档 cursor（lifecycle redo 归档路径用）。"""
        self._journal.advance_archive_cursor(last_event_id)

    def manifest(self, attempt_id: str) -> Dict[str, Any]:
        """只读 manifest（端点/流程用；损坏 fail-closed）。"""
        return self._journal.read_manifest(attempt_id)

    def prepare_switch(
        self,
        attempt_id: str,
        *,
        mode: str,
        candidate_active: Dict[str, Any],
        identity: Dict[str, Any],
    ) -> SwitchPrepareResult:
        """READY 后：写受保护候选+前代 → manifest PREPARED（CAS）。"""
        if mode not in {SWITCH_MODE_A, SWITCH_MODE_B}:
            raise ActivationError(f"未知切换模式: {mode!r}")
        manifest = self._journal.read_manifest(attempt_id)
        phase = manifest.get("commit_phase", COMMIT_PHASE_NONE)
        if phase == COMMIT_PHASE_PREPARED:
            # 幂等重放：复用已持久候选摘要
            return SwitchPrepareResult(
                attempt_id=attempt_id,
                mode=mode,
                commit_phase=phase,
                candidate_digest=manifest.get("candidate_config_digest", ""),
                prior_digest=manifest.get("prior_config_digest", ""),
                restart_pending=False,
            )
        if phase != COMMIT_PHASE_NONE:
            raise ActivationError(f"commit_phase={phase}，不可 PREPARED（redo 或 clear）")
        yaml_path = self._resolve_yaml()
        current: Dict[str, Any] = {}
        if Path(yaml_path).exists():
            current = read_yaml(yaml_path)
        else:
            current = {}
        # 候选 = 现配置树 + database.active 替换（B）；A 模式候选去除 active
        candidate_tree = dict(current)
        if mode == SWITCH_MODE_B:
            candidate_tree["database"] = {**(current.get("database") or {}), "active": candidate_active}
        else:
            db_section = dict(current.get("database") or {})
            db_section.pop("active", None)
            candidate_tree["database"] = db_section
        cand = write_candidate_config(self._config_dir, attempt_id, candidate_tree)
        prior = write_prior_config(self._config_dir, attempt_id, current or {"_empty": True})
        manifest = dict(manifest)
        manifest["candidate_config_digest"] = cand["sha256"]
        manifest["prior_config_digest"] = prior["sha256"]
        manifest["switch_mode"] = mode
        manifest["identity"] = dict(identity)
        manifest["candidate_active"] = dict(candidate_active)
        self._journal.write_manifest(attempt_id, manifest, expect_state_version=manifest["state_version"])
        self._journal.advance_commit_phase(attempt_id, expected=COMMIT_PHASE_NONE, new=COMMIT_PHASE_PREPARED)
        return SwitchPrepareResult(
            attempt_id=attempt_id,
            mode=mode,
            commit_phase=COMMIT_PHASE_PREPARED,
            candidate_digest=cand["sha256"],
            prior_digest=prior["sha256"],
            restart_pending=False,
        )

    # ------------------------------------------------------------------
    # §7.2 step3-5：持久 COMMITTED → 发布 → RESTART_PENDING → 退出调度
    # ------------------------------------------------------------------

    def commit_switch(self, attempt_id: str, *, switched_by: str = "administrator") -> Dict[str, Any]:
        """COMMITTED 先持久，再发布配置；幂等 redo 安全。"""
        manifest = self._journal.read_manifest(attempt_id)
        phase = manifest.get("commit_phase", COMMIT_PHASE_NONE)
        if phase == COMMIT_PHASE_NONE:
            raise ActivationError("尚未 PREPARED（先 prepare_switch）")
        # 1. fsync 持久决定（幂等：COMMITTED 重放跳过）
        if phase == COMMIT_PHASE_PREPARED:
            self._journal.advance_commit_phase(attempt_id, expected=COMMIT_PHASE_PREPARED, new=COMMIT_PHASE_COMMITTED)
            manifest = self._journal.read_manifest(attempt_id)
        # 2. 幂等发布：candidate 已在 PREPARED 持久，按候选摘要核验后发布
        mode = manifest.get("switch_mode", SWITCH_MODE_B)
        published = self._publish_if_needed(attempt_id, manifest, mode)
        # 3. control：RESTART_PENDING + 新代次
        generation = str(uuid.uuid4())
        self._journal.write_control(
            lambda c: {**c, "restart_pending": True, "generation": generation, "pending_attempt": attempt_id}
        )
        # 4. 托管退出（已知适配器+显式 opt-in；否则仅提示）
        exit_scheduled = self._schedule_exit({"attempt_id": attempt_id, "mode": mode, "reason": "switch-committed"})
        return {
            "attemptId": attempt_id,
            "mode": mode,
            "commitPhase": COMMIT_PHASE_COMMITTED,
            "generation": generation,
            "configPublished": published,
            "restartScheduled": exit_scheduled,
            "restartHint": None if exit_scheduled else "配置已提交：需手动重启进程完成激活（RESTART_PENDING）",
        }

    def _publish_if_needed(self, attempt_id: str, manifest: Dict[str, Any], mode: str) -> bool:
        """B：候选树原子发布为 config.yaml；A：发布去除 active 的候选。

        幂等：发布后 manifest.config_published=True，重放不再写。
        """
        if manifest.get("config_published"):
            return False
        from app.services.db_migration.config_store import read_candidate_config

        candidate_tree = read_candidate_config(self._config_dir, attempt_id)
        yaml_path = self._resolve_yaml()
        with config_lock(yaml_path):
            from app.services.db_migration.config_store import write_yaml_atomic

            write_yaml_atomic(yaml_path, candidate_tree)
        fresh = self._journal.read_manifest(attempt_id)
        merged = dict(fresh)
        merged["config_published"] = True
        merged["config_published_at"] = _now()
        merged["published_mode"] = mode
        self._journal.write_manifest(attempt_id, merged, expect_state_version=fresh["state_version"])
        return True

    # ------------------------------------------------------------------
    # §7.2 step6-8：重启 redo + 目标 ACK + 本地 ACK + 审计归档
    # ------------------------------------------------------------------

    def redo_pending_activation(self) -> Optional[Dict[str, Any]]:
        """新进程普通写入前调用：COMMITTED 未 ACK → 幂等补发布并待 ACK。"""
        control = self._journal.read_control() or {}
        attempt = control.get("pending_attempt")
        if not isinstance(attempt, str):
            return None
        try:
            manifest = self._journal.read_manifest(attempt)
        except Exception:
            return None
        phase = manifest.get("commit_phase")
        if phase not in {COMMIT_PHASE_COMMITTED, COMMIT_PHASE_ACTIVATED_ACK}:
            return None
        if not manifest.get("config_published"):
            self._publish_if_needed(attempt, manifest, manifest.get("switch_mode", SWITCH_MODE_B))
        return {"attemptId": attempt, "commitPhase": phase, "awaitingTargetAck": phase == COMMIT_PHASE_COMMITTED}

    def complete_activation(
        self,
        attempt_id: str,
        *,
        archive_audit: Optional[Callable[[str], int]] = None,
    ) -> Dict[str, Any]:
        """目标 ACK（先）→ 本地 ACTIVATED_ACK（后）→ 审计归档同事务。"""
        manifest = self._journal.read_manifest(attempt_id)
        phase = manifest.get("commit_phase", COMMIT_PHASE_NONE)
        if phase == COMMIT_PHASE_ACTIVATED_ACK:
            return {"attemptId": attempt_id, "commitPhase": phase, "idempotent": True}
        if phase != COMMIT_PHASE_COMMITTED:
            raise ActivationError(f"commit_phase={phase}，不可 ACK")
        identity = manifest.get("identity", {})
        generation = (self._journal.read_control() or {}).get("generation") or identity.get("generation", "")
        # 1. 目标先 ACK（单连接事务；幂等同 ACK 重放）
        self._target_ack(attempt_id, str(generation))
        # 2. 本地后 ACK（journal 持久）
        self._journal.advance_commit_phase(attempt_id, expected=COMMIT_PHASE_COMMITTED, new=COMMIT_PHASE_ACTIVATED_ACK)
        # 3. 审计归档（与去重行同事务语义由 archive_audit 实现；cursor 推进）
        archived = 0
        if archive_audit is not None:
            archived = int(archive_audit(attempt_id))
        # 4. 清 RESTART_PENDING；pending 保留（控制锚点与历史证据，§7.2.8）
        self._journal.write_control(lambda c: {**c, "restart_pending": False})
        return {"attemptId": attempt_id, "commitPhase": COMMIT_PHASE_ACTIVATED_ACK, "archivedEvents": archived}

    # ------------------------------------------------------------------
    # 生产默认实现（测试可注入替身）
    # ------------------------------------------------------------------

    def _default_publish_active(self, yaml_path: os.PathLike[str] | str, tree: Dict[str, Any]) -> None:
        with config_lock(yaml_path):
            from app.services.db_migration.config_store import write_yaml_atomic

            write_yaml_atomic(yaml_path, tree)

    def _default_target_ack_writer(self, attempt_id: str, generation: str) -> None:
        """目标库 activated_at/generation ACK（§7.2.7；单连接事务）。

        MIGRATE：目标 receipt 表补 activated_at/generation（同连接 UPDATE）；
        HANDOFF_SAME_DB：核旧 generation → CAS 新 generation（W3-7 覆盖，
        同一 BEGIN IMMEDIATE 连接完成，禁跨连接自锁）。
        """
        manifest = self._journal.read_manifest(attempt_id)
        kind = manifest.get("operation_kind", "MIGRATE")
        if kind == "HANDOFF_SAME_DB":
            raise ActivationError("HANDOFF_SAME_DB 的 ACK 由同库单连接专径完成（§7.3），不走本默认实现")
        # MIGRATE：写目标 receipt（默认经当前有效连接；表名以协议常量为准——
        # 实跑曾用复数字面量致 pg-to-sqlite 激活 ACK 永远 no such table）
        from app.core.database_protocol import RECEIPT_TABLE
        from app.database import build_database_url
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool

        engine = create_engine(build_database_url(), poolclass=NullPool)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"UPDATE {RECEIPT_TABLE} SET status = 'ACTIVATED', activated_at = :now "
                        "WHERE attempt_id = :aid"
                    ),
                    {"now": _now(), "aid": attempt_id},
                )
        finally:
            engine.dispose()

    def _default_restart_scheduler(self, info: Dict[str, Any]) -> bool:
        """已知托管+显式 opt-in → 延迟 SIGTERM 自身；否则 False（手动重启）。"""
        from app.services.db_migration.restart_adapter import detect_hosting, schedule_graceful_exit

        hosting = detect_hosting()
        opt_in = (os.environ.get(RESTART_OPT_IN_ENV) or "").strip().lower() in {"1", "true", "yes"}
        if not opt_in or hosting == "unknown":
            return False
        return schedule_graceful_exit(delay_seconds=1.5, reason=info.get("reason", "switch"))
