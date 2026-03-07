# -*- coding: utf-8 -*-
"""
种子同步任务基础模块

提供种子信息同步和Tracker同步的公共基础类和工具函数。
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo as trackerInfoModel

logger = logging.getLogger(__name__)


class BaseSyncTask:
    """种子同步任务基类"""

    # 任务元数据
    name = "种子同步基类"
    description = "种子同步任务基类"
    version = "2.0.0"
    author = "btpManager"
    category = "torrent"

    def __init__(self):
        """初始化任务"""
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_processed = 0
        self.total_failed = 0
        # ✅ 新增：下载器级别的分布式锁，防止并发同步冲突
        self._downloader_locks: Dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # 保护 _downloader_locks 的锁

    async def get_valid_downloaders(self, app) -> List[Any]:
        """
        获取有效的下载器列表（fail_time=0）

        Args:
            app: FastAPI应用实例

        Returns:
            有效的下载器列表
        """
        if not hasattr(app, 'state') or not hasattr(app.state, 'store'):
            logger.error("下载器缓存未初始化 (app.state.store 不存在)")
            return []

        cached_downloaders = await app.state.store.get_snapshot()

        if not cached_downloaders:
            logger.warning("下载器缓存为空")
            return []

        # 只返回有效的下载器（fail_time=0）
        valid_downloaders = [
            d for d in cached_downloaders
            if hasattr(d, 'fail_time') and d.fail_time == 0
        ]

        # 记录失效下载器数量
        failed_count = len([
            d for d in cached_downloaders
            if hasattr(d, 'fail_time') and d.fail_time > 0
        ])

        if failed_count > 0:
            logger.warning(f"发现 {failed_count} 个失效的下载器（fail_time > 0），已跳过")

        return valid_downloaders

    async def _get_downloader_lock(self, downloader_id: str) -> asyncio.Lock:
        """
        获取下载器级别的锁

        确保同一下载器同时只有一个同步任务在执行，防止并发写入导致的 UNIQUE 约束冲突

        Args:
            downloader_id: 下载器ID

        Returns:
            该下载器专用的异步锁
        """
        async with self._locks_lock:
            if downloader_id not in self._downloader_locks:
                self._downloader_locks[downloader_id] = asyncio.Lock()
                logger.debug(f"[锁管理] 为下载器 {downloader_id} 创建新锁")
            return self._downloader_locks[downloader_id]

    async def sync_single_downloader(
        self,
        downloader: Any,
        sync_func,
        sync_type: str
    ) -> Dict[str, Any]:
        """
        同步单个下载器

        ✅ 修复：添加下载器级别的锁，防止并发同步冲突

        Args:
            downloader: 下载器对象
            sync_func: 同步函数
            sync_type: 同步类型标识

        Returns:
            同步结果字典
        """
        # ✅ 获取下载器ID
        downloader_id = getattr(downloader, 'downloader_id', None)
        nickname = getattr(downloader, 'nickname', 'unknown')

        # ✅ 获取该下载器的专用锁
        if downloader_id is None:
            lock_key = f"unknown:{id(downloader)}"
            logger.warning(
                f"[{sync_type}] downloader_id missing; using lock key {lock_key} for {nickname}"
            )
        else:
            lock_key = str(downloader_id)
        lock = await self._get_downloader_lock(lock_key)

        # ✅ 使用锁保护同步操作，确保同一下载器不会并发执行
        async with lock:
            logger.debug(f"[{sync_type}] 获取锁成功: {nickname} (downloader_id={downloader_id})")

            try:
                downloader_info = {
                    'downloader_id': downloader_id,
                    'nickname': nickname,
                    'host': getattr(downloader, 'host', None),
                    'port': getattr(downloader, 'port', None),
                    'username': getattr(downloader, 'username', None),
                    'password': getattr(downloader, 'password', None),
                    'downloader_type': getattr(downloader, 'downloader_type', None),
                    'torrent_save_path': getattr(downloader, 'torrent_save_path', None),
                    'enabled': '1',
                    'status': '1'
                }

                result = await sync_func(downloader_info)

                return result

            except Exception as e:
                error_result = {
                    "status": "failed",
                    "message": f"{sync_type} error for {nickname}: {str(e)}",
                    "nickname": nickname
                }
                return error_result
            finally:
                logger.debug(f"[{sync_type}] 释放锁: {nickname} (downloader_id={downloader_id})")

    async def execute_sync_with_concurrency(
        self,
        downloaders: List[Any],
        sync_func,
        sync_type: str,
        max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        并发执行同步任务

        Args:
            downloaders: 下载器列表
            sync_func: 同步函数
            sync_type: 同步类型标识
            max_concurrent: 最大并发数

        Returns:
            同步结果汇总字典
        """
        if not downloaders:
            return {
                "status": "no_action",
                "message": "没有有效的下载器可同步",
                "successful_syncs": 0,
                "failed_syncs": 0,
                "total_downloaders": 0
            }

        # 记录将要同步的下载器列表
        for downloader in downloaders:
            nickname = getattr(downloader, 'nickname', 'unknown')
            logger.info(f"[{sync_type}] 准备同步: {nickname}")

        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)

        async def sync_with_semaphore(downloader):
            async with semaphore:
                return await self.sync_single_downloader(downloader, sync_func, sync_type)

        # 并发执行同步任务
        logger.info(f"[{sync_type}] 开始并发同步 {len(downloaders)} 个下载器（最大并发数: {max_concurrent}）")
        tasks = [sync_with_semaphore(d) for d in downloaders]
        sync_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        successful_syncs = 0
        failed_syncs = 0

        for result in sync_results:
            if isinstance(result, Exception):
                failed_syncs += 1
                logger.error(f"[{sync_type}] 同步异常: {str(result)}")
            elif not isinstance(result, dict):
                failed_syncs += 1
                logger.warning(f"[{sync_type}] 同步失败: invalid result type {type(result)}")
            elif result.get('status') == 'success':
                successful_syncs += 1
                logger.info(f"[{sync_type}] 同步成功: {result.get('nickname', 'unknown')}")
            else:
                failed_syncs += 1
                logger.warning(f"[{sync_type}] 同步失败: {result.get('nickname', 'unknown')} - {result.get('message', 'Unknown error')}")

        # 确定整体状态
        if successful_syncs == 0 and failed_syncs == 0:
            status = "no_action"
        elif failed_syncs == 0:
            status = "success"
        elif successful_syncs == 0:
            status = "failed"
        else:
            status = "partial"

        return {
            "status": status,
            "message": f"{sync_type} 完成",
            "successful_syncs": successful_syncs,
            "failed_syncs": failed_syncs,
            "total_downloaders": len(downloaders)
        }

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
            "total_processed": self.total_processed,
            "total_failed": self.total_failed,
            "last_execution_time": self.last_execution_time,
            "success_rate": (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0
        }
