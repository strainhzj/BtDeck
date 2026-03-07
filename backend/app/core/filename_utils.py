"""
文件名处理工具

用于清理和生成安全的文件名，处理非法字符、长度限制等问题。
主要用于种子文件备份的文件名生成。
"""

import re
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class FilenameUtils:
    """文件名处理工具类"""

    # Windows非法字符集：< > : " / \ | ? *
    # 以及一些可能导致问题的字符
    INVALID_CHARS_PATTERN = r'[<>:"/\\|?*\x00-\x1f]'

    # 文件名最大长度（Windows限制）
    MAX_FILENAME_LENGTH = 255

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        清理文件名，移除非法字符

        保留合法字符，移除其他字符（替换为下划线）

        Args:
            filename: 原始文件名

        Returns:
            清理后的文件名
        """
        if not filename:
            return "unnamed"

        # 替换非法字符为下划线
        sanitized = re.sub(FilenameUtils.INVALID_CHARS_PATTERN, '_', filename)

        # 移除多余的空格和点
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = re.sub(r'\.+', '.', sanitized)
        sanitized = sanitized.strip(' ._')

        # 确保不为空
        if not sanitized:
            return "unnamed"

        return sanitized

    @staticmethod
    def generate_backup_filename(info_id: str, name: str, max_length: Optional[int] = None) -> str:
        """
        生成种子文件备份的文件名

        格式：{info_id}_{name}.torrent
        - 如果超长则使用 {info_id}.torrent
        - name部分会清理非法字符

        Args:
            info_id: 种子信息ID（UUID）
            name: 种子名称
            max_length: 最大文件名长度（默认使用MAX_FILENAME_LENGTH）

        Returns:
            备份文件名（不含路径）
        """
        if max_length is None:
            max_length = FilenameUtils.MAX_FILENAME_LENGTH

        # 清理种子名称
        clean_name = FilenameUtils.sanitize_filename(name)

        # 尝试使用 {info_id}_{name}.torrent 格式
        base_filename = f"{info_id}_{clean_name}.torrent"

        # 检查长度
        if len(base_filename) <= max_length:
            return base_filename

        # 如果超长，使用 {info_id}.torrent 格式
        logger.info(
            f"种子名称过长（{len(base_filename)} > {max_length}），"
            f"使用info_id作为文件名: {name[:50]}..."
        )
        return f"{info_id}.torrent"

    @staticmethod
    def ensure_directory_exists(directory_path: str) -> bool:
        """
        确保目录存在，不存在则创建

        Args:
            directory_path: 目录路径

        Returns:
            是否成功（True: 目录存在或创建成功，False: 失败）
        """
        try:
            os.makedirs(directory_path, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"创建目录失败: {directory_path}, 错误: {e}")
            return False

    @staticmethod
    def is_path_too_long(full_path: str, max_length: int = 260) -> bool:
        """
        检查路径是否过长

        Windows MAX_PATH 限制为260字符

        Args:
            full_path: 完整路径
            max_length: 最大路径长度

        Returns:
            是否过长
        """
        return len(full_path) > max_length

    @staticmethod
    def safe_path_join(directory: str, filename: str) -> str:
        """
        安全地拼接路径

        Args:
            directory: 目录路径
            filename: 文件名

        Returns:
            完整路径
        """
        # 规范化路径分隔符
        directory = os.path.normpath(directory)
        filename = FilenameUtils.sanitize_filename(filename)

        return os.path.join(directory, filename)
