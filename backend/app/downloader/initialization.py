import asyncio
import socket
import logging
from fastapi import FastAPI
from typing import List, Any, Callable, Dict
from collections import defaultdict
import time
from datetime import datetime

logger = logging.getLogger(__name__)

from sqlalchemy import text
from app.database import SessionLocal
from app.downloader.request import DownloaderCheckVO
from app.downloader.torrent_stats_cache import TorrentStatsCache
from app.downloader.responseVO import DownloaderVO
from qbittorrentapi import Client as qbClient, APIConnectionError, LoginFailed
from transmission_rpc import Client as trClient, TransmissionAuthError, TransmissionTimeoutError, \
    TransmissionConnectError


# ❌ 删除全局 app 变量，避免与真正的 FastAPI 实例混淆
# 原代码: app = FastAPI()  # 这会导致缓存初始化在错误的实例上
# 现在通过函数参数传递正确的 app 实例


class DownloaderInitialization:
    def __init__(self, check_status_func: Callable[[Any], bool]):
        self._data = []  # 核心数据（写时复制）
        self._buffer = []  # 写缓冲区
        self._cache = None  # 读缓存
        self._cache_time = 0  # 缓存时间
        self._cache_ttl = 0.5  # 缓存有效期（秒）
        self._lock = asyncio.Lock()  # 写操作锁
        self._processing = False  # 缓冲区处理状态

        # 校验相关属性
        self.check_status = check_status_func  # 同步校验函数
        self.check_status_async = check_status_async  # 异步校验函数
        self.failure_counts = defaultdict(int)  # 失败计数器 {item: 失败次数}
        self.last_check_time = 0  # 上次校验时间
        self.check_interval = 5  # 校验间隔（秒）
        self.failure_threshold = 3  # 失败阈值，达到此值则移除

    async def add(self, item: Any, immediate: bool = False):
        """添加下载器到缓存

        Args:
            item: 下载器对象
            immediate: 是否立即写入（绕过缓冲区）
        """
        if immediate:
            # 初始化失败计数（锁外）
            if not hasattr(item, 'fail_time'):
                item.fail_time = 0
            else:
                item.fail_time = 0

            # 立即写入模式：绕过缓冲区，直接写入核心数据
            async with self._lock:
                new_data = self._data.copy()
                new_data.append(item)
                self._data = new_data
                self._cache = None  # 使缓存失效
            return

        # 缓冲区模式：批量写入，提高性能
        self._buffer.append(item)
        # 触发处理（如果未在处理中）
        if not self._processing:
            asyncio.create_task(self._process_buffer())

    async def _process_buffer(self):
        """后台处理缓冲区"""
        self._processing = True
        try:
            while self._buffer:
                # 批量获取缓冲区数据
                batch = self._buffer[:100]  # 每次最多处理100个
                self._buffer = self._buffer[100:]

                # 写时复制更新
                async with self._lock:
                    new_data = self._data.copy()
                    new_data.extend(batch)
                    self._data = new_data
                    self._cache = None  # 使缓存失效

                    # 初始化新元素的失败计数
                    for item in batch:
                        item.fail_time = 0
        finally:
            self._processing = False

    async def get_snapshot(self) -> List[Any]:
        """获取数据快照（带缓存）"""
        now = time.time()
        # 检查缓存是否有效
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache.copy()

        # 尝试获取锁重建缓存
        if not self._lock.locked():
            try:
                # 异步获取锁
                await self._lock.acquire()
                self._cache = self._data.copy()
                self._cache_time = now
                return self._cache.copy()
            except Exception as e:
                print(f"Error acquiring lock: {e}")
            finally:
                self._lock.release()

        # 锁被占用时直接返回当前数据
        return self._data.copy()

    def get_snapshot_sync(self) -> List[Any]:
        """同步方式获取数据快照（带缓存）

        ⚠️ 注意：此方法设计为在同步上下文中调用。
        如果在异步上下文中调用，请使用 get_snapshot() 方法。
        """
        now = time.time()
        # 检查缓存是否有效
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache.copy()

        # 锁被占用时直接返回当前数据
        if self._lock.locked():
            return self._data.copy()

        # 检查事件循环是否已经在运行
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 事件循环正在运行，无法使用 run_until_complete()
                # 直接返回当前数据（在异步上下文中应使用 get_snapshot()）
                return self._data.copy()
            else:
                # 事件循环未运行，可以使用 run_until_complete()
                try:
                    result = loop.run_until_complete(self._get_snapshot_with_lock())
                    return result
                except (RuntimeError, asyncio.TimeoutError, asyncio.CancelledError):
                    # 发生错误，返回当前数据
                    return self._data.copy()
        except RuntimeError:
            # 无法获取事件循环，返回当前数据
            return self._data.copy()

    async def _get_snapshot_with_lock(self) -> List[Any]:
        """异步获取带锁的快照"""
        async with self._lock:
            self._cache = self._data.copy()
            self._cache_time = time.time()
            return self._cache.copy()

    async def check_and_remove_invalid(self):
        """检查并移除连续五次校验失败的元素"""
        now = time.time()
        # 检查是否达到校验间隔
        if now - self.last_check_time < self.check_interval:
            return

        # 获取当前数据快照（避免处理过程中数据变化）
        current_data = await self.get_snapshot()  # 使用异步版本
        items_to_remove = []

        # 遍历快照中的每个元素
        for item in current_data:
            try:
                # 调用异步校验函数
                is_valid = await self.check_status_async(item)

                if is_valid:
                    # 校验成功，重置失败计数
                    item.fail_time = 0
                else:
                    # 校验失败，增加失败计数
                    item.fail_time += 1
                    # 检查是否达到移除阈值
                    if item.fail_time >= self.failure_threshold:
                        items_to_remove.append(item)
            except Exception as e:
                # 校验过程中出现异常，视为校验失败
                print(f"Error checking downloader {item.nickname}: {e}")
                item.fail_time += 1
                if item.fail_time >= self.failure_threshold:
                    items_to_remove.append(item)

        # 如果有待移除的元素，执行移除操作
        if items_to_remove:
            await self._remove_items(items_to_remove)

        # 更新最后校验时间
        self.last_check_time = now

    async def _remove_items(self, items_to_remove: List[Any]):
        """移除指定元素（需要获取锁）"""
        async with self._lock:
            # 创建新列表，不包含要移除的元素
            new_data = [item for item in self._data if item not in items_to_remove]
            self._data = new_data
            self._cache = None  # 使缓存失效

            # 从失败计数中移除这些元素
            for item in items_to_remove:
                self.failure_counts.pop(item, None)
                print(f"Removed invalid downloader: {item}")


# 改进的连通性检测方法
def _clean_host_url(host: str) -> str:
    """
    清理主机地址，移除协议前缀和路径

    Args:
        host: 可能包含协议前缀的主机地址（如 "https://example.com" 或 "example.com"）

    Returns:
        str: 清理后的纯主机名（如 "example.com"）

    Examples:
        >>> _clean_host_url("https://qb.smalltrain.top")
        "qb.smalltrain.top"
        >>> _clean_host_url("http://192.168.1.1:8080")
        "192.168.1.1"
        >>> _clean_host_url("qb.smalltrain.top")
        "qb.smalltrain.top"
    """
    if not host:
        return host

    # 移除协议前缀（http:// 或 https://）
    if "://" in host:
        host = host.split("://", 1)[1]

    # 移除路径部分（保留主机名和端口）
    if "/" in host:
        host = host.split("/", 1)[0]

    # 移除端口号（如果有的话），只保留主机名
    # 注意：这里我们保留端口号用于日志，但 socket 连接时单独使用 port 参数
    # 所以不做进一步处理

    return host.strip()


async def check_port_connectivity(host: str, port: int, timeout: float = 3.0, max_retries: int = 3) -> bool:
    """
    检查端口连通性（使用 socket.connect）

    Args:
        host: 主机地址（可能包含协议前缀，会自动清理）
        port: 端口号
        timeout: 每次连接的超时时间（秒）
        max_retries: 最大重试次数

    Returns:
        bool: 端口是否可达
    """
    # ✅ 清理主机地址，移除协议前缀
    clean_host = _clean_host_url(host)

    for attempt in range(1, max_retries + 1):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((clean_host, port))

            if result == 0:
                logger.debug(f"✅ 端口连通性检查成功: {clean_host}:{port} (尝试 {attempt}/{max_retries})")
                return True
            else:
                logger.debug(f"⚠️  端口连接失败: {clean_host}:{port} (错误码: {result}, 尝试 {attempt}/{max_retries})")

        except socket.gaierror as e:
            logger.debug(f"❌ DNS解析失败: {clean_host} (尝试 {attempt}/{max_retries}): {e}")
            # DNS 失败不继续重试
            break
        except socket.timeout as e:
            logger.debug(f"⏱️  连接超时: {clean_host}:{port} (尝试 {attempt}/{max_retries})")
        except Exception as e:
            logger.debug(f"❌ 连接异常: {clean_host}:{port} (尝试 {attempt}/{max_retries}): {e}")
        finally:
            # ✅ 确保 socket 总是被关闭，避免资源泄漏
            if sock is not None:
                try:
                    sock.close()
                except Exception as e:
                    print(f"⚠️  关闭 socket 时出错: {e}")

    # 如果原始 host 包含协议前缀，在日志中同时显示原始值和清理后的值
    if clean_host != host:
        print(f"❌ 端口连通性检查失败，已重试 {max_retries} 次: {host}:{port} (清理后: {clean_host}:{port})")
    else:
        print(f"❌ 端口连通性检查失败，已重试 {max_retries} 次: {clean_host}:{port}")

    return False


async def check_downloader_connectivity_with_retry(
        downloader_info: Dict[str, Any],
        timeout: float = 3.0,
        max_port_retries: int = 3,
        max_auth_retries: int = 3
) -> bool:
    """
    分层检查下载器连通性，包含重试机制

    第一步：端口可达性检查（socket.connect）
      - 超时：timeout 秒
      - 重试：max_port_retries 次
      - 失败：记录警告，跳过后续步骤

    第二步：认证检查（客户端库自带超时）
      - 重试：max_auth_retries 次
      - 超时：由客户端库处理
      - 失败：记录警告，返回 False

    Args:
        downloader_info: 下载器信息字典
        timeout: 端口检查超时时间（秒）
        max_port_retries: 端口检查最大重试次数
        max_auth_retries: 认证检查最大重试次数

    Returns:
        bool: 下载器是否可用
    """
    nickname = downloader_info.get('nickname', 'Unknown')
    host = downloader_info.get('host')
    port = downloader_info.get('port')
    downloader_type = downloader_info.get('downloader_type')

    print(f"\n{'=' * 60}")
    print(f"开始检查下载器: {nickname} ({host}:{port})")
    print(f"{'=' * 60}")

    # ✅ 添加全局超时保护（30秒）
    async def _check_with_timeout():
        # 第一步：端口连通性检查
        logger.debug(f"[第一步] 检查端口连通性...")
        port_accessible = await check_port_connectivity(host, port, timeout, max_port_retries)

        if not port_accessible:
            logger.debug(f"⚠️  下载器 {nickname} 端口不可达，跳过后续检查")
            return False

        # 第二步：认证检查
        print(f"[第二步] 检查认证...")

        for auth_attempt in range(1, max_auth_retries + 1):
            try:
                if downloader_type == 'qBittorrent':
                    return await _check_qbittorrent_auth_with_retry(downloader_info, auth_attempt, max_auth_retries)
                elif downloader_type == 'Transmission':
                    return await _check_transmission_auth_with_retry(downloader_info, auth_attempt, max_auth_retries)
                else:
                    print(f"❌ 不支持的下载器类型: {downloader_type}")
                    return False

            except Exception as e:
                print(f"❌ 认证检查异常 (尝试 {auth_attempt}/{max_auth_retries}): {e}")
                if auth_attempt < max_auth_retries:
                    print(f"等待 1 秒后重试...")
                    await asyncio.sleep(1)
                else:
                    print(f"❌ 认证检查失败，已重试 {max_auth_retries} 次")
                    return False

        return False

    try:
        # ✅ 使用 asyncio.wait_for 实现超时控制（兼容 Python 3.10+）
        return await asyncio.wait_for(_check_with_timeout(), timeout=30.0)
    except asyncio.TimeoutError:
        print(f"❌ 连通性检查超时（30秒）: {nickname}")
        return False


async def _check_qbittorrent_auth_with_retry(downloader_info: Dict[str, Any], attempt: int, max_retries: int) -> bool:
    """qBittorrent 认证检查（带重试）"""
    from qbittorrentapi import Client as qbClient

    nickname = downloader_info.get('nickname', 'Unknown')
    host = downloader_info.get('host')
    port = downloader_info.get('port')
    username = downloader_info.get('username')
    password = downloader_info.get('password')

    try:
        logger.debug(f"创建 qBittorrent 客户端连接... (尝试 {attempt}/{max_retries})")
        client = qbClient(
            host=f"http://{host}:{port}",
            username=username,
            password=password
        )

        # 尝试获取应用版本（验证认证）
        logger.debug(f"验证 qBittorrent 认证... (尝试 {attempt}/{max_retries})")
        app_version = await asyncio.to_thread(client.app_version)

        if app_version:
            logger.debug(f"✅ qBittorrent 认证成功: {nickname}, 版本: {app_version}")
            return True
        else:
            logger.debug(f"⚠️  qBittorrent 认证失败: {nickname} (无法获取版本信息)")
            return False

    except APIConnectionError as e:
        print(f"❌ qBittorrent 连接失败 (尝试 {attempt}/{max_retries}): {e}")
        raise
    except LoginFailed as e:
        print(f"❌ qBittorrent 认证失败 (尝试 {attempt}/{max_retries}): {e}")
        raise
    except Exception as e:
        print(f"❌ qBittorrent 检查异常 (尝试 {attempt}/{max_retries}): {e}")
        raise


async def _check_transmission_auth_with_retry(downloader_info: Dict[str, Any], attempt: int, max_retries: int) -> bool:
    """Transmission 认证检查（带重试）"""
    from transmission_rpc import Client as trClient

    nickname = downloader_info.get('nickname', 'Unknown')
    host = downloader_info.get('host')
    port = downloader_info.get('port')
    username = downloader_info.get('username')
    password = downloader_info.get('password')

    try:
        logger.debug(f"创建 Transmission 客户端连接... (尝试 {attempt}/{max_retries})")
        client = trClient(
            host=host,
            port=port,
            username=username,
            password=password
        )

        # 尝试获取会话统计（验证认证）
        logger.debug(f"验证 Transmission 认证... (尝试 {attempt}/{max_retries})")
        session_stats = await asyncio.to_thread(client.session_stats)

        if session_stats:
            logger.debug(f"✅ Transmission 认证成功: {nickname}")
            return True
        else:
            logger.debug(f"⚠️  Transmission 认证失败: {nickname} (无法获取会话信息)")
            return False

    except TransmissionAuthError as e:
        print(f"❌ Transmission 认证失败 (尝试 {attempt}/{max_retries}): {e}")
        raise
    except TransmissionTimeoutError as e:
        print(f"❌ Transmission 超时 (尝试 {attempt}/{max_retries}): {e}")
        raise
    except TransmissionConnectError as e:
        print(f"❌ Transmission 连接失败 (尝试 {attempt}/{max_retries}): {e}")
        raise
    except Exception as e:
        print(f"❌ Transmission 检查异常 (尝试 {attempt}/{max_retries}): {e}")
        raise


