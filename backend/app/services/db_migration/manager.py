"""迁移管理器（database-migration-ui W3-3，PLANS §5.1/§6.3/§6.4；T07/T17）。

单飞行编排：MaintenanceController（准入排空/取消 epoch/worker_generation）+
source_fence（可证明停写）+ W1 六阶段管线（worker 线程）+ journal（manifest/
control 持久权威）+ config_store（候选配置）+ local_audit（事件）。

评审修正落实：
- **动作 API 暴露前完整管理 worker/fence 生命周期**：leave 前必须 worker ACK/
  事务收尾/持久撤销资格（switch_eligible 撤销+epoch 推进）再放闸；
- **REBIND 三段式**：controller.enter_rebind 的 drift 检查返回后**再次 CAS**
  attempt+epoch+stateVersion，再持久 REBIND_PREPARED → 目标事务 CAS
  eligible_epoch → 持久 REBIND_ACK；不以 controller 内存 epoch 替代持久协议；
- **晚回调核 worker_generation**：worker 每次派生自增代次，回调（cancel/
  progress/checkpoint 落盘）携带代次，过期即拒（StaleEpochError）。
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.core.database_bootstrap import db_migration_dir, is_valid_attempt_id
from app.core.database_protocol import ATTEMPTS_DIRNAME
from app.services.db_migration.journal import (
    COMMIT_PHASE_NONE,
    Journal,
    JournalConflict,
    OPERATION_KIND_MIGRATE,
    make_manifest_payload,
)
from app.services.db_migration.local_audit import MaintenanceLocalAudit
from app.services.db_migration.maintenance import (
    AdmissionRejected,
    ControllerCancellation,
    MaintenanceController,
    StaleEpochError,
    TransitionError,
)
from app.services.db_migration.pipeline import (
    DIGEST_VERSION_CANONICAL_V1,
    TOOL_VERSION,
    PipelineContext,
    make_attempt_id,
)

__all__ = [
    "ManagerError",
    "StateConflict",
    "NeedsCredentials",
    "WorkerNotStopped",
    "MigrationManager",
    "ManagerStatus",
]

CREDENTIALS_FILENAME = "target-credentials.json"
_REBIND_RECORDS_KEY = "rebind_records"


class ManagerError(RuntimeError):
    """管理器基类。"""


class StateConflict(ManagerError):
    """单飞行/CAS/状态冲突（IN_PROGRESS/STATE_CONFLICT 语义）。"""


class NeedsCredentials(ManagerError):
    """重启恢复缺目标凭据（§6.3：不猜目标、不宣称零凭据自动恢复）。"""


class WorkerNotStopped(ManagerError):
    """worker 未安全收尾（§6.4：禁止 leave/discard/switch/new start）。"""


@dataclass(frozen=True)
class ManagerStatus:
    """状态接口快照（/migration/status 数据源；脱敏）。"""

    attempt_id: Optional[str]
    phase: str  # idle|preparing|draining|frozen|importing|verifying|ready_to_switch|cancelling|cancelled|failed|held|committed
    epoch: str
    state_version: int
    commit_phase: Optional[str]
    worker_generation: int
    needs_credentials: bool
    restart_pending: bool
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "attemptId": self.attempt_id,
            "phase": self.phase,
            "epoch": self.epoch,
            "stateVersion": self.state_version,
            "commitPhase": self.commit_phase,
            "workerGeneration": self.worker_generation,
            "needsCredentials": self.needs_credentials,
            "restartPending": self.restart_pending,
            **({"detail": self.detail} if self.detail else {}),
        }


PipelineRunner = Callable[[PipelineContext, Dict[str, Any]], Dict[str, Any]]
"""管线执行器：ctx + manifest 视图 → 结果（receipt 摘要等）。

