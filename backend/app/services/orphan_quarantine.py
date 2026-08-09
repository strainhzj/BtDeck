# -*- coding: utf-8 -*-
"""
孤儿文件隔离区管理（v1.0.6+ 语义重做）

自动清理流程：移入隔离区（不直接删除）→ 保留期到期 → 物理删除。

隔离区策略（用户确认：默认扫描根下 + 每下载器可覆盖）：
- 默认：在每个扫描根下建 .btdeck_quarantine/<scan_id>/（同文件系统，os.rename 恒原子）
- 覆盖：path_mapping JSON 支持 quarantine_root 可选字段（每下载器独立配置）

@file: orphan_quarantine.py
@time: 2026-07-11
"""

import errno
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

_OPERATION_DIR_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def _rename_no_replace(src_path: str, dest_path: str) -> None:
    """同文件系统移动且绝不覆盖目标；不支持 renameat2 时用 link+unlink 安全退化。"""
    if os.name == "nt":
        os.rename(src_path, dest_path)
        return

    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(src_path), -100, os.fsencode(dest_path), 1)
        if result == 0:
            return
        error = ctypes.get_errno()
        if error not in (38, 95):  # ENOSYS / EOPNOTSUPP 才允许安全退化
            raise OSError(error, os.strerror(error), dest_path)
    except AttributeError:
        pass

    # hard-link 创建本身具备 no-replace 语义；崩溃时 journal 会处理双路径状态。
    os.link(src_path, dest_path, follow_symlinks=False)
    os.unlink(src_path)


def resolve_quarantine_root(
    scan_root: str,
    downloader_path_mapping: Optional[str] = None,
    scan_id: Optional[str] = None,
) -> str:
    """解析隔离区根目录。

    优先级：
    1. path_mapping JSON 的 quarantine_root 字段（每下载器覆盖）
    2. 默认：<scan_root>/<ORPHAN_QUARANTINE_DIR_NAME>/<scan_id 或 uuid>

    Args:
        scan_root: 扫描根目录（外部路径）
        downloader_path_mapping: 下载器 path_mapping JSON 字符串（可含 quarantine_root）
        scan_id: 扫描批次 ID（用于隔离子目录）

    Returns:
        隔离区根目录绝对路径
    """
    # 尝试从 path_mapping 取 quarantine_root
    custom_root = _extract_quarantine_root(downloader_path_mapping)
    if custom_root and os.path.isabs(custom_root):
        sub = scan_id or uuid.uuid4().hex[:8]
        return os.path.join(custom_root, sub)

    # 默认：扫描根下的隐藏目录
    dir_name = settings.ORPHAN_QUARANTINE_DIR_NAME
    sub = scan_id or uuid.uuid4().hex[:8]
    return os.path.join(scan_root, dir_name, sub)


def _extract_quarantine_root(path_mapping_json: Optional[str]) -> Optional[str]:
    """从 path_mapping JSON 提取 quarantine_root（每下载器自定义隔离区）。"""
    if not path_mapping_json:
        return None
    try:
        config = json.loads(path_mapping_json)
        return config.get("quarantine_root")
    except (json.JSONDecodeError, TypeError):
        return None


def build_quarantine_path(src_path: str, quarantine_root: str) -> str:
    """原子创建私有操作目录并返回唯一目标，避免 rename 覆盖已有文件。"""
    os.makedirs(quarantine_root, exist_ok=True)
    operation_dir = os.path.join(quarantine_root, uuid.uuid4().hex)
    os.mkdir(operation_dir)
    return os.path.join(operation_dir, os.path.basename(src_path))


def _remove_empty_directory(path: str) -> bool:
    """仅删除真实空目录；非空、已不存在和符号链接均安全跳过。"""
    if not path or os.path.islink(path):
        return False
    try:
        os.rmdir(path)
        logger.info("[隔离区] 已清理空目录: %s", path)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST, errno.ENOENT):
            logger.warning("[隔离区] 空目录清理失败 %s: %s", path, exc)
        return False


