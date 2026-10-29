"""受管持久化仓储（database-migration-ui W3-1，PLANS §4.2/§7；单一写权威）。

评审修正（2026-10-28 对话 01a18094）落实：
- **不可两套独立权威**：control/manifest/commit_phase 的持久事实以本模块为唯一
  写者（部署互斥锁+代次 CAS+原子写+fsync）；controller 内存态只是运行视图；
  maintenance-intent.json 是 journal 的**兼容投影**（同路径同格式），重启判定
  以 journal 权威为准——COMMITTED 决定绝不被残留 intent 或 exit_maintenance
  放回 NORMAL。
- **审计回放归档**：按 event_id 去重、与 ACK 同事务写入最终库；spool 归档采用
  cursor + 快照令牌（回放期间新追加不丢尾部，clear 仅在文件未变化时允许）。

写入纪律（§4.2）：部署互斥锁 → 同目录临时文件 0600 → flush/fsync → 原子
replace → 父目录 fsync。受管证据存在而文件缺失/损坏/代次不符 → fail-closed
（抛 JournalCorrupted），禁止重建默认配置。
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from app.core.database_bootstrap import (
    db_migration_dir,
    is_valid_attempt_id,
    pending_attempt_from_control,
    read_control,
    read_manifest,
)
from app.core.database_protocol import (
    ATTEMPTS_DIRNAME,
    CONTROL_FILE,
    MANIFEST_FILENAME,
)

__all__ = [
    "COMMIT_PHASE_NONE",
    "COMMIT_PHASE_PREPARED",
    "COMMIT_PHASE_COMMITTED",
    "COMMIT_PHASE_ACTIVATED_ACK",
    "JournalError",
    "JournalConflict",
    "JournalCorrupted",
    "CommitPhaseError",
    "Journal",
    "deployment_lock",
    "atomic_write_bytes",
    "atomic_write_json",
    "fsync_dir",
    "make_manifest_payload",
]

# ---------------------------------------------------------------------------
# commit_phase（§7.1）：NONE → PREPARED → COMMITTED → ACTIVATED_ACK 单向
# ---------------------------------------------------------------------------

COMMIT_PHASE_NONE = "NONE"
COMMIT_PHASE_PREPARED = "PREPARED"
COMMIT_PHASE_COMMITTED = "COMMITTED"
COMMIT_PHASE_ACTIVATED_ACK = "ACTIVATED_ACK"

_COMMIT_PHASE_ORDER: Dict[str, int] = {
    COMMIT_PHASE_NONE: 0,
    COMMIT_PHASE_PREPARED: 1,
    COMMIT_PHASE_COMMITTED: 2,
    COMMIT_PHASE_ACTIVATED_ACK: 3,
}

MANIFEST_SCHEMA_VERSION = 1
OPERATION_KIND_MIGRATE = "MIGRATE"
OPERATION_KIND_HANDOFF_SAME_DB = "HANDOFF_SAME_DB"

INTENT_FILENAME = "maintenance-intent.json"
ARCHIVE_CURSOR_FILENAME = "maintenance-audit-archive-cursor.json"


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class JournalError(RuntimeError):
    """journal 基类。"""


class JournalConflict(JournalError):
    """代次/state_version CAS 冲突（并发写者或过期视图）。"""


class JournalCorrupted(JournalError):
    """受管证据损坏/缺失（fail-closed，禁止默认化重建）。"""


class CommitPhaseError(JournalError):
    """commit_phase 非法推进（回退/跳级）。"""


# ---------------------------------------------------------------------------
# 原子持久写（§4.2 写入纪律）
# ---------------------------------------------------------------------------


def fsync_dir(path: os.PathLike[str] | str) -> None:
    """fsync 父目录（replace 持久化；不支持目录 fsync 的平台静默跳过）。"""
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - 平台差异（某些 FS 不支持目录 fsync）
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: os.PathLike[str] | str, data: bytes) -> None:
    """0600 临时文件 → flush+fsync → 原子 replace → 父目录 fsync。

    受管子树目录权限（0700）由调用方（Journal/锁）在创建时设定。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        fsync_dir(target.parent)
    finally:
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()


