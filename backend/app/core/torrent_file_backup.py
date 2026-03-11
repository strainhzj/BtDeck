"""
种子文件备份服务

负责从下载器备份目录读取种子文件，复制到项目备份目录，用于回收站还原功能。
支持qBittorrent和Transmission两种下载器类型。

路径处理：
- 所有路径拼接使用 os.path.join() 和 pathlib.Path，确保跨平台兼容性（Windows/Linux）
- 容器内部路径通过路径映射服务转换为主机路径

备份策略：
1. 优先从下载器备份目录读取种子文件（需要正确配置路径映射）
2. 如果找不到文件，记录WARNING日志并返回错误（不影响同步流程）

注意事项：
- qBittorrent和Transmission均不支持API下载种子文件
- 必须确保路径映射配置正确，能够访问下载器服务器上的种子文件目录
- qBittorrent种子文件目录：/config/qBittorrent/BT_backup/{hash}.torrent
- Transmission种子文件目录：下载目录/.torrents/{hash}.torrent
"""

import os
import shutil
import logging
import tempfile
from typing import Optional, Dict, Any
from pathlib import Path

from app.core.filename_utils import FilenameUtils
from app.core.path_mapping import PathMappingService

logger = logging.getLogger(__name__)


class TorrentFileBackupService:
    """种子文件备份服务"""

    # 默认备份目录（如果环境变量未设置）
    DEFAULT_BACKUP_DIR = "backup/torrents"

    # qBittorrent种子文件备份目录（相对路径）
    QB_BACKUP_DIR = "/config/qBittorrent/BT_backup"

    # Transmission种子文件存储目录（相对于下载目录）
    TR_BACKUP_DIR = ".torrents"

    def __init__(
        self,
        backup_dir: Optional[str] = None,
        path_mapping_service: Optional[PathMappingService] = None
    ):
        """
        初始化备份服务

        Args:
            backup_dir: 备份目录路径（优先级高于环境变量）
            path_mapping_service: 路径映射服务（可选）
        """
        self.backup_dir = backup_dir or os.environ.get(
            'BACKUP_TORRENT_DIR',
            self.DEFAULT_BACKUP_DIR
        )
        self.path_mapping_service = path_mapping_service

        # 确保备份目录存在
        FilenameUtils.ensure_directory_exists(self.backup_dir)

    def _get_qbittorrent_backup_path(
        self,
        torrent_hash: str,
        downloader_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        获取qBittorrent种子文件的备份路径

        Args:
            torrent_hash: 种子哈希值
            downloader_config: 下载器配置

        Returns:
            种子文件路径（如果存在）或None
        """
        try:
            # 构建qBittorrent备份文件路径
            backup_filename = f"{torrent_hash}.torrent"
            backup_path = os.path.join(self.QB_BACKUP_DIR, backup_filename)

            # 如果有路径映射服务，尝试转换路径
            if self.path_mapping_service:
                # 将内部路径转换为外部路径
                backup_path = self.path_mapping_service.internal_to_external(backup_path)

            # 检查文件是否存在
            if os.path.exists(backup_path):
                return backup_path

            logger.warning(f"qBittorrent种子文件不存在: {backup_path}")
            return None

        except Exception as e:
            logger.error(f"获取qBittorrent种子文件路径失败: {e}")
            return None

    def _get_transmission_backup_path(
        self,
        torrent_hash: str,
        save_path: str,
        downloader_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        获取Transmission种子文件的备份路径

        优先级：
        1. 使用Torrent对象的torrent_file属性（最准确）
        2. 尝试下载目录的.torrents子目录
        3. 尝试下载目录上级的.torrents目录

        Args:
            torrent_hash: 种子哈希值
            save_path: 保存路径
            downloader_config: 下载器配置（包含torrent_file_path）

        Returns:
            种子文件路径（如果存在）或None
        """
        try:
            # 修复P1-1: 优先方案使用Torrent对象提供的torrent_file路径（最准确）
            torrent_file_path = downloader_config.get('torrent_file_path', '未提供')
            if torrent_file_path and torrent_file_path != '未提供':
                logger.debug(f"Transmission torrent_file原始路径: {torrent_file_path}")

                # 如果有路径映射服务，尝试转换路径
                if self.path_mapping_service:
                    converted_path = self.path_mapping_service.internal_to_external(torrent_file_path)
                    if converted_path != torrent_file_path:
                        logger.debug(f"路径映射转换: {torrent_file_path} -> {converted_path}")
                        torrent_file_path = converted_path
                    else:
                        logger.debug(f"路径映射未匹配，使用原路径: {torrent_file_path}")
                else:
                    logger.debug("未配置路径映射服务，使用原路径")

                # 检查文件是否存在
                if os.path.exists(torrent_file_path):
                    logger.debug(f"✓ 找到种子文件: {torrent_file_path}")
                    return torrent_file_path
                else:
                    logger.debug(f"torrent_file路径不存在，尝试备用路径: {torrent_file_path}")

            # 备用方案1：下载目录的.torrents子目录
            backup_filename = f"{torrent_hash}.torrent"
            backup_dir = os.path.join(save_path, self.TR_BACKUP_DIR)
            backup_path = os.path.join(backup_dir, backup_filename)

            logger.debug(f"备用路径1（下载目录/.torrents）: {backup_path}")

            # 如果有路径映射服务，尝试转换路径
            if self.path_mapping_service:
                backup_path = self.path_mapping_service.internal_to_external(backup_path)

            # 检查文件是否存在
            if os.path.exists(backup_path):
                logger.debug(f"✓ 找到种子文件（备用路径1）: {backup_path}")
                return backup_path

            # 备用方案2：下载目录上级的.torrents目录
            backup_path_alt = os.path.join(
                os.path.dirname(save_path),
                ".torrents",
                backup_filename
            )
            logger.debug(f"备用路径2（上级目录/.torrents）: {backup_path_alt}")

            if self.path_mapping_service:
                backup_path_alt = self.path_mapping_service.internal_to_external(
                    backup_path_alt
                )

            if os.path.exists(backup_path_alt):
                logger.info(f"✓ 找到种子文件（备用路径2）: {backup_path_alt}")
                return backup_path_alt

            # 所有路径都失败，输出详细警告
            logger.warning(
                f"❌ Transmission种子文件查找失败:\n"
                f"  - torrent_file路径: {torrent_file_path}\n"
                f"  - 备用路径1: {backup_path}\n"
                f"  - 备用路径2: {backup_path_alt}\n"
                f"提示：请检查路径映射配置，确保能访问Transmission服务器上的种子文件目录"
            )
            return None

        except Exception as e:
            logger.error(f"获取Transmission种子文件路径失败: {e}")
            return None

    def backup_torrent_file(
        self,
        info_id: str,
        torrent_hash: str,
        torrent_name: str,
        downloader_type: str,
        save_path: Optional[str] = None,
        downloader_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        备份种子文件到项目备份目录

        备份策略（按下载器类型）：

        **qBittorrent**:
        1. 从qBittorrent备份目录读取种子文件（/config/qBittorrent/BT_backup/）
        2. 如果找不到，记录WARNING日志并返回错误（不支持API下载）
           - 需要配置正确的路径映射（容器路径 → 主机路径）
           - 确保主机可访问qBittorrent服务器上的种子文件目录

        **Transmission**:
        1. 从文件系统路径读取种子文件
        2. 如果找不到，记录WARNING日志并返回错误（RPC协议不支持API下载）
           - 需要配置正确的路径映射
           - 确保主机可访问Transmission服务器上的种子文件目录

        Args:
            info_id: 种子信息ID
            torrent_hash: 种子哈希值
            torrent_name: 种子名称
            downloader_type: 下载器类型（qbittorrent/transmission）
            save_path: 保存路径（Transmission需要）
            downloader_config: 下载器配置

        Returns:
            操作结果字典
            {
                "success": bool,
                "backup_file_path": str,  # 备份文件路径
                "source_path": str,  # 源文件路径
                "error_message": Optional[str]
            }
        """
        result = {
            "success": False,
            "backup_file_path": "",
            "source_path": "",
            "error_message": None
        }

        source_path = None

        try:
            # 1. 获取源文件路径（优先使用用户配置的种子保存目录）
            torrent_save_path = downloader_config.get('torrent_save_path') if downloader_config else None
            
            if torrent_save_path and torrent_save_path.strip():
                # 直接使用用户配置的种子保存目录
                source_path = torrent_save_path
                # 构建完整的种子文件路径
                source_path = os.path.join(source_path, f"{torrent_hash}.torrent")
                
                if os.path.exists(source_path):
                    result["source_path"] = source_path
                    logger.debug(f"使用用户配置的种子保存目录: {source_path}")
                else:
                    result["error_message"] = f"种子文件不存在于配置的目录: {source_path}"
                    logger.warning(result["error_message"])
                    return result
            else:
                # 回退到原有的默认路径逻辑
                if downloader_type == 'qbittorrent':
                    source_path = self._get_qbittorrent_backup_path(
                        torrent_hash,
                        downloader_config or {}
                    )
                elif downloader_type == 'transmission':
                    source_path = self._get_transmission_backup_path(
                        torrent_hash,
                        save_path or "",
                        downloader_config or {}
                    )
                else:
                    result["error_message"] = f"不支持的下载器类型: {downloader_type}"
                    return result

            # 2. 降级策略：如果找不到文件，根据下载器类型处理
            if not source_path:
                if downloader_type == 'qbittorrent':
                    # qBittorrent不支持API下载种子文件，直接返回错误
                    result["error_message"] = (
                        f"qBittorrent种子文件路径未找到，且不支持API下载。\n"
                        f"请确保：\n"
                        f"1. qBittorrent服务器上的种子文件目录可访问\n"
                        f"2. 路径映射配置正确（容器路径 → 主机路径）\n"
                        f"3. 种子文件确实存在于预期位置（{self.QB_BACKUP_DIR}）"
                    )
                    return result

                elif downloader_type == 'transmission':
                    # Transmission不支持API下载种子文件，直接返回错误
                    result["error_message"] = (
                        f"Transmission种子文件路径未找到，且RPC协议不支持API下载。\n"
                        f"请确保：\n"
                        f"1. Transmission服务器上的种子文件目录可访问\n"
                        f"2. 路径映射配置正确（容器路径 → 主机路径）\n"
                        f"3. 种子文件确实存在于预期位置"
                    )
                    return result

                else:
                    result["error_message"] = f"不支持的下载器类型: {downloader_type}"
                    return result
            else:
                result["source_path"] = source_path

            # 3. 生成备份文件名
            backup_filename = FilenameUtils.generate_backup_filename(
                info_id,
                torrent_name
            )

            # 4. 构建备份文件路径
            backup_path = FilenameUtils.safe_path_join(
                self.backup_dir,
                backup_filename
            )

            # 检查路径长度
            if FilenameUtils.is_path_too_long(backup_path):
                logger.error(f"备份路径过长: {len(backup_path)} 字符")
                result["error_message"] = "备份路径过长"
                return result

            # 修复P1-2: 如果文件已存在，先删除（处理竞争条件）
            try:
                os.remove(backup_path)
                logger.debug(f"删除已存在的备份文件: {backup_path}")
            except FileNotFoundError:
                # 文件不存在，无需删除
                logger.debug(f"备份文件不存在，无需删除: {backup_path}")
            except PermissionError as e:
                logger.error(f"无权限删除备份文件: {backup_path}, 错误: {e}")
                result["error_message"] = f"无权限删除备份文件: {str(e)}"
                return result
            except Exception as e:
                logger.error(f"删除备份文件失败: {backup_path}, 错误: {e}")
                result["error_message"] = f"删除备份文件失败: {str(e)}"
                return result

            # 6. 复制文件
            shutil.copy2(source_path, backup_path)
            logger.debug(
                f"种子文件备份成功: {source_path} -> {backup_path}"
            )

            result["success"] = True
            result["backup_file_path"] = backup_path
            return result

        except Exception as e:
            error_msg = f"备份种子文件失败: {str(e)}"
            logger.error(error_msg)
            result["error_message"] = error_msg
            return result

    def backup_torrent_file_from_path(
        self,
        info_id: str,
        torrent_name: str,
        source_file_path: str
    ) -> Dict[str, Any]:
        """
        从指定路径备份种子文件

        用于直接从文件路径备份种子文件到项目备份目录。

        Args:
            info_id: 种子信息ID
            torrent_name: 种子名称
            source_file_path: 源文件路径

        Returns:
            操作结果字典
        """
        result = {
            "success": False,
            "backup_file_path": "",
            "source_path": source_file_path,
            "error_message": None
        }

        try:
            # 检查源文件是否存在
            if not os.path.exists(source_file_path):
                result["error_message"] = "源文件不存在"
                return result

            # 生成备份文件名
            backup_filename = FilenameUtils.generate_backup_filename(
                info_id,
                torrent_name
            )

            # 构建备份文件路径
            backup_path = FilenameUtils.safe_path_join(
                self.backup_dir,
                backup_filename
            )

            # 检查路径长度
            if FilenameUtils.is_path_too_long(backup_path):
                logger.error(f"备份路径过长: {len(backup_path)} 字符")
                result["error_message"] = "备份路径过长"
                return result

            # 如果文件已存在，先删除
            if os.path.exists(backup_path):
                os.remove(backup_path)

            # 复制文件
            shutil.copy2(source_file_path, backup_path)
            logger.debug(
                f"种子文件备份成功: {source_file_path} -> {backup_path}"
            )

            result["success"] = True
            result["backup_file_path"] = backup_path
            return result

        except Exception as e:
            error_msg = f"从路径备份种子文件失败: {str(e)}"
            logger.error(error_msg)
            result["error_message"] = error_msg
            return result

    def _download_from_qb_api(
        self,
        torrent_hash: str,
        downloader_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        [已废弃] 从qBittorrent API下载种子文件到临时文件

        .. deprecated::
            此方法已废弃，不再使用API下载种子文件。
            qBittorrent和Transmission都要求通过文件系统访问种子文件，
            需要正确配置路径映射服务。

        Args:
            torrent_hash: 种子哈希值
            downloader_config: 下载器配置（包含host, port, username, password）

        Returns:
            临时文件路径或None（始终返回None）
        """
        logger.warning(
            f"_download_from_qb_api方法已废弃，不再支持API下载种子文件。"
            f"请确保路径映射配置正确，可直接访问qBittorrent的种子文件目录。"
            f"种子哈希: {torrent_hash}"
        )
        return None

    def backup_torrent_file_from_downloader_save_path(
        self,
        info_id: str,
        torrent_hash: str,
        torrent_name: str,
        downloader_save_path: str
    ) -> Dict[str, Any]:
        """
        从下载器配置的种子保存目录备份种子文件

        种子文件路径规则: {downloader_save_path}/{torrent_hash}.torrent

        Args:
            info_id: 种子信息ID
            torrent_hash: 种子哈希值
            torrent_name: 种子名称
            downloader_save_path: 下载器配置的种子保存目录路径（绝对路径）

        Returns:
            操作结果字典
            {
                "success": bool,
                "backup_file_path": str,  # 备份文件路径
                "source_path": str,  # 源文件路径
                "error_message": Optional[str]
            }
        """
        result = {
            "success": False,
            "backup_file_path": "",
            "source_path": "",
            "error_message": None
        }

        try:
            # 验证 downloader_save_path 不为空
            if not downloader_save_path or not downloader_save_path.strip():
                result["error_message"] = "下载器种子保存目录未配置（torrent_save_path为空）"
                logger.warning(result["error_message"])
                return result

            # 构建种子文件完整路径
            source_path = os.path.join(downloader_save_path, f"{torrent_hash}.torrent")
            logger.debug(f"尝试从下载器保存目录备份种子文件: {source_path}")

            # 检查源文件是否存在
            if not os.path.exists(source_path):
                result["error_message"] = (
                    f"种子文件不存在于下载器保存目录: {source_path}\n"
                    f"请检查：\n"
                    f"1. 下载器配置的 torrent_save_path 是否正确\n"
                    f"2. 种子文件是否在该目录下（文件名: {torrent_hash}.torrent）"
                )
                logger.warning(result["error_message"])
                return result

            # 生成备份文件名
            backup_filename = FilenameUtils.generate_backup_filename(
                info_id,
                torrent_name
            )

            # 构建备份文件路径
            backup_path = FilenameUtils.safe_path_join(
                self.backup_dir,
                backup_filename
            )

            # 检查路径长度
            if FilenameUtils.is_path_too_long(backup_path):
                logger.error(f"备份路径过长: {len(backup_path)} 字符")
                result["error_message"] = "备份路径过长"
                return result

            # 如果文件已存在，先删除
            try:
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                    logger.debug(f"删除已存在的备份文件: {backup_path}")
            except PermissionError as e:
                logger.error(f"无权限删除备份文件: {backup_path}, 错误: {e}")
                result["error_message"] = f"无权限删除备份文件: {str(e)}"
                return result
            except Exception as e:
                logger.error(f"删除备份文件失败: {backup_path}, 错误: {e}")
                result["error_message"] = f"删除备份文件失败: {str(e)}"
                return result

            # 复制文件
            shutil.copy2(source_path, backup_path)
            logger.debug(
                f"种子文件备份成功（从下载器保存目录）: {source_path} -> {backup_path}"
            )

            result["success"] = True
            result["backup_file_path"] = backup_path
            result["source_path"] = source_path
            return result

        except Exception as e:
            error_msg = f"从下载器保存目录备份种子文件失败: {str(e)}"
            logger.error(error_msg)
            result["error_message"] = error_msg
            return result

    def delete_backup_file(self, backup_file_path: str) -> bool:
        """
        删除备份文件

        Args:
            backup_file_path: 备份文件路径

        Returns:
            是否成功
        """
        try:
            if os.path.exists(backup_file_path):
                os.remove(backup_file_path)
                logger.debug(f"删除备份文件: {backup_file_path}")
            return True
        except Exception as e:
            logger.error(f"删除备份文件失败: {backup_file_path}, 错误: {e}")
            return False