def prune_empty_quarantine_parents(file_path: Optional[str], quarantine_root: Optional[str]) -> int:
    """删除已移走/删除文件留下的空父目录，并在为空时删除 scan_id 根目录。

    只沿 ``file_path`` 到已记录 ``quarantine_root`` 的路径向上执行 ``os.rmdir``；
    不递归、不删除非空目录，也不会越过 scan_id 根目录删除全局
    ``.btdeck_quarantine`` 或自定义隔离父目录。
    """
    if not file_path or not quarantine_root or not os.path.isabs(quarantine_root) or os.path.islink(quarantine_root):
        return 0

    root_path = os.path.abspath(quarantine_root)
    parent_path = os.path.abspath(os.path.dirname(file_path))
    root_real = os.path.realpath(root_path)
    parent_real = os.path.realpath(parent_path)
    try:
        lexical_root = os.path.commonpath([parent_path, root_path])
        resolved_root = os.path.commonpath([parent_real, root_real])
        if os.path.normcase(lexical_root) != os.path.normcase(root_path) or os.path.normcase(
            resolved_root
        ) != os.path.normcase(root_real):
            logger.warning("[隔离区] 拒绝清理越界目录: file=%s root=%s", file_path, quarantine_root)
            return 0
    except ValueError:
        return 0

    removed = 0
    current = parent_path
    while os.path.normcase(current) != os.path.normcase(root_path):
        if not _remove_empty_directory(current):
            break
        removed += 1
        parent = os.path.dirname(current)
        if parent == current:
            return removed
        current = parent

    if _remove_empty_directory(root_path):
        removed += 1
    return removed


def prune_recorded_quarantine_root(quarantine_root: Optional[str]) -> int:
    """清理已记录 scan_id 根目录下历史遗留的空 UUID 操作目录。

    历史 tombstone 路径在候选标记 purged 后会被清空，无法逐个反查；因此这里只
    扫描隔离根的直接子目录，并且仅处理 ``uuid4().hex`` 形态的空目录。
    """
    if not quarantine_root or not os.path.isabs(quarantine_root) or os.path.islink(quarantine_root):
        return 0

    root_real = os.path.realpath(quarantine_root)
    removed = 0
    try:
        entries = list(os.scandir(root_real))
    except FileNotFoundError:
        return 0
    except OSError as exc:
        logger.warning("[隔离区] 无法扫描历史空目录 %s: %s", quarantine_root, exc)
        return 0

    for entry in entries:
        if not _OPERATION_DIR_PATTERN.fullmatch(entry.name):
            continue
        try:
            is_directory = entry.is_dir(follow_symlinks=False)
        except OSError:
            continue
        if is_directory and _remove_empty_directory(entry.path):
            removed += 1

    if _remove_empty_directory(root_real):
        removed += 1
    return removed


def quarantine_file(
    src_path: str,
    quarantine_root: str,
    dest_path: Optional[str] = None,
    expected_size: Optional[int] = None,
    expected_mtime_ns: Optional[int] = None,
    expected_inode: Optional[Tuple[int, int]] = None,
) -> str:
    """将文件移入隔离区（原子优先，跨文件系统退化 copy+delete）。

    Args:
        src_path: 源文件绝对路径
        quarantine_root: 隔离区根目录

    Returns:
        隔离后的文件路径

    Raises:
        OSError: 文件操作失败
    """
    # 确保隔离区目录存在
    os.makedirs(quarantine_root, exist_ok=True)

    # 生成隔离后的文件名（用 uuid 防冲突）
    dest_path = dest_path or build_quarantine_path(src_path, quarantine_root)
    if os.path.commonpath([os.path.realpath(dest_path), os.path.realpath(quarantine_root)]) != os.path.realpath(
        quarantine_root
    ):
        raise OSError("隔离目标路径逃逸隔离根")

    src_stat = os.stat(src_path)
    expected_identity = expected_inode or (src_stat.st_dev, src_stat.st_ino)

    root_stat = os.stat(quarantine_root)
    if root_stat.st_dev != src_stat.st_dev:
        raise OSError("隔离区与源文件不在同一文件系统，拒绝非原子 copy+delete")

    _rename_no_replace(src_path, dest_path)
    moved_stat = os.stat(dest_path)
    identity_ok = (
        (moved_stat.st_dev, moved_stat.st_ino) == expected_identity
        and (expected_size is None or moved_stat.st_size == expected_size)
        and (expected_mtime_ns is None or moved_stat.st_mtime_ns == expected_mtime_ns)
    )
    if not identity_ok:
        if not os.path.exists(src_path):
            _rename_no_replace(dest_path, src_path)
        raise OSError(f"隔离后文件身份不一致: {dest_path}")
    logger.info(f"[隔离区] 原子移动: {src_path} → {dest_path}")

    return dest_path