async def check_status_async_new(item: Any) -> bool:
    """
    新版异步连通性检查（使用分层检查 + 重试机制）
    """
    try:
        # 获取基础连接信息
        nickname = getattr(item, 'nickname', 'Unknown')
        host = getattr(item, 'host', None)
        port = getattr(item, 'port', None)
        downloader_type = getattr(item, 'downloader_type', None)
        username = getattr(item, 'username', None)
        password = getattr(item, 'password', None)

        if not all([host, port, downloader_type]):
            print(f"⚠️  下载器 {nickname} 缺少必要信息，跳过检查")
            return False

        downloader_info = {
            'nickname': nickname,
            'host': host,
            'port': port,
            'downloader_type': downloader_type,
            'username': username,
            'password': password
        }

        return await check_downloader_connectivity_with_retry(downloader_info)

    except Exception as e:
        print(f"❌ 连通性检查异常 {getattr(item, 'nickname', 'Unknown')}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_status_async(item: Any) -> bool:
    """
    异步分层验证下载器连通性：
    1. 测试地址能否访问
    2. 测试账号密码是否能登录
    3. 其他异常处理
    """
    try:
        # 获取基础连接信息
        nickname = getattr(item, 'nickname', 'Unknown')

        if isinstance(item.client, qbClient):
            # qBittorrent 客户端校验
            return await _check_qbittorrent_connectivity_async(item.client, nickname)
        elif isinstance(item.client, trClient):
            # Transmission 客户端校验
            return await _check_transmission_connectivity_async(item.client, nickname)
        else:
            print(f"Unsupported client type for {nickname}: {type(item.client)}")
            return False

    except Exception as e:
        print(f"Unexpected error during connectivity check for {getattr(item, 'nickname', 'Unknown')}: {e}")
        return False


def check_status(item: Any) -> bool:
    """
    分层验证下载器连通性（同步版本，保持兼容性）：
    1. 测试地址能否访问
    2. 测试账号密码是否能登录
    3. 其他异常处理
    """
    try:
        # 获取基础连接信息
        nickname = getattr(item, 'nickname', 'Unknown')

        if isinstance(item.client, qbClient):
            # qBittorrent 客户端校验
            return _check_qbittorrent_connectivity(item.client, nickname)
        elif isinstance(item.client, trClient):
            # Transmission 客户端校验
            return _check_transmission_connectivity(item.client, nickname)
        else:
            print(f"Unsupported client type for {nickname}: {type(item.client)}")
            return False

    except Exception as e:
        print(f"Unexpected error during connectivity check for {getattr(item, 'nickname', 'Unknown')}: {e}")
        return False


async def _check_qbittorrent_connectivity_async(client: qbClient, nickname: str) -> bool:
    """异步qBittorrent 连通性分层检测"""
    try:
        # 第一层：测试地址访问（通过获取应用版本）
        print(f"Testing address access for qBittorrent: {nickname}")
        app_version = await asyncio.to_thread(client.app_version)
        if not app_version:
            print(f"Failed to access qBittorrent API for {nickname}")
            return False
        print(f"Address access successful for {nickname}, version: {app_version}")

        # 第二层：测试账号密码登录（通过获取认证信息）
        print(f"Testing authentication for qBittorrent: {nickname}")
        auth_info = await asyncio.to_thread(client.auth_log_in)
        print(f"Authentication successful for {nickname}")

        # 第三层：测试基本功能（获取torrent列表）
        print(f"Testing basic functionality for qBittorrent: {nickname}")
        torrents = await asyncio.to_thread(client.torrents_info, limit=1)  # 只获取1个torrent进行测试
        print(f"Basic functionality test passed for {nickname}")

        return True

    except APIConnectionError as e:
        print(f"Address access failed for qBittorrent {nickname}: {e}")
        return False
    except LoginFailed as e:
        print(f"Authentication failed for qBittorrent {nickname}: {e}")
        return False
    except Exception as e:
        print(f"Other error during qBittorrent connectivity check for {nickname}: {e}")
        return False


def _check_qbittorrent_connectivity(client: qbClient, nickname: str) -> bool:
    """qBittorrent 连通性分层检测（同步版本）"""
    try:
        # 第一层：测试地址访问（通过获取应用版本）
        print(f"Testing address access for qBittorrent: {nickname}")
        app_version = client.app_version()
        if not app_version:
            print(f"Failed to access qBittorrent API for {nickname}")
            return False
        print(f"Address access successful for {nickname}, version: {app_version}")

        # 第二层：测试账号密码登录（通过获取认证信息）
        print(f"Testing authentication for qBittorrent: {nickname}")
        auth_info = client.auth_log_in()
        print(f"Authentication successful for {nickname}")

        # 第三层：测试基本功能（获取torrent列表）
        print(f"Testing basic functionality for qBittorrent: {nickname}")
        torrents = client.torrents_info(limit=1)  # 只获取1个torrent进行测试
        print(f"Basic functionality test passed for {nickname}")

        return True

    except APIConnectionError as e:
        print(f"Address access failed for qBittorrent {nickname}: {e}")
        return False
    except LoginFailed as e:
        print(f"Authentication failed for qBittorrent {nickname}: {e}")
        return False
    except Exception as e:
        print(f"Other error during qBittorrent connectivity check for {nickname}: {e}")
        return False


async def _check_transmission_connectivity_async(client: trClient, nickname: str) -> bool:
    """异步Transmission 连通性分层检测"""
    try:
        # 第一层：测试地址访问（通过获取会话统计）
        print(f"Testing address access for Transmission: {nickname}")
        session_stats = await asyncio.to_thread(client.session_stats)
        if not session_stats:
            print(f"Failed to access Transmission API for {nickname}")
            return False
        print(f"Address access successful for {nickname}")

        # 第二层：测试账号密码认证（session_stats 成功说明认证通过）
        print(f"Authentication successful for Transmission: {nickname}")

        # 第三层：测试基本功能（获取torrent列表）
        print(f"Testing basic functionality for Transmission: {nickname}")
        torrents = await asyncio.to_thread(client.get_torrent, torrent_id=1)  # 只获取1个torrent进行测试
        print(f"Basic functionality test passed for {nickname}")

        return True

    except TransmissionConnectError as e:
        print(f"Address access failed for Transmission {nickname}: {e}")
        return False
    except TransmissionAuthError as e:
        print(f"Authentication failed for Transmission {nickname}: {e}")
        return False
    except TransmissionTimeoutError as e:
        print(f"Timeout during Transmission connectivity check for {nickname}: {e}")
        return False
    except Exception as e:
        print(f"Other error during Transmission connectivity check for {nickname}: {e}")
        return False


def _check_transmission_connectivity(client: trClient, nickname: str) -> bool:
    """Transmission 连通性分层检测（同步版本）"""
    try:
        # 第一层：测试地址访问（通过获取会话统计）
        print(f"Testing address access for Transmission: {nickname}")
        session_stats = client.session_stats()
        if not session_stats:
            print(f"Failed to access Transmission API for {nickname}")
            return False
        print(f"Address access successful for {nickname}")

        # 第二层：测试账号密码认证（session_stats 成功说明认证通过）
        print(f"Authentication successful for Transmission: {nickname}")

        # 第三层：测试基本功能（获取torrent列表）
        print(f"Testing basic functionality for Transmission: {nickname}")
        torrents = client.get_torrents(ids=1)  # 只获取1个torrent进行测试
        print(f"Basic functionality test passed for {nickname}")

        return True

    except TransmissionConnectError as e:
        print(f"Address access failed for Transmission {nickname}: {e}")
        return False
    except TransmissionAuthError as e:
        print(f"Authentication failed for Transmission {nickname}: {e}")
        return False
    except TransmissionTimeoutError as e:
        print(f"Timeout during Transmission connectivity check for {nickname}: {e}")
        return False
    except Exception as e:
        print(f"Other error during Transmission connectivity check for {nickname}: {e}")
        return False


async def startup_event(app: FastAPI):
    """
    初始化下载器缓存系统

    Args:
        app: FastAPI 应用实例（通过依赖注入传入，确保使用正确的实例）
    """
    # 初始化数据存储
    print("=== 开始持久化下载器数据 ===")
    app.state.store = DownloaderInitialization(check_status)

    # 启动定时校验任务
    # loop = asyncio.get_event_loop()
    # loop.create_task(periodic_check())
    # loop.create_task(cached_downloader_sync_task())
    # loop.create_task(full_database_sync_task())

    # 异步执行初始化任务，不阻塞服务器启动
    print("=== 异步执行初始化任务 ===")
    # 创建后台任务，不阻塞服务器启动
    asyncio.create_task(_async_initialization_tasks(app))

    # 启动状态轮询任务（10秒间隔）
    print("=== 启动下载器状态轮询任务 ===")
    asyncio.create_task(downloader_status_polling_task(app))


async def _async_initialization_tasks(app: FastAPI):
    """
    异步执行初始化任务，不阻塞服务器启动

    Args:
        app: FastAPI 应用实例
    """
    try:
        print("=== 开始异步初始化任务 ===")

        # 初始加载所有启用的下载器（已包含完整同步逻辑）
        await _load_initial_downloaders(app)

        # 服务启动时执行一次下载器缓存同步任务
        await _perform_initial_downloader_cache_sync(app)

        print("=== 异步初始化任务完成 ===")

    except Exception as e:
        print(f"异步初始化任务执行出错: {e}")
        # 不重新抛出异常，避免影响服务器启动


async def _perform_initial_downloader_cache_sync(app: FastAPI):
    """
    服务启动时执行一次下载器缓存同步任务

    Args:
        app: FastAPI 应用实例
    """
    print("=== 开始初始下载器缓存同步 ===")
    try:
        from app.tasks.logger import TaskLogger

        async with TaskLogger("initial_downloader_cache_sync", task_type=4) as logger:
            logger.add_log("Starting initial downloader cache sync")

            # 获取当前缓存中的下载器列表
            cached_downloaders = await app.state.store.get_snapshot()

            if not cached_downloaders:
                logger.add_log("No cached downloaders found during initial sync")
                return

            logger.add_log(f"Found {len(cached_downloaders)} cached downloaders during initial sync")

            # 统计有效下载器数量
            valid_downloaders = [
                d for d in cached_downloaders
                if hasattr(d, 'fail_time') and d.fail_time == 0
            ]

            logger.add_log(f"Found {len(valid_downloaders)} valid downloaders (fail_time=0) during initial sync")

            # 执行连通性验证统计
            verified_count = 0
            failed_count = 0

            for downloader in cached_downloaders:
                if hasattr(downloader, 'fail_time'):
                    if downloader.fail_time == 0:
                        verified_count += 1
                    else:
                        failed_count += 1

            logger.add_log(f"Initial downloader status: {verified_count} verified, {failed_count} failed")
            logger.add_log("Initial downloader cache sync completed")

        print("=== 初始下载器缓存同步完成 ===")

    except Exception as e:
        print(f"Error during initial downloader cache sync: {e}")
        # 不重新抛出异常，避免影响服务器启动


async def _load_initial_downloaders(app: FastAPI):
    """
    初始加载所有启用的下载器（复用full_sync逻辑）

    Args:
        app: FastAPI 应用实例
    """
    print("=== 开始加载初始下载器数据 ===")
    try:
        # 调用完整同步方法，跳过缓存对比（因为初始时缓存为空）
        await _perform_initial_full_sync(app, skip_cache_comparison=True)
        print("=== 初始下载器数据加载完成 ===")
    except Exception as e:
        print(f"Error during initial downloader loading: {e}")
        raise


def _refresh_cached_downloader_fields(cached_downloaders, db_downloaders, logger=None):
    """
    刷新缓存下载器的字段值（如torrent_save_path）

    Args:
        cached_downloaders: 缓存中的下载器列表
        db_downloaders: 数据库中的下载器列表
        logger: TaskLogger实例（可选）

    Returns:
        更新的下载器数量
    """
    # 防御性检查
    if not cached_downloaders or not db_downloaders:
        return 0

    db_by_id = {d.get('downloader_id'): d for d in db_downloaders if d.get('downloader_id')}
    db_by_nickname = {d.get('nickname'): d for d in db_downloaders if d.get('nickname')}
    updated = 0

    for cached in cached_downloaders:
        db_row = None
        cached_id = getattr(cached, 'downloader_id', None)

        if cached_id and cached_id in db_by_id:
            db_row = db_by_id.get(cached_id)
        else:
            cached_nick = getattr(cached, 'nickname', None)
            if cached_nick in db_by_nickname:
                db_row = db_by_nickname.get(cached_nick)

        if not db_row:
            continue

        db_save_path = db_row.get('torrent_save_path')
        if db_save_path and db_save_path.strip():
            if getattr(cached, 'torrent_save_path', None) != db_save_path:
                try:
                    cached.torrent_save_path = db_save_path
                    updated += 1
                except Exception:
                    continue

    if logger:
        logger.debug(f"Refreshed torrent_save_path for {updated} cached downloaders")

    return updated


async def _perform_initial_full_sync(app: FastAPI, skip_cache_comparison: bool = False):
    """
    系统首次启动时执行一次全局下载器同步任务

    Args:
        app: FastAPI 应用实例
        skip_cache_comparison: 是否跳过缓存对比（用于初始加载时优化性能）
    """
    from app.tasks.logger import TaskLogger

    try:
        async with TaskLogger("initial_full_sync", task_type=4) as logger:
            logger.add_log("Starting initial full sync on system startup")

            # 获取数据库中所有启用的下载器
            from sqlalchemy import text
            db = SessionLocal()

            try:
                sql = """
                SELECT downloader_id, host, nickname, username, status, enabled, is_search,
                       downloader_type, port, password, is_ssl, torrent_save_path
                FROM bt_downloaders
                WHERE enabled = true AND dr = 0
                """
                result = db.execute(text(sql))
                db_downloaders = [row._asdict() for row in result]

                logger.add_log(f"Found {len(db_downloaders)} downloaders in database")

                if not db_downloaders:
                    logger.add_log("No enabled downloaders found in database")
                    return

                # 根据参数决定是否进行缓存对比
                if skip_cache_comparison:
                    # 跳过缓存对比，直接处理所有下载器（适用于初始加载）
                    logger.add_log("Skipping cache comparison, processing all downloaders")
                    new_downloaders = db_downloaders
                    orphaned_downloaders = []
                    cached_downloaders = []  # 初始化为空列表，避免变量未定义错误
                else:
                    # 进行缓存对比（适用于常规同步）
                    # 获取当前缓存中的下载器
                    cached_downloaders = await app.state.store.get_snapshot()
                    _refresh_cached_downloader_fields(cached_downloaders, db_downloaders, logger)
                    cached_nickname_set = {d.nickname for d in cached_downloaders}
                    db_nickname_set = {d['nickname'] for d in db_downloaders}

                    # 找出在数据库中但不在缓存中的下载器
                    new_downloaders = [d for d in db_downloaders if d['nickname'] not in cached_nickname_set]

                    # 找出在缓存中但不在数据库中的下载器（可能是已删除的）
                    orphaned_downloaders = [d for d in cached_downloaders if d.nickname not in db_nickname_set]

                    logger.add_log(f"New downloaders to check: {len(new_downloaders)}")
                    logger.add_log(f"Orphaned downloaders in cache: {len(orphaned_downloaders)}")

                # 处理新下载器
                successful_additions = 0
                failed_additions = 0

                for downloader_data in new_downloaders:
                    try:
                        logger.add_log(f"Processing downloader: {downloader_data['nickname']}")
                        await _check_and_add_new_downloader(app, downloader_data)
                        successful_additions += 1
                        logger.add_log(f"Successfully processed downloader: {downloader_data['nickname']}")
                    except Exception as e:
                        failed_additions += 1
                        logger.add_log(f"Failed to process downloader {downloader_data['nickname']}: {e}")

                # 处理孤立的下载器（从缓存中移除）
                if orphaned_downloaders:
                    logger.add_log(f"Removing {len(orphaned_downloaders)} orphaned downloaders from cache")
                    await app.state.store._remove_items(orphaned_downloaders)
                    for orphan in orphaned_downloaders:
                        logger.add_log(f"Removed orphaned downloader: {orphan.nickname}")

                # 记录同步结果
                if skip_cache_comparison:
                    logger.add_log(
                        f"Initial loading summary: {successful_additions} processed, {failed_additions} failed")
                else:
                    logger.add_log(
                        f"Initial sync summary: {successful_additions} added, {failed_additions} failed, {len(orphaned_downloaders)} removed")

                # ✅ 修复：等待所有缓冲区数据处理完成
                max_wait = 10  # 最多等待10秒
                wait_count = 0
                while app.state.store._buffer and wait_count < max_wait:
                    await asyncio.sleep(1)
                    wait_count += 1

                if wait_count >= max_wait:
                    logger.add_log(f"⚠️ 缓冲区处理超时，剩余 {len(app.state.store._buffer)} 个下载器未处理")
                else:
                    logger.add_log(f"✅ 缓冲区处理完成，等待时间: {wait_count} 秒")

                # ✅ 诊断：输出最终缓存状态
                final_cache = await app.state.store.get_snapshot()
                logger.add_log(f"📊 最终缓存状态: {len(final_cache)} 个下载器")
                for downloader in final_cache:
                    logger.add_log(f"   - {downloader.nickname} (fail_time={downloader.fail_time})")

                logger.add_log("Initial full sync completed successfully")

            except Exception as e:
                logger.add_log(f"Error during initial full sync: {e}")
                raise
            finally:
                db.close()

    except Exception as e:
        print(f"Error during initial full sync: {e}")


async def full_database_sync_task():
    """定时全量获取数据库下载器列表，与缓存对比并进行连通性校验"""
    from sqlalchemy import text
    from app.tasks.logger import TaskLogger

    # 动态调整同步间隔的配置
    default_interval = 600  # 默认10分钟
    max_interval = 3600  # 最大1小时
    min_interval = 300  # 最小5分钟

    # 首次执行时先等待一段时间
    await asyncio.sleep(60)  # 首次启动等待1分钟

    while True:
        try:
            # 获取上次同步的成功率和时间，动态调整间隔
            current_interval = _calculate_sync_interval(default_interval, min_interval, max_interval)

            async with TaskLogger("full_database_sync", task_type=4) as logger:
                logger.add_log(f"Starting full database sync with interval: {current_interval}s")

                logger.add_log("Acquiring database connection")
                db = SessionLocal()

                try:
                    # 查询数据库中所有启用的下载器
                    sql = """
                    SELECT downloader_id, host, nickname, username, status, enabled, is_search,
                           downloader_type, port, password, is_ssl, torrent_save_path
                    FROM bt_downloaders
                    WHERE enabled = true AND dr = 0
                    """
                    result = db.execute(text(sql))
                    db_downloaders = [row._asdict() for row in result]

                    logger.add_log(f"Found {len(db_downloaders)} downloaders in database")

                    if not db_downloaders:
                        logger.add_log("No enabled downloaders found in database")
                        continue

                    # 获取当前缓存中的下载器（需要上锁保护）
                    logger.add_log("Acquiring cache lock for reading")
                    cached_downloaders = await app.state.store.get_snapshot()
                    _refresh_cached_downloader_fields(cached_downloaders, db_downloaders, logger)
                    logger.add_log("Cache snapshot acquired successfully")

                    cached_nickname_set = {d.nickname for d in cached_downloaders}
                    db_nickname_set = {d['nickname'] for d in db_downloaders}

                    # 找出在数据库中但不在缓存中的下载器
                    new_downloaders = [d for d in db_downloaders if d['nickname'] not in cached_nickname_set]

                    # 找出在缓存中但不在数据库中的下载器（可能是已删除的）
                    orphaned_downloaders = [d for d in cached_downloaders if d.nickname not in db_nickname_set]

                    logger.add_log(f"New downloaders to check: {len(new_downloaders)}")
                    logger.add_log(f"Orphaned downloaders in cache: {len(orphaned_downloaders)}")

                    # 处理新下载器
                    successful_additions = 0
                    failed_additions = 0

                    for downloader_data in new_downloaders:
                        try:
                            logger.add_log(f"Processing new downloader: {downloader_data['nickname']}")
                            await _check_and_add_new_downloader(app, downloader_data)
                            successful_additions += 1
                            logger.add_log(f"Successfully added downloader: {downloader_data['nickname']}")
                        except Exception as e:
                            failed_additions += 1
                            logger.add_log(f"Failed to add downloader {downloader_data['nickname']}: {e}")

                    # 处理孤立的下载器（可选：从缓存中移除）
                    if orphaned_downloaders:
                        logger.add_log(f"Found {len(orphaned_downloaders)} orphaned downloaders in cache")
                        # 这里可以选择是否移除孤立的下载器
                        # logger.add_log("Removing orphaned downloaders from cache")
                        # await app.state.store._remove_items(orphaned_downloaders)

                    # 记录同步结果
                    logger.add_log(f"Sync summary: {successful_additions} added, {failed_additions} failed")
                    logger.add_log("Full database sync task completed successfully")

                    # 更新同步统计信息
                    await _update_sync_statistics(successful_additions, failed_additions)

                except Exception as e:
                    logger.add_log(f"Error during full database sync: {e}")
                    raise
                finally:
                    db.close()

            # 在TaskLogger上下文外部进行睡眠，避免重复等待
            await asyncio.sleep(current_interval)

        except Exception as e:
            print(f"Error in full database sync task: {e}")
            await asyncio.sleep(default_interval)  # 出错时使用默认间隔重试


def _calculate_sync_interval(default_interval: int, min_interval: int, max_interval: int) -> int:
    """根据历史记录计算动态同步间隔（同步函数，避免异步循环问题）"""
    try:
        # 简单的基于内存统计的间隔调整
        global _sync_stats

        total = _sync_stats['total_additions'] + _sync_stats['total_failures']

        if total == 0:
            return default_interval

        success_rate = (_sync_stats['total_additions'] / total) * 100

        if success_rate >= 90:  # 成功率很高，可以延长间隔
            return min(max_interval, int(default_interval * 1.5))
        elif success_rate >= 70:  # 成功率中等，保持默认间隔
            return default_interval
        elif success_rate >= 50:  # 成功率较低，缩短间隔
            return max(min_interval, int(default_interval * 0.7))
        else:  # 成功率很低，大幅缩短间隔
            return max(min_interval, int(default_interval * 0.5))

    except Exception as e:
        print(f"Error calculating sync interval: {e}")
        return default_interval


# 简单的内存统计存储（生产环境建议使用Redis或数据库）
_sync_stats = {
    'total_additions': 0,
    'total_failures': 0,
    'last_update': None
}

# 种子同步统计存储
_torrent_sync_stats = {
    'total_successful': 0,
    'total_failed': 0,
    'last_duration': 0,
    'avg_duration': 0,
    'last_update': None
}


def _calculate_torrent_sync_interval(default_interval: int, min_interval: int, max_interval: int) -> int:
    """根据历史执行时间和成功率计算动态同步间隔"""
    try:
        global _torrent_sync_stats

        total = _torrent_sync_stats['total_successful'] + _torrent_sync_stats['total_failed']

        if total == 0:
            return default_interval

        success_rate = (_torrent_sync_stats['total_successful'] / total) * 100
        avg_duration = _torrent_sync_stats['avg_duration']

        # 根据成功率和平均执行时间动态调整间隔
        if success_rate >= 90 and avg_duration < 300:  # 成功率高且执行时间短
            return min(max_interval, int(default_interval * 1.5))
        elif success_rate >= 70:  # 成功率中等
            return default_interval
        elif success_rate >= 50:  # 成功率较低
            return max(min_interval, int(default_interval * 0.8))
        else:  # 成功率很低
            return max(min_interval, int(default_interval * 0.6))

    except Exception as e:
        print(f"Error calculating torrent sync interval: {e}")
        return default_interval


async def _update_torrent_sync_statistics(successful: int, failed: int):
    """更新种子同步统计信息（保持向后兼容）"""
    await _update_torrent_sync_statistics_with_duration(successful, failed, 0)


async def _update_torrent_sync_statistics_with_duration(successful: int, failed: int, duration: int):
    """更新种子同步统计信息，包含实际执行时间"""
    global _torrent_sync_stats

    _torrent_sync_stats['total_successful'] += successful
    _torrent_sync_stats['total_failed'] += failed
    _torrent_sync_stats['last_duration'] = duration
    _torrent_sync_stats['last_update'] = datetime.now()

    # 使用实际执行时间计算移动平均
    if duration > 0:  # 只有当提供了实际执行时间时才更新平均值
        if _torrent_sync_stats['avg_duration'] == 0:
            _torrent_sync_stats['avg_duration'] = duration
        else:
            # 使用指数移动平均，权重0.3给新的执行时间
            _torrent_sync_stats['avg_duration'] = int(
                (_torrent_sync_stats['avg_duration'] * 0.7) + (duration * 0.3)
            )

    # 定期清理统计信息（每天重置一次）
    import time
    current_time = time.time()
    if not hasattr(_update_torrent_sync_statistics_with_duration, 'last_reset'):
        _update_torrent_sync_statistics_with_duration.last_reset = current_time

    # 如果距离上次重置超过24小时，则重置统计
    if current_time - _update_torrent_sync_statistics_with_duration.last_reset > 86400:  # 24小时 = 86400秒
        _torrent_sync_stats['total_successful'] = 0
        _torrent_sync_stats['total_failed'] = 0
        _torrent_sync_stats['avg_duration'] = 0
        _torrent_sync_stats['last_duration'] = 0
        _update_torrent_sync_statistics_with_duration.last_reset = current_time


async def _update_sync_statistics(successful: int, failed: int):
    """更新同步统计信息"""
    global _sync_stats

    _sync_stats['total_additions'] += successful
    _sync_stats['total_failures'] += failed
    _sync_stats['last_update'] = datetime.now()

    # 定期清理统计信息（每天重置一次）
    import time
    current_time = time.time()
    if not hasattr(_update_sync_statistics, 'last_reset'):
        _update_sync_statistics.last_reset = current_time

    # 如果距离上次重置超过24小时，则重置统计
    if current_time - _update_sync_statistics.last_reset > 86400:  # 24小时 = 86400秒
        _sync_stats['total_additions'] = 0
        _sync_stats['total_failures'] = 0
        _update_sync_statistics.last_reset = current_time


async def _is_downloader_duplicate(app: FastAPI, host: str, port: Any) -> bool:
    """
    检查指定 host:port 组合的下载器是否已存在

    Args:
        app: FastAPI 应用实例
        host: 下载器主机地址
        port: 下载器端口

    Returns:
        bool: 如果存在重复返回 True，否则返回 False
    """
    try:
        # 获取当前数据快照
        current_downloaders = await app.state.store.get_snapshot()

        # 遍历检查是否有相同的 host:port 组合
        for downloader in current_downloaders:
            if hasattr(downloader, 'host') and hasattr(downloader, 'port'):
                # 将 port 转换为字符串进行比较，避免类型不一致问题
                existing_host = str(downloader.host) if downloader.host is not None else ""
                existing_port = str(downloader.port) if downloader.port is not None else ""
                new_host = str(host) if host is not None else ""
                new_port = str(port) if port is not None else ""

                if existing_host == new_host and existing_port == new_port:
                    return True

        return False

    except Exception as e:
        print(f"Error checking downloader duplicate for {host}:{port}: {e}")
        # 出现异常时保守处理，认为可能存在重复
        return True


async def _check_and_add_new_downloader(app: FastAPI, downloader_data: Dict[str, Any], immediate: bool = False):
    """
    检查新下载器的连通性（使用分层检查 + 重试机制），如果通过则添加到缓存

    分层检查流程：
    1. 端口连通性检查（socket.connect，3秒超时 × 3次重试）
    2. 认证检查（客户端库自带超时 × 3次重试）

    Args:
        app: FastAPI 应用实例
        downloader_data: 下载器数据字典
        immediate: 是否立即写入缓存（绕过缓冲区）
    """
    from app.utils.encryption import decrypt_password

    try:
        nickname = downloader_data.get('nickname', 'Unknown')
        logger.debug(f"\n{'=' * 60}")
        logger.debug(f"开始处理下载器: {nickname}")
        logger.debug(f"{'=' * 60}")

        # ✅ 清理 host 字段（移除协议前缀和路径）
        original_host = downloader_data.get('host', '')
        clean_host = _clean_host_url(original_host)
        downloader_data['host'] = clean_host  # 更新为清理后的值

        # 如果 host 被清理过，记录日志
        if clean_host != original_host:
            logger.info(f"🧹 清理 host 字段: {original_host} → {clean_host}")

        # 检查 host:port 组合是否已存在
        if await _is_downloader_duplicate(app, clean_host, downloader_data['port']):
            logger.warning(f"⚠️  下载器 host:port {clean_host}:{downloader_data['port']} 已存在，跳过添加")
            return False

        # 类型转换：确保端口是整数并验证范围
        try:
            port_int = int(downloader_data['port'])
            # ✅ 验证端口号范围（1-65535）
            if not (1 <= port_int <= 65535):
                logger.warning(f"❌ 端口号超出有效范围 (1-65535): {port_int}，跳过添加下载器 {nickname}")
                return False
        except (ValueError, TypeError):
            logger.warning(f"❌ 无效的端口号: {downloader_data['port']}，跳过添加下载器 {nickname}")
            return False

        # 第一步：端口连通性检查（3秒超时 × 3次重试）
        logger.debug(f"[第一步] 检查端口连通性: {clean_host}:{port_int}")
        port_accessible = await check_port_connectivity(
            host=clean_host,  # ✅ 使用清理后的 host
            port=port_int,
            timeout=3.0,
            max_retries=3
        )

        if not port_accessible:
            logger.warning(f"⚠️  下载器 {nickname} 端口不可达（{clean_host}:{port_int}），跳过添加")
            return False

        # 第二步：认证检查
        logger.debug(f"[第二步] 开始认证检查...")

        # 解密密码
        decrypted_password = decrypt_password(downloader_data['password']) if downloader_data.get('password') else None

        # 准备下载器类型信息
        # ✅ 修复：兼容整数和字符串类型（数据库查询可能返回字符串 "0"/"1"）
        downloader_type_raw = downloader_data.get('downloader_type')

        # 尝试转换为整数
        try:
            downloader_type_int = int(downloader_type_raw)
        except (ValueError, TypeError):
            logger.warning(
                f"❌ 下载器类型值无效: {downloader_type_raw} (类型: {type(downloader_type_raw).__name__})，"
                f"跳过添加下载器 {nickname}"
            )
            return False

        # 验证类型值是否在有效范围内
        if downloader_type_int == 0:
            downloader_type_str = 'qBittorrent'
        elif downloader_type_int == 1:
            downloader_type_str = 'Transmission'
        else:
            logger.warning(
                f"❌ 不支持的下载器类型: {downloader_type_int}，"
                f"跳过添加下载器 {nickname}"
            )
            return False

        # 构建下载器信息字典（用于认证检查）
        downloader_info = {
            'nickname': nickname,
            'host': downloader_data['host'],
            'port': port_int,
            'downloader_type': downloader_type_str,
            'username': downloader_data.get('username'),
            'password': decrypted_password
        }

        # 执行认证检查（最多3次重试）
        auth_success = False
        for auth_attempt in range(1, 4):
            try:
                logger.debug(f"尝试认证检查 ({auth_attempt}/3)...")

                if downloader_type_str == 'qBittorrent':
                    auth_success = await _check_qbittorrent_auth_with_retry(downloader_info, auth_attempt, 3)
                elif downloader_type_str == 'Transmission':
                    auth_success = await _check_transmission_auth_with_retry(downloader_info, auth_attempt, 3)

                if auth_success:
                    break
                else:
                    if auth_attempt < 3:
                        print(f"等待 1 秒后重试...")
                        await asyncio.sleep(1)
                    else:
                        print(f"❌ 认证检查失败，已重试 3 次")

            except Exception as e:
                print(f"❌ 认证检查异常 (尝试 {auth_attempt}/3): {e}")
                if auth_attempt < 3:
                    print(f"等待 1 秒后重试...")
                    await asyncio.sleep(1)
                else:
                    print(f"❌ 认证检查失败，已重试 3 次")
                    break

        # 根据检查结果决定是否添加到缓存
        if auth_success:
            # 认证成功，创建客户端并添加到缓存
            logger.debug(f"✅ 下载器 {nickname} 检查通过，正在添加到缓存...")

            try:
                # 创建客户端连接
                if downloader_type_int == 0:
                    client = qbClient(
                        host=downloader_data['host'],
                        port=port_int,
                        username=downloader_data.get('username'),
                        password=decrypted_password,
                        VERIFY_WEBUI_CERTIFICATE=False,
                        REQUESTS_ARGS={'timeout': 30}
                    )
                elif downloader_type_int == 1:
                    protocol = "https" if downloader_data.get('is_ssl') == "1" else "http"
                    client = trClient(
                        host=downloader_data['host'],
                        username=downloader_data.get('username'),
                        password=decrypted_password,
                        port=port_int,
                        protocol=protocol,
                        timeout=30.0
                    )
                else:
                    logger.warning(f"❌ 不支持的下载器类型: {downloader_type_int}，跳过添加下载器 {nickname}")
                    return False

                # 创建种子统计缓存
                stats_cache = TorrentStatsCache(
                    downloader_id=downloader_data.get('downloader_id'),
                    full_sync_interval=3600,  # 每小时全量同步
                    cache_ttl=7200  # 缓存2小时
                )

                # 创建校验对象
                check_vo = DownloaderCheckVO(
                    nickname=nickname,
                    client=client,
                    fail_time=0,
                    downloader_id=downloader_data.get('downloader_id'),
                    host=downloader_data['host'],
                    port=port_int,
                    username=downloader_data.get('username'),
                    password=decrypted_password,
                    downloader_type=downloader_type_int,
                    torrent_save_path=downloader_data.get('torrent_save_path'),
                    stats_cache=stats_cache  # 添加缓存
                )

                # 添加到缓存
                await app.state.store.add(check_vo, immediate=immediate)
                logger.info(f"✅ 下载器 {nickname} 已成功添加到缓存")

                # ✅ 修复：仅在缓冲区模式下等待处理完成（解决异步时序问题）
                if not immediate:
                    await asyncio.sleep(0.5)  # 给缓冲区处理留出时间（0.5秒足够）

                return True  # ✅ 返回成功标志

            except Exception as e:
                logger.error(f"❌ 添加下载器 {nickname} 到缓存时出错: {e}")
                import traceback
                traceback.print_exc()
                return False
        else:
            logger.warning(f"⚠️  下载器 {nickname} 认证失败，未添加到缓存")
            return False

    except Exception as e:
        logger.error(f"❌ 检查新下载器 {downloader_data.get('nickname', 'Unknown')} 时出错: {e}")
        import traceback
        traceback.print_exc()
        return False


async def periodic_check():
    """定时校验任务"""
    while True:
        await asyncio.sleep(10)  # 使用异步睡眠
        await app.state.store.check_and_remove_invalid()


# 注意：原来的 cached_downloader_sync_task() 方法已被重构为独立的任务类
# app.tasks.scheduler.downloader_cache_sync.CachedDownloaderSyncTask
# 保留此注释以防有其他代码引用该方法


# ============================================================
# 下载器状态轮询任务（新增）
# ============================================================

async def downloader_status_polling_task(app: FastAPI):
    """
    定时轮询所有下载器状态并更新到缓存（热冷数据分离）

    - 热数据（速度、连接状态）：10秒更新一次
    - 冷数据（种子统计）：60秒更新一次

    Args:
        app: FastAPI 应用实例
    """
    import time

    hot_poll_interval = 10  # 热数据轮询间隔（秒）
    cold_poll_interval = 60  # 冷数据轮询间隔（秒）

    print(f"=== 下载器状态轮询任务已启动（热数据{hot_poll_interval}秒，冷数据{cold_poll_interval}秒） ===")

    cold_update_counter = 0  # 冷数据更新计数器

    while True:
        try:
            # ✅ P0-1修复: 添加防御性检查，确保缓存已初始化
            if not hasattr(app, 'state') or not hasattr(app.state, 'store') or app.state.store is None:
                print(f"[状态轮询] ⚠️ 缓存服务未初始化，等待 {hot_poll_interval} 秒后重试")
                await asyncio.sleep(hot_poll_interval)
                continue

            # 获取当前缓存中的所有下载器
            cached_downloaders = await app.state.store.get_snapshot()

            if not cached_downloaders:
                print(f"[状态轮询] 缓存中无下载器，等待 {hot_poll_interval} 秒后重试")
                await asyncio.sleep(hot_poll_interval)
                continue

            # 判断本次是否需要更新冷数据
            update_cold = (cold_update_counter % (cold_poll_interval // hot_poll_interval)) == 0
            cold_update_counter += 1

            logger.debug(
                f"[状态轮询] 开始更新 {len(cached_downloaders)} 个下载器 (热数据: 是, 冷数据: {'是' if update_cold else '否'})")

            # ✅ P1-1修复: 并发更新所有下载器状态（增加并发限制）
            update_tasks = []
            for downloader in cached_downloaders:
                # 只更新已通过验证的下载器（fail_time = 0）
                if hasattr(downloader, 'fail_time') and downloader.fail_time == 0:
                    update_tasks.append(_update_downloader_status(downloader, update_cold=update_cold))

            # 并发执行所有更新任务并记录总耗时
            import time
            start_time = time.time()

            if update_tasks:
                # ✅ P1-1修复: 使用信号量限制并发数量（最多5个并发）
                semaphore = asyncio.Semaphore(5)

                async def bounded_update(task):
                    """带并发限制的任务包装器"""
                    async with semaphore:
                        return await task

                # 创建有界任务
                bounded_tasks = [bounded_update(task) for task in update_tasks]

                # 执行所有任务
                results = await asyncio.gather(*bounded_tasks, return_exceptions=True)

                # ✅ P1-1修复: 更安全的异常统计
                success_count = 0
                error_count = 0
                for r in results:
                    if isinstance(r, Exception):
                        error_count += 1
                        # 记录具体异常类型，便于调试
                        print(f"[状态轮询] ⚠️ 任务异常: {type(r).__name__}: {r}")
                    elif r is True:
                        success_count += 1
                    else:
                        # 处理未预期的返回值
                        error_count += 1
                        print(f"[状态轮询] ⚠️ 未预期的返回值: {r}")

                # 统计耗时
                elapsed = time.time() - start_time
                logger.debug(
                    f"[状态轮询] 状态更新完成 (耗时: {elapsed:.2f}秒, 成功: {success_count}, 失败: {error_count})")

                # 警告：如果单次轮询超过热数据间隔，说明冷数据拖慢了整体进度
                if update_cold and elapsed > hot_poll_interval:
                    logger.debug(
                        f"[状态轮询] ⚠️ 警告：冷数据更新耗时({elapsed:.2f}秒)超过了热数据间隔({hot_poll_interval}秒)")

        except Exception as e:
            print(f"[状态轮询] 任务执行异常: {e}")
            import traceback
            traceback.print_exc()

        # 等待下次轮询（固定10秒）
        await asyncio.sleep(hot_poll_interval)


async def _update_downloader_status(downloader: Any, update_cold: bool = False) -> bool:
    """更新单个下载器的状态（热冷数据分离 + 延迟测试 + 端口连通性检查）

    Args:
        downloader: 下载器对象
        update_cold: 是否更新冷数据（种子统计），默认False

    Returns:
        bool: 更新是否成功
    """
    import time
    import ping3

    try:
        downloader_type = getattr(downloader, 'downloader_type', None)
        nickname = getattr(downloader, 'nickname', 'Unknown')
        host = getattr(downloader, 'host', None)
        port = getattr(downloader, 'port', None)

        if not host or not port:
            print(f"[状态更新] {nickname}: 缺少host或port信息")
            return False

        start_time = time.time()

        # ========== 1. 测试网络延迟（每次都测试） ==========
        try:
            if "127.0.0.1" in host or "localhost" in host:
                delay = 1.0  # 本地固定为1ms
            else:
                # 异步执行ping操作，超时3秒
                delay_result = await asyncio.to_thread(ping3.ping, host, 3, "ms", "0.0.0.0", seq=2)

                # ✅ P1-2修复: 更安全地转换延迟值，处理所有可能的异常情况（避免panic）
                try:
                    if delay_result is None or delay_result is False:
                        delay = None
                    elif isinstance(delay_result, (int, float)):
                        # 验证延迟值在合理范围内
                        delay = float(delay_result)
                        # 检查延迟值是否合理（0-30秒）
                        if delay < 0 or delay > 30000:
                            print(f"[状态更新] {nickname}: ⚠️ 延迟值超出合理范围: {delay}ms")
                            delay = None
                    else:
                        # 尝试转换其他类型（如字符串）
                        delay = float(delay_result)
                        # 再次验证范围
                        if delay < 0 or delay > 30000:
                            print(f"[状态更新] {nickname}: ⚠️ 延迟值超出合理范围: {delay}ms")
                            delay = None
                except (ValueError, TypeError, OverflowError) as e:
                    # 处理各种转换异常
                    print(
                        f"[状态更新] {nickname}: ⚠️ 延迟值转换失败: {e}, 原始值: {delay_result}, 类型: {type(delay_result)}")
                    delay = None
            downloader.delay = delay
        except Exception as e:
            print(f"[状态更新] {nickname}: 延迟测试失败 - {e}")
            downloader.delay = None

        # ========== 2. 检查端口连通性（判断是否在线） ==========
        try:
            # 安全地转换端口号，验证范围
            try:
                port_int = int(port)
                if not (1 <= port_int <= 65535):
                    print(f"[状态更新] {nickname}: 端口号超出有效范围(1-65535): {port}")
                    downloader.is_online = False
                    downloader.upload_speed = 0
                    downloader.download_speed = 0
                    downloader.last_update = time.time()
                    return True
            except (ValueError, TypeError) as e:
                print(f"[状态更新] {nickname}: 端口号无效: {port} - {e}")
                downloader.is_online = False
                downloader.upload_speed = 0
                downloader.download_speed = 0
                downloader.last_update = time.time()
                return True

            is_online = await check_port_connectivity(host, port_int, timeout=3.0, max_retries=1)
            downloader.is_online = is_online

            if not is_online:
                print(f"[状态更新] {nickname}: 端口{port}不可达，跳过状态更新")
                downloader.upload_speed = 0
                downloader.download_speed = 0
                downloader.last_update = time.time()
                return True  # 端口不通也算更新成功（状态已标记为离线）

        except Exception as e:
            print(f"[状态更新] {nickname}: 端口连通性检查失败 - {e}")
            downloader.is_online = False
            downloader.upload_speed = 0
            downloader.download_speed = 0
            downloader.last_update = time.time()
            return True

        # ========== 3. 获取下载器状态（仅在在线时） ==========
        if downloader_type == 0:
            # qBittorrent
            status_data = await _get_qbittorrent_status(downloader, update_cold=update_cold)
        elif downloader_type == 1:
            # Transmission
            status_data = await _get_transmission_status(downloader, update_cold=update_cold)
        else:
            print(f"[状态更新] 不支持的下载器类型: {downloader_type}")
            return False

        # ========== 4. 更新下载器对象的状态字段 ==========
        # 确保status_data包含有效数据
        if status_data and isinstance(status_data, dict) and len(status_data) > 0:
            downloader.upload_speed = status_data.get('upload_speed', 0) or 0
            downloader.download_speed = status_data.get('download_speed', 0) or 0

            # 仅在更新冷数据时才更新种子统计
            if update_cold:
                downloader.downloading_count = status_data.get('downloading_count', 0) or 0
                downloader.seeding_count = status_data.get('seeding_count', 0) or 0

            downloader.last_update = time.time()

            elapsed = time.time() - start_time

            # 根据是否更新冷数据，输出不同的日志
            delay_str = f"{delay:.1f}ms" if delay else "N/A"
            if update_cold:
                logger.debug(f"[状态更新] {nickname} (含冷数据): "
                             f"延迟={delay_str}, "
                             f"上传={status_data.get('upload_speed')} KB/s, "
                             f"下载={status_data.get('download_speed')} KB/s, "
                             f"下载中={status_data.get('downloading_count')}, "
                             f"做种中={status_data.get('seeding_count')}, "
                             f"耗时={elapsed:.2f}秒")
            else:
                logger.debug(f"[状态更新] {nickname} (仅热数据): "
                             f"延迟={delay_str}, "
                             f"上传={status_data.get('upload_speed')} KB/s, "
                             f"下载={status_data.get('download_speed')} KB/s, "
                             f"耗时={elapsed:.2f}秒")

            return True
        else:
            print(f"[状态更新] {nickname}: 获取到的状态数据无效")
            return False

    except Exception as e:
        print(f"[状态更新] 更新下载器 {getattr(downloader, 'nickname', 'Unknown')} 状态失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# 智能种子统计更新（分片 + 增量/全量）
# ============================================================

async def update_torrent_stats_smart(
        downloader: Any,
        force_full_sync: bool = False
) -> dict:
    """智能种子统计更新（支持分片和增量更新）

    核心特性：
    1. 全量更新：每隔1小时或首次运行
    2. 增量更新：使用 'recently-active' 获取变更的种子
    3. 分片获取：每批最多200个种子
    4. 使用 hash 而不是 id（hash 已持久化）

    职责说明：
    - 本函数仅用于仪表盘统计（显示"下载中X个、做种中Y个"）
    - 不负责同步完整的种子数据到数据库
    - 完整数据同步由 TorrentSyncTask → qb_add_torrents_async 负责

    Args:
        downloader: 下载器对象
        force_full_sync: 强制全量统计

    Returns:
        统计结果：{
            'downloading_count': int,
            'seeding_count': int,
            'sync_mode': 'full' | 'incremental',
            'elapsed': float,
            'from_cache': bool
        }
    """
    from app.downloader.torrent_fetcher import TorrentFetcher

    client = downloader.client
    downloader_type = downloader.downloader_type
    nickname = downloader.nickname

    # 获取缓存管理器（如果不存在则创建）
    if not hasattr(downloader, 'stats_cache') or downloader.stats_cache is None:
        from app.downloader.torrent_stats_cache import TorrentStatsCache
        downloader.stats_cache = TorrentStatsCache(
            downloader_id=downloader.downloader_id or "unknown",
            full_sync_interval=3600,
            cache_ttl=7200
        )

    cache = downloader.stats_cache

    import time
    import logging
    logger = logging.getLogger(__name__)

    start_time = time.time()

    # ========== 判断是否需要全量统计 ==========
    should_full_sync = (
            force_full_sync or
            cache.should_full_sync()
    )

    sync_mode = 'full' if should_full_sync else 'incremental'

    # 确定日志前缀（区分下载器类型）
    log_prefix = "[qb-统计]" if downloader_type == 0 else "[tr-统计]"

    try:
        # ========== Transmission 统计逻辑 ==========
        if downloader_type == 1:  # Transmission
            if should_full_sync:
                # 全量统计：分片获取所有种子
                logger.debug(f"{log_prefix} {nickname}：开始种子统计（全量模式）")

                all_torrents = await asyncio.to_thread(
                    TorrentFetcher.get_transmission_torrents_batch,
                    client,
                    torrent_hashes=None,  # 全量
                    batch_size=200  # 每批200个
                )

                # 更新缓存
                cache.update_cache(all_torrents)
                cache.mark_full_sync()

                # 全量统计结果（INFO级别）
                elapsed = time.time() - start_time
                logger.info(
                    f"{log_prefix} {nickname}：统计完成：获取{len(all_torrents)}个，"
                    f"下载中={cache.get_stats()['downloading']}，"
                    f"做种中={cache.get_stats()['seeding']}，"
                    f"耗时={elapsed:.2f}秒"
                )

            else:
                # 增量统计：使用 'recently-active'
                logger.debug(f"{log_prefix} {nickname}：开始种子统计（增量模式）")

                try:
                    # Transmission 特性：获取最近活动的种子
                    active_torrents, removed_ids = await asyncio.to_thread(
                        TorrentFetcher.get_transmission_recently_active,
                        client
                    )

                    if active_torrents:
                        # 更新活动的种子
                        cache.update_cache(active_torrents)

                    # 增量统计结果（DEBUG级别）
                    elapsed = time.time() - start_time
                    logger.debug(
                        f"{log_prefix} {nickname}：统计完成：更新{len(active_torrents)}个，"
                        f"下载中={cache.get_stats()['downloading']}，"
                        f"做种中={cache.get_stats()['seeding']}，"
                        f"耗时={elapsed:.2f}秒"
                    )

                except Exception as e:
                    # 保留WARNING日志
                    logger.warning(
                        f"{log_prefix} {nickname}：增量统计失败，降级为全量：{e}"
                    )
                    # 降级为全量统计
                    return await update_torrent_stats_smart(
                        downloader,
                        force_full_sync=True
                    )

        # ========== qBittorrent 统计逻辑 ==========
        elif downloader_type == 0:  # qBittorrent
            if should_full_sync:
                # 全量统计：分页获取所有种子（不使用状态过滤）
                logger.debug(f"{log_prefix} {nickname}：开始种子统计（全量模式）")

                all_torrents = []
                offset = 0
                batch_size = 100  # 每批100个

                # 分页获取所有种子（不带 status_filter，避免重复统计）
                while True:
                    batch = await asyncio.to_thread(
                        TorrentFetcher.get_qbittorrent_torrents_batch,
                        client,
                        status_filter=None,  # 不过滤状态，获取所有种子
                        offset=offset,
                        limit=batch_size
                    )

                    if not batch:
                        break

                    all_torrents.extend(batch)
                    offset += len(batch)

                    # 防止无限循环
                    if len(batch) < batch_size:
                        break

                # 更新缓存
                cache.update_cache(all_torrents)
                cache.mark_full_sync()

                # 全量统计结果（INFO级别）
                elapsed = time.time() - start_time
                logger.info(
                    f"{log_prefix} {nickname}：统计完成：获取{len(all_torrents)}个，"
                    f"下载中={cache.get_stats()['downloading']}，"
                    f"做种中={cache.get_stats()['seeding']}，"
                    f"耗时={elapsed:.2f}秒"
                )

            else:
                # 增量统计：只获取 active 的种子
                logger.debug(f"{log_prefix} {nickname}：开始种子统计（增量模式）")

                active = await asyncio.to_thread(
                    TorrentFetcher.get_qbittorrent_torrents_batch,
                    client,
                    status_filter='active',  # 只获取活动的
                    limit=500  # 扩大限制
                )

                if active:
                    cache.update_cache(active)

                # 增量统计结果（DEBUG级别）
                elapsed = time.time() - start_time
                logger.debug(
                    f"{log_prefix} {nickname}：统计完成：更新{len(active)}个，"
                    f"下载中={cache.get_stats()['downloading']}，"
                    f"做种中={cache.get_stats()['seeding']}，"
                    f"耗时={elapsed:.2f}秒"
                )

        # ========== 返回统计结果 ==========
        stats = cache.get_stats()
        elapsed_total = time.time() - start_time

        return {
            'downloading_count': stats['downloading'],
            'seeding_count': stats['seeding'],
            'sync_mode': sync_mode,
            'elapsed': elapsed_total,
            'from_cache': False
        }

    except Exception as e:
        # 异常情况
        logger.error(f"{log_prefix} {nickname}：统计失败: {e}")
        import traceback
        traceback.print_exc()

        # 降级：返回缓存数据
        stats = cache.get_stats()
        elapsed_total = time.time() - start_time

        return {
            'downloading_count': stats['downloading'],
            'seeding_count': stats['seeding'],
            'sync_mode': 'cache',
            'elapsed': elapsed_total,
            'from_cache': True
        }


async def _get_qbittorrent_status(downloader: Any, update_cold: bool = False) -> dict:
    """获取 qBittorrent 下载器状态（热冷数据分离）

    Args:
        downloader: 下载器对象
        update_cold: 是否获取冷数据（种子统计），默认False

    Returns:
        dict: 包含热数据和可选冷数据的字典
    """
    try:
        client = downloader.client

        # 获取全局传输信息（热数据：速度）
        transfer_info = await asyncio.to_thread(client.transfer_info)

        result = {
            'upload_speed': transfer_info.get('up_info_speed', 0) / 1024,  # 转换为 KB/s
            'download_speed': transfer_info.get('dl_info_speed', 0) / 1024  # 转换为 KB/s
        }

        # 仅在需要时获取冷数据（使用智能更新）
        if update_cold:
            # 使用智能统计更新（分片 + 增量/全量）
            stats_result = await update_torrent_stats_smart(downloader, force_full_sync=False)

            result['downloading_count'] = stats_result.get('downloading_count', 0)
            result['seeding_count'] = stats_result.get('seeding_count', 0)

            # 添加调试信息
            logger.debug(
                f"  └─ qBittorrent冷数据获取: "
                f"下载中={result['downloading_count']}, "
                f"做种中={result['seeding_count']}, "
                f"模式={stats_result.get('sync_mode', 'unknown')}, "
                f"耗时={stats_result.get('elapsed', 0):.2f}秒"
            )
        else:
            # 不更新冷数据时，返回默认值0（或者可以返回上次的值）
            result['downloading_count'] = 0
            result['seeding_count'] = 0

        return result

    except Exception as e:
        print(f"[qBittorrent状态] 获取失败: {e}")
        import traceback
        traceback.print_exc()
        return {}


async def _get_transmission_status(downloader: Any, update_cold: bool = False) -> dict:
    """获取 Transmission 下载器状态（热冷数据分离）

    Args:
        downloader: 下载器对象
        update_cold: 是否获取冷数据（种子统计），默认False

    Returns:
        dict: 包含热数据和可选冷数据的字典
    """
    try:
        client = downloader.client

        # 获取会话统计信息（热数据：速度）
        session_stats = await asyncio.to_thread(client.session_stats)

        result = {
            'upload_speed': session_stats.upload_speed / 1024,  # 转换为 KB/s
            'download_speed': session_stats.download_speed / 1024  # 转换为 KB/s
        }

        # 仅在需要时获取冷数据（使用智能更新）
        if update_cold:
            # 使用智能统计更新（分片 + 增量/全量）
            stats_result = await update_torrent_stats_smart(downloader, force_full_sync=False)

            result['downloading_count'] = stats_result.get('downloading_count', 0)
            result['seeding_count'] = stats_result.get('seeding_count', 0)

            # 添加调试信息
            logger.debug(
                f"  └─ Transmission冷数据获取: "
                f"下载中={result['downloading_count']}, "
                f"做种中={result['seeding_count']}, "
                f"模式={stats_result.get('sync_mode', 'unknown')}, "
                f"耗时={stats_result.get('elapsed', 0):.2f}秒"
            )
        else:
            # 不更新冷数据时，返回默认值0（或者可以返回上次的值）
            result['downloading_count'] = 0
            result['seeding_count'] = 0

        return result

    except Exception as e:
        print(f"[Transmission状态] 获取失败: {e}")
        import traceback
        traceback.print_exc()
        return {}
