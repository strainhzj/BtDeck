"""
Tracker判断引擎 - 基于关键词池的tracker状态判断

该模块实现了基于关键词池的tracker状态判断逻辑，支持失败优先策略，
即只要消息包含失败关键词就判定为失败，否则检查成功关键词。

核心特性:
- 关键词缓存机制：从数据库加载关键词到内存，按语言分组
- 失败优先策略：失败关键词优先于成功关键词判断
- 精确短语匹配：简单包含匹配，不区分大小写
- 多语言支持：支持中英俄日等多语言关键词池
- 自动缓存刷新：支持TTL自动刷新和手动刷新
- 线程安全：使用RLock保护并发访问

作者: AI开发助手
创建时间: 2026-01-26
版本: 1.1.0
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.torrents.models import TrackerKeywordConfig

logger = logging.getLogger(__name__)


class TrackerStatus:
    """Tracker状态常量类"""

    DISABLED = "已禁用"
    NOT_CONTACTED = "未联系"
    WORKING = "工作中"
    FAILED = "工作失败"


class TrackerJudgmentEngine:
    """
    Tracker判断引擎

    基于关键词池的tracker状态判断引擎，支持失败优先策略和多语言关键词。

    线程安全：所有公共方法都使用RLock保护，支持多线程并发访问。

    属性:
        keyword_cache: 关键词缓存字典，按类型(success/failure)分组
        keyword_cache_by_language: 按语言分组的关键词缓存
        last_cache_update: 最后一次缓存更新时间
        cache_ttl: 缓存有效期（秒），默认3600秒（1小时）

    示例:
        >>> engine = TrackerJudgmentEngine()
        >>> status = engine.judge_status("工作中", "Download success")
        >>> print(status)  # 输出: "工作中"
    """

    def __init__(self, cache_ttl: int = 3600, auto_load: bool = True):
        """
        初始化Tracker判断引擎

        Args:
            cache_ttl: 缓存有效期（秒），默认3600秒（1小时）
            auto_load: 是否在初始化时自动加载关键词，默认True
        """
        self.keyword_cache: Dict[str, List[str]] = {
            'candidate': [],
            'ignored': [],
            'success': [],
            'failed': []
        }
        self.keyword_cache_by_language: Dict[str, Dict[str, List[str]]] = {}
        self.last_cache_update: Optional[datetime] = None
        self.cache_ttl: int = cache_ttl
        self._lock: threading.RLock = threading.RLock()  # 线程安全的可重入锁
        self._cache_jitter: int = 60  # 缓存刷新抖动范围（秒）

        # 初始化时自动加载关键词（如果启用）
        if auto_load:
            self.load_keywords()

    def load_keywords(self) -> bool:
        """
        从数据库加载关键词到缓存

        从tracker_keyword_config表加载所有启用的关键词（enabled=True且dr=0），
        按类型(success/failure)和语言(universal/具体语言)分组存储到内存缓存。

        线程安全：使用RLock保护，支持并发调用。

        Returns:
            bool: 加载是否成功
        """
        start_time = time.time()

        try:
            db = SessionLocal()
            try:
                # 查询所有启用的关键词
                keywords = db.query(TrackerKeywordConfig).filter(
                    TrackerKeywordConfig.enabled == True,
                    TrackerKeywordConfig.dr == 0
                ).all()

                # 使用锁保护缓存更新
                with self._lock:
                    # 清空缓存 - 支持所有类型
                    self.keyword_cache = {
                        'candidate': [],
                        'ignored': [],
                        'success': [],
                        'failed': []
                    }
                    self.keyword_cache_by_language = {}

                    # 按类型和语言分组
                    for keyword in keywords:
                        key = keyword.keyword_type  # 'candidate', 'ignored', 'success', 'failed'
                        lang = keyword.language or 'universal'

                        # 确保类型在缓存中存在
                        if key not in self.keyword_cache:
                            self.keyword_cache[key] = []

                        # 添加到通用缓存（转换为小写）
                        keyword_lower = keyword.keyword.lower()
                        self.keyword_cache[key].append(keyword_lower)

                        # 添加到语言特定缓存
                        if lang not in self.keyword_cache_by_language:
                            # 初始化时支持所有可能的类型
                            self.keyword_cache_by_language[lang] = {
                                'candidate': [],
                                'ignored': [],
                                'success': [],
                                'failed': []
                            }

                        # 确保类型在语言缓存中存在
                        if key not in self.keyword_cache_by_language[lang]:
                            self.keyword_cache_by_language[lang][key] = []

                        self.keyword_cache_by_language[lang][key].append(keyword_lower)

                    # 记录加载时间
                    self.last_cache_update = datetime.now()

                # 统计信息 - 支持所有类型
                success_count = len(self.keyword_cache.get('success', []))
                failed_count = len(self.keyword_cache.get('failed', []))
                candidate_count = len(self.keyword_cache.get('candidate', []))
                ignored_count = len(self.keyword_cache.get('ignored', []))
                language_count = len(self.keyword_cache_by_language)
                total_count = success_count + failed_count + candidate_count + ignored_count
                elapsed_ms = (time.time() - start_time) * 1000

                logger.info(
                    f"关键词加载成功: 成功{success_count}条, 失败{failed_count}条, "
                    f"候选{candidate_count}条, 忽略{ignored_count}条, "
                    f"总计{total_count}条, 语言{language_count}种, 耗时{elapsed_ms:.2f}ms"
                )
                return True

            except SQLAlchemyError as e:
                logger.error(f"数据库查询失败: {e}", exc_info=True)
                return False
            finally:
                db.close()

        except Exception as e:
            logger.error(f"加载关键词失败: {e}", exc_info=True)
            return False

    def _match_keyword(self, keyword: str, msg: str) -> bool:
        """
        精确短语匹配（不区分大小写）

        使用简单的字符串包含匹配，检查消息中是否包含指定的关键词。
        匹配不区分大小写，支持多语言字符。

        Args:
            keyword: 关键词
            msg: 消息

        Returns:
            bool: 是否匹配

        示例:
            >>> engine = TrackerJudgmentEngine()
            >>> engine._match_keyword("success", "Download success")
            True
            >>> engine._match_keyword("SUCCESS", "download success")
            True
            >>> engine._match_keyword("超时", "连接超时")
            True
        """
        if not keyword or not msg:
            return False

        # 简单包含匹配（不区分大小写）
        return keyword.lower() in msg.lower()

    def _match_any_keyword(self, keywords: List[str], msg: str) -> bool:
        """
        批量匹配，任意一个关键词匹配即返回True

        遍历关键词列表，只要消息中包含任意一个关键词就返回True。
        匹配成功时会记录debug日志。

        Args:
            keywords: 关键词列表
            msg: 消息

        Returns:
            bool: 是否有匹配的关键词

        示例:
            >>> engine = TrackerJudgmentEngine()
            >>> engine._match_any_keyword(["success", "ok"], "Download success")
            True
            >>> engine._match_any_keyword(["success", "ok"], "Unknown status")
            False
        """
        if not keywords or not msg:
            return False

        for keyword in keywords:
            if self._match_keyword(keyword, msg):
                logger.debug(f"匹配到关键词: '{keyword}' in msg: '{msg[:50]}...'")
                return True

        return False

    def _should_refresh_cache(self) -> bool:
        """
        检查是否需要刷新缓存

        根据最后更新时间、缓存TTL和随机抖动判断缓存是否过期。
        添加随机抖动避免多个实例同时刷新缓存。

        Returns:
            bool: 是否需要刷新

        示例:
            >>> engine = TrackerJudgmentEngine()
            >>> engine._should_refresh_cache()  # 刚加载过，返回False
            False
        """
        if self.last_cache_update is None:
            return True

        with self._lock:
            if self.last_cache_update is None:
                return True

            elapsed = (datetime.now() - self.last_cache_update).total_seconds()

            # 添加随机抖动，避免多个实例同时刷新
            import random
            jitter = random.uniform(0, self._cache_jitter)

            return elapsed > (self.cache_ttl + jitter)

    def _ensure_cache_loaded(self) -> None:
        """
        确保缓存已加载（懒加载）

        如果缓存未加载，自动加载关键词。线程安全。

        Returns:
            None
        """
        if self.last_cache_update is None:
            with self._lock:
                # 双重检查锁定模式
                if self.last_cache_update is None:
                    self.load_keywords()

    def judge_status(
        self,
        original_status: str,
        msg: str,
        language: Optional[str] = None
    ) -> str:
        """
        综合判断tracker状态（失败优先策略）

        判断流程：
        1. 确保缓存已加载（懒加载）
        2. 检查缓存是否需要刷新，如需要则自动刷新
        3. 检查msg是否包含失败关键词 → 返回"工作失败"
        4. 检查msg是否包含成功关键词 → 返回"工作中"
        5. 无匹配 → 返回original_status

        线程安全：使用锁保护缓存访问。

        Args:
            original_status: tracker原始状态（已禁用/未联系/工作中/工作失败）
            msg: tracker返回的消息
            language: 语言标识（可选），如"zh_CN", "en_US"，None表示使用通用池

        Returns:
            最终判定的状态字符串

        示例:
            >>> engine = TrackerJudgmentEngine()
            >>> engine.judge_status("工作中", "Connection timed out")
            '工作失败'
            >>> engine.judge_status("工作失败", "Download success")
            '工作中'
            >>> engine.judge_status("未联系", "Unknown status")
            '未联系'
        """
        start_time = time.time()

        # 参数验证
        if not msg:
            logger.debug(f"空消息，保持原状态: {original_status}")
            return original_status

        # 确保缓存已加载
        self._ensure_cache_loaded()

        # 检查缓存是否需要刷新并获取关键词
        with self._lock:
            if self._should_refresh_cache():
                logger.info("缓存已过期，自动刷新关键词")
                # 释放锁后加载，避免死锁
                self._lock.release()
                try:
                    self.load_keywords()
                finally:
                    self._lock.acquire()

            # 选择关键词池（优先使用指定语言）
            if language and language in self.keyword_cache_by_language:
                # 合并失败池和忽略池的关键词
                failed_keywords = (
                    self.keyword_cache_by_language[language].get('failed', []) +
                    self.keyword_cache_by_language[language].get('ignored', [])
                )
                success_keywords = self.keyword_cache_by_language[language].get('success', [])
            else:
                # 合并失败池和忽略池的关键词
                failed_keywords = (
                    self.keyword_cache.get('failed', []) +
                    self.keyword_cache.get('ignored', [])
                )
                success_keywords = self.keyword_cache.get('success', [])

        # Step 1: 失败优先判断
        if self._match_any_keyword(failed_keywords, msg):
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                f"判定为失败: msg包含失败/忽略关键词 | "
                f"原状态: {original_status} | msg: '{msg[:100]}' | "
                f"耗时: {elapsed_ms:.2f}ms"
            )
            return TrackerStatus.FAILED  # "工作失败"

        # Step 2: 成功判断
        if self._match_any_keyword(success_keywords, msg):
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                f"判定为成功: msg包含成功关键词 | "
                f"原状态: {original_status} | msg: '{msg[:100]}' | "
                f"耗时: {elapsed_ms:.2f}ms"
            )
            return TrackerStatus.WORKING  # "工作中"

        # Step 3: 无匹配，返回原始状态
        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug(
            f"无关键词匹配，保持原状态: {original_status} | msg: '{msg[:100]}' | "
            f"耗时: {elapsed_ms:.2f}ms"
        )
        return original_status

    def refresh_cache(self) -> bool:
        """
        手动刷新关键词缓存

        强制从数据库重新加载关键词到缓存，更新last_cache_update时间。
        线程安全。

        Returns:
            bool: 刷新是否成功

        示例:
            >>> engine = TrackerJudgmentEngine()
            >>> old_time = engine.last_cache_update
            >>> engine.refresh_cache()
            True
            >>> assert engine.last_cache_update > old_time
        """
        logger.info("手动刷新关键词缓存")
        return self.load_keywords()

    def get_cache_stats(self) -> Dict[str, Union[int, str, bool, None]]:
        """
        获取缓存统计信息

        线程安全：使用锁保护缓存读取。

        Returns:
            包含缓存统计信息的字典，包括关键词数量、语言数量、最后更新时间等

        示例:
            >>> engine = TrackerJudgmentEngine()
            >>> stats = engine.get_cache_stats()
            >>> print(stats['success_count'])
            15
            >>> print(stats['failed_count'])
            17
        """
        with self._lock:
            return {
                'candidate_count': len(self.keyword_cache.get('candidate', [])),
                'ignored_count': len(self.keyword_cache.get('ignored', [])),
                'success_count': len(self.keyword_cache.get('success', [])),
                'failed_count': len(self.keyword_cache.get('failed', [])),
                'language_count': len(self.keyword_cache_by_language),
                'last_cache_update': self.last_cache_update.isoformat() if self.last_cache_update else None,
                'cache_ttl_seconds': self.cache_ttl,
                'is_cache_expired': self._should_refresh_cache()
            }


# 全局单例，供其他模块导入使用
judgment_engine = TrackerJudgmentEngine()