def is_path_in_quarantine(path: str, scan_roots) -> bool:
    """判断路径是否在任一扫描根的隔离区内。

    Args:
        path: 待检查路径
        scan_roots: 扫描根列表（用于推导隔离区路径）

    Returns:
        是否在隔离区内
    """
    dir_name = settings.ORPHAN_QUARANTINE_DIR_NAME
    path_parts = Path(path).parts
    if dir_name in path_parts:
        return True
    return False


def find_hardlink_copies(
    target_inode: Tuple[int, int],
    scan_roots: List[str],
    exclude_path: Optional[str],
) -> List[str]:
    """在给定扫描根下枚举与目标 inode 相同的其它硬链接路径。

    用于隔离删除的诊断：删除隔离副本不会释放空间时，定位剩余副本。仅扫描候选
    所属 downloader 的 scan_roots（不扫全盘），排除被删路径本身。

    Args:
        target_inode: (st_dev, st_ino)，被删文件的 inode 身份
        scan_roots: 候选所属 downloader 的扫描根列表（manifest.scan_roots 的 root 部分）
        exclude_path: 被删文件绝对路径（隔离路径），需从结果排除

    Returns:
        其它硬链接路径绝对路径列表（顺序不保证）；扫描根外的链接不返回。

    Raises:
        OSError: inode 不可靠或扫描失败（网络盘/CIFS 等），由调用方兜底处理。
    """
    if not target_inode or not scan_roots:
        return []

    target_dev, target_ino = target_inode
    exclude_abs = os.path.abspath(exclude_path) if exclude_path else None
    found: List[str] = []

    for root in scan_roots:
        if not root or not os.path.isabs(root):
            continue
        for dir_path, _dirnames, filenames in os.walk(root):
            for name in filenames:
                full = os.path.join(dir_path, name)
                abs_full = os.path.abspath(full)
                if exclude_abs is not None and os.path.normcase(abs_full) == os.path.normcase(exclude_abs):
                    continue
                try:
                    st = os.stat(full)
                except OSError:
                    # 单文件 stat 失败不中断整体枚举
                    continue
                if st.st_dev == target_dev and st.st_ino == target_ino:
                    found.append(abs_full)
    return found


def compute_purge_after(quarantined_at, retention_days: Optional[int] = None):
    """计算允许物理删除的时间（quarantined_at + 保留期）。"""
    from datetime import timedelta

    days = retention_days if retention_days is not None else settings.ORPHAN_QUARANTINE_RETENTION_DAYS
    return quarantined_at + timedelta(days=days)


def verify_file_identity(
    file_path: str,
    expected_size: Optional[int] = None,
    expected_mtime_ns: Optional[int] = None,
    expected_inode: Optional[Tuple[int, int]] = None,
) -> Tuple[bool, str]:
    """验证文件身份是否与预期一致（清理前实时复核）。

    检查项：
    1. 文件存在且是普通文件（非符号链接/目录/设备文件）
    2. size 匹配（如提供）
    3. mtime_ns 匹配（如提供）
    4. inode (st_dev, st_ino) 匹配（如提供）

    Args:
        file_path: 文件路径
        expected_size: 期望大小（字节）
        expected_mtime_ns: 期望 mtime（纳秒）
        expected_inode: 期望 (st_dev, st_ino)

    Returns:
        (是否通过, 拒绝原因)
    """
    # 不跟随符号链接（lstat 判断链接本身）
    if os.path.islink(file_path):
        return False, f"符号链接不清理: {file_path}"

    if not os.path.exists(file_path):
        return False, f"文件不存在: {file_path}"

    if not os.path.isfile(file_path):
        return False, f"非普通文件: {file_path}"

    try:
        stat_info = os.stat(file_path)
    except OSError as e:
        return False, f"stat 失败: {file_path} ({e})"

    if expected_size is not None and stat_info.st_size != expected_size:
        return (
            False,
            f"size 不匹配: {file_path} (期望 {expected_size}, 实际 {stat_info.st_size})",
        )

    if expected_mtime_ns is not None and stat_info.st_mtime_ns != expected_mtime_ns:
        return (
            False,
            f"mtime_ns 不匹配: {file_path} (期望 {expected_mtime_ns}, 实际 {stat_info.st_mtime_ns})",
        )

    if expected_inode is not None:
        actual_inode = (stat_info.st_dev, stat_info.st_ino)
        if actual_inode != expected_inode:
            return (
                False,
                f"inode 不匹配: {file_path} (期望 {expected_inode}, 实际 {actual_inode})",
            )

    return True, ""
