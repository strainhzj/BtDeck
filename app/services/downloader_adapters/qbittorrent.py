"""
qBittorrent删除适配器
提供qBittorrent下载器的种子删除功能
"""

from typing import List, Dict, Any, Optional, Tuple
import asyncio
import logging
import os
from qbittorrentapi import Client, NotFound404Error, LoginFailed
from app.services.torrent_deletion_service import (
    DownloaderDeleteAdapter,
    DeleteOption,
    SafetyCheckLevel
)
from app.utils.encryption import decrypt_password

logger = logging.getLogger(__name__)


class QBittorrentDeleteAdapter(DownloaderDeleteAdapter):
    """qBittorrent删除适配器"""

    def __init__(self, client: Client = None, host: str = None, username: str = None, password: str = None, port: int = 8080, use_ssl: bool = False):
        """
        初始化qBittorrent适配器

        Args:
            client: 已初始化的qBittorrent客户端对象（优先使用，从缓存获取）
            host: qBittorrent主机地址（仅当client为None时使用）
            username: 用户名（仅当client为None时使用）
            password: 密码（仅当client为None时使用）
            port: 端口号（仅当client为None时使用）
            use_ssl: 是否使用HTTPS（仅当client为None时使用）
        """
        self._client = client
        self.host = host
        self.username = username
        self.encrypted_password = password
        self.port = port
        self.use_ssl = use_ssl
        self._connection_tested = False

    @property
    def client(self) -> Client:
        """获取qBittorrent客户端实例"""
        if self._client:
            # 使用传入的已初始化客户端（从缓存获取）
            return self._client

        # 兼容旧逻辑：如果没有传入client，则创建新的（不推荐）
        if not self._client:
            # 解密密码
            password = decrypt_password(self.encrypted_password)

            # 构建基础URL
            protocol = "https" if self.use_ssl else "http"
            base_url = f"{protocol}://{self.host}:{self.port}/"

            # 创建客户端（移除不支持的REQUESTS_TIMEOUT参数）
            self._client = Client(
                host=base_url,
                username=self.username,
                password=password,
                VERIFY_WEBUI_CERTIFICATE=False  # 跳过SSL证书验证
            )

            # 测试连接
            try:
                self._client.auth.log_in()
                logger.info(f"成功连接到qBittorrent: {base_url}")
                self._connection_tested = True
            except LoginFailed as e:
                logger.error(f"qBittorrent登录失败: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"qBittorrent连接失败: {str(e)}")
                raise

        return self._client

    async def delete_torrents(
        self,
        torrent_hashes: List[str],
        delete_option: DeleteOption,
        safety_check_level: SafetyCheckLevel = SafetyCheckLevel.ENHANCED
    ) -> Dict[str, Any]:
        """
        删除qBittorrent中的种子（公开接口）

        注意：此方法为公开接口，供TorrentDeletionService内部调用。
        外部代码应使用TorrentDeletionService的统一入口，不应直接调用此方法。

        Args:
            torrent_hashes: 种子哈希值列表
            delete_option: 删除选项
            safety_check_level: 安全检查级别

        Returns:
            删除结果字典
        """
        # 委托给私有实现方法
        return await self._delete_torrents_impl(
            torrent_hashes, delete_option, safety_check_level
        )

    async def _delete_torrents_impl(
        self,
        torrent_hashes: List[str],
        delete_option: DeleteOption,
        safety_check_level: SafetyCheckLevel = SafetyCheckLevel.ENHANCED
    ) -> Dict[str, Any]:
        """
        内部实现：删除qBittorrent种子（私有方法）

        注意：此方法为私有方法，仅供QBittorrentDeleteAdapter内部使用。
        外部代码应使用TorrentDeletionService的统一入口。

        Args:
            torrent_hashes: 种子哈希值列表
            delete_option: 删除选项
            safety_check_level: 安全检查级别

        Returns:
            删除结果字典
        """
        result = {
            "success_hashes": [],
            "failed_hashes": {},
            "warnings": [],
            "deleted_files": []
        }

        if not torrent_hashes:
            return result

        try:
            # 验证种子存在
            existing_torrents = await self.validate_torrents_exist(torrent_hashes)
            valid_hashes = [h for h, exists in existing_torrents.items() if exists]

            if not valid_hashes:
                result["warnings"].append("没有找到可删除的有效种子")
                return result

            # 获取种子信息用于安全检查
            for hash_value in valid_hashes:
                try:
                    torrent_info = await self.get_torrent_info(hash_value)
                    if torrent_info:
                        # 执行安全检查
                        safety_warnings = await self._perform_safety_check(
                            torrent_info, delete_option, safety_check_level
                        )
                        result["warnings"].extend(safety_warnings)
                except Exception as e:
                    logger.warning(f"获取种子{hash_value}信息失败: {str(e)}")
                    result["warnings"].append(f"种子{hash_value[:8]}...信息获取失败")

            # 确定删除参数
            delete_files = (delete_option == DeleteOption.DELETE_FILES_AND_TORRENT)
            skip_other_check = (safety_check_level == SafetyCheckLevel.BASIC)

            # 批量删除种子
            try:
                # qBittorrent支持批量删除
                self.client.torrents.delete(
                    hashes=valid_hashes,
                    delete_files=delete_files,
                    skip_other_check=skip_other_check
                )

                # 记录成功删除的种子
                result["success_hashes"] = valid_hashes
                result["deleted_files"] = valid_hashes if delete_files else []

                logger.info(f"成功删除{len(valid_hashes)}个qBittorrent种子，删除文件: {delete_files}")

            except Exception as e:
                logger.error(f"批量删除失败，尝试逐个删除: {str(e)}")

                # 如果批量删除失败，尝试逐个删除
                await self._delete_torrents_individually(
                    valid_hashes, delete_option, safety_check_level, result
                )

        except Exception as e:
            logger.error(f"删除qBittorrent种子时发生错误: {str(e)}")

            # 记录所有种子为失败
            for hash_value in torrent_hashes:
                result["failed_hashes"][hash_value] = str(e)

        return result

    async def _delete_torrents_individually(
        self,
        torrent_hashes: List[str],
        delete_option: DeleteOption,
        safety_check_level: SafetyCheckLevel,
        result: Dict[str, Any]
    ):
        """逐个删除种子（当批量删除失败时使用）"""
        delete_files = (delete_option == DeleteOption.DELETE_FILES_AND_TORRENT)
        skip_other_check = (safety_check_level == SafetyCheckLevel.BASIC)

        for hash_value in torrent_hashes:
            try:
                self.client.torrents.delete(
                    hashes=[hash_value],
                    delete_files=delete_files,
                    skip_other_check=skip_other_check
                )

                result["success_hashes"].append(hash_value)
                if delete_files:
                    result["deleted_files"].append(hash_value)

                logger.info(f"成功删除单个种子: {hash_value[:8]}...")

            except Exception as e:
                error_msg = str(e)
                result["failed_hashes"][hash_value] = error_msg
                logger.warning(f"删除种子{hash_value[:8]}...失败: {error_msg}")

    async def validate_torrents_exist(self, torrent_hashes: List[str]) -> Dict[str, bool]:
        """验证种子是否存在"""
        existence_map = {}

        try:
            # 获取所有种子信息
            all_torrents = self.client.torrents.info()

            # 构建存在性映射
            existing_hashes = {t.hash for t in all_torrents}

            for hash_value in torrent_hashes:
                existence_map[hash_value] = hash_value in existing_hashes

        except Exception as e:
            logger.error(f"验证种子存在性失败: {str(e)}")
            # 发生错误时假设所有种子都不存在
            for hash_value in torrent_hashes:
                existence_map[hash_value] = False

        return existence_map

    async def get_torrent_info(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """获取种子信息"""
        try:
            # 尝试获取单个种子信息
            torrents = self.client.torrents.info(hashes=[torrent_hash])

            if torrents:
                torrent = torrents[0]
                return {
                    "hash": torrent.hash,
                    "name": torrent.name,
                    "size": torrent.size,
                    "state": torrent.state,
                    "progress": torrent.progress,
                    "ratio": torrent.ratio,
                    "downloaded": torrent.downloaded,
                    "uploaded": torrent.uploaded,
                    "download_path": torrent.save_path,
                    "completion_date": torrent.completion_on,
                    "addition_date": torrent.added_on,
                    "category": torrent.category,
                    "tags": torrent.tags
                }
            else:
                return None

        except Exception as e:
            logger.error(f"获取种子{torrent_hash}信息失败: {str(e)}")
            return None

    def get_downloader_type(self) -> str:
        """获取下载器类型"""
        return "qbittorrent"

    async def _perform_safety_check(
        self,
        torrent_info: Dict[str, Any],
        delete_option: DeleteOption,
        safety_check_level: SafetyCheckLevel
    ) -> List[str]:
        """执行安全检查"""
        warnings = []

        if safety_check_level == SafetyCheckLevel.BASIC:
            return warnings

        state = torrent_info.get("state", "").lower()
        progress = torrent_info.get("progress", 0)
        ratio = torrent_info.get("ratio", 0)

        # 检查种子状态
        if state in ["downloading", "pausedDL", "stalledDL", "checking", "queuedDL"]:
            warnings.append(f"种子状态为'{state}'，正在下载或检查中")

        if state == "seeding" and progress >= 1.0:
            warnings.append("种子已完成且正在做种，删除可能影响分享")

        # 检查分享比率
        if ratio < 1.0:
            warnings.append(f"分享比率{ratio:.2f} < 1.0，可能影响分享生态")

        # 检查是否删除文件
        if delete_option == DeleteOption.DELETE_FILES_AND_TORRENT:
            if progress < 1.0:
                warnings.append("种子未下载完成，删除文件可能导致文件不完整")

            # 严格安全检查
            if safety_check_level == SafetyCheckLevel.STRICT:
                size = torrent_info.get("size", 0)
                if size > 50 * 1024 * 1024 * 1024:  # 50GB
                    warnings.append(f"文件较大({size/1024/1024/1024:.1f}GB)，请确认需要删除")

        return warnings

    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            # 尝试获取API版本
            version = self.client.app.version()
            logger.info(f"qBittorrent连接测试成功，版本: {version}")
            return True
        except Exception as e:
            logger.error(f"qBittorrent连接测试失败: {str(e)}")
            return False

    async def get_downloader_info(self) -> Dict[str, Any]:
        """获取下载器信息"""
        try:
            info = self.client.app.preferences()
            return {
                "version": self.client.app.version(),
                "build_info": self.client.app.build_info(),
                "web_api_version": self.client.app.web_api_version(),
                "download_path": info.get("save_path", ""),
                "temp_path": info.get("temp_path", ""),
                "max_connections": info.get("max_conn_per_torrent", 0),
                "max_upload_slots": info.get("max_uploads_per_torrent", 0)
            }
        except Exception as e:
            logger.error(f"获取下载器信息失败: {str(e)}")
            return {}

    async def get_torrents_for_detection(self) -> List[Dict[str, Any]]:
        """
        获取所有种子列表（用于重复检测）

        Returns:
            List[Dict[str, Any]]: 种子列表，每个种子包含:
                - hash: str (标准化后的hash值，小写无空格)
                - name: str (种子名称)
                - size: int (种子大小，字节)
        """
        try:
            # 获取所有种子信息
            all_torrents = self.client.torrents.info()

            # 转换为统一格式
            result = []
            for torrent in all_torrents:
                # 标准化hash值
                raw_hash = torrent.hash
                normalized_hash = self._normalize_hash(raw_hash)

                # 验证hash值有效性
                if not self._is_valid_hash(normalized_hash):
                    logger.warning(f"qBittorrent返回无效hash值: '{raw_hash}'，已跳过")
                    continue

                result.append({
                    'hash': normalized_hash,
                    'name': torrent.name,
                    'size': torrent.size
                })

            logger.info(f"成功从qBittorrent获取{len(result)}个种子")
            return result

        except Exception as e:
            logger.error(f"获取qBittorrent种子列表失败: {str(e)}")
            raise

    def _normalize_hash(self, hash_value: str) -> str:
        """
        标准化hash值

        Args:
            hash_value: 原始hash值

        Returns:
            str: 标准化后的hash值（小写、去除空格）
        """
        if not hash_value:
            return hash_value
        return hash_value.lower().strip()

    def _is_valid_hash(self, hash_value: str) -> bool:
        """
        验证hash值格式

        Args:
            hash_value: 标准化后的hash值

        Returns:
            bool: 是否为有效的40位十六进制hash值
        """
        if not hash_value:
            return False
        # 验证长度为40位且只包含十六进制字符
        return len(hash_value) == 40 and all(c in '0123456789abcdef' for c in hash_value)

    async def add_tag_to_torrent(
        self,
        torrent_hash: str,
        tag: str
    ) -> Tuple[bool, Optional[str]]:
        """
        为种子添加标签（等级4删除使用）

        Args:
            torrent_hash: 种子哈希值
            tag: 要添加的标签

        Returns:
            (成功标志, 错误信息)
        """
        try:
            # 创建标签（如果不存在）
            try:
                self.client.torrent_tags.create_tags(tags=tag)
            except Exception as e:
                # 标签可能已存在,忽略错误
                logger.debug(f"创建标签可能失败(可能已存在): {str(e)}")

            # 为种子添加标签
            self.client.torrents_add_tags(
                torrent_hashes=[torrent_hash],
                tags=[tag]
            )

            logger.info(f"qBittorrent种子 {torrent_hash} 已添加标签: {tag}")
            return True, ""

        except Exception as e:
            error_msg = f"qBittorrent添加标签失败: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    async def create_marker_file(
        self,
        torrent_hash: str,
        torrent_name: str,
        download_path: str
    ) -> Tuple[bool, Optional[str]]:
        """
        创建标记文件（等级3删除使用）

        Args:
            torrent_hash: 种子哈希值
            torrent_name: 种子名称
            download_path: 下载路径

        Returns:
            (成功标志, 错误信息)
        """
        try:
            # 获取种子文件列表
            success, file_list, error_msg = await self.get_torrent_files(torrent_hash)
            if not success:
                return False, f"获取文件列表失败: {error_msg}"

            if not file_list or len(file_list) == 0:
                return False, "种子文件列表为空"

            # 使用第一个文件所在目录作为基准目录
            first_file_path = os.path.join(download_path, file_list[0])
            base_dir = os.path.dirname(first_file_path)

            # 创建标记文件路径：使用种子hash作为文件名
            marker_file_path = os.path.join(base_dir, f".deleteme_{torrent_hash}")

            # 创建标记文件
            with open(marker_file_path, 'w', encoding='utf-8') as f:
                f.write(f"Torrent: {torrent_name}\n")
                f.write(f"Hash: {torrent_hash}\n")
                f.write(f"Download Path: {download_path}\n")
                f.write(f"File Count: {len(file_list)}\n")

            logger.info(f"已创建标记文件: {marker_file_path}")
            return True, ""

        except Exception as e:
            error_msg = f"创建标记文件失败: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    async def get_torrent_files(
        self,
        torrent_hash: str
    ) -> Tuple[bool, Optional[List[str]], Optional[str]]:
        """
        获取种子文件列表（用于验证和记录）

        Args:
            torrent_hash: 种子哈希值

        Returns:
            (成功标志, 文件列表, 错误信息)
        """
        try:
            # 调用 qBittorrent API 获取文件列表
            torrent_files = self.client.torrents.files(torrent_hash=torrent_hash)

            if not torrent_files:
                return False, None, f"种子 {torrent_hash} 没有文件信息"

            # 提取相对路径列表
            file_list = [f.name for f in torrent_files]

            logger.info(
                f"qBittorrent种子 {torrent_hash} 文件列表获取成功，"
                f"共 {len(file_list)} 个文件"
            )
            return True, file_list, ""

        except Exception as e:
            error_msg = f"获取qBittorrent种子文件列表失败: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

    def __del__(self):
        """清理资源"""
        if self._client:
            try:
                self._client.auth.log_out()
            except Exception as e:
                logger.warning(f"登出qBittorrent时发生错误: {str(e)}")