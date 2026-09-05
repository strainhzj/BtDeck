"""协议无关单种子添加服务（HTTP ``/torrent/add`` 与未来 MCP 共用）。

从 torrent_crud.py 的 create_torrent endpoint 原样抽取（PLANS/mcp-service-capabilities.md
§4.7/§10.3）：store 显式注入、审计信息经 AuditContext 传入、领域结果显式携带
status/code/msg 由调用方映射协议响应。为保持 HTTP 行为零变化，各失败路径的
status/code/msg 与原 endpoint 完全一致（含历史遗留的 status 未覆盖路径）。
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Optional, Union

from sqlalchemy.orm import Session

from qbittorrentapi.exceptions import APIError
from transmission_rpc import TransmissionError

from app.database import AsyncSessionLocal
from app.services.audit_context import AuditContext
from app.services.audit_service import get_audit_service
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.api.endpoints.torrent_helpers import (
    calculate_info_hash,
    get_transmission_torrent_info,
    create_qbittorrent_torrent_record,
    create_transmission_torrent_record,
)
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.torrents.models import TorrentInfo

logger = logging.getLogger(__name__)

# 单次下载器 API 调用超时（秒）：与 tracker.py 切片同风格；qB/TR add 及轮询单次调用
# 沿用 30s 预算（原 qbittorrentapi / transmission_rpc HTTP 默认超时），轮询循环本身
# （30 次 × sleep 1s）由服务既有逻辑控制，不因 runtime timeout 改变重试语义。
_QB_CALL_TIMEOUT = 30.0
_TR_CALL_TIMEOUT = 30.0


@dataclass
class TorrentAddParams:
    """单种子添加参数（与 HTTP /torrent/add Form 字段一一对应）。"""

    downloader_id: Optional[str]
    save_path: Optional[str]
    tags: Optional[str] = ""
    category: Optional[str] = ""
    paused: Optional[bool] = False
    skip_hash_check: Optional[bool] = False
    is_sequential_download: Optional[bool] = False
    is_first_last_piece_priority: Optional[bool] = False
    upload_limit: Optional[Union[str, int]] = False
    download_limit: Optional[Union[str, int]] = False


@dataclass
class TorrentAddResult:
    """领域结果：status/code/msg 与原 endpoint 各路径完全一致，由调用方映射协议响应。"""

    status: str = "success"
    code: str = "200"
    msg: str = "种子添加成功"

    @property
    def ok(self) -> bool:
        return self.code == "200"


class TorrentAddService:
    """协议无关单种子添加服务。"""

    def __init__(self, db: Session, store: Any = None):
        """
        Args:
            db: 数据库会话（同步）
            store: 下载器缓存（app.state.store；由端点或 MCP 运行时显式注入）
        """
        self.db = db
        self.store = store

    async def add_torrent(
        self,
        params: TorrentAddParams,
        torrent_content: Optional[bytes],
        audit_context: Optional[AuditContext] = None,
        operator: str = "admin",
    ) -> TorrentAddResult:
        """添加单个 .torrent 种子。

        Args:
            params: 添加参数（downloader_id/save_path/标签/限速等）
            torrent_content: .torrent 文件字节内容；None 表示未上传文件
                （Transmission 分支返回 400；qBittorrent 分支与原实现一致按未定义路径失败）
            audit_context: 协议无关审计上下文（HTTP 端点经 AuditContext.from_request 构造）
            operator: 审计操作者（HTTP 现状为默认 "admin"，MCP 侧传 principal 用户名）
        """
        result = TorrentAddResult()
        downloader_id = params.downloader_id
        save_path = params.save_path
        tags = params.tags
        category = params.category
        paused = params.paused
        skip_hash_check = params.skip_hash_check
        upload_limit = params.upload_limit
        download_limit = params.download_limit

        tmp_file_path: Optional[str] = None
        info_hash: Optional[str] = None
        db_torrent: Optional[TorrentInfo] = None
        downloader: Any = None

        # ========== 从注入的 store 获取缓存的下载器（强制规范） ==========
        if self.store is None:
            result.code = "500"
            result.msg = "下载器缓存未初始化"
            result.status = "failed"
            return result

        # 🔧 修复：使用异步版本 get_snapshot() 避免线程问题
        cached_downloaders = await self.store.get_snapshot()
        downloader_vo = next((d for d in cached_downloaders if d.downloader_id == downloader_id), None)

        if not downloader_vo:
            result.code = "404"
            result.msg = f"下载器不在缓存中 [downloader_id={downloader_id}]"
            result.status = "failed"
            return result

        if hasattr(downloader_vo, "fail_time") and downloader_vo.fail_time > 0:
            result.code = "503"
            result.msg = f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]"
            result.status = "failed"
            return result

        client = downloader_vo.client
        if not client:
            result.code = "500"
            result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
            result.status = "failed"
            return result

        # mypy 收窄：能通过下载器缓存匹配即证明 downloader_id 非空（参数类型为 Optional[str]），
        # 后续 call_downloader_api / get_transmission_torrent_info 均要求 str。
        assert downloader_id is not None

        downloader = downloader_vo
        if torrent_content is not None:
            # 将文件写入操作放到线程池中执行
            def write_temp_file(content):
                """安全地写入临时文件"""
                tmp_file = None
                try:
                    tmp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".torrent")
                    tmp_file.write(content)
                    tmp_file.flush()  # 确保数据写入磁盘
                    os.fsync(tmp_file.fileno())  # 强制同步
                    tmp_file.close()
                    return tmp_file.name
                except Exception as e:
                    logging.error(f"写入临时文件失败: {str(e)}")
                    if tmp_file is not None:
                        try:
                            tmp_file.close()
                        except OSError as close_err:
                            logging.debug(f"关闭临时文件失败: {close_err}")
                    raise

            tmp_path: str = await asyncio.to_thread(write_temp_file, torrent_content)
            tmp_file_path = tmp_path

            try:
                # 计算文件哈希
                info_hash = await calculate_info_hash(tmp_path)
            except Exception as e:
                # 如果出错，删除临时文件
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                result.code = "500"
                result.msg = str(e)
                return result

        # 🔧 修复：使用 downloader_type 字段判断下载器类型
        # downloader_type: 0=qBittorrent, 1=Transmission
        if downloader.downloader_type == 1:  # Transmission
            try:
                # 使用缓存的客户端连接（强制规范）
                tr_client = client
                # 准备添加参数
                add_args = {"paused": paused, "download_dir": save_path if save_path else None}

                # 如果有种子文件，添加文件
                if tmp_file_path:
                    # mypy 收窄：TR 分支文件必经临时路径产生，info_hash 已同步计算
                    assert info_hash is not None

                    # 将文件读取操作放到线程池中执行
                    def read_file_data(file_path):
                        with open(file_path, "rb") as f:
                            return f.read()

                    file_data = await asyncio.to_thread(read_file_data, tmp_file_path)

                    # P0-04 修复：add_torrent 经 INTERACTIVE lane 线程池执行，不阻塞事件循环
                    await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        tr_client.add_torrent,
                        args=(BytesIO(file_data),),
                        kwargs=add_args,
                        timeout=_TR_CALL_TIMEOUT,
                        operation="add_torrent",
                    )
                else:
                    result.code = "400"
                    result.msg = "Transmission需要种子文件"
                    return result

                # 等待Transmission处理种子（最多30秒）
                tr_torrent = None
                max_retries = 30
                retry_count = 0
                while tr_torrent is None and retry_count < max_retries:
                    await asyncio.sleep(1)
                    tr_torrent = await get_transmission_torrent_info(downloader_id, tr_client, info_hash)
                    retry_count += 1

                if not tr_torrent:
                    result.code = "408"
                    result.msg = "获取种子信息超时，请检查Transmission连接"
                    return result

                # 检查数据库中是否已存在该种子
                # ⚠️ 必须查询完整实体而非仅 info_id 列：审计日志构造时会访问 .name/.hash/.size，
                # 若只 select info_id 返回 Row 对象，访问未选中列会触发 AttributeError("name")
                # （SQLAlchemy 2.0 Row.__getattr__ 行为），表现为日志 "记录审计日志失败: name"。
                existing_torrent = (
                    self.db.query(TorrentInfo)
                    .filter(TorrentInfo.hash == info_hash)
                    .filter(TorrentInfo.dr == 0)
                    .filter(TorrentInfo.downloader_id == downloader_id)
                    .first()
                )

                if existing_torrent is None:
                    # 不存在：创建新记录
                    db_torrent = create_transmission_torrent_record(downloader, downloader_id, tr_torrent)
                    self.db.add(db_torrent)
                    self.db.commit()
                    self.db.refresh(db_torrent)
                else:
                    # 已存在：使用现有记录
                    db_torrent = existing_torrent

            except TransmissionError as e:
                result.code = "500"
                result.msg = str(e)
                return result
            except Exception as e:
                # 兜底：捕获非领域异常（ValueError/TypeError/requests 内部异常等）。
                # 修复 prod-hotfix-2026-07-19：transmission_rpc→requests.post(json=query)
                # 在 RPC 请求体序列化阶段会抛 TypeError("Object of type ValueError is not
                # JSON serializable")，原 except 只认 TransmissionError，会冒泡到全局 500
                # handler 暴露内部堆栈信息。与 batch add 路径对齐。
                logging.exception(
                    "添加种子失败 [Transmission downloader_id=%s info_hash=%s]",
                    downloader_id,
                    info_hash if info_hash is not None else "<unknown>",
                )
                result.status = "failed"
                result.code = "500"
                result.msg = f"添加种子失败: {type(e).__name__}: {e}"
                return result
        # 🔧 修复：使用 downloader_type 字段判断下载器类型
        # downloader_type: 0=qBittorrent, 1=Transmission
        if downloader.downloader_type == 0:  # qBittorrent
            try:
                # 使用缓存的客户端连接（强制规范）
                qb_client = client

                # 将文件读取操作放到线程池中执行
                def read_file_data_qb(file_path):
                    with open(file_path, "rb") as f:
                        return f.read()

                file_data = await asyncio.to_thread(read_file_data_qb, tmp_file_path)

                # P0-04 修复：torrents_add 经 INTERACTIVE lane 线程池执行，不阻塞事件循环
                await call_downloader_api(
                    downloader_id,
                    DownloadLane.INTERACTIVE,
                    qb_client.torrents_add,
                    kwargs={
                        "torrent_files": BytesIO(file_data),
                        "save_path": save_path,
                        "is_stopped": paused,
                        "tags": tags,
                        "category": category,
                        "is_skip_checking": skip_hash_check,
                        "is_sequential_download": params.is_sequential_download,
                        "is_first_last_piece_priority": params.is_first_last_piece_priority,
                        "upload_limit": upload_limit,
                        "download_limit": download_limit,
                    },
                    timeout=_QB_CALL_TIMEOUT,
                    operation="add_torrent",
                )

                # 从qBittorrent获取种子信息（最多30秒）
                torrents = None
                max_retries = 30
                retry_count = 0
                while (torrents is None or len(torrents) == 0) and retry_count < max_retries:
                    await asyncio.sleep(1)
                    # P0-04 修复：轮询内的 torrents_info 同样经 INTERACTIVE lane 执行
                    torrents = await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        qb_client.torrents_info,
                        kwargs={"torrent_hashes": info_hash},
                        timeout=_QB_CALL_TIMEOUT,
                        operation="get_qb_torrent_info",
                    )
                    retry_count += 1

                # 双重检查：确保torrents列表不为空
                if not torrents or len(torrents) == 0:
                    result.code = "500"
                    result.msg = "种子添加到qBittorrent后无法获取信息"
                    return result

                qb_torrent = torrents[0]

                # 检查数据库中是否已存在该种子
                # ⚠️ 必须查询完整实体而非仅 info_id 列：审计日志构造时会访问 .name/.hash/.size，
                # 若只 select info_id 返回 Row 对象，访问未选中列会触发 AttributeError("name")
                # （SQLAlchemy 2.0 Row.__getattr__ 行为），表现为日志 "记录审计日志失败: name"。
                existing_torrent = (
                    self.db.query(TorrentInfo)
                    .filter(TorrentInfo.hash == info_hash)
                    .filter(TorrentInfo.dr == 0)
                    .filter(TorrentInfo.downloader_id == downloader_id)
                    .first()
                )

                if existing_torrent is None:
                    # 不存在：创建新记录
                    db_torrent = create_qbittorrent_torrent_record(downloader, downloader_id, qb_torrent, tmp_file_path)
                    self.db.add(db_torrent)
                    self.db.commit()
                    self.db.refresh(db_torrent)
                else:
                    # 已存在：使用现有记录
                    db_torrent = existing_torrent
            except APIError as e:
                result.code = "500"
                result.msg = str(e)
                return result
            except Exception as e:
                # 兜底：捕获非 APIError 异常（ValueError/TypeError/SQLAlchemy StatementError/
                # 网络层异常等），避免冒泡到调用方暴露内部堆栈。
                #
                # ⚠️ prod-hotfix-2026-07-19 真实根因（已复现）：
                # 早期版本 try 块只覆盖 torrents_add/torrents_info 轮询，把
                # create_qbittorrent_torrent_record + db.commit() 留在 try 之外。
                # 当 qBittorrent 返回的种子字段是异常对象（如 added_on/total_size 为
                # ValueError 实例）时，create_qbittorrent_torrent_record 内部的
                # `qb_torrent.added_on > 0` 或 SQLAlchemy Column 类型转换会抛 TypeError，
                # 直接冒泡到 unhandled_exception_handler。
                # 本实现把整个分支（含 ORM 写入）纳入 try，与 Transmission 分支结构对齐。
                logging.exception(
                    "添加种子失败 [qBittorrent downloader_id=%s info_hash=%s]",
                    downloader_id,
                    info_hash if info_hash is not None else "<unknown>",
                )
                result.status = "failed"
                result.code = "500"
                result.msg = f"添加种子失败: {type(e).__name__}: {e}"
                return result

        # ========== 记录审计日志（异步） ==========
        audit_info = audit_context.as_dict() if audit_context is not None else {}

        async def write_audit_log_async():
            """异步写入审计日志的内部函数"""
            try:
                async with AsyncSessionLocal() as async_db:
                    audit_service = await get_audit_service(async_db)
                    await audit_service.log_operation(
                        operation_type=AuditOperationType.ADD,
                        operator=operator,
                        torrent_info_id=db_torrent.info_id,
                        operation_detail={
                            "torrent_name": db_torrent.name,
                            "torrent_hash": db_torrent.hash,
                            "downloader_id": downloader_id,
                            "downloader_name": downloader.nickname,
                            "save_path": save_path,
                            "tags": tags,
                            "category": category,
                            "paused": paused,
                            "file_size": db_torrent.size,
                        },
                        new_value={"status": "added"},
                        operation_result=AuditOperationResult.SUCCESS,
                        downloader_id=downloader_id,
                        **audit_info,
                    )
            except Exception as audit_error:
                # 审计日志失败不影响主业务
                logging.error(f"记录审计日志失败: {str(audit_error)}")

        # 在后台执行审计日志写入（不阻塞主业务）
        # ⚠️ 异步任务异常需要注意：如果任务失败，异常会被静默忽略
        asyncio.create_task(write_audit_log_async())
        # ========== 审计日志记录结束 ==========

        # 清理临时文件
        if tmp_file_path and os.path.exists(tmp_file_path):
            try:
                os.unlink(tmp_file_path)
            except OSError:
                pass

        return result