def atomic_write_json(path: os.PathLike[str] | str, payload: Dict[str, Any]) -> None:
    atomic_write_bytes(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


# ---------------------------------------------------------------------------
# 部署互斥锁（进程内重入；跨进程互斥）
# ---------------------------------------------------------------------------

_journal_locks: Dict[str, "_DeploymentLock"] = {}
_journal_locks_guard = threading.Lock()

_LOCK_FILENAME = ".journal.lock"


class _DeploymentLock:
    """进程内 threading.RLock 重入 + 跨进程 fcntl.flock 独占。

    首次获取时持有文件锁直至进程退出（部署级单写者假设；不主动释放文件锁
    避免多线程重入窗口内被其他进程插入）。
    """

    def __init__(self, lock_path: Path) -> None:
        self._rlock = threading.RLock()
        self._lock_path = lock_path
        self._fd: Optional[int] = None
        self._fd_guard = threading.Lock()

    def _ensure_file_lock(self) -> None:
        with self._fd_guard:
            if self._fd is not None:
                return
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self._lock_path.parent, 0o700)  # 受管子树 0700（§4.2）
            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                raise JournalConflict("部署 journal 锁被其他进程持有（db-migration 单写者被违反）") from None
            self._fd = fd

    @contextlib.contextmanager
    def acquire(self) -> Iterator[None]:
        with self._rlock:
            self._ensure_file_lock()
            yield


@contextlib.contextmanager
def deployment_lock(config_dir: os.PathLike[str] | str) -> Iterator[None]:
    """获取部署级 journal 锁（进程内重入；跨进程冲突 → JournalConflict）。"""
    key = str(Path(config_dir).resolve())
    with _journal_locks_guard:
        lock = _journal_locks.get(key)
        if lock is None:
            lock = _DeploymentLock(db_migration_dir(config_dir) / _LOCK_FILENAME)
            _journal_locks[key] = lock
    with lock.acquire():
        yield


# ---------------------------------------------------------------------------
# manifest payload 构造（§4.2 字段全集；不含密码）
# ---------------------------------------------------------------------------


