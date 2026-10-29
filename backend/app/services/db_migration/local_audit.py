# -*- coding: utf-8 -*-
"""维护本地审计（database-migration-ui W2-6，PLANS §5.3/§11 T22）。

维护模式下的审计**不写源/业务库**（源零写铁律），落本地受保护文件：

- 位置：``<config_dir>/db-migration/maintenance-audit.jsonl``（0600，逐行 JSON）；
- **关键副作用前先持久化**：``audit_event`` 返回前已 append+flush+fsync，
  写失败（磁盘满/权限/容量上限）即抛 ``LocalAuditUnavailable`` ——调用方
  必须放弃该危险动作（fail-closed），而不是丢日志继续干；
- 容量上限：默认 10MiB / 20000 条（可注入），超限同样拒绝新**关键**事件
  （非关键事件在超限时聚合丢弃计数并落一条哨兵行，不静默无痕）；
- 脱敏：键名命中禁记清单（password/totp/token/secret/密钥/确认口令等）
  一律以 ``<redacted>`` 替换；绝不允许把密码/TOTP/token/清理确认记进日志；
- 回放：``replay_events`` 按 ``event_id`` 去重（崩溃重放/重复 append 安全），
  供 W3 ACK 归档时与正式审计同事务写入最终服务库；放弃路径归档回恢复的源。

事件结构对齐正式审计字段（operator/action/target/detail/ip/user_agent），
外带维护协议字段（event_id/kind/attempt_id/epoch/outcome/source）。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.core.database_protocol import DB_MIGRATION_DIR

AUDIT_FILENAME = "maintenance-audit.jsonl"

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_EVENTS = 20000

#: 禁记键名（小写子串匹配；命中即 <redacted>，防密码/TOTP/token/确认口令入库）
_FORBIDDEN_KEY_PATTERN = re.compile(
    r"(password|passwd|totp|token|secret|api[_-]?key|private[_-]?key|confirm|confirmation|credential)"
)

_REDACTED = "<redacted>"

#: 关键动作类型（W2 预置；W3 提交/激活/放弃等在其上扩展）
KIND_GATE_CHANGE = "gate_change"
KIND_AUTH = "auth"
KIND_CANCEL = "cancel"
KIND_FENCE = "fence"
KIND_CONTROL = "control"


class LocalAuditUnavailable(RuntimeError):
    """本地审计不可写（磁盘满/权限/容量上限）——危险动作必须放弃（§5.3）。"""


def redact(value: Any) -> Any:
    """递归脱敏：键名命中禁记清单 → 值替换为 <redacted>。"""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if _FORBIDDEN_KEY_PATTERN.search(str(k).lower()) else redact(v)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class MaintenanceLocalAudit:
    """线程安全本地审计写入器（lifespan 维护分支/控制面共用单例）。"""

    def __init__(
        self,
        config_dir: os.PathLike[str] | str,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> None:
        self._path = Path(config_dir) / DB_MIGRATION_DIR / AUDIT_FILENAME
        self._max_bytes = max_bytes
        self._max_events = max_events
        self._lock = threading.Lock()
        self._dropped_count = 0

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def audit_event(
        self,
        kind: str,
        *,
        operator: str = "",
        action: str = "",
        target: str = "",
        detail: Optional[Dict[str, Any]] = None,
        ip: str = "",
        user_agent: str = "",
        attempt_id: Optional[str] = None,
        epoch: Optional[str] = None,
        outcome: str = "ok",
        critical: bool = True,
    ) -> Dict[str, Any]:
        """持久化一条审计事件（返回已持久化的行；critical 事件写失败即抛）。

        - ``critical=True``（默认）：控制动作/认证/取消/fence 等关键副作用前
          调用；磁盘满/超容量 → ``LocalAuditUnavailable``，调用方放弃动作；
        - ``critical=False``：观测类事件；超容量时聚合丢弃并记哨兵，
          写失败静默返回哨兵行（不阻断，但留痕）。
        """
        event = {
            "event_id": uuid.uuid4().hex,
            "ts": time.time(),
            "kind": kind,
            "operator": str(operator or "system"),
            "action": str(action),
            "target": str(target),
            "detail": redact(detail or {}),
            "ip": str(ip or ""),
            "user_agent": str(user_agent or ""),
            "attempt_id": attempt_id,
            "epoch": epoch,
            "outcome": outcome,
            "source": "maintenance",
        }
        line = json.dumps(event, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self._ensure_dir()
            full = self._is_full()
            if full and critical:
                raise LocalAuditUnavailable(
                    f"本地审计容量上限（{self._path}，max_bytes={self._max_bytes}, max_events={self._max_events}）——拒绝关键动作"
                )
            if full:
                # 非关键事件超容：聚合丢弃 + 立即补哨兵（不静默无痕；尽力而为）
                self._dropped_count += 1
                try:
                    self._write_sentinel_unlocked()
                except OSError:
                    pass
                return {"event_id": event["event_id"], "kind": "audit_dropped", "detail": {"reason": "capacity"}}
            try:
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                os.chmod(self._path, 0o600)
                if self._dropped_count:
                    # 之前有非关键丢弃：补记哨兵（尽力而为）
                    self._write_sentinel_unlocked()
                    self._dropped_count = 0
                return event
            except OSError as exc:
                if critical:
                    raise LocalAuditUnavailable(f"本地审计写入失败（{self._path}）: {exc}") from exc
                self._dropped_count += 1
                return {"event_id": event["event_id"], "kind": "audit_dropped", "detail": {"reason": str(exc)}}

    def _ensure_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _is_full(self) -> bool:
        try:
            size = self._path.stat().st_size
        except OSError:
            return False
        if size >= self._max_bytes:
            return True
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                count = sum(1 for _ in fh)
        except OSError:
            return False
        return count >= self._max_events

    def _write_sentinel_unlocked(self) -> None:
        sentinel = {
            "event_id": uuid.uuid4().hex,
            "ts": time.time(),
            "kind": "audit_dropped_aggregate",
            "operator": "system",
            "detail": {"dropped": self._dropped_count},
            "source": "maintenance",
        }
        try:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(sentinel, ensure_ascii=False, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            self._dropped_count += 1  # 哨兵也写不进：下次成功时再补

    # ------------------------------------------------------------------
    # 回放（W3 ACK 归档同事务写入最终服务库；event_id 去重）
    # ------------------------------------------------------------------

    def replay_events(self) -> List[Dict[str, Any]]:
        """读全量事件，按 event_id 去重（保首见序；崩溃/重复 append 安全）。"""
        seen: Dict[str, Dict[str, Any]] = {}
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue  # 半行（崩溃窗口）：跳过，不视为事件
                    event_id = row.get("event_id")
                    if isinstance(event_id, str) and event_id and event_id not in seen:
                        seen[event_id] = row
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise LocalAuditUnavailable(f"本地审计读取失败: {exc}") from exc
        return list(seen.values())

    def iter_events(self) -> Iterator[Dict[str, Any]]:
        yield from self.replay_events()

    def clear(self) -> None:
        """归档完成后的显式清理（W3 ACK 流程调用；普通路径禁止触碰）。"""
        with self._lock:
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass
