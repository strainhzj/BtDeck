"""
Transmission删除适配器
提供Transmission下载器的种子删除功能

强制使用缓存连接，不支持创建新连接
"""

from typing import List, Dict, Any, Optional, Tuple
import asyncio
import logging
import os
from app.services.torrent_deletion_service import (
    DownloaderDeleteAdapter,
    DeleteOption,
    SafetyCheckLevel
)

logger = logging.getLogger(__name__)


class TransmissionDeleteAdapter(DownloaderDeleteAdapter):
    """Transmission删除适配器（严格使用缓存连接）"""

    def __init__(self, client=None):
        """
        初始化Transmission适配器

        Args:
            client: 已初始化的transmission_rpc.Client对象（必须从缓存获取）

        Raises:
            ValueError: 如果client为None
        """
        if client is None:
            raise ValueError("TransmissionDeleteAdapter 必须使用缓存的客户端连接")

        self._client = client

    @property
    def client(self):
        """
        获取Transmission客户端实例

        Returns:
            transmission_rpc.Client: 缓存的客户端实例

        Raises:
            ValueError: 如果客户端不存在
        """
        if self._client is None:
            raise ValueError("Transmission客户端连接不存在，下载器可能离线")

        return self._client

    async def delete_torrents(
        self,
        torrent_hashes: List[str],
        delete_option: DeleteOption,
        safety_check_level: SafetyCheckLevel = SafetyCheckLevel.ENHANCED
    ) -> Dict[str, Any]:
        """
        删除Transmission中的种子（公开接口）

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
        内部实现：删除Transmission种子（私有方法）

        注意：此方法为私有方法，仅供TransmissionDeleteAdapter内部使用。
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
            delete_data = delete_option == DeleteOption.DELETE_FILES_AND_TORRENT

            # 使用transmission_rpc.Client删除种子
            try:
                # 批量删除
                for torrent_hash in valid_hashes:
                    try:
                        # 使用transmission_rpc的remove_torrent方法
                        # 注意：参数名是 ids，不是 torrent_id
                        self.client.remove_torrent(
                            ids=torrent_hash,
                            delete_data=delete_data
                        )
                        result["success_hashes"].append(torrent_hash)
                        if delete_data:
                            result["deleted_files"].append(torrent_hash)
                    except Exception as e:
                        result["failed_hashes"][torrent_hash] = str(e)
                        logger.warning(f"删除种子{torrent_hash[:8]}...失败: {str(e)}")

                logger.info(f"成功删除{len(result['success_hashes'])}个Transmission种子，删除文件: {delete_data}")

            except Exception as e:
                logger.error(f"批量删除失败: {str(e)}")

                # 记录所有种子为失败
                for hash_value in valid_hashes:
                    if hash_value not in result["failed_hashes"]:
                        result["failed_hashes"][hash_value] = str(e)

        except Exception as e:
            logger.error(f"删除Transmission种子时发生错误: {str(e)}")

            # 记录所有种子为失败
            for hash_value in torrent_hashes:
                result["failed_hashes"][hash_value] = str(e)

        return result

    async def validate_torrents_exist(self, torrent_hashes: List[str]) -> Dict[str, bool]:
        """
        验证种子是否存在

        Args:
            torrent_hashes: 种子哈希值列表

        Returns:
            Dict[str, bool]: 种子存在性映射 {hash: exists}
        """
        existence_map = {}

        try:
            # 使用transmission_rpc.Client的get_torrents方法
            all_torrents = await asyncio.to_thread(
                self.client.get_torrents
            )

            # 构建已存在种子的hash集合
            existing_hashes = {t.hash_string for t in all_torrents}

            # 检查每个hash是否存在
            for hash_value in torrent_hashes:
                existence_map[hash_value] = hash_value in existing_hashes

        except Exception as e:
            logger.error(f"验证种子存在性失败: {str(e)}")
            # 发生错误时假设所有种子都不存在
            for hash_value in torrent_hashes:
                existence_map[hash_value] = False

        return existence_map

    async def get_torrent_info(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """
        获取种子信息

        Args:
            torrent_hash: 种子哈希值

        Returns:
            Optional[Dict[str, Any]]: 种子信息字典，不存在时返回None
        """
        try:
            # 使用transmission_rpc.Client的get_torrent方法
            torrent = await asyncio.to_thread(
                self.client.get_torrent,
                torrent_hash
            )

            if not torrent:
                return None

            # 转换状态
            status_map = {
                "stopped": "paused",
                "check pending": "checking",
                "checking": "checking",
                "download pending": "downloading",
                "downloading": "downloading",
                "seed pending": "seeding",
                "seeding": "seeding"
            }

            status_value = (torrent.status or "").lower() if hasattr(torrent, "status") else ""
            return {
                "hash": torrent.hash_string,
                "name": torrent.name,
                "size": torrent.total_size,
                "state": status_map.get(status_value, "unknown"),
                "progress": torrent.progress,
                "ratio": torrent.ratio,
                "downloaded": torrent.downloaded_ever,
                "uploaded": torrent.uploaded_ever,
                "download_path": torrent.download_dir,
                "completion_date": torrent.done_date,
                "addition_date": torrent.added_date,
                "category": " ".join(torrent.labels) if torrent.labels else "",
                "tags": ",".join(torrent.labels) if torrent.labels else ""
            }

        except Exception as e:
            logger.error(f"获取种子{torrent_hash}信息失败: {str(e)}")

        return None

    def get_downloader_type(self) -> str:
        """获取下载器类型"""
        return "transmission"

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
        if state in ["downloading", "checking"]:
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
        """
        测试连接

        Returns:
            bool: 连接是否成功
        """
        try:
            # 使用transmission_rpc.Client的session_stats方法测试连接
            await asyncio.to_thread(
                self.client.session_stats
            )
            logger.info("Transmission连接测试成功")
            return True
        except Exception as e:
            logger.error(f"Transmission连接测试失败: {str(e)}")

        return False

    async def get_downloader_info(self) -> Dict[str, Any]:
        """
        获取下载器信息

        Returns:
            Dict[str, Any]: 下载器信息字典
        """
        try:
            # 使用transmission_rpc.Client的get_session方法
            session = await asyncio.to_thread(
                self.client.get_session
            )

            return {
                "version": session.version,
                "rpc_version": session.rpc_version,
                "download_path": session.download_dir,
                "incomplete_path": session.incomplete_dir,
                "max_connections": session.peer_limit_per_torrent,
                "max_upload_slots": session.upload_slots_per_torrent
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
            # 使用transmission_rpc.Client的get_torrents方法
            torrents = await asyncio.to_thread(
                self.client.get_torrents
            )

            # 转换为统一格式
            result = []
            for torrent in torrents:
                # 标准化hash值
                raw_hash = torrent.hash_string
                normalized_hash = self._normalize_hash(raw_hash)

                # 验证hash值有效性
                if not self._is_valid_hash(normalized_hash):
                    logger.warning(f"Transmission返回无效hash值: '{raw_hash}'，已跳过")
                    continue

                result.append({
                    'hash': normalized_hash,
                    'name': torrent.name,
                    'size': torrent.total_size
                })

            logger.info(f"成功从Transmission获取{len(result)}个种子")
            return result

        except Exception as e:
            logger.error(f"获取Transmission种子列表失败: {str(e)}")
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
            # 获取种子信息（包含现有标签）
            torrent = await asyncio.to_thread(
                self.client.get_torrent,
                torrent_hash
            )

            if not torrent:
                return False, f"种子 {torrent_hash} 不存在"

            # 提取现有标签列表
            existing_labels = list(torrent.labels) if torrent.labels else []

            # 追加新标签（自动去重）
            if tag not in existing_labels:
                existing_labels.append(tag)
                logger.debug(f"Transmission标签追加: {torrent_hash}, 原标签: {existing_labels[:-1]}, 新标签: {tag}")
            else:
                logger.info(f"Transmission标签已存在: {torrent_hash}, label: {tag}")
                return True, ""

            # 设置更新后的标签列表
            await asyncio.to_thread(
                self.client.change_torrent,
                ids=[torrent_hash],
                labels=existing_labels
            )

            logger.info(f"Transmission种子 {torrent_hash} 已添加label: {tag}, 完整标签列表: {existing_labels}")
            return True, ""

        except Exception as e:
            error_msg = f"Transmission添加label失败: {str(e)}"
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
            # 获取种子信息
            torrent = await asyncio.to_thread(
                self.client.get_torrent,
                torrent_hash
            )

            if not torrent:
                return False, None, f"种子 {torrent_hash} 不存在"

            # transmission_rpc 返回的文件列表
            # 注意：需要获取种子的文件信息
            torrent_with_files = await asyncio.to_thread(
                self.client.get_torrent,
                torrent_hash,
                arguments=['files']
            )

            files = getattr(torrent_with_files, "files", None)
            if not torrent_with_files or not files:
                return False, None, f"种子 {torrent_hash} 没有文件信息"

            # 提取相对路径列表
            file_list = [f.name for f in files]

            logger.info(
                f"Transmission种子 {torrent_hash} 文件列表获取成功，"
                f"共 {len(file_list)} 个文件"
            )
            return True, file_list, ""

        except Exception as e:
            error_msg = f"获取Transmission种子文件列表失败: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
