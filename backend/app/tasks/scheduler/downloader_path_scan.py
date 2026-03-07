"""
下载器路径扫描任务类

定时扫描 torrent_info 表，发现种子保存路径并自动添加到下载器的路径映射配置中。
同时同步路径信息到 downloader_path_maintenance 表，支持种子转移功能。
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Set, Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo
from app.tasks.models import TaskLogs
from app.core.path_mapping import PathMappingService
from app.core.path_mapping import PathMappingConverter
from app.models.downloader_path_maintenance import DownloaderPathMaintenance

logger = logging.getLogger(__name__)


class DownloaderPathScanTask:
    """下载器路径扫描任务

    定期扫描 torrent_info 表，发现种子保存路径并自动添加到下载器的 path_mapping 配置中。
    采用增量更新策略，只添加新发现的路径。
    """

    # 任务元数据
    name = "下载器路径扫描任务"
    description = "自动扫描种子保存路径并更新到下载器路径映射配置"
    version = "1.0.0"
    author = "btpmanager"
    category = "downloader"

    # 任务配置
    default_interval = 3600  # 默认1小时执行一次
    no_timeout = True        # 不设置超时限制

    def __init__(self):
        """初始化任务"""
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_scan_count = 0  # 总扫描下载器次数
        self.total_new_paths = 0   # 总新增路径数

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行路径扫描任务

        流程：
        1. 查询所有启用的下载器
        2. 对每个下载器：
           - 从 torrent_info 表查询该下载器的所有 save_path
           - 读取现有的 path_mapping 配置
           - 识别新路径（不在现有配置中的）
           - 如果有新路径，更新 path_mapping
           - 如果有路径映射规则，更新所有路径的 external 字段
        3. 记录执行日志到 task_logs 表

        Args:
            **kwargs: 任务参数（可选）

        Returns:
            任务执行结果字典
        """
        start_time = datetime.now()
        self.last_execution_time = start_time
        self.execution_count += 1

        # 记录任务开始
        result = {
            "task_name": self.name,
            "execution_time": start_time,
            "execution_count": self.execution_count,
            "status": "running",
            "message": "下载器路径扫描任务开始"
        }

        try:
            async with AsyncSessionLocal() as db:
                # 查询所有启用的下载器
                downloader_result = await db.execute(
                    select(BtDownloaders).where(
                        BtDownloaders.enabled == True,
                        BtDownloaders.dr == 0
                    )
                )
                downloaders = downloader_result.scalars().all()

                if not downloaders:
                    logger.warning("没有找到启用的下载器")
                    result.update({
                        "status": "success",
                        "message": "没有找到启用的下载器",
                        "total_downloaders": 0,
                        "processed_downloaders": 0,
                        "new_paths_added": 0,
                        "updated_external_count": 0,
                        "details": []
                    })
                    self.success_count += 1
                    return result

                # 扫描结果
                total_downloaders = len(downloaders)
                processed_downloaders = 0
                total_new_paths = 0
                total_updated_external = 0
                details = []

                for downloader in downloaders:
                    try:
                        # 扫描单个下载器的路径
                        scan_result = await self._scan_downloader_paths(
                            db, downloader
                        )

                        processed_downloaders += 1
                        total_new_paths += scan_result["new_paths_count"]
                        total_updated_external += scan_result.get("updated_external_count", 0)

                        details.append({
                            "downloader_id": downloader.downloader_id,
                            "downloader_name": downloader.nickname,
                            "total_paths": scan_result["total_paths"],
                            "existing_mappings": scan_result["existing_mappings"],
                            "new_paths": scan_result["new_paths_count"],
                            "new_paths_list": scan_result["new_paths_list"],
                            "updated_external_count": scan_result.get("updated_external_count", 0)
                        })

                        logger.info(
                            f"下载器 {downloader.nickname} 扫描完成: "
                            f"发现 {scan_result['new_paths_count']} 个新路径, "
                            f"更新 {scan_result.get('updated_external_count', 0)} 个 external 字段"
                        )

                    except Exception as e:
                        logger.error(
                            f"扫描下载器 {downloader.nickname} 时出错: {str(e)}",
                            exc_info=True
                        )
                        details.append({
                            "downloader_id": downloader.downloader_id,
                            "downloader_name": downloader.nickname,
                            "error": str(e)
                        })

                # 更新统计信息
                self.total_scan_count += total_downloaders
                self.total_new_paths += total_new_paths
                self.success_count += 1

                # 构建消息
                message_parts = [f"路径扫描完成"]
                if total_new_paths > 0:
                    message_parts.append(f"共发现 {total_new_paths} 个新路径")
                if total_updated_external > 0:
                    message_parts.append(f"更新 {total_updated_external} 个路径的 external 字段")
                
                result.update({
                    "status": "success",
                    "message": ", ".join(message_parts),
                    "total_downloaders": total_downloaders,
                    "processed_downloaders": processed_downloaders,
                    "new_paths_added": total_new_paths,
                    "updated_external_count": total_updated_external,
                    "details": details,
                    "success_count": self.success_count,
                    "failure_count": self.failure_count
                })

                # 记录任务日志到 task_logs 表
                await self._log_task_execution(
                    db, start_time, datetime.now(), True, result
                )

                return result

        except Exception as e:
            self.failure_count += 1
            error_result = {
                "task_name": self.name,
                "execution_time": start_time,
                "execution_count": self.execution_count,
                "status": "failed",
                "message": f"路径扫描任务失败: {str(e)}",
                "success_count": self.success_count,
                "failure_count": self.failure_count
            }

            logger.error(f"路径扫描任务执行失败: {str(e)}", exc_info=True)

            # 尝试记录失败日志
            try:
                async with AsyncSessionLocal() as db:
                    await self._log_task_execution(
                        db, start_time, datetime.now(), False, error_result
                    )
            except Exception as log_error:
                logger.error(f"记录任务日志失败: {str(log_error)}")

            return error_result

    async def _scan_downloader_paths(
        self, db: AsyncSession, downloader: BtDownloaders
    ) -> Dict[str, Any]:
        """
        扫描单个下载器的路径

        Args:
            db: 数据库会话
            downloader: 下载器模型实例

        Returns:
            扫描结果字典
        """
        # 1. 查询该下载器的所有种子保存路径
        torrent_result = await db.execute(
            select(TorrentInfo.save_path).where(
                TorrentInfo.downloader_id == downloader.downloader_id,
                TorrentInfo.dr == 0  # 只查询未删除的记录
            ).distinct()
        )
        paths = [row[0] for row in torrent_result.all() if row[0]]

        if not paths:
            # 没有种子的下载器，不生成配置（保持 path_mapping 为 NULL）
            return {
                "total_paths": 0,
                "existing_mappings": 0,
                "new_paths_count": 0,
                "new_paths_list": [],
                "updated_external_count": 0
            }

        # 2. 标准化路径
        path_service = PathMappingService()
        normalized_paths: Set[str] = set()
        for path in paths:
            normalized_path = path_service._normalize_path(path)
            if normalized_path:
                normalized_paths.add(normalized_path)

        # 3. 读取现有的 path_mapping 配置
        existing_mappings = []
        existing_paths = set()
        default_mapping = None

        if downloader.path_mapping:
            try:
                mapping_service = PathMappingService(downloader.path_mapping)
                existing_mappings = mapping_service.mappings.copy()
                default_mapping = mapping_service.default_mapping

                # 提取现有路径的 internal 字段
                for mapping in existing_mappings:
                    internal_path = mapping.get("internal", "")
                    if internal_path:
                        existing_paths.add(internal_path)
            except Exception as e:
                logger.warning(
                    f"下载器 {downloader.nickname} 的路径映射配置解析失败: {str(e)}"
                )

        # 4. 识别新路径
        new_paths = normalized_paths - existing_paths

        # 5. 检查是否需要更新 external 路径（有转换规则的情况）
        updated_external_count = 0
        if downloader.path_mapping_rules and existing_mappings:
            updated_external_count = await self._update_external_paths(
                db, downloader, existing_mappings
            )

        # 6. 如果有新路径，更新 path_mapping
        if new_paths:
            await self._update_path_mapping(
                db, downloader, new_paths, existing_mappings, default_mapping
            )

        # 7. 如果更新了 external 路径，记录统计
        if updated_external_count > 0:
            logger.info(
                f"下载器 {downloader.nickname} 更新了 {updated_external_count} 个路径的 external 字段"
            )

        # 8. 同步路径信息到 downloader_path_maintenance 表
        await self._sync_to_maintenance_table(
            db, downloader, normalized_paths
        )

        return {
            "total_paths": len(normalized_paths),
            "existing_mappings": len(existing_mappings),
            "new_paths_count": len(new_paths),
            "new_paths_list": sorted(list(new_paths)),
            "updated_external_count": updated_external_count
        }

    async def _update_path_mapping(
        self,
        db: AsyncSession,
        downloader: BtDownloaders,
        new_paths: Set[str],
        existing_mappings: List[Dict],
        default_mapping: Optional[str]
    ):
        """
        更新下载器的路径映射配置

        保留现有映射，追加新发现的路径，设置第一个映射为默认映射。

        Args:
            db: 数据库会话
            downloader: 下载器模型实例
            new_paths: 新发现的路径集合
            existing_mappings: 现有映射列表（完整映射对象）
            default_mapping: 当前默认映射名称
        """
        try:
            # 保留现有映射
            mappings = existing_mappings.copy()

            # 加载路径转换规则
            converter = None
            converted_count = 0
            if downloader.path_mapping_rules:
                try:
                    converter = PathMappingConverter(downloader.path_mapping_rules)
                    if converter.is_enabled():
                        logger.info(f"下载器 {downloader.nickname} 已启用路径转换规则")
                    else:
                        converter = None
                except Exception as e:
                    logger.warning(f"路径转换规则加载失败: {str(e)}")
                    converter = None

            # 添加新路径映射
            discovery_count = 1
            downloader_name = downloader.nickname or downloader.downloader_id
            for path in sorted(new_paths):
                # 生成映射名称（包含下载器名称）
                mapping_name = f"{downloader_name}-自动发现-路径{discovery_count:03d}"
                discovery_count += 1

                # 判断路径类型（简单的启发式判断）
                if path.startswith("/downloads/") or path.startswith("/mnt/"):
                    mapping_type = "docker"
                elif path.startswith("//") or path.startswith("\\\\"):
                    mapping_type = "network"
                elif path.startswith("/volume"):
                    mapping_type = "nas"
                else:
                    mapping_type = "local"

                # 应用路径转换规则
                external_path = ""
                if converter:
                    converted = converter.convert(path)
                    if converted:
                        external_path = converted
                        converted_count += 1
                        logger.info(f"路径转换: {path} -> {external_path}")

                new_mapping = {
                    "name": mapping_name,
                    "description": f"系统自动发现于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "internal": path,
                    "external": external_path,  # 使用转换后的路径
                    "mapping_type": mapping_type,
                }
                mappings.append(new_mapping)

            # 设置默认映射：如果不存在，则使用第一个映射
            if not default_mapping and mappings:
                default_mapping = mappings[0]["name"]

            # 更新 discovery_stats
            discovery_stats = {
                "last_discovery_time": datetime.now().isoformat(),
                "total_paths": len(mappings),
                "auto_discovered_count": len(new_paths)
            }

            # 构建新配置
            new_config = {
                "mappings": mappings,
                "discovery_stats": discovery_stats,
                "default_mapping": default_mapping  # ✅ 总是包含该字段
            }

            # 更新数据库
            await db.execute(
                update(BtDownloaders)
                .where(BtDownloaders.downloader_id == downloader.downloader_id)
                .values(path_mapping=json.dumps(new_config, ensure_ascii=False))
            )
            await db.commit()

            logger.info(
                f"下载器 {downloader.nickname} 路径映射已更新: "
                f"现有 {len(existing_mappings)} 个，新增 {len(new_paths)} 个，"
                f"转换 {converted_count} 个路径，"
                f"默认映射: {default_mapping}"
            )

        except Exception as e:
            logger.error(f"更新路径映射配置失败: {str(e)}", exc_info=True)
            raise

    async def _update_external_paths(
        self,
        db: AsyncSession,
        downloader: BtDownloaders,
        existing_mappings: List[Dict]
    ) -> int:
        """
        更新现有映射的 external 路径
        
        对所有已有的路径映射重新应用转换规则，生成新的 external 路径。
        完全覆盖现有的 external 字段。
        
        Args:
            db: 数据库会话
            downloader: 下载器模型实例
            existing_mappings: 现有映射列表（会被修改）
            
        Returns:
            更新的映射数量
        """
        try:
            # 加载路径转换规则
            converter = None
            if not downloader.path_mapping_rules:
                return 0
                
            try:
                converter = PathMappingConverter(downloader.path_mapping_rules)
                if not converter.is_enabled():
                    logger.info(f"下载器 {downloader.nickname} 路径转换规则未启用")
                    return 0
            except Exception as e:
                logger.warning(f"路径转换规则加载失败: {str(e)}")
                return 0
            
            # 更新所有映射的 external 字段
            updated_count = 0
            for mapping in existing_mappings:
                internal_path = mapping.get("internal", "")
                if not internal_path:
                    continue
                
                # 应用转换规则
                converted = converter.convert(internal_path)
                if converted:
                    # 更新 external 字段（完全覆盖）
                    old_external = mapping.get("external", "")
                    mapping["external"] = converted
                    updated_count += 1
                    
                    # 记录变更
                    if old_external != converted:
                        logger.debug(
                            f"路径映射更新: {mapping.get('name')} "
                            f"{internal_path} -> {converted} "
                            f"(原: {old_external})"
                        )
            
            # 如果有更新，保存到数据库
            if updated_count > 0:
                # 读取当前配置以保留其他字段
                mapping_service = PathMappingService(downloader.path_mapping)
                default_mapping = mapping_service.default_mapping
                
                # 构建新配置
                new_config = {
                    "mappings": existing_mappings,
                    "discovery_stats": mapping_service.mappings[0].get("discovery_stats", {}) if mapping_service.mappings else {},
                    "default_mapping": default_mapping
                }
                
                # 更新数据库
                await db.execute(
                    update(BtDownloaders)
                    .where(BtDownloaders.downloader_id == downloader.downloader_id)
                    .values(path_mapping=json.dumps(new_config, ensure_ascii=False))
                )
                await db.commit()
                
                logger.info(
                    f"下载器 {downloader.nickname} 更新了 {updated_count} 个路径映射的 external 字段"
                )
            
            return updated_count
            
        except Exception as e:
            logger.error(f"更新 external 路径失败: {str(e)}", exc_info=True)
            return 0

    async def _log_task_execution(
        self,
        db: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        success: bool,
        result: Dict[str, Any]
    ):
        """
        记录任务执行日志到 task_logs 表

        Args:
            db: 数据库会话
            start_time: 开始时间
            end_time: 结束时间
            success: 是否成功
            result: 执行结果
        """
        try:
            duration = int((end_time - start_time).total_seconds())

            # 构建日志详情
            log_detail = json.dumps(
                result, ensure_ascii=False, default=str
            )[:2000]  # 限制长度

            task_log = TaskLogs(
                task_name=self.name,
                task_type=4,  # Python内部类
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=success,
                log_detail=log_detail
            )

            db.add(task_log)
            await db.commit()

        except Exception as e:
            logger.error(f"记录任务日志失败: {str(e)}", exc_info=True)
            raise

    def get_task_info(self) -> Dict[str, Any]:
        """获取任务信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_scan_count": self.total_scan_count,
            "total_new_paths": self.total_new_paths,
            "last_execution_time": self.last_execution_time,
            "success_rate": (
                self.success_count / self.execution_count * 100
                if self.execution_count > 0 else 0
            )
        }

    def get_schedule_config(self) -> Dict[str, Any]:
        """获取调度配置建议"""
        return {
            "cron_expression": "0 * * * *",  # 每小时执行一次
            "timezone": "Asia/Shanghai",
            "max_instances": 1,     # 防止重叠执行
            "coalesce": True,       # 合并错过的执行
            "misfire_grace_time": 900,  # 错过执行的宽限时间（15分钟）
            "default_interval": self.default_interval,
            "no_timeout": self.no_timeout,
            "estimated_duration": "Variable (no timeout limit)"
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if self.execution_count == 0:
            return {
                "average_scan_per_execution": 0,
                "average_new_paths_per_execution": 0,
                "total_processing_time": "N/A"
            }

        return {
            "average_scan_per_execution": (
                self.total_scan_count / self.execution_count
            ),
            "average_new_paths_per_execution": (
                self.total_new_paths / self.execution_count
            ),
            "task_reliability": (
                self.success_count / self.execution_count * 100
            )
        }

    async def _sync_to_maintenance_table(
        self,
        db: AsyncSession,
        downloader: BtDownloaders,
        normalized_paths: Set[str]
    ):
        """
        同步路径信息到 downloader_path_maintenance 表

        支持种子转移功能，提供默认路径和在用路径的维护。

        Args:
            db: 数据库会话
            downloader: 下载器模型实例
            normalized_paths: 标准化后的路径集合
        """
        try:
            # 1. 获取下载器客户端以获取默认路径
            default_path = await self._get_default_path_from_downloader(downloader)

            if not default_path and normalized_paths:
                # 如果无法从下载器获取默认路径，使用出现次数最多的路径
                path_count_result = await db.execute(
                    select(
                        TorrentInfo.save_path,
                        func.count(TorrentInfo.hash).label('count')
                    ).where(
                        TorrentInfo.downloader_id == downloader.downloader_id,
                        TorrentInfo.dr == 0
                    ).group_by(TorrentInfo.save_path).order_by(
                        func.count(TorrentInfo.hash).desc()
                    ).limit(1)
                )
                first_path = path_count_result.first()
                if first_path:
                    default_path = first_path[0]
                    logger.info(
                        f"下载器 {downloader.nickname} 使用统计得出的默认路径: {default_path}"
                    )

            # 2. 同步默认路径
            if default_path:
                await self._sync_default_path(db, downloader.downloader_id, default_path)

            # 3. 统计每个路径的种子数量
            # 注意：这里查询所有路径（不过滤），因为 save_path 存储的是原始路径
            # 而传入的 normalized_paths 是标准化后的路径（带尾部斜杠），不能直接匹配
            path_count_result = await db.execute(
                select(
                    TorrentInfo.save_path,
                    func.count(TorrentInfo.hash).label('count')
                ).where(
                    TorrentInfo.downloader_id == downloader.downloader_id,
                    TorrentInfo.dr == 0
                ).group_by(TorrentInfo.save_path)
            )

            path_counts = {row[0]: row[1] for row in path_count_result.all()}

            # 4. 同步所有在用路径
            for path_value, torrent_count in path_counts.items():
                await self._sync_active_path(
                    db, downloader.downloader_id, path_value, torrent_count
                )

            # 5. 清理不再使用的路径（可选，标记为禁用）
            await self._cleanup_obsolete_paths(
                db, downloader.downloader_id, set(path_counts.keys())
            )

            logger.info(
                f"下载器 {downloader.nickname} 路径同步完成: "
                f"默认路径={default_path}, 在用路径={len(path_counts)}个"
            )

        except Exception as e:
            logger.error(
                f"同步下载器 {downloader.nickname} 到 maintenance 表失败: {str(e)}",
                exc_info=True
            )

    async def _get_default_path_from_downloader(
        self, downloader: BtDownloaders
    ) -> Optional[str]:
        """
        从下载器客户端获取默认保存路径

        Args:
            downloader: 下载器模型实例

        Returns:
            默认保存路径，获取失败返回 None
        """
        try:
            # 从缓存获取下载器客户端
            from app.main import app

            # 检查 app.state.store 是否可用
            if not hasattr(app.state, 'store') or app.state.store is None:
                logger.warning(f"下载器缓存 store 不可用，跳过从客户端获取默认路径")
                return None

            cached_downloaders = await app.state.store.get_snapshot()

            downloader_vo = next(
                (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
                None
            )

            if not downloader_vo or not downloader_vo.client:
                logger.warning(f"下载器 {downloader.nickname} 客户端不可用")
                return None

            client = downloader_vo.client

            # 根据下载器类型获取默认路径
            if downloader_vo.downloader_type == 0:  # qBittorrent
                try:
                    default_path = client.app_default_save_path()
                    logger.debug(f"qBittorrent 默认路径: {default_path}")
                    return default_path
                except Exception as e:
                    logger.warning(f"从 qBittorrent 获取默认路径失败: {str(e)}")
                    return None

            elif downloader_vo.downloader_type == 1:  # Transmission
                try:
                    response = client.get_session_variables()
                    if response and 'download-dir' in response:
                        default_path = response['download-dir']
                        logger.debug(f"Transmission 默认路径: {default_path}")
                        return default_path
                    logger.warning("Transmission 响应中未找到 download-dir 字段")
                    return None
                except Exception as e:
                    logger.warning(f"从 Transmission 获取默认路径失败: {str(e)}")
                    return None

            else:
                logger.warning(f"不支持的下载器类型: {downloader_vo.downloader_type}")
                return None

        except Exception as e:
            logger.warning(f"获取下载器 {downloader.nickname} 默认路径时出错: {str(e)}，将使用统计方法获取默认路径")
            return None

    async def _sync_default_path(
        self,
        db: AsyncSession,
        downloader_id: int,
        default_path: str
    ):
        """
        同步默认路径到 maintenance 表

        Args:
            db: 数据库会话
            downloader_id: 下载器ID
            default_path: 默认路径
        """
        try:
            # 查找是否已存在默认路径记录
            existing = await db.execute(
                select(DownloaderPathMaintenance).where(
                    DownloaderPathMaintenance.downloader_id == downloader_id,
                    DownloaderPathMaintenance.path_type == 'default'
                )
            )
            existing_record = existing.scalar_one_or_none()

            if existing_record:
                # 更新现有记录
                if existing_record.path_value != default_path:
                    existing_record.path_value = default_path
                    existing_record.last_updated_time = datetime.utcnow()
                    existing_record.updated_at = datetime.utcnow()
                    logger.debug(
                        f"更新下载器 {downloader_id} 的默认路径: {default_path}"
                    )
                else:
                    # 仅更新时间戳
                    existing_record.last_updated_time = datetime.utcnow()
            else:
                # 创建新记录
                new_record = DownloaderPathMaintenance(
                    downloader_id=downloader_id,
                    path_type='default',
                    path_value=default_path,
                    is_enabled=True,
                    torrent_count=0,
                    last_updated_time=datetime.utcnow()
                )
                db.add(new_record)
                logger.debug(
                    f"创建下载器 {downloader_id} 的默认路径: {default_path}"
                )

            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(f"同步默认路径失败: {str(e)}")
            raise

    async def _sync_active_path(
        self,
        db: AsyncSession,
        downloader_id: int,
        path_value: str,
        torrent_count: int
    ):
        """
        同步在用路径到 maintenance 表

        Args:
            db: 数据库会话
            downloader_id: 下载器ID
            path_value: 路径值
            torrent_count: 使用该路径的种子数量
        """
        try:
            # 查找是否已存在该路径记录
            existing = await db.execute(
                select(DownloaderPathMaintenance).where(
                    DownloaderPathMaintenance.downloader_id == downloader_id,
                    DownloaderPathMaintenance.path_type == 'active',
                    DownloaderPathMaintenance.path_value == path_value
                )
            )
            existing_record = existing.scalar_one_or_none()

            if existing_record:
                # 更新种子数量和时间戳
                existing_record.torrent_count = torrent_count
                existing_record.last_updated_time = datetime.utcnow()
                existing_record.updated_at = datetime.utcnow()
                logger.debug(
                    f"更新下载器 {downloader_id} 的在用路径: {path_value}, "
                    f"种子数量: {torrent_count}"
                )
            else:
                # 创建新记录
                new_record = DownloaderPathMaintenance(
                    downloader_id=downloader_id,
                    path_type='active',
                    path_value=path_value,
                    is_enabled=True,
                    torrent_count=torrent_count,
                    last_updated_time=datetime.utcnow()
                )
                db.add(new_record)
                logger.debug(
                    f"创建下载器 {downloader_id} 的在用路径: {path_value}, "
                    f"种子数量: {torrent_count}"
                )

            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(f"同步在用路径失败: {str(e)}")
            raise

    async def _cleanup_obsolete_paths(
        self,
        db: AsyncSession,
        downloader_id: int,
        current_paths: Set[str]
    ):
        """
        清理不再使用的路径（标记为禁用）

        Args:
            db: 数据库会话
            downloader_id: 下载器ID
            current_paths: 当前使用的路径集合
        """
        try:
            # 查找所有在用路径记录
            all_active = await db.execute(
                select(DownloaderPathMaintenance).where(
                    DownloaderPathMaintenance.downloader_id == downloader_id,
                    DownloaderPathMaintenance.path_type == 'active',
                    DownloaderPathMaintenance.is_enabled == True
                )
            )
            all_active_records = all_active.scalars().all()

            # 禁用不再使用的路径
            disabled_count = 0
            for record in all_active_records:
                if record.path_value not in current_paths:
                    record.is_enabled = False
                    record.updated_at = datetime.utcnow()
                    disabled_count += 1
                    logger.debug(
                        f"禁用下载器 {downloader_id} 的废弃路径: {record.path_value}"
                    )

            if disabled_count > 0:
                await db.commit()
                logger.info(
                    f"下载器 {downloader_id} 禁用了 {disabled_count} 个废弃路径"
                )

        except Exception as e:
            await db.rollback()
            logger.error(f"清理废弃路径失败: {str(e)}")
