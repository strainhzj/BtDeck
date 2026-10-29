"""config.yaml 仓储（database-migration-ui W3-2，PLANS §4.1/§4.2；T09/T15）。

- **RMW 统一锁**：config.yaml 的全部写入（init_config_file 安全密钥补齐 /
  activation 候选发布 / clear 交接 / 未来任何配置写）共用同一路径级文件锁；
- **原子写**：tmp → flush/fsync → replace → 父目录 fsync（沿用 journal 纪律，
  但 config.yaml 保持其既有权限位，仅新建时收紧 0640）；
- **未知节保留**：RMW 以读-改-写整棵 YAML 树（yaml round-trip 保留未知键），
  禁止"默认配置重建"吞掉用户自定义节（T09）；
- **受保护候选/前代配置**：仅用户确认切换准备后写入
  ``db-migration/attempts/<uuid>/{candidate-config,prior-config}.yaml``
  （0600/0700，含 B 记录凭据——与正式 config.yaml 同级敏感，绝不进导出/Git），
  并提供 sha256 摘要供 manifest 绑定（§4.2 候选/前代配置摘要）。
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Mapping, Optional

import yaml

from app.core.database_bootstrap import db_migration_dir, is_valid_attempt_id
from app.core.database_protocol import ATTEMPTS_DIRNAME

__all__ = [
    "ConfigStoreError",
    "config_lock",
    "read_yaml",
    "write_yaml_atomic",
    "rmw_yaml",
    "write_candidate_config",
    "write_prior_config",
    "read_candidate_config",
    "read_prior_config",
    "yaml_digest",
]

CANDIDATE_CONFIG_FILENAME = "candidate-config.yaml"
PRIOR_CONFIG_FILENAME = "prior-config.yaml"

_LOCK_SUFFIX = ".rmw.lock"


class ConfigStoreError(RuntimeError):
    """config 仓储错误（损坏 fail-closed / CAS 冲突等）。"""


# ---------------------------------------------------------------------------
# 路径级 RMW 锁（进程内重入；跨进程互斥）
# ---------------------------------------------------------------------------

_config_locks: Dict[str, "_PathLock"] = {}
_config_locks_guard = threading.Lock()


class _PathLock:
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
            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                raise ConfigStoreError(f"config.yaml RMW 锁被其他进程持有: {self._lock_path}") from None
            self._fd = fd

    @contextlib.contextmanager
    def acquire(self) -> Iterator[None]:
        with self._rlock:
            self._ensure_file_lock()
            yield


@contextlib.contextmanager
def config_lock(yaml_path: os.PathLike[str] | str) -> Iterator[None]:
    """获取 config.yaml 路径级 RMW 锁（同路径进程内重入；跨进程 → ConfigStoreError）。"""
    path = Path(yaml_path)
    key = str(path.resolve())
    with _config_locks_guard:
        lock = _config_locks.get(key)
        if lock is None:
            lock = _PathLock(path.with_name(path.name + _LOCK_SUFFIX))
            _config_locks[key] = lock
    with lock.acquire():
        yield


# ---------------------------------------------------------------------------
# 原子读写（未知节保留）
# ---------------------------------------------------------------------------


def read_yaml(yaml_path: os.PathLike[str] | str) -> Dict[str, Any]:
    """只读解析 config.yaml；缺失/损坏 → ConfigStoreError（fail-closed）。"""
    path = Path(yaml_path)
    if not path.exists():
        raise ConfigStoreError(f"{path} 不存在")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigStoreError(f"{path} 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigStoreError(f"{path} 顶层必须为映射")
    return data


def write_yaml_atomic(yaml_path: os.PathLike[str] | str, data: Mapping[str, Any]) -> None:
    """原子写 YAML（保留既有权限位；新建 0640；父目录 fsync）。"""
    from app.services.db_migration.journal import fsync_dir

    path = Path(yaml_path)
    mode = 0o640
    if path.exists():
        mode = path.stat().st_mode & 0o777
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.dump(dict(data), fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        fsync_dir(path.parent)
    finally:
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()


def rmw_yaml(
    yaml_path: os.PathLike[str] | str,
    mutator: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    *,
    allow_missing: bool = False,
) -> Dict[str, Any]:
    """锁内读-改-写（未知节天然保留）；返回写入后的完整配置树。

    - 文件缺失且 allow_missing=False → ConfigStoreError（受管证据缺失不凭空造）；
    - 损坏 YAML → ConfigStoreError（fail-closed，禁止默认化重建，T09）。
    """
    path = Path(yaml_path)
    with config_lock(path):
        if path.exists():
            try:
                current = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                raise ConfigStoreError(f"{path} 解析失败（拒绝默认化重建）: {exc}") from exc
            if not isinstance(current, dict):
                raise ConfigStoreError(f"{path} 顶层必须为映射（当前: {type(current).__name__}）")
        elif allow_missing:
            current = {}
        else:
            raise ConfigStoreError(f"{path} 不存在（受管配置缺失，拒绝凭空创建）")
        mutated = mutator(dict(current))
        result = current if mutated is None else mutated
        if not isinstance(result, dict):
            raise ConfigStoreError("config mutator 必须返回 dict 或 None")
        write_yaml_atomic(path, result)
        return result


def yaml_digest(data: Mapping[str, Any]) -> str:
    """候选/前代配置 sha256 摘要（manifest 绑定用；输入为已脱敏外的明文树）。"""
    canonical = yaml.dump(dict(data), default_flow_style=False, allow_unicode=True, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 受保护候选/前代配置（db-migration 子树 0600/0700）
# ---------------------------------------------------------------------------


def _attempt_dir(config_dir: os.PathLike[str] | str, attempt_id: str) -> Path:
    if not is_valid_attempt_id(attempt_id):
        raise ConfigStoreError(f"attempt_id 形态非法（拒绝路径映射）: {attempt_id!r}")
    d = db_migration_dir(config_dir) / ATTEMPTS_DIRNAME / attempt_id.rsplit("/", 1)[1]
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def write_candidate_config(
    config_dir: os.PathLike[str] | str, attempt_id: str, data: Mapping[str, Any]
) -> Dict[str, str]:
    """写受保护候选配置（仅用户确认切换准备后调用；§4.2）。返回路径+摘要。"""
    from app.services.db_migration.journal import deployment_lock

    with deployment_lock(config_dir):
        path = _attempt_dir(config_dir, attempt_id) / CANDIDATE_CONFIG_FILENAME
        _write_sensitive_yaml(path, data)
        return {"path": str(path), "sha256": yaml_digest(data)}


def write_prior_config(config_dir: os.PathLike[str] | str, attempt_id: str, data: Mapping[str, Any]) -> Dict[str, str]:
    """写前代配置备份（切换前代留档；同候选保护级别）。"""
    from app.services.db_migration.journal import deployment_lock

    with deployment_lock(config_dir):
        path = _attempt_dir(config_dir, attempt_id) / PRIOR_CONFIG_FILENAME
        _write_sensitive_yaml(path, data)
        return {"path": str(path), "sha256": yaml_digest(data)}


def read_candidate_config(config_dir: os.PathLike[str] | str, attempt_id: str) -> Dict[str, Any]:
    return _read_sensitive_yaml(_attempt_dir(config_dir, attempt_id) / CANDIDATE_CONFIG_FILENAME)


def read_prior_config(config_dir: os.PathLike[str] | str, attempt_id: str) -> Dict[str, Any]:
    return _read_sensitive_yaml(_attempt_dir(config_dir, attempt_id) / PRIOR_CONFIG_FILENAME)


def _write_sensitive_yaml(path: Path, data: Mapping[str, Any]) -> None:
    from app.services.db_migration.journal import fsync_dir

    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.dump(dict(data), fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        fsync_dir(path.parent)
    finally:
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()


def _read_sensitive_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ConfigStoreError(f"受保护配置不存在: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigStoreError(f"{path} 解析失败（受管证据损坏）: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigStoreError(f"{path} 顶层必须为映射")
    return data
