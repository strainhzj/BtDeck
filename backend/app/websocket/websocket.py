from fastapi import WebSocket,Request,HTTPException,status
from starlette.websockets import WebSocketDisconnect
from typing import List, Any, Dict
import time
from fastapi import APIRouter
import asyncio
from qbittorrentapi import Client, LoginFailed
import threading
from app.downloader import models
from contextlib import asynccontextmanager
from app.core.config import settings
from app.auth import utils
import ping3
from aiosqlite import connect, Connection
import logging  # P1-2 修复: 导入logging模块

router = APIRouter()

logger = logging.getLogger(__name__)

_original_ws_disconnect_init = WebSocketDisconnect.__init__


def _patched_ws_disconnect_init(self, *args, **kwargs):
    kwargs.pop("message", None)
    _original_ws_disconnect_init(self, *args, **kwargs)


WebSocketDisconnect.__init__ = _patched_ws_disconnect_init

# 修复P2-1: 使用线程锁保护全局变量
import threading

# P0-6 修复: 提取魔术字符串为常量
THREAD_LOCKED_FLAG = "is_locked"

global main_loop
downloader_names = []
downloader_names_lock = threading.Lock()

global running_thread_names
threads = []
threads_lock = threading.Lock()


# 连接管理类
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.lock = threading.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        with self.lock:
            self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        with self.lock:
            try:
                self.active_connections.remove(websocket)
            except ValueError:
                pass

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def send_json_data(self, data: Any, websocket: WebSocket):
        await websocket.send_json(data)

    async def broadcast(self, message: str, sender: WebSocket):
        with self.lock:
            connections_snapshot = list(self.active_connections)

        for connection in connections_snapshot:
            try:
                if connection != sender:
                    await connection.send_text(message)
            except WebSocketDisconnect:
                self.disconnect(connection)
            except Exception as e:
                logger.warning(f"广播消息失败，移除连接: {e}")
                self.disconnect(connection)


# 创建连接管理器实例
manager = ConnectionManager()


class WebsocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.server_statuses: Dict[str, Any] = {}
        # 修复P1-1: 添加线程锁保护并发访问
        self._lock = threading.Lock()

    # 连接
    async def connect(self, websocket: WebSocket):
        # 修复P1-1: 使用锁保护连接列表修改
        with self._lock:
            await websocket.accept()
            self.active_connections.append(websocket)

    # 断开连接
    async def disconnect(self, websocket: WebSocket):
        # 修复P1-1: 使用锁保护连接列表修改
        with self._lock:
            try:
                self.active_connections.remove(websocket)
            except ValueError:
                # 连接已不在列表中，无需移除
                pass

    # 更新状态（线程安全）
    def update_status(self, downloader_id: str, status: Dict[str, Any]):
        # 修复P1-1: 使用锁保护状态字典修改
        with self._lock:
            self.server_statuses[downloader_id] = status

    # 获取状态（线程安全）
    def get_status(self, downloader_id: str = None) -> Dict[str, Any] | Dict[str, Dict[str, Any]]:
        # 修复P1-1: 使用锁保护状态字典读取
        with self._lock:
            if downloader_id:
                return self.server_statuses.get(downloader_id)
            return self.server_statuses.copy()  # 返回副本，避免外部修改

    async def get_downloader_status_async(self, downloader: models.BtDownloaders):
        """异步版本的下载器状态获取"""
        try:
            if "127.0.0.1" in downloader.host:
                delay = 1
            else:
                # 使用线程池执行ping操作，避免阻塞
                delay = await asyncio.to_thread(ping3.ping, downloader.host, 5000, "ms", "0.0.0.0", seq=2)
                # 修复P1-4: 统一处理None为False
                delay = delay if delay is not None else False
            client_status = "1"
        except Exception as e:
            # P1-2 修复: 使用logger替代print
            logger.error(f"连接下载器时出错: {e}")
            delay = False
            client_status = "0"

    def get_downloader_status(self, downloader: models.BtDownloaders):
        """同步版本的下载器状态获取（保持兼容性）"""
        try:
            if "127.0.0.1" in downloader.host:
                delay = 1
            else:
                # 使用线程池执行ping操作，避免阻塞
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(ping3.ping, downloader.host, 5000, "ms", "0.0.0.0", seq=2)
                    delay = future.result(timeout=6)  # 6秒超时
                    # 修复P1-4: 统一处理None为False
                    delay = delay if delay is not None else False
            client_status = "1"
        except Exception as e:
            # P1-2 修复: 使用logger替代print
            logger.error(f"连接下载器时出错: {e}")
            delay = False
            client_status = "0"

        if not delay:
            client_status = "0"
        upload_speed = 0
        download_speed = 0
        if client_status == "1":
            # 修复P2-2: 自动为HTTP协议添加https://前缀
            if not downloader.host.startswith(('http://', 'https://')):
                downloader.host = f"https://{downloader.host}"
            # 修复P1-1: 添加10秒超时，避免无限阻塞
            client = Client(
                host=downloader.host,
                username=downloader.username,
                password=downloader.password,
                REQUESTS_ARGS={'timeout': 10}
            )
            torrents_info = client.torrents_info(status_filter="active")
            for torrent in torrents_info:
                upload_speed = upload_speed + torrent['upspeed']
                download_speed = download_speed + torrent['dlspeed']
            status = {
                "connect_status": client_status,
                "nickname": downloader.nickname,
                "delay": delay,
                "id": downloader.id,
                "upload_speed": upload_speed,
                "download_speed": download_speed
            }
        else:
            status = {
                "connect_status": client_status,
                "nickname": downloader.nickname,
                "delay": delay,
                "id": downloader.id
            }
        # 修复P1-2: 使用字典更新而非覆盖，保留其他下载器状态
        # 修复P1-1: 使用线程安全的update_status方法
        self.update_status(downloader.id, status)
        time.sleep(1)
        # await manager.send_json_data(self.server_statuses)


    def broadcast_status(self, downloader: models.BtDownloaders, websocket, stop_event, running_thread_names):
        # 修复P0-2: 使用可变字典来传递连接状态，避免参数传递问题
        connection_state = {"connected": True}
        loop = None
        try:
            # 子线程中必须显式创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            while connection_state["connected"]:
                self.get_downloader_status(downloader)
                # 修复P0-2: 使用loop.run_until_complete代替asyncio.run，避免事件循环冲突
                # 修复P1-1: 使用线程安全的get_status方法获取所有状态
                all_statuses = self.get_status()
                loop.run_until_complete(self.send_json_data(downloader, all_statuses, websocket, running_thread_names, connection_state))
                time.sleep(1)  # 在子线程中使用同步sleep是安全的
        except LoginFailed:
            # 登录失败，设置停止事件
            stop_event.set()
        except BaseException as e:
            # 清理资源：添加锁定标志并移除下载器ID
            running_thread_names.append(THREAD_LOCKED_FLAG)
            if downloader.id in running_thread_names:
                running_thread_names.remove(downloader.id)
            logger.info(f"检测到异常，正在断开连接: {e}")
        except Exception as e:
            # 兜底异常处理：记录错误日志
            logger.error(f"广播状态异常: {e}")
        finally:
            # 清理事件循环
            if loop and not loop.is_closed():
                loop.close()

                # 发送状态
    async def send_json_data(self,downloader, data: Any, websocket: WebSocket, running_thread_names, connection_state):
        try:
            await websocket.send_json(data)
        except BaseException as e:
            # 修复P0-2: 修改可变字典的值，影响外部作用域
            connection_state["connected"] = False
            if THREAD_LOCKED_FLAG not in running_thread_names:
                running_thread_names.append(THREAD_LOCKED_FLAG)
            # 修复P0-3: 安全移除downloader.id
            if downloader.id in running_thread_names:
                running_thread_names.remove(downloader.id)
            raise