def make_manifest_payload(
    *,
    attempt_id: str,
    direction: str,
    operation_kind: str,
    epoch: str,
    source: Dict[str, Any],
    target: Dict[str, Any],
    tool_version: str,
    digest_version: str,
    objects: Optional[List[str]] = None,
    staging_path: Optional[str] = None,
    final_path: Optional[str] = None,
    source_snapshot: Optional[Dict[str, Any]] = None,
    candidate_config_digest: Optional[str] = None,
    prior_config_digest: Optional[str] = None,
    progress: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造 manifest 初始 payload（commit_phase=NONE、state_version=1）。

    source/target 为**不含密码**的连接描述（dialect/database_id/路径或 host 等）。
    """
    if not is_valid_attempt_id(attempt_id):
        raise JournalError(f"attempt_id 形态非法: {attempt_id!r}")
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "direction": direction,
        "operation_kind": operation_kind,
        "epoch": epoch,
        "state_version": 1,
        "commit_phase": COMMIT_PHASE_NONE,
        "tool_version": tool_version,
        "digest_version": digest_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": dict(source),
        "target": dict(target),
        "objects": list(objects or []),
        "staging_path": staging_path,
        "final_path": final_path,
        "source_snapshot": dict(source_snapshot or {}),
        "candidate_config_digest": candidate_config_digest,
        "prior_config_digest": prior_config_digest,
        "progress": dict(progress or {}),
    }


# ---------------------------------------------------------------------------
# intent 权威评估（评审修正：journal 是事实，intent 是投影）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntentAuthority:
    """journal 权威 vs intent 投影的一致性判定。"""

    pending_attempt: Optional[str]
    commit_phase: Optional[str]
    intent_state: Optional[str]
    verdict: str  # consistent | stale_intent | no_intent
    committed_pending_restart: bool

    @property
    def may_return_normal(self) -> bool:
        """是否允许回 NORMAL（COMMITTED/ACTIVATED_ACK 决定绝不放回普通启动）。"""
        return not self.committed_pending_restart


def _read_intent_tolerant(intent_path: Path) -> Optional[Dict[str, Any]]:
    if not intent_path.exists():
        return None
    try:
        data = json.loads(intent_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "<corrupt>", "corrupt": True}
    return data if isinstance(data, dict) else {"state": "<corrupt>", "corrupt": True}


class Journal:
    """db-migration/ 受管文件的唯一写者（control/manifest/commit_phase/intent 投影）。"""

    def __init__(self, config_dir: os.PathLike[str] | str) -> None:
        self._config_dir = Path(config_dir)
        self._base = db_migration_dir(self._config_dir)

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------

    @property
    def control_path(self) -> Path:
        return self._base / CONTROL_FILE

    @property
    def intent_path(self) -> Path:
        return self._base / INTENT_FILENAME

    def manifest_path(self, attempt_id: str) -> Path:
        if not is_valid_attempt_id(attempt_id):
            raise JournalError(f"attempt_id 形态非法（拒绝路径映射）: {attempt_id!r}")
        tail = attempt_id.rsplit("/", 1)[1]
        return self._base / ATTEMPTS_DIRNAME / tail / MANIFEST_FILENAME

    # ------------------------------------------------------------------
    # control（代次 CAS RMW）
    # ------------------------------------------------------------------

    def read_control(self) -> Optional[Dict[str, Any]]:
        try:
            return read_control(self._config_dir)
        except Exception as exc:  # bootstrap 抛 ManagedStateError 等
            raise JournalCorrupted(f"control.json 读取失败: {exc}") from exc

    def write_control(
        self,
        mutator: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
        *,
        expect_generation: Optional[str] = None,
        deployment_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """锁内 RMW control.json；expect_generation CAS 冲突 → JournalConflict。

        control 缺失时以 deployment_id 初始化（deployment_id 必须提供）；
        已存在而损坏 → fail-closed（不重建）。
        """
        with deployment_lock(self._config_dir):
            current = self.read_control()
            if current is None:
                if deployment_id is None:
                    raise JournalError("control.json 不存在且未提供 deployment_id（拒绝凭空初始化）")
                current = {"deployment_id": deployment_id, "generation": str(uuid.uuid4())}
            if expect_generation is not None and current.get("generation") != expect_generation:
                raise JournalConflict(
                    f"control 代次 CAS 冲突: expect={expect_generation!r} " f"actual={current.get('generation')!r}"
                )
            mutated = mutator(dict(current))
            if mutated is None:
                mutated = current
            if not isinstance(mutated, dict):
                raise JournalError("control mutator 必须返回 dict 或 None")
            atomic_write_json(self.control_path, mutated)
            return mutated

    # ------------------------------------------------------------------
    # manifest（state_version CAS）
    # ------------------------------------------------------------------

    def read_manifest(self, attempt_id: str) -> Dict[str, Any]:
        try:
            return read_manifest(self._config_dir, attempt_id)
        except FileNotFoundError as exc:
            raise JournalCorrupted(f"manifest 不存在: {attempt_id}") from exc
        except Exception as exc:
            raise JournalCorrupted(f"manifest 读取失败: {exc}") from exc

    def write_manifest(
        self,
        attempt_id: str,
        payload: Dict[str, Any],
        *,
        expect_state_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """写入 manifest（state_version 乐观并发；attempt_id 一致性校验）。"""
        if payload.get("attempt_id") != attempt_id:
            raise JournalError(f"manifest.attempt_id 与目标不一致: {payload.get('attempt_id')!r}")
        path = self.manifest_path(attempt_id)
        with deployment_lock(self._config_dir):
            path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(path.parent, 0o700)  # attempts/<uuid>/ 0700
            if path.exists():
                existing = self.read_manifest(attempt_id)
                if expect_state_version is not None:
                    if existing.get("state_version") != expect_state_version:
                        raise JournalConflict(
                            f"manifest state_version CAS 冲突: expect={expect_state_version} "
                            f"actual={existing.get('state_version')}"
                        )
                new_version = int(existing.get("state_version", 0)) + 1
            else:
                if expect_state_version is not None:
                    raise JournalConflict(f"manifest 不存在但要求 CAS state_version={expect_state_version}")
                new_version = int(payload.get("state_version", 1))
            merged = dict(payload)
            merged["state_version"] = new_version
            merged.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
            atomic_write_json(path, merged)
            return merged

    # ------------------------------------------------------------------
    # commit_phase 单向推进（§7.1）
    # ------------------------------------------------------------------

    def advance_commit_phase(self, attempt_id: str, *, expected: str, new: str) -> Dict[str, Any]:
        """COMMITTED 等持久决定推进；同值幂等 OK，回退/跳级 → CommitPhaseError。"""
        if expected not in _COMMIT_PHASE_ORDER or new not in _COMMIT_PHASE_ORDER:
            raise CommitPhaseError(f"未知 commit_phase: {expected!r}→{new!r}")
        if _COMMIT_PHASE_ORDER[new] < _COMMIT_PHASE_ORDER[expected]:
            raise CommitPhaseError(f"commit_phase 禁止回退: {expected}→{new}")
        if _COMMIT_PHASE_ORDER[new] > _COMMIT_PHASE_ORDER[expected] + 1:
            raise CommitPhaseError(f"commit_phase 禁止跳级: {expected}→{new}")
        with deployment_lock(self._config_dir):
            manifest = self.read_manifest(attempt_id)
            current = manifest.get("commit_phase", COMMIT_PHASE_NONE)
            if current == new:
                if current != expected:
                    raise CommitPhaseError(f"commit_phase 已为 {current}（期望 {expected}）")
                return manifest  # 幂等重放
            if current != expected:
                raise CommitPhaseError(f"commit_phase 实际为 {current}（期望 {expected}）")
            merged = dict(manifest)
            merged["commit_phase"] = new
            merged["updated_at"] = datetime.now(timezone.utc).isoformat()
            merged["state_version"] = int(manifest.get("state_version", 0)) + 1
            path = self.manifest_path(attempt_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(path.parent, 0o700)
            atomic_write_json(path, merged)
            return merged

    # ------------------------------------------------------------------
    # intent 兼容投影（同路径同格式；权威在 journal）
    # ------------------------------------------------------------------

    def write_intent_projection(self, payload: Dict[str, Any]) -> None:
        """controller 运行视图投影（崩溃现场时序证据；非权威）。"""
        with deployment_lock(self._config_dir):
            atomic_write_json(self.intent_path, payload)

    def clear_intent_projection(self) -> None:
        with deployment_lock(self._config_dir):
            with contextlib.suppress(OSError):
                self.intent_path.unlink()

    def evaluate_intent_authority(self) -> IntentAuthority:
        """重启判定入口：journal 权威（control+manifest）vs intent 投影一致性。

        - committed_pending_restart：pending attempt 的 commit_phase ∈
          {COMMITTED, ACTIVATED_ACK} → 绝不放回 NORMAL（幂等 redo 提交决定）。
        - stale_intent：intent 与权威不符（如 journal 已 COMMITTED 而 intent 仍
          PREPARING）→ intent 只作线索，不覆盖事实。
        """
        control = self.read_control()
        pending = pending_attempt_from_control(control)  # 形态非法 → fail-closed
        commit_phase: Optional[str] = None
        if pending is not None and isinstance(pending, str):
            try:
                manifest = self.read_manifest(pending)
                commit_phase = manifest.get("commit_phase", COMMIT_PHASE_NONE)
            except JournalCorrupted:
                commit_phase = "<corrupt>"
        committed_pending_restart = commit_phase in {COMMIT_PHASE_COMMITTED, COMMIT_PHASE_ACTIVATED_ACK}
        intent = _read_intent_tolerant(self.intent_path)
        if intent is None:
            verdict = "no_intent"
        else:
            intent_attempt = intent.get("attempt_id")
            if committed_pending_restart and (
                intent_attempt != pending
                or intent.get("state")
                in {"PREPARING", "DRAINING", "FROZEN", "IMPORTING", "VERIFYING", "READY_TO_SWITCH"}
            ):
                verdict = "stale_intent"
            else:
                verdict = "consistent"
        return IntentAuthority(
            pending_attempt=pending if isinstance(pending, str) else None,
            commit_phase=commit_phase,
            intent_state=intent.get("state") if intent else None,
            verdict=verdict,
            committed_pending_restart=committed_pending_restart,
        )

    # ------------------------------------------------------------------
    # 审计归档（cursor + 快照令牌；不清 spool 丢尾部——评审修正）
    # ------------------------------------------------------------------

    @property
    def archive_cursor_path(self) -> Path:
        return self._base / ARCHIVE_CURSOR_FILENAME

    def read_archive_cursor(self) -> Optional[str]:
        path = self.archive_cursor_path
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        value = data.get("last_event_id") if isinstance(data, dict) else None
        return value if isinstance(value, str) else None

    def advance_archive_cursor(self, last_event_id: str) -> None:
        with deployment_lock(self._config_dir):
            atomic_write_json(
                self.archive_cursor_path,
                {"last_event_id": last_event_id, "updated_at": datetime.now(timezone.utc).isoformat()},
            )

    # ------------------------------------------------------------------
    # 诊断（只读；维护面/测试用）
    # ------------------------------------------------------------------

    def diagnose(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {"config_dir": str(self._config_dir)}
        try:
            control = self.read_control()
            report["control"] = (
                {
                    "ok": True,
                    "deployment_id": control.get("deployment_id"),
                    "generation": control.get("generation"),
                    "pending_attempt": control.get("pending_attempt"),
                    "restart_pending": bool(control.get("restart_pending", False)),
                }
                if control
                else {"ok": False, "missing": True}
            )
        except JournalCorrupted as exc:
            report["control"] = {"ok": False, "corrupt": str(exc)}
        authority = None
        try:
            authority = self.evaluate_intent_authority()
            report["intent_authority"] = {
                "verdict": authority.verdict,
                "pending_attempt": authority.pending_attempt,
                "commit_phase": authority.commit_phase,
                "intent_state": authority.intent_state,
                "committed_pending_restart": authority.committed_pending_restart,
            }
        except JournalCorrupted as exc:
            report["intent_authority"] = {"corrupt": str(exc)}
        report["archive_cursor"] = self.read_archive_cursor()
        return report
