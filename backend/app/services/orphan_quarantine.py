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

import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


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


def quarantine_file(src_path: str, quarantine_root: str) -> str:
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
    src_name = os.path.basename(src_path)
    dest_name = f"{uuid.uuid4().hex[:8]}_{src_name}"
    dest_path = os.path.join(quarantine_root, dest_name)

    src_stat = os.stat(src_path)

    try:
        # 优先 os.rename（同文件系统原子操作）
        os.rename(src_path, dest_path)
        logger.info(f"[隔离区] 原子移动: {src_path} → {dest_path}")
    except OSError as rename_err:
        # 跨文件系统（errno.EXDEV）→ 退化 copy + 校验 + delete
        logger.warning(f"[隔离区] os.rename 失败({rename_err})，退化 copy+delete: {src_path} → {dest_path}")
        shutil.copy2(src_path, dest_path)
        # 校验 size 一致后删源
        dest_stat = os.stat(dest_path)
        if dest_stat.st_size != src_stat.st_size:
            os.remove(dest_path)
            raise OSError(f"隔离 copy 后 size 校验失败: {src_path} (期望 {src_stat.st_size}, 实际 {dest_stat.st_size})")
        os.remove(src_path)
        logger.info(f"[隔离区] copy+delete 完成: {src_path} → {dest_path}")

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
        return False, f"size 不匹配: {file_path} (期望 {expected_size}, 实际 {stat_info.st_size})"

    if expected_mtime_ns is not None and stat_info.st_mtime_ns != expected_mtime_ns:
        return False, f"mtime_ns 不匹配: {file_path} (期望 {expected_mtime_ns}, 实际 {stat_info.st_mtime_ns})"

    if expected_inode is not None:
        actual_inode = (stat_info.st_dev, stat_info.st_ino)
        if actual_inode != expected_inode:
            return False, f"inode 不匹配: {file_path} (期望 {expected_inode}, 实际 {actual_inode})"

    return True, ""