# 连接池管理
class Database:
    _conn: Connection | None = None
    _last_used: float = 0
    _timeout: int = 300  # 5分钟超时
    _lock = threading.Lock()

    @classmethod
    @asynccontextmanager
    async def get_cursor(cls):
        # 修复P2-1: 添加连接超时和重连机制
        import time

        now = time.time()

        # 使用锁保护连接状态检查
        with cls._lock:
            # 检查连接是否超时
            if cls._conn and (now - cls._last_used) > cls._timeout:
                try:
                    # 连接超时，关闭并重新连接
                    await cls._conn.close()
                except Exception:
                    pass  # 忽略关闭错误
                cls._conn = None

            if not cls._conn:
                cls._conn = await connect(settings.DATABASE_NAME)

            cls._last_used = now

        try:
            async with cls._conn.cursor() as cursor:
                yield cursor
        except aiosqlite.Error as e:
            # 修复P2-1: 连接错误时重置连接
            logger.error(f"数据库连接错误: {e}")
            with cls._lock:
                if cls._conn:
                    try:
                        await cls._conn.close()
                    except Exception:
                        pass
                    cls._conn = None
            raise  # 重新抛出异常


# 监听下载器状态
@router.websocket("/downloaderStatus")
async def websocket_endpoint(websocket: WebSocket):
    # P1-2 修复: 使用logger替代print
    logger.info("WebSocket连接尝试...")
    # 接受WebSocket连接
    try:
        # P0-7 修复: 安全获取Cookie，使用get方法并提供默认值
        cookie = websocket.cookies.get('x-access-token')
        if not cookie:
            await manager.broadcast("连接已断开，原因：缺少认证token", websocket)
            manager.disconnect(websocket)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少认证token")
        utils.verify_access_token(cookie)
    except HTTPException:
        raise
    except Exception as e:
        await manager.broadcast(f"连接已断开，原因：" + str(e), websocket)
        manager.disconnect(websocket)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    try:
        await manager.connect(websocket)
        websocket_manager = WebsocketManager()
        # 创建停止事件和线程列表
        stop_event = threading.Event()
        is_connected = True
        running_thread_names=[]
        async with Database.get_cursor() as cursor:
            while is_connected:
                await cursor.execute("SELECT * FROM bt_downloaders where dr=1")
                data_list = [models.BtDownloaders(*row) async for row in cursor]

                try:
                    for downloader in data_list:
                        # 修复P2-1: 使用线程锁保护downloader_names
                        with downloader_names_lock:
                            if downloader.nickname not in downloader_names:
                                downloader_names.append(downloader.nickname)

                        if downloader.id not in running_thread_names and THREAD_LOCKED_FLAG not in running_thread_names:
                            # 修复P1-2: 使用非守护线程，确保线程能够优雅退出
                            thread = threading.Thread(
                                target=websocket_manager.broadcast_status,
                                args=(downloader, websocket, stop_event, running_thread_names),
                                daemon=False,  # 改为非守护线程，确保资源正确释放
                                name=downloader.id
                            )
                            # 修复P2-1: 使用线程锁保护threads列表
                            with threads_lock:
                                threads.append(thread)
                            thread.start()
                            running_thread_names.append(downloader.id)
                    if len(running_thread_names) == 1 and THREAD_LOCKED_FLAG in running_thread_names:
                        is_connected = False
                        stop_event.set()
                        # P0-3 修复: 创建列表副本，避免迭代时并发修改
                        for thread in list(threads):
                            thread.join(timeout=1.0)
                        # 修复P0-3: 安全移除THREAD_LOCKED_FLAG
                        if THREAD_LOCKED_FLAG in running_thread_names:
                            running_thread_names.remove(THREAD_LOCKED_FLAG)
                except Exception as e:
                    # 停止所有线程并关闭连接
                    stop_event.set()
                    for thread in list(threads):
                        thread.join(timeout=1.0)
                    manager.disconnect(websocket)



    except WebSocketDisconnect as e:
        await manager.broadcast(f"连接已断开，原因：" + e.reason, websocket)
        manager.disconnect(websocket)
    except BaseException as e:
        manager.disconnect(websocket)
        logger.warning(f"检测到被动断开，原因：{e}")
