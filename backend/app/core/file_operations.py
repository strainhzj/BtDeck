"""
文件操作服务

提供标记文件的创建、删除、检查功能，支持批量操作和自动回滚。
主要用于回收站功能的标记文件管理。

功能特性:
- 创建.waiting-delete标记文件（包含UUID关联数据库）
- 删除标记文件
- 检查标记文件状态
- 批量操作（支持自动回滚）
- 路径映射集成
- 完善的错误处理和降级方案
- 详细的日志记录

标记文件格式:
.waiting-delete文件内容:
    Deleted at: 2025-01-31T12:00:00.123456
    Torrent: {torrent_name}
    Torrent UUID: {uuid}
    Downloader ID: {downloader_id}
"""

import os
import asyncio
import logging
import shutil
import platform
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from pathlib import Path

from app.core.path_mapping import PathMappingService

logger = logging.getLogger(__name__)


class FileOperationService:
    """文件操作服务

    提供标记文件的创建、删除、检查功能。
    支持路径映射、批量操作和自动回滚。
    """

    MARKER_FILE = ".waiting-delete"

    def __init__(self, path_mapping_service: Optional[PathMappingService] = None):
        """
        初始化文件操作服务

        Args:
            path_mapping_service: 路径映射服务（可选）
        """
        self.path_mapping_service = path_mapping_service

    @staticmethod
    def _mask_uuid(uuid: Optional[str]) -> str:
        """
        脱敏UUID，用于日志输出

        Args:
            uuid: 原始UUID

        Returns:
            脱敏后的UUID
        """
        if not uuid or not isinstance(uuid, str):
            return "***"
        if len(uuid) <= 8:
            return f"{uuid[:4]}****"
        return f"{uuid[:4]}****{uuid[-4:]}"

    @staticmethod
    def _sanitize_path(path: str) -> str:
        """
        清理路径，防止路径遍历攻击

        Args:
            path: 原始路径

        Returns:
            清理后的路径
        """
        if not path:
            return path

        # 检查是否包含可疑的路径遍历字符
        if ".." in path:
            logger.warning(f"检测到可疑路径（包含..）: {path}")

        # 转换为绝对路径进行规范化
        try:
            # 规范化路径（移除多余的斜杠等）
            normalized = os.path.normpath(path)
            # 如果是相对路径，转换为绝对路径
            if not os.path.isabs(normalized):
                normalized = os.path.abspath(normalized)
            return normalized
        except Exception as e:
            logger.warning(f"路径规范化失败: {path} - {str(e)}")
            return path

    @staticmethod
    def _normalize_unc_path(path: str) -> Tuple[str, bool]:
        """
        根据操作系统类型规范化UNC路径格式

        Windows UNC路径标准格式: \\server\share\path
        Linux/Unix UNC路径格式: //server/share/path

        Args:
            path: 原始路径

        Returns:
            (规范化后的路径, 是否进行了转换)
        """
        if not path or not isinstance(path, str):
            return path, False

        # 检测是否是UNC路径（以//或\\开头）
        is_unc = path.startswith("//") or path.startswith("\\\\")

        if not is_unc:
            return path, False

        is_windows = platform.system() == "Windows"
        converted = False

        if is_windows:
            # Windows系统：确保使用反斜杠
            if "/" in path:
                # 将 // 替换为 \\，将路径中的 / 替换为 \
                normalized = path.replace("/", "\\")
                converted = True
                logger.debug(f"[Windows UNC路径转换] {path} -> {normalized}")
            else:
                normalized = path
        else:
            # Linux/Unix系统：确保使用正斜杠
            if "\\" in path:
                normalized = path.replace("\\", "/")
                converted = True
                logger.debug(f"[Unix UNC路径转换] {path} -> {normalized}")
            else:
                normalized = path

        return normalized, converted

    @staticmethod
    def _check_file_exists_with_fallback(path: str) -> Tuple[bool, str]:
        """
        检查文件是否存在，支持多种路径格式的降级尝试

        尝试顺序：
        1. 原始路径
        2. 系统原生UNC格式
        3. 混合格式（Windows: 正斜杠 -> 反斜杠）
        4. 目录列表验证（UNC路径访问诊断）

        Args:
            path: 原始路径

        Returns:
            (文件是否存在, 实际使用的路径)
        """
        # 🔍 深度诊断：检查文件名编码
        try:
            path_encoded = path.encode('utf-8', errors='strict').decode('utf-8')
            if path != path_encoded:
                logger.warning(f"[文件名编码问题] 检测到编码不一致，可能存在隐藏字符")
                logger.warning(f"  原始路径长度: {len(path)}, 编码后长度: {len(path_encoded)}")
        except Exception as e:
            logger.warning(f"[文件名编码检查失败] {e}")

        # 尝试1：原始路径
        if os.path.exists(path):
            logger.debug(f"[文件存在验证] 原始路径有效")
            return True, path

        # 尝试2：系统原生UNC格式
        normalized_path, was_converted = FileOperationService._normalize_unc_path(path)
        if was_converted and os.path.exists(normalized_path):
            logger.info(f"[路径格式修复] 使用系统原生格式: {normalized_path}")
            return True, normalized_path

        # 尝试3：对于Windows，尝试反斜杠版本
        if platform.system() == "Windows" and "/" in path:
            backslash_path = path.replace("/", "\\")
            if os.path.exists(backslash_path):
                logger.info(f"[路径格式修复] 使用反斜杠格式: {backslash_path}")
                return True, backslash_path

        # 尝试4：对于Windows，尝试正斜杠版本
        if platform.system() == "Windows" and "\\" in path:
            forward_slash_path = path.replace("\\", "/")
            if os.path.exists(forward_slash_path):
                logger.info(f"[路径格式修复] 使用正斜杠格式: {forward_slash_path}")
                return True, forward_slash_path

        # 🔍 深度诊断：尝试列出目录内容，验证UNC访问权限
        if platform.system() == "Windows":
            import ctypes
            import ctypes.wintypes

            try:
                # 提取目录路径
                dir_path = os.path.dirname(path)
                file_name = os.path.basename(path)

                logger.info(f"[UNC访问诊断] 尝试列出目录: {dir_path}")
                logger.info(f"[UNC访问诊断] 目标文件名: {file_name}")

                # 尝试使用os.listdir列出目录
                try:
                    files_in_dir = os.listdir(dir_path)
                    logger.info(f"[UNC访问诊断] 成功列出目录，文件数: {len(files_in_dir)}")

                    # 查找包含 "waiting-delete" 的文件
                    matching_files = [f for f in files_in_dir if "waiting-delete" in f]

                    if matching_files:
                        logger.info(f"[UNC访问诊断] 找到 {len(matching_files)} 个包含 'waiting-delete' 的文件:")
                        for mf in matching_files[:5]:  # 只显示前5个
                            logger.info(f"  - {mf}")
                            logger.info(f"    编码: {mf.encode('utf-8', errors='replace')}")

                            # 检查是否完全匹配
                            if mf == file_name:
                                exact_match_path = os.path.join(dir_path, mf)
                                logger.info(f"[UNC访问诊断] 找到完全匹配的文件: {exact_match_path}")
                                return True, exact_match_path

                        # 尝试使用第一个匹配的文件
                        if matching_files:
                            fallback_path = os.path.join(dir_path, matching_files[0])
                            logger.warning(f"[UNC访问诊断] 未找到完全匹配，使用第一个匹配文件: {fallback_path}")
                            return True, fallback_path
                    else:
                        logger.warning(f"[UNC访问诊断] 目录中未找到包含 'waiting-delete' 的文件")
                        logger.info(f"[UNC访问诊断] 目录中的前10个文件: {files_in_dir[:10]}")

                except PermissionError as pe:
                    logger.error(f"[UNC访问诊断] 权限不足，无法访问目录: {dir_path}")
                    logger.error(f"[UNC访问诊断] 错误详情: {pe}")

                    # 尝试使用Windows API检查当前用户
                    try:
                        import win32api
                        current_user = win32api.GetUserName()
                        logger.error(f"[UNC访问诊断] 当前Python进程用户: {current_user}")
                    except Exception:
                        pass

                except Exception as list_err:
                    logger.error(f"[UNC访问诊断] 列出目录失败: {list_err}")

            except Exception as e:
                logger.warning(f"[UNC访问诊断] 诊断过程出错: {e}")

        # 所有尝试都失败
        logger.debug(f"[文件不存在] 所有路径格式尝试均失败: {path}")
        return False, path

    def _convert_path(self, path: str) -> str:
        """
        转换路径（如果有路径映射服务）

        转换流程：
        1. 路径清理和安全检查
        2. 路径映射（内部路径 -> 外部路径）
        3. 根据操作系统类型规范化UNC路径格式

        Args:
            path: 原始路径

        Returns:
            转换后的路径（符合操作系统原生格式）
        """
        # P2-1: 路径清理
        path = self._sanitize_path(path)

        # 应用路径映射
        if self.path_mapping_service:
            path = self.path_mapping_service.internal_to_external(path)

        # 根据操作系统类型规范化UNC路径格式
        normalized_path, _ = self._normalize_unc_path(path)

        return normalized_path

    def convert_to_external_path(self, path: str) -> str:
        """
        将内部路径转换为外部路径（公共方法）

        用于文件操作时的路径转换，确保使用实际文件系统路径。

        Args:
            path: 内部路径（如容器内的路径）

        Returns:
            外部路径（如Windows共享路径）
        """
        return self._convert_path(path)

    async def create_marker_file(
        self,
        directory_path: str,
        torrent_name: Optional[str] = None,
        torrent_uuid: Optional[str] = None,
        downloader_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建标记文件

        Args:
            directory_path: 种子下载目录
            torrent_name: 种子名称（可选，用于日志和标记文件）
            torrent_uuid: 种子UUID（可选，用于关联数据库）
            downloader_id: 下载器ID（可选，用于追踪）

        Returns:
            操作结果字典
            {
                "success": bool,
                "marker_file_path": str,
                "error_message": Optional[str],
                "fallback": bool,  # 是否使用了降级方案
                "converted_path": str  # 转换后的路径（便于调试）
            }
        """
        result = {
            "success": False,
            "marker_file_path": "",
            "error_message": None,
            "fallback": False,
            "converted_path": ""
        }

        # P0-3: 路径验证
        if not directory_path or not isinstance(directory_path, str):
            error_msg = "目录路径不能为空"
            result["error_message"] = error_msg
            result["fallback"] = True
            logger.error(f"创建标记文件失败: {error_msg}, directory_path={directory_path}")
            return result

        try:
            # 转换路径
            converted_path = self._convert_path(directory_path)
            result["converted_path"] = converted_path
            marker_path = os.path.join(converted_path, self.MARKER_FILE)
            result["marker_file_path"] = marker_path

            # 确保目录存在
            os.makedirs(converted_path, exist_ok=True)

            # 创建标记文件内容（包含UUID关联数据库）
            content_lines = [
                f"Deleted at: {datetime.now().isoformat()}",
            ]

            if torrent_name:
                content_lines.append(f"Torrent: {torrent_name}")

            if torrent_uuid:
                content_lines.append(f"Torrent UUID: {torrent_uuid}")

            if downloader_id:
                content_lines.append(f"Downloader ID: {downloader_id}")

            # 写入标记文件
            with open(marker_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content_lines) + '\n')

            result["success"] = True

            # P1-2: 日志脱敏处理
            logger.info(
                f"创建标记文件成功: {marker_path} "
                f"(torrent={torrent_name}, uuid={self._mask_uuid(torrent_uuid)})"
            )

        except PermissionError as e:
            error_msg = f"权限不足: {str(e)}"
            result["error_message"] = error_msg
            result["fallback"] = True

            logger.warning(
                f"创建标记文件失败（权限不足）: {directory_path} - {error_msg}"
            )

        except OSError as e:
            error_msg = f"OS错误: {str(e)}"
            result["error_message"] = error_msg
            result["fallback"] = True

            logger.error(
                f"创建标记文件失败: {directory_path} - {error_msg}"
            )

        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            result["error_message"] = error_msg
            result["fallback"] = True

            logger.error(
                f"创建标记文件失败（未知错误）: {directory_path} - {error_msg}",
                exc_info=True
            )

        return result

    async def delete_marker_file(
        self,
        directory_path: str,
        torrent_name: Optional[str] = None,
        torrent_original_filename: Optional[str] = None,
        delete_pending_delete_folder: bool = False
    ) -> Dict[str, Any]:
        """
        删除标记文件（.waiting-delete）或 .pending_delete 文件夹

        Args:
            directory_path: 种子下载目录
            torrent_name: 种子名称（用于日志）
            torrent_original_filename: 原始文件名（用于构建pending_delete路径）
            delete_pending_delete_folder: 是否删除 .pending_delete 文件夹
                - True: 删除整个 .pending_delete 文件夹（用于兼容旧逻辑）
                - False: 只删除标记文件，保留 .pending_delete 文件夹（默认）

        Returns:
            操作结果字典
            {
                "success": bool,
                "error_message": Optional[str],
                "file_existed": bool,  # 文件/文件夹是否存在
                "deleted_type": str,   # "single_file" 或 "multi_file" 或 "marker_file"
                "deleted_path": str     # 实际删除的路径
            }
        """
        result = {
            "success": False,
            "error_message": None,
            "file_existed": False,
            "deleted_type": "",
            "deleted_path": ""
        }

        # 构建日志上下文
        log_context = f"种子[{torrent_name}] " if torrent_name else ""

        try:
            # 判断是否删除 .pending_delete 文件夹
            if delete_pending_delete_folder and torrent_original_filename:
                # ========== 旧逻辑：删除 .pending_delete 文件夹 ==========
                target_filename = torrent_original_filename

                # 转换路径
                converted_path = self._convert_path(directory_path)

                # 判断种子类型并构建 xxx.pending_delete 路径
                is_single_file = self.is_single_file_torrent(target_filename)

                if is_single_file:
                    # 单文件种子：movie.pending_delete.mkv
                    name_without_ext, ext = os.path.splitext(target_filename)
                    pending_delete_name = f"{name_without_ext}.pending_delete{ext}"
                    result["deleted_type"] = "single_file"
                else:
                    # 多文件种子：[文件夹名].pending_delete
                    pending_delete_name = f"{target_filename}.pending_delete"
                    result["deleted_type"] = "multi_file"

                pending_delete_path = os.path.join(converted_path, pending_delete_name)
                result["deleted_path"] = pending_delete_path

                # 🔍 诊断日志：记录原始路径信息
                logger.info(
                    f"{log_context}[路径诊断] pending_delete路径: {pending_delete_path}, "
                    f"操作系统: {platform.system()}, "
                    f"路径类型: {'UNC路径' if (pending_delete_path.startswith('//') or pending_delete_path.startswith('\\\\')) else '本地路径'}"
                )

                # 检查文件/文件夹是否存在（支持多种路径格式降级尝试）
                file_exists, actual_path = self._check_file_exists_with_fallback(pending_delete_path)

                if not file_exists:
                    # 文件不存在，视为成功（降级处理）
                    result["success"] = True
                    result["file_existed"] = False
                    logger.info(
                        f"{log_context}pending_delete文件/文件夹不存在（降级）: {pending_delete_path}"
                    )
                    return result

                # 如果使用了修复后的路径，更新删除路径
                if actual_path != pending_delete_path:
                    result["deleted_path"] = actual_path
                    logger.info(
                        f"{log_context}[路径修复] 使用修复后的路径: {actual_path}"
                    )

                result["file_existed"] = True

                # 删除文件或文件夹（使用修复后的路径）
                if os.path.isfile(actual_path):
                    os.remove(actual_path)
                    logger.info(
                        f"{log_context}删除pending_delete文件成功: {actual_path}"
                    )
                elif os.path.isdir(actual_path):
                    import shutil
                    shutil.rmtree(actual_path)
                    logger.info(
                        f"{log_context}删除pending_delete文件夹成功: {actual_path}"
                    )
                else:
                    # 既不是文件也不是文件夹，视为不存在（降级处理）
                    result["success"] = True
                    result["file_existed"] = False
                    logger.warning(
                        f"{log_context}pending_delete路径既非文件也非文件夹（降级）: {actual_path}"
                    )
                    return result

                result["success"] = True

            else:
                # ========== 新逻辑：只删除标记文件 ==========
                result["deleted_type"] = "marker_file"

                # 转换路径
                converted_path = self._convert_path(directory_path)

                # 构建标记文件路径
                marker_file_name = torrent_name if torrent_name else "unknown"
                marker_file_path = os.path.join(converted_path, f"{marker_file_name}.waiting-delete")

                result["deleted_path"] = marker_file_path

                # 🔍 诊断日志：记录原始路径信息
                logger.info(
                    f"{log_context}[路径诊断] 原始路径: {marker_file_path}, "
                    f"操作系统: {platform.system()}, "
                    f"路径类型: {'UNC路径' if (marker_file_path.startswith('//') or marker_file_path.startswith('\\\\')) else '本地路径'}"
                )

                # 检查标记文件是否存在（支持多种路径格式降级尝试）
                file_exists, actual_path = self._check_file_exists_with_fallback(marker_file_path)

                if not file_exists:
                    # 标记文件不存在，视为成功（降级处理）
                    result["success"] = True
                    result["file_existed"] = False
                    logger.info(
                        f"{log_context}标记文件不存在（降级）: {marker_file_path}"
                    )
                    return result

                # 如果使用了修复后的路径，更新删除路径
                if actual_path != marker_file_path:
                    result["deleted_path"] = actual_path
                    logger.info(
                        f"{log_context}[路径修复] 使用修复后的路径: {actual_path}"
                    )

                result["file_existed"] = True

                # 删除标记文件（使用修复后的路径）
                os.remove(actual_path)
                logger.info(
                    f"{log_context}删除标记文件成功: {actual_path}"
                )

                result["success"] = True

        except PermissionError as e:
            error_msg = f"权限不足: {str(e)}"
            result["error_message"] = error_msg
            logger.warning(
                f"{log_context}删除标记文件失败（权限不足）: {directory_path} - {error_msg}"
            )

        except OSError as e:
            error_msg = f"OS错误: {str(e)}"
            result["error_message"] = error_msg
            logger.error(
                f"{log_context}删除标记文件失败: {directory_path} - {error_msg}"
            )

        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            result["error_message"] = error_msg
            logger.error(
                f"{log_context}删除标记文件失败（未知错误）: {directory_path}",
                exc_info=True
            )

        return result

    async def check_marker_file(
        self,
        directory_path: str
    ) -> bool:
        """
        检查标记文件是否存在

        Args:
            directory_path: 种子下载目录

        Returns:
            标记文件是否存在
        """
        try:
            # 转换路径
            converted_path = self._convert_path(directory_path)
            marker_path = os.path.join(converted_path, self.MARKER_FILE)

            # 检查文件
            exists = os.path.exists(marker_path)

            logger.debug(f"检查标记文件: {marker_path} - 存在: {exists}")
            return exists

        except Exception as e:
            logger.error(
                f"检查标记文件失败: {directory_path} - {str(e)}",
                exc_info=True
            )
            return False

    async def read_marker_file(
        self,
        directory_path: str
    ) -> Dict[str, Any]:
        """
        读取标记文件内容

        Args:
            directory_path: 种子下载目录

        Returns:
            标记文件内容字典
            {
                "success": bool,
                "exists": bool,
                "deleted_at": Optional[str],
                "torrent_name": Optional[str],
                "torrent_uuid": Optional[str],
                "downloader_id": Optional[str],
                "error_message": Optional[str]
            }
        """
        result = {
            "success": False,
            "exists": False,
            "deleted_at": None,
            "torrent_name": None,
            "torrent_uuid": None,
            "downloader_id": None,
            "error_message": None
        }

        try:
            # 转换路径
            converted_path = self._convert_path(directory_path)
            marker_path = os.path.join(converted_path, self.MARKER_FILE)

            # 检查文件是否存在
            if not os.path.exists(marker_path):
                result["exists"] = False
                result["success"] = True
                return result

            result["exists"] = True

            # 读取文件内容
            with open(marker_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # P0-2: 安全解析内容，防止IndexError
            for line in content.strip().split('\n'):
                try:
                    if line.startswith("Deleted at:"):
                        parts = line.split(":", 1)
                        result["deleted_at"] = parts[1].strip() if len(parts) > 1 else ""
                    elif line.startswith("Torrent:"):
                        parts = line.split(":", 1)
                        result["torrent_name"] = parts[1].strip() if len(parts) > 1 else ""
                    elif line.startswith("Torrent UUID:"):
                        parts = line.split(":", 1)
                        result["torrent_uuid"] = parts[1].strip() if len(parts) > 1 else ""
                    elif line.startswith("Downloader ID:"):
                        parts = line.split(":", 1)
                        result["downloader_id"] = parts[1].strip() if len(parts) > 1 else ""
                except Exception as e:
                    logger.warning(f"解析标记文件行失败: {line} - {str(e)}")
                    continue

            result["success"] = True
            logger.debug(f"读取标记文件成功: {marker_path}")

        except Exception as e:
            error_msg = f"读取标记文件失败: {str(e)}"
            result["error_message"] = error_msg
            logger.error(
                f"读取标记文件失败: {directory_path} - {error_msg}",
                exc_info=True
            )

        return result

    async def batch_create_markers(
        self,
        directories: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        批量创建标记文件（支持自动回滚）

        Args:
            directories: 目录列表
            [
                {
                    "path": "/downloads/torrent1/",
                    "name": "Torrent1",
                    "uuid": "xxx-xxx-xxx",
                    "downloader_id": "downloader1"
                },
                ...
            ]

        Returns:
            批量操作结果
            {
                "total": int,
                "success_count": int,
                "failed_count": int,
                "fallback_count": int,
                "rollback_count": int,  # 回滚的数量
                "results": List[Dict],
                "rolled_back_paths": List[str]  # 被回滚的路径
            }
        """
        # P0-1 & P1-1: 输入验证
        if not directories or not isinstance(directories, list):
            logger.warning("batch_create_markers: directories参数为空或无效")
            return {
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "fallback_count": 0,
                "rollback_count": 0,
                "results": [],
                "rolled_back_paths": []
            }

        results = {
            "total": len(directories),
            "success_count": 0,
            "failed_count": 0,
            "fallback_count": 0,
            "rollback_count": 0,
            "results": [],
            "rolled_back_paths": []
        }

        # 记录已成功创建的文件路径（用于回滚）
        created_files = []

        try:
            for dir_info in directories:
                # P0-1: 验证每个元素
                if not isinstance(dir_info, dict) or "path" not in dir_info:
                    logger.error(f"无效的目录信息（缺少path键或不是字典）: {dir_info}")
                    results["failed_count"] += 1
                    # 添加失败结果
                    results["results"].append({
                        "success": False,
                        "marker_file_path": "",
                        "error_message": "无效的目录信息（缺少path键）",
                        "fallback": False,
                        "converted_path": ""
                    })
                    continue

                result = await self.create_marker_file(
                    directory_path=dir_info["path"],
                    torrent_name=dir_info.get("name"),
                    torrent_uuid=dir_info.get("uuid"),
                    downloader_id=dir_info.get("downloader_id")
                )

                results["results"].append(result)

                if result["success"]:
                    results["success_count"] += 1
                    # 记录成功创建的文件路径
                    created_files.append(result["marker_file_path"])
                else:
                    results["failed_count"] += 1
                    results["fallback_count"] += 1 if result["fallback"] else 0

                    # 创建失败，执行回滚
                    logger.warning(
                        f"批量创建标记文件失败，开始回滚已创建的 {len(created_files)} 个文件"
                    )

                    for marker_path in created_files:
                        try:
                            if os.path.exists(marker_path):
                                os.remove(marker_path)
                                results["rolled_back_paths"].append(marker_path)
                                results["rollback_count"] += 1
                                logger.info(f"回滚删除标记文件: {marker_path}")
                        except Exception as e:
                            logger.error(f"回滚删除标记文件失败: {marker_path} - {str(e)}")

                    # 回滚后立即返回
                    logger.error(
                        f"批量创建标记文件失败并回滚: "
                        f"总计{results['total']}, "
                        f"成功{results['success_count']}, "
                        f"失败{results['failed_count']}, "
                        f"回滚{results['rollback_count']}"
                    )
                    return results

            # 全部成功
            logger.info(
                f"批量创建标记文件完成: "
                f"总计{results['total']}, "
                f"成功{results['success_count']}, "
                f"失败{results['failed_count']}, "
                f"降级{results['fallback_count']}"
            )

        except Exception as e:
            logger.error(
                f"批量创建标记文件异常: {str(e)}",
                exc_info=True
            )

            # 尝试回滚已创建的文件
            if created_files:
                logger.warning(f"发生异常，尝试回滚已创建的 {len(created_files)} 个文件")
                for marker_path in created_files:
                    try:
                        if os.path.exists(marker_path):
                            os.remove(marker_path)
                            results["rolled_back_paths"].append(marker_path)
                            results["rollback_count"] += 1
                    except Exception as e:
                        logger.error(f"异常回滚删除标记文件失败: {marker_path} - {str(e)}")

        return results

    async def batch_delete_markers(
        self,
        directories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        批量删除标记文件

        Args:
            directories: 目录路径列表

        Returns:
            批量操作结果
            {
                "total": int,
                "success_count": int,
                "failed_count": int,
                "existed_count": int,  # 实际存在的文件数量
                "results": List[Dict]
            }
        """
        # P0-4: 输入验证
        if not directories or not isinstance(directories, list):
            logger.warning("batch_delete_markers: directories参数为空或无效")
            return {
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "existed_count": 0,
                "results": []
            }

        # 验证并过滤有效路径
        valid_directories = []
        for d in directories:
            if isinstance(d, str) and d.strip():
                valid_directories.append(d.strip())
            else:
                logger.warning(f"过滤无效路径: {d}")

        if len(valid_directories) != len(directories):
            logger.warning(f"过滤了 {len(directories) - len(valid_directories)} 个无效路径")

        results = {
            "total": len(valid_directories),
            "success_count": 0,
            "failed_count": 0,
            "existed_count": 0,
            "results": []
        }

        for directory in valid_directories:
            result = await self.delete_marker_file(directory)

            results["results"].append(result)

            if result["success"]:
                results["success_count"] += 1
                if result["marker_file_existed"]:
                    results["existed_count"] += 1
            else:
                results["failed_count"] += 1

        logger.info(
            f"批量删除标记文件完成: "
            f"总计{results['total']}, "
            f"成功{results['success_count']}, "
            f"失败{results['failed_count']}, "
            f"实际存在{results['existed_count']}"
        )

        return results

    async def rename_folder_for_recycle(
        self,
        directory_path: str,
        torrent_name: str,
        suffix: str = ".pending_delete"
    ) -> Dict[str, Any]:
        """
        重命名文件夹以标记为回收站状态

        在等级3删除中使用，将种子文件夹重命名为 原名称.pending_delete
        实现视觉提示和避免路径冲突

        Args:
            directory_path: 种子保存路径（包含文件夹）
            torrent_name: 种子名称（文件夹名称）
            suffix: 要添加的后缀，默认为 ".pending_delete"

        Returns:
            操作结果
            {
                "success": bool,
                "original_path": str,      # 原始完整路径
                "new_path": str,           # 新的完整路径
                "folder_name": str,        # 原始文件夹名称
                "new_folder_name": str,    # 新的文件夹名称
                "error": str (可选)        # 错误信息
            }
        """
        try:
            # 输入验证
            if not directory_path or not torrent_name:
                return {
                    "success": False,
                    "error": "directory_path或torrent_name为空"
                }

            # 转换路径格式
            directory_path = self._convert_path(directory_path)
            directory_path = self._sanitize_path(directory_path)

            # 检查目录是否存在
            if not os.path.exists(directory_path):
                logger.warning(f"重命名文件夹失败: 目录不存在 - {directory_path}")
                return {
                    "success": False,
                    "error": "目录不存在",
                    "directory_path": directory_path
                }

            # 提取文件夹名称和父目录
            folder_name = os.path.basename(directory_path)
            parent_dir = os.path.dirname(directory_path)

            # 构建新的文件夹名称
            new_folder_name = f"{folder_name}{suffix}"
            new_path = os.path.join(parent_dir, new_folder_name)

            # 检查目标路径是否已存在
            if os.path.exists(new_path):
                logger.warning(f"重命名文件夹失败: 目标路径已存在 - {new_path}")
                return {
                    "success": False,
                    "error": "目标文件夹已存在",
                    "new_path": new_path
                }

            # 在线程池中执行重命名操作
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                os.rename,
                directory_path,
                new_path
            )

            logger.info(f"文件夹重命名成功: {folder_name} -> {new_folder_name}")

            return {
                "success": True,
                "original_path": directory_path,
                "new_path": new_path,
                "folder_name": folder_name,
                "new_folder_name": new_folder_name
            }

        except Exception as e:
            logger.error(f"重命名文件夹失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "directory_path": directory_path
            }

    async def restore_folder_from_recycle(
        self,
        current_path: str,
        original_name: str
    ) -> Dict[str, Any]:
        """
        从回收站还原文件夹名称

        在还原操作中使用，将 .pending_delete 后缀移除，恢复原始名称

        Args:
            current_path: 当前文件夹完整路径（包含.pending_delete后缀）
            original_name: 原始文件夹名称（不带后缀）

        Returns:
            操作结果
            {
                "success": bool,
                "original_path": str,      # 当前路径
                "new_path": str,           # 还原后的路径
                "error": str (可选)        # 错误信息
            }
        """
        try:
            # 输入验证
            if not current_path or not original_name:
                return {
                    "success": False,
                    "error": "current_path或original_name为空"
                }

            # 转换路径格式
            current_path = self._convert_path(current_path)
            current_path = self._sanitize_path(current_path)

            # 检查目录是否存在
            if not os.path.exists(current_path):
                logger.warning(f"还原文件夹失败: 目录不存在 - {current_path}")
                return {
                    "success": False,
                    "error": "目录不存在",
                    "current_path": current_path
                }

            # 提取父目录
            parent_dir = os.path.dirname(current_path)
            new_path = os.path.join(parent_dir, original_name)

            # 检查目标路径是否已存在
            if os.path.exists(new_path):
                logger.warning(f"还原文件夹失败: 目标路径已存在 - {new_path}")
                return {
                    "success": False,
                    "error": "目标文件夹已存在，无法还原",
                    "new_path": new_path
                }

            # 在线程池中执行重命名操作
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                os.rename,
                current_path,
                new_path
            )

            logger.info(f"文件夹还原成功: {os.path.basename(current_path)} -> {original_name}")

            return {
                "success": True,
                "original_path": current_path,
                "new_path": new_path
            }

        except Exception as e:
            logger.error(f"还原文件夹失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "current_path": current_path
            }

    # ========== 新增：智能种子重命名方法（支持单文件和多文件） ==========

    @staticmethod
    def is_single_file_torrent(torrent_name: str, save_path: str = None) -> bool:
        """
        检测种子是否为单文件种子（混合策略）

        优先级：
        1. 文件系统检测（最准确，需要提供 save_path）
        2. 扩展名判断（回退方案，覆盖常见文件类型）

        Args:
            torrent_name: 种子名称
            save_path: 种子保存路径（可选，用于文件系统检测）

        Returns:
            True: 单文件种子
            False: 多文件种子（文件夹）
        """
        # ========== 优先级1：文件系统检测（最准确） ==========
        if save_path:
            try:
                # 构建完整路径
                full_path = os.path.join(save_path, torrent_name)

                # 检查路径是否存在
                if os.path.exists(full_path):
                    # 文件存在，直接判断是文件还是文件夹
                    is_file = os.path.isfile(full_path)
                    logger.debug(
                        f"[单文件检测: 文件系统] {torrent_name} -> "
                        f"{'单文件' if is_file else '多文件'}"
                    )
                    return is_file
                else:
                    logger.debug(
                        f"[单文件检测: 文件系统] 路径不存在: {full_path}，"
                        f"回退到扩展名判断"
                    )
            except Exception as e:
                logger.debug(
                    f"[单文件检测: 文件系统] 检测失败: {e}，"
                    f"回退到扩展名判断"
                )

        # ========== 优先级2：扩展名判断（回退方案） ==========
        # 覆盖常见文件类型
        all_extensions = [
            # 视频文件
            '.mkv', '.mp4', '.avi', '.wmv', '.mov', '.flv', '.ts', '.m2ts',
            '.rmvb', '.rm', '.mpg', '.mpeg', '.3gp', '.webm', '.ogv',
            # 电子书文件
            '.epub', '.mobi', '.azw3', '.pdf', '.cbr', '.cbz',
            # 压缩文件
            '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
            # 音频文件
            '.mp3', '.flac', '.wav', '.aac', '.ogg', '.wma',
            # 图片文件
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
            # 文档文件
            '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            # 其他常见文件
            '.txt', '.iso', '.dmg', '.exe', '.apk'
        ]

        # 检查种子名称是否以已知扩展名结尾
        torrent_name_lower = torrent_name.lower()
        is_single = any(torrent_name_lower.endswith(ext) for ext in all_extensions)

        logger.debug(
            f"[单文件检测: 扩展名] {torrent_name} -> "
            f"{'单文件' if is_single else '多文件（未知扩展名）'}"
        )

        return is_single

    async def get_torrent_actual_path(
        self,
        save_path: str,
        torrent_name: str
    ) -> Dict[str, Any]:
        """
        获取种子的实际路径（自动检测单文件或多文件，支持fallback）

        Args:
            save_path: 种子保存路径（通用下载目录）
            torrent_name: 种子名称

        Returns:
            {
                "success": bool,
                "actual_path": str,        # 实际路径（文件或文件夹）
                "is_directory": bool,       # True=文件夹, False=单文件
                "exists": bool,             # 路径是否存在
                "error": str (可选)         # 错误信息
            }
        """
        try:
            # 记录原始输入
            original_save_path = save_path

            # 转换路径格式（_convert_path 内部已经调用了 _sanitize_path）
            save_path = self._convert_path(save_path)

            # 判断种子类型
            is_single_file = self.is_single_file_torrent(torrent_name)
            torrent_type = "single_file" if is_single_file else "multi_file"

            logger.info(
                f"[路径检测] 种子名称: {torrent_name}, "
                f"原始save_path: {original_save_path}, "
                f"转换后save_path: {save_path}, "
                f"判断类型: {torrent_type}"
            )

            if is_single_file:
                # 单文件种子：文件直接在save_path下
                actual_path = os.path.join(save_path, torrent_name)
                is_directory = False
                exists = os.path.exists(actual_path)

                logger.info(
                    f"[路径检测] 单文件模式\n"
                    f"  - 构建路径: {actual_path}\n"
                    f"  - 路径存在: {exists}\n"
                    f"  - 是否目录: {is_directory}"
                )

                if exists:
                    return {
                        "success": True,
                        "actual_path": actual_path,
                        "is_directory": is_directory,
                        "exists": exists,
                        "torrent_type": torrent_type
                    }
            else:
                # 多文件种子：save_path下的文件夹
                actual_path = os.path.join(save_path, torrent_name)
                is_directory = True
                exists = os.path.exists(actual_path)

                logger.info(
                    f"[路径检测] 多文件模式\n"
                    f"  - 构建路径: {actual_path}\n"
                    f"  - 路径存在: {exists}\n"
                    f"  - 是否目录: {is_directory}\n"
                    f"  - save_path类型: {type(save_path)}\n"
                    f"  - torrent_name类型: {type(torrent_name)}"
                )

                if exists:
                    return {
                        "success": True,
                        "actual_path": actual_path,
                        "is_directory": is_directory,
                        "exists": exists,
                        "torrent_type": torrent_type
                    }

                # ========== Fallback逻辑：多文件路径不存在，尝试单文件 ==========
                # 可能种子名称不包含扩展名，但实际上是单文件
                logger.warning(
                    f"[路径检测] 多文件路径不存在，尝试fallback到单文件检测: {actual_path}"
                )

                # 尝试常见的视频扩展名
                video_extensions = ['.mkv', '.mp4', '.avi', '.wmv', '.mov', '.flv', '.ts', '.m2ts']

                for ext in video_extensions:
                    fallback_path = os.path.join(save_path, f"{torrent_name}{ext}")
                    if os.path.exists(fallback_path):
                        logger.info(
                            f"[路径检测] Fallback成功：找到单文件 "
                            f"{torrent_name}{ext}"
                        )
                        return {
                            "success": True,
                            "actual_path": fallback_path,
                            "is_directory": False,
                            "exists": True,
                            "torrent_type": "single_file_fallback"
                        }

            # 所有尝试都失败
            logger.error(
                f"[路径检测] 所有路径尝试失败，最后尝试的路径: {actual_path}, "
                f"类型: {torrent_type}"
            )

            return {
                "success": True,
                "actual_path": actual_path,
                "is_directory": is_directory,
                "exists": False,
                "torrent_type": torrent_type
            }

        except Exception as e:
            logger.error(f"获取种子实际路径失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "actual_path": None,
                "is_directory": False,
                "exists": False
            }

    async def rename_torrent_for_recycle(
        self,
        save_path: str,
        torrent_name: str,
        suffix: str = ".pending_delete"
    ) -> Dict[str, Any]:
        """
        智能重命名种子（支持单文件和多文件）

        - 单文件：movie.mkv -> movie.pending_delete.mkv
        - 多文件：[文件夹名] -> [文件夹名].pending_delete

        Args:
            save_path: 种子保存路径（通用下载目录）
            torrent_name: 种子名称
            suffix: 要添加的后缀，默认为 ".pending_delete"

        Returns:
            {
                "success": bool,
                "original_path": str,      # 原始完整路径
                "new_path": str,           # 新的完整路径
                "is_directory": bool,      # True=文件夹, False=单文件
                "original_name": str,      # 原始名称
                "new_name": str,           # 新名称
                "torrent_type": str,       # "single_file" 或 "multi_file"
                "error": str (可选)        # 错误信息
            }
        """
        try:
            # 输入验证
            if not save_path or not torrent_name:
                return {
                    "success": False,
                    "error": "save_path或torrent_name为空"
                }

            # 获取种子实际路径
            path_info = await self.get_torrent_actual_path(save_path, torrent_name)

            if not path_info.get("success"):
                return {
                    "success": False,
                    "error": f"获取种子路径失败: {path_info.get('error')}"
                }

            original_path = path_info.get("actual_path")
            is_directory = path_info.get("is_directory")
            torrent_type = path_info.get("torrent_type")

            # 检查路径是否存在
            if not path_info.get("exists"):
                logger.warning(f"重命名种子失败: 路径不存在 - {original_path} (type={torrent_type})")
                return {
                    "success": False,
                    "error": f"{'文件' if not is_directory else '文件夹'}不存在",
                    "original_path": original_path,
                    "torrent_type": torrent_type
                }

            # 根据类型构建新名称
            if is_directory:
                # 多文件种子（文件夹）：直接添加后缀
                original_name = os.path.basename(original_path)
                parent_dir = os.path.dirname(original_path)
                new_name = f"{original_name}{suffix}"
                new_path = os.path.join(parent_dir, new_name)
            else:
                # 单文件种子：在扩展名前添加后缀
                # movie.mkv -> movie.pending_delete.mkv
                original_name = os.path.basename(original_path)
                parent_dir = os.path.dirname(original_path)
                name_without_ext, ext = os.path.splitext(original_name)
                new_name = f"{name_without_ext}{suffix}{ext}"
                new_path = os.path.join(parent_dir, new_name)

            # 检查目标路径是否已存在
            if os.path.exists(new_path):
                logger.warning(f"重命名种子失败: 目标路径已存在 - {new_path}")
                return {
                    "success": False,
                    "error": "目标已存在，无法重命名",
                    "new_path": new_path,
                    "torrent_type": torrent_type
                }

            # 在线程池中执行重命名操作
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                os.rename,
                original_path,
                new_path
            )

            logger.info(
                f"种子重命名成功 ({torrent_type}): {original_name} -> {new_name}"
            )

            return {
                "success": True,
                "original_path": original_path,
                "new_path": new_path,
                "is_directory": is_directory,
                "original_name": original_name,
                "new_name": new_name,
                "torrent_type": torrent_type
            }

        except Exception as e:
            logger.error(f"重命名种子失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "save_path": save_path,
                "torrent_name": torrent_name
            }

    async def restore_torrent_from_recycle(
        self,
        current_path: str,
        original_name: str,
        is_directory: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        智能还原种子（支持单文件和多文件）

        还原逻辑变更（适配新的删除逻辑）：
        - 单文件：movie.pending_delete.mkv -> movie.mkv（直接重命名）
        - 多文件：将 [文件夹名].pending_delete 中的所有文件移动到 [文件夹名]

        Args:
            current_path: 当前路径（带.pending_delete后缀）
            original_name: 原始名称（不带后缀）
            is_directory: 是否为文件夹（可选，自动检测）

        Returns:
            {
                "success": bool,
                "original_path": str,      # 当前路径（带后缀）
                "new_path": str,           # 还原后的路径
                "is_directory": bool,      # True=文件夹, False=单文件
                "current_name": str,       # 当前名称（带后缀）
                "restored_name": str,      # 还原后的名称
                "torrent_type": str,       # "single_file" 或 "multi_file"
                "error": str (可选)        # 错误信息
            }
        """
        try:
            # 输入验证
            if not current_path or not original_name:
                return {
                    "success": False,
                    "error": "current_path或original_name为空"
                }

            # 转换路径格式
            current_path = self._convert_path(current_path)
            current_path = self._sanitize_path(current_path)

            # 检查当前路径是否存在
            if not os.path.exists(current_path):
                logger.warning(f"还原种子失败: 路径不存在 - {current_path}")
                return {
                    "success": False,
                    "error": "路径不存在",
                    "current_path": current_path
                }

            # 获取父目录和目标路径
            parent_dir = os.path.dirname(current_path)
            new_path = os.path.join(parent_dir, original_name)

            # 判断类型（如果未指定）
            if is_directory is None:
                is_directory = os.path.isdir(current_path)

            current_name = os.path.basename(current_path)
            torrent_type = "multi_file" if is_directory else "single_file"

            # 处理单文件种子
            if not is_directory:
                # 单文件：直接重命名
                if os.path.exists(new_path):
                    # 目标文件已存在，先删除
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, os.remove, new_path)
                    logger.info(f"删除已存在的目标文件: {new_path}")

                # 重命名文件
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, os.rename, current_path, new_path)

                logger.info(f"单文件种子还原成功: {current_name} -> {original_name}")

                return {
                    "success": True,
                    "original_path": current_path,
                    "new_path": new_path,
                    "is_directory": False,
                    "current_name": current_name,
                    "restored_name": original_name,
                    "torrent_type": "single_file"
                }

            # 处理多文件种子（文件夹）
            else:
                # 确保目标文件夹存在
                if not os.path.exists(new_path):
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, os.makedirs, new_path, exist_ok=True)
                    logger.info(f"创建目标文件夹: {new_path}")

                # 移动所有文件到目标文件夹
                moved_count = 0
                error_count = 0
                loop = asyncio.get_event_loop()

                try:
                    # 遍历源文件夹中的所有文件和子文件夹
                    entries = await loop.run_in_executor(None, os.listdir, current_path)

                    for entry in entries:
                        src_entry = os.path.join(current_path, entry)
                        dst_entry = os.path.join(new_path, entry)

                        try:
                            # 如果目标已存在，先删除
                            if os.path.exists(dst_entry):
                                if os.path.isdir(dst_entry):
                                    await loop.run_in_executor(None, shutil.rmtree, dst_entry)
                                else:
                                    await loop.run_in_executor(None, os.remove, dst_entry)
                                logger.debug(f"删除已存在的目标: {dst_entry}")

                            # 移动文件或文件夹
                            await loop.run_in_executor(None, os.rename, src_entry, dst_entry)
                            moved_count += 1
                            logger.debug(f"移动文件: {src_entry} -> {dst_entry}")

                        except Exception as e:
                            error_count += 1
                            logger.warning(f"移动文件失败: {src_entry}, 错误: {e}")

                except Exception as e:
                    logger.error(f"遍历源文件夹失败: {current_path}, 错误: {e}")
                    return {
                        "success": False,
                        "error": f"遍历源文件夹失败: {str(e)}",
                        "current_path": current_path
                    }

                # 检查源文件夹是否为空
                try:
                    remaining_entries = await loop.run_in_executor(None, os.listdir, current_path)
                    if not remaining_entries:
                        # 源文件夹为空，删除
                        await loop.run_in_executor(None, os.rmdir, current_path)
                        logger.info(f"删除空的源文件夹: {current_path}")
                    else:
                        logger.warning(
                            f"源文件夹不为空，保留: {current_path}, "
                            f"剩余文件数: {len(remaining_entries)}"
                        )
                except Exception as e:
                    logger.warning(f"检查源文件夹失败: {current_path}, 错误: {e}")

                logger.info(
                    f"多文件种子还原成功: {current_name} -> {original_name}, "
                    f"移动文件数: {moved_count}, 错误数: {error_count}"
                )

                return {
                    "success": True,
                    "original_path": current_path,
                    "new_path": new_path,
                    "is_directory": True,
                    "current_name": current_name,
                    "restored_name": original_name,
                    "torrent_type": "multi_file"
                }

        except Exception as e:
            logger.error(f"还原种子失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "current_path": current_path if 'current_path' in locals() else None
            }