默认实现按 direction 分派 W1 run_sqlite_to_pg/run_pg_to_sqlite；测试注入替身。
"""


class MigrationManager:
    """单飞行迁移管理器（进程级挂 app.state.database_migration_manager）。"""

    def __init__(
        self,
        config_dir: os.PathLike[str] | str,
        *,
        controller: Optional[MaintenanceController] = None,
        audit: Optional[MaintenanceLocalAudit] = None,
        pipeline_runner: Optional[PipelineRunner] = None,
        deployment_id: str = "default",
    ) -> None:
        self._config_dir = str(config_dir)
        self._journal = Journal(config_dir)
        self._controller = controller or MaintenanceController(config_dir)
        self._audit = audit or MaintenanceLocalAudit(config_dir)
        self._pipeline_runner = pipeline_runner or self._default_pipeline_runner
        self._deployment_id = deployment_id
        self._lock = threading.RLock()
        self._worker: Optional[threading.Thread] = None
        self._worker_error: Optional[str] = None
        self._worker_result: Optional[Dict[str, Any]] = None
        self._phase = "idle"
        self._last_progress: Dict[str, Any] = {}
        self._target_desc: Dict[str, Any] = {}
        self._ctx: Optional[PipelineContext] = None

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------

    @property
    def controller(self) -> MaintenanceController:
        return self._controller

    def _manifest_view(self) -> Dict[str, Any]:
        control = self._journal.read_control() or {}
        attempt = control.get("pending_attempt")
        if isinstance(attempt, str) and is_valid_attempt_id(attempt):
            try:
                return self._journal.read_manifest(attempt)
            except Exception:
                return {}
        return {}

    def status(self) -> ManagerStatus:
        manifest = self._manifest_view()
        with self._lock:
            phase = self._phase
            if self._controller.cancel_requested and phase not in {"cancelled", "failed"}:
                phase = "cancelling"
            return ManagerStatus(
                attempt_id=manifest.get("attempt_id"),
                phase=phase,
                epoch=manifest.get("epoch", self._controller.epoch),
                state_version=int(manifest.get("state_version", 0)),
                commit_phase=manifest.get("commit_phase"),
                worker_generation=self._controller.worker_generation,
                needs_credentials=self._credentials_lost(manifest),
                restart_pending=bool((self._journal.read_control() or {}).get("restart_pending", False)),
                detail={"progress": self._last_progress, "target": self._target_desc or manifest.get("target", {})},
            )

    def _credentials_lost(self, manifest: Dict[str, Any]) -> bool:
        attempt = manifest.get("attempt_id")
        if not isinstance(attempt, str):
            return False
        return not self._credentials_path(attempt).exists()

    def _credentials_path(self, attempt_id: str) -> Path:
        base = db_migration_dir(self._config_dir) / ATTEMPTS_DIRNAME / attempt_id.rsplit("/", 1)[1]
        return base / CREDENTIALS_FILENAME

    # ------------------------------------------------------------------
    # start（§5.1/§6.1：关准入并排空后才快照）
    # ------------------------------------------------------------------

    def start_migration(
        self,
        direction: str,
        target: Dict[str, Any],
        *,
        password: str,
        initiated_by: str = "administrator",
        source_desc: Optional[Dict[str, Any]] = None,
    ) -> ManagerStatus:
        if direction not in {"sqlite-to-pg", "pg-to-sqlite"}:
            raise ManagerError(f"未知方向: {direction!r}")
        with self._lock:
            if self._phase not in {"idle", "cancelled", "failed"}:
                raise StateConflict(f"单飞行约束：attempt 进行中（phase={self._phase}）")
            attempt_id = make_attempt_id(direction)
            # 1. PREPARING：先持久 intent 再关门查重任务（controller §5.1）
            try:
                self._controller.begin_prepare(attempt_id=attempt_id)
            except (TransitionError, AdmissionRejected) as exc:
                raise StateConflict(str(exc)) from exc
            except Exception as exc:
                if "不可等待" in str(exc) or "409" in str(exc):
                    raise StateConflict(f"不可等待重任务在途: {exc}") from exc
                raise
            self._phase = "preparing"
            # 2. 排空（超时→HELD，manager 停在 held；人工 leave/恢复）
            if not self._controller.run_drain(timeout=30.0):
                self._phase = "held"
                raise StateConflict("排空超时→HELD（等待人工处置；不可自动恢复业务）")
            self._phase = "draining"
            # 3. 冻结（fence 令牌进 controller；指纹进 manifest）
            fence = self._acquire_source_fence(direction, source_desc)
            self._controller.enter_frozen(getattr(fence, "token", None))
            self._phase = "frozen"
            fingerprint = getattr(getattr(fence, "token", None), "fingerprint", "")
            # 4. journal：manifest+control 持久（先持久锚点才允许目标副作用）
            self._ctx = PipelineContext(attempt_id=attempt_id, operation_kind=OPERATION_KIND_MIGRATE)
            manifest = make_manifest_payload(
                attempt_id=attempt_id,
                direction=direction,
                operation_kind=OPERATION_KIND_MIGRATE,
                epoch=self._ctx.eligible_epoch,
                source=source_desc or {"dialect": "sqlite" if direction == "sqlite-to-pg" else "postgresql"},
                target={k: v for k, v in target.items() if k != "password"},
                tool_version=TOOL_VERSION,
                digest_version=DIGEST_VERSION_CANONICAL_V1,
                source_snapshot={"fingerprint": fingerprint, "taken_at": time.time()},
            )
            manifest["ownership_nonce"] = self._ctx.ownership_nonce
            manifest["origin_epoch"] = self._ctx.origin_epoch
            manifest["worker_generation"] = self._controller.next_worker_generation()
            self._journal.write_control(
                lambda c: {**c, "pending_attempt": attempt_id, "restart_pending": False},
                deployment_id=self._deployment_id,
            )
            self._journal.write_manifest(attempt_id, manifest)
            self._store_credentials(attempt_id, target, password)
            self._target_desc = {k: v for k, v in target.items() if k != "password"}
            self._audit.audit_event(
                "migration",
                action="start",
                outcome="ok",
                detail={"direction": direction, "attemptId": attempt_id},
                attempt_id=attempt_id,
            )
            # 5. worker 线程（register_child 继承准入；cancel_check 核 epoch+代次）
            self._spawn_worker(manifest)
            return self.status()

    def _acquire_source_fence(self, direction: str, source_desc: Optional[Dict[str, Any]]):
        """按方向取源 fence（测试可注入 fence_factory；缺省真实实现）。"""
        factory = getattr(self, "fence_factory", None)
        if factory is not None:
            return factory(direction, source_desc)
        from app.models.database_migration import business_tables
        from app.models.model_registry import register_all_models

        register_all_models()
        tables = [t.name for t in business_tables()]
        if direction == "sqlite-to-pg":
            from app.services.db_migration.source_fence import SqliteSourceFence

            source_path = (source_desc or {}).get("path") or os.environ.get("DATABASE_PATH", "app.db")
            if not source_path:
                raise ManagerError("sqlite-to-pg 需要 source_desc['path']")
            return SqliteSourceFence(str(source_path), tables)
        from app.services.db_migration.target_params import PostgresParams, build_pg_url

        from app.services.db_migration.source_fence import PgSourceFence

        pg = (source_desc or {}).get("pg") if source_desc else None
        params = pg if isinstance(pg, PostgresParams) else None
        if params is None:
            raise ManagerError("pg-to-sqlite 需要 source_desc['pg']=PostgresParams")
        return PgSourceFence(build_pg_url(params), tables)

    def _spawn_worker(self, manifest: Dict[str, Any]) -> None:
        ctx = self._ctx
        assert ctx is not None
        attempt_id = manifest["attempt_id"]
        generation = manifest["worker_generation"]
        controller = self._controller

        runtime_epoch = controller.epoch  # 运行准入 epoch（≠管线 eligible_epoch）

        def cancel_check() -> None:
            # 晚回调防线：运行 epoch+worker_generation 双核（T07/T17）；
            # 管线资格 epoch（manifest.epoch）不参与取消判定（rebind 才动它）。
            if generation != controller.worker_generation:
                raise StaleEpochError(f"过期 worker 回调（generation={generation}）")
            controller.cancel_check(epoch=runtime_epoch)

        ctx.cancel_check = cancel_check
        ctx.progress = self._make_progress_recorder(attempt_id, generation)
        # worker 是维护控制面执行者（非业务准入）：业务准入已在 PREPARING 关闭；
        # 生命周期由 manager 线程句柄承载（wait_worker_stopped join 即
        # WORKER_NOT_STOPPED 判定），取消 ACK 由 controller 事件承载。

        def run() -> None:
            try:
                self._phase = "importing"
                result = self._pipeline_runner(ctx, manifest)
                self._worker_result = result
                self._phase = "verifying"
                controller.set_pipeline_state("verified")
                self._phase = "ready_to_switch"
                self._audit.audit_event(
                    "migration",
                    action="verify-done",
                    outcome="ok",
                    detail={"attemptId": attempt_id},
                    attempt_id=attempt_id,
                )
            except BaseException as exc:  # noqa: BLE001 - worker 兜底记录
                self._worker_error = str(exc)
                if isinstance(exc, (ControllerCancellation, StaleEpochError)) and isinstance(
                    exc, ControllerCancellation
                ):
                    self._phase = "cancelled"
                    controller.ack_cancel(epoch=runtime_epoch)
                else:
                    self._phase = "failed"
                    with contextlib.suppress(TransitionError):
                        controller.set_pipeline_state("failed")
                self._audit.audit_event(
                    "migration",
                    action="worker-exit",
                    outcome="failed",
                    detail={"attemptId": attempt_id, "error": str(exc)[:200]},
                    attempt_id=attempt_id,
                )

        self._worker = threading.Thread(target=run, name=f"migration-{attempt_id}", daemon=True)
        self._worker.start()

    def _make_progress_recorder(self, attempt_id: str, generation: int) -> Callable[[str, int, int], None]:
        last: Dict[str, Any] = {"ts": 0.0}

        def record(phase: str, done: int, total: int) -> None:
            with self._lock:
                if generation != self._controller.worker_generation:
                    raise StaleEpochError(f"过期 progress 回调（generation={generation}）")
                now = time.time()
                if now - last["ts"] < 1.0:  # 节流：manifest 落盘 ≤1Hz
                    self._last_progress = {"phase": phase, "done": done, "total": total}
                    return
                last["ts"] = now
                self._last_progress = {"phase": phase, "done": done, "total": total}
                try:
                    manifest = self._journal.read_manifest(attempt_id)
                    manifest.setdefault("progress", {})
                    manifest["progress"] = {"phase": phase, "done": done, "total": total}
                    self._journal.write_manifest(attempt_id, manifest, expect_state_version=manifest["state_version"])
                except (JournalConflict, Exception):  # 节流失败不阻断管线
                    pass

        return record

    # ------------------------------------------------------------------
    # 凭据（§6.3 NEEDS_CREDENTIALS）
    # ------------------------------------------------------------------

    def _store_credentials(self, attempt_id: str, target: Dict[str, Any], password: str) -> None:
        from app.services.db_migration.journal import atomic_write_json

        path = self._credentials_path(attempt_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        atomic_write_json(path, {"attempt_id": attempt_id, "target": target, "password": password})

    def provide_credentials(self, attempt_id: str, *, password: str, target: Dict[str, Any]) -> None:
        """恢复路径重输凭据（校验 attempt 一致后限权落盘）。"""
        manifest = self._journal.read_manifest(attempt_id)
        if manifest.get("attempt_id") != attempt_id:
            raise StateConflict("attempt 不一致")
        self._store_credentials(attempt_id, target, password)

    # ------------------------------------------------------------------
    # cancel / leave（§6.4：先 ACK 后状态；leave 先撤销资格+推进 epoch）
    # ------------------------------------------------------------------

    def request_cancel(self, *, reason: str = "") -> ManagerStatus:
        attempt = self._require_pending("cancel")
        self._controller.request_cancel(reason=reason)
        self._audit.audit_event(
            "migration",
            action="cancel-request",
            outcome="ok",
            detail={"attemptId": attempt, "reason": reason},
            attempt_id=str(attempt),
        )
        return self.status()

    def wait_worker_stopped(self, timeout: Optional[float] = 30.0) -> bool:
        """worker 安全收尾判定（线程结束 + ACK 完成；§6.4 禁止硬杀当成功）。"""
        worker = self._worker
        if worker is None:
            return True
        worker.join(timeout=timeout)
        return not worker.is_alive()

    def leave(
        self, *, expect_epoch: str, expect_state_version: int, worker_stop_timeout: float = 30.0
    ) -> ManagerStatus:
        """安全放弃回源（D1）：须 worker 已收尾且未 COMMITTED；先持久撤销资格
        并推进 epoch，再恢复普通准入。"""
        manifest = self._require_pending("leave")
        self._assert_cas(manifest, expect_epoch, expect_state_version)
        if manifest.get("commit_phase", COMMIT_PHASE_NONE) != COMMIT_PHASE_NONE:
            raise StateConflict("commit_phase 已推进，leave 拒绝（只能 redo 或 clear 交接）")
        if not self.wait_worker_stopped(timeout=worker_stop_timeout):
            raise WorkerNotStopped("worker 未收尾（等待 ACK 或受控重启；禁止硬杀当成功）")
        attempt = manifest["attempt_id"]
        # 1. 持久撤销资格 + 推进 epoch（manifest abandoned + control 清 pending）
        manifest["abandoned"] = True
        manifest["epoch"] = f"epoch-{uuid.uuid4().hex[:16]}"  # 资格作废代次
        self._journal.write_manifest(attempt, manifest, expect_state_version=manifest["state_version"])
        self._journal.write_control(lambda c: {**c, "pending_attempt": None})
        # 2. controller 侧同源推进 + 退出维护（journal 守卫：COMMITTED 拒回 NORMAL）
        try:
            state = self._controller.status().state
            if state == "FROZEN":
                self._controller.abort_from_frozen(reason="leave")
            else:
                self._controller.abort_from_held(reason="leave")
            self._controller.exit_maintenance()
        except TransitionError as exc:
            self._phase = "held"
            raise StateConflict(f"leave 受阻: {exc}") from exc
        with self._lock:
            self._phase = "idle"
            self._ctx = None
            self._worker = None
        self._audit.audit_event(
            "migration",
            action="leave",
            outcome="ok",
            detail={"attemptId": attempt},
            attempt_id=attempt,
        )
        return self.status()

    # ------------------------------------------------------------------
    # REBIND 三段式（§6.3 epoch 重绑协议；T07）
    # ------------------------------------------------------------------

    def rebind_epoch(
        self,
        *,
        expect_epoch: str,
        expect_state_version: int,
        proof_hash: str,
        target_cas: Callable[[str, str], bool],
    ) -> Dict[str, Any]:
        """重新冻结后重绑资格：REBIND_PREPARED → 目标事务 CAS → REBIND_ACK。

        - controller.enter_rebind 的 drift 检查返回后**再次 CAS**（锁外窗口防护）；
        - target_cas(old_epoch, new_epoch) 在目标事务内 CAS receipt.eligible_epoch
          与存续 marker/checkpoint 的 epoch，返回是否成功；
        - ACK 前不进入 READY；三段各自持久（manifest rebind_records）。
        """
        with self._lock:
            manifest = self._require_pending("rebind")
            self._assert_cas(manifest, expect_epoch, expect_state_version)
            if manifest.get("commit_phase", COMMIT_PHASE_NONE) in {"COMMITTED", "ACTIVATED_ACK"}:
                raise StateConflict("COMMITTED 终态禁重绑（§6.4）")
            old_epoch = manifest["epoch"]
            # controller 运行 epoch 与管线 eligible_epoch 双轨：运行面重绑用
            # controller 自身 epoch（HELD 校验+代次前进）；管线资格 CAS 用 manifest。
            try:
                self._controller.enter_rebind(expected_epoch=self._controller.epoch, drift_check=lambda: True)
            except (TransitionError, StaleEpochError) as exc:
                raise StateConflict(str(exc)) from exc
            # enter_rebind 返回后再次 CAS：窗口内 manifest 不得已被他人推进
            fresh = self._journal.read_manifest(manifest["attempt_id"])
            if fresh.get("epoch") != old_epoch or int(fresh["state_version"]) != int(manifest["state_version"]):
                raise StateConflict("rebind 窗口内状态被推进（重新核验后重试）")
            new_epoch = self._controller.epoch
            prepared = dict(fresh)
            records: List[Dict[str, Any]] = list(prepared.get(_REBIND_RECORDS_KEY, []))
            records.append(
                {
                    "stage": "REBIND_PREPARED",
                    "old": old_epoch,
                    "new": new_epoch,
                    "proof": hashlib.sha256(proof_hash.encode()).hexdigest(),
                }
            )
            prepared[_REBIND_RECORDS_KEY] = records
            prepared["epoch"] = new_epoch
            self._journal.write_manifest(manifest["attempt_id"], prepared, expect_state_version=fresh["state_version"])
            # 目标事务 CAS（失败→HELD，不半途而废）
            if not target_cas(old_epoch, new_epoch):
                self._controller.note_unknown_writer("rebind target CAS 失败")
                raise StateConflict("目标 eligible_epoch CAS 失败（epoch 漂移→HELD）")
            acked = self._journal.read_manifest(manifest["attempt_id"])
            records = list(acked.get(_REBIND_RECORDS_KEY, []))
            records.append({"stage": "REBIND_ACK", "new": new_epoch, "at": time.time()})
            acked[_REBIND_RECORDS_KEY] = records
            self._journal.write_manifest(manifest["attempt_id"], acked, expect_state_version=acked["state_version"])
            return self._journal.read_manifest(manifest["attempt_id"])

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _require_pending(self, action: str) -> Dict[str, Any]:
        manifest = self._manifest_view()
        if not manifest:
            raise StateConflict(f"无进行中 attempt（{action} 不可用）")
        return manifest

    def _assert_cas(self, manifest: Dict[str, Any], expect_epoch: str, expect_state_version: int) -> None:
        if manifest.get("epoch") != expect_epoch or int(manifest.get("state_version", 0)) != int(expect_state_version):
            raise StateConflict(
                f"CAS 失败: epoch={manifest.get('epoch')!r}/sv={manifest.get('state_version')!r} "
                f"≠ expect {expect_epoch!r}/{expect_state_version}"
            )

    def _default_pipeline_runner(self, ctx: PipelineContext, manifest: Dict[str, Any]) -> Dict[str, Any]:
        direction = manifest.get("direction")
        if direction == "sqlite-to-pg":
            from app.services.db_migration.sqlite_to_pg import run_sqlite_to_pg
            from app.services.db_migration.target_params import PostgresParams

            target = manifest.get("target", {})
            params = target.get("_pg_params") if isinstance(target, dict) else None
            if not isinstance(params, PostgresParams):
                raise ManagerError("sqlite-to-pg 需要 target['_pg_params']=PostgresParams（凭据路径）")
            from sqlalchemy import create_engine
            from app.services.db_migration.target_params import build_pg_url
            from sqlalchemy.pool import NullPool

            engine = create_engine(build_pg_url(params), poolclass=NullPool)
            try:
                return run_sqlite_to_pg(manifest.get("source", {}).get("path", ""), pg_engine=engine, ctx=ctx)
            finally:
                engine.dispose()
        if direction == "pg-to-sqlite":
            from app.services.db_migration.pg_to_sqlite import run_pg_to_sqlite

            source = manifest.get("source", {})
            params = source.get("_pg_params")
            if params is None:
                raise ManagerError("pg-to-sqlite 需要 source['_pg_params']")
            from sqlalchemy import create_engine
            from sqlalchemy.pool import NullPool

            from app.services.db_migration.target_params import build_pg_url

            engine = create_engine(build_pg_url(params), poolclass=NullPool)
            try:
                return run_pg_to_sqlite(engine, target_dir=manifest.get("final_path") or ".", ctx=ctx)
            finally:
                engine.dispose()
        raise ManagerError(f"未知方向: {direction!r}")
