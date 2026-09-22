"""种子添加辅助函数（服务层共享，feature mcp-service-capabilities W3-③）。

从 ``app/api/endpoints/torrent_helpers.py`` 原样迁移（PLANS/mcp-service-capabilities
§11.1 分层债收尾）：单种子添加（TorrentAddService）、批量添加
（TorrentBatchAddService）与状态端点共用的 info hash 计算、TR 轮询、
qB/TR 种子记录构造与审计写入辅助。服务层依赖 HTTP endpoint 层会阻断
MCP 共用边界（G0 禁 app/mcp import app.api 的口径下同款约束），
故归属到服务层；HTTP 端点（torrent_status.py）改为正向依赖本模块。

迁移纪律：函数体与 torrent_helpers 原实现逐字一致；唯一差异是
``get_transmission_torrent_info`` 的 ``tr_client`` 类型注解由
``transmission_rpc.Client`` 改为 ``Any``——本模块作为架构守卫登记对象
（tests/architecture/test_async_downloader_calls.py），模块级客户端库
import 不允许出现（先例：recycle_bin_service 同款处理）。
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import bencodepy

from app.core.torrent_status_mapper import TorrentStatusMapper
from app.database import AsyncSessionLocal
from app.services.audit_service import get_audit_service
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.services.torrent_ratio_values import normalize_ratio, normalize_ratio_limit
from app.torrents.models import TorrentInfo as torrentInfoModel

logger = logging.getLogger(__name__)


async def calculate_info_hash(torrent_file_path: str) -> str:
    """计算种子文件的info_hash"""
    try:
        # 将文件读取和解析操作放到线程池中执行
        def read_and_decode_file(file_path):
            with open(file_path, "rb") as f:
                file_content = f.read()
            return bencodepy.decode(file_content)

        torrent_data = await asyncio.to_thread(read_and_decode_file, torrent_file_path)

        # 获取info部分并计算SHA1哈希
        info_data = bencodepy.encode(torrent_data[b"info"])
        info_hash = hashlib.sha1(info_data).hexdigest()

        return info_hash
    except Exception as e:
        raise Exception(f"计算info_hash失败: {str(e)}")


async def get_transmission_torrent_info(
    downloader_id: str,
    tr_client: Any,
    info_hash: str,
    timeout: int = 10,
    per_call_timeout: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """从Transmission获取种子信息（经 INTERACTIVE lane 调用，禁止裸同步调用）

    P0-04 修复（sync-database-blocking-remediation W2-3）：tr_client.get_torrents
    由 call_downloader_api 在 INTERACTIVE lane 线程池中执行，不再阻塞事件循环；
    downloader_id 由调用方传入（用于 per-downloader 限流与日志）。轮询重试逻辑
    （timeout 秒窗口、异常后 sleep 1s 重试）保持原语义不变。
    """
    import time

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # 获取所有种子（经 runtime 线程池执行）
            torrents = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                tr_client.get_torrents,
                args=(info_hash,),
                timeout=per_call_timeout,
                operation="get_transmission_torrent_info",
            )
            return torrents[0]
            # 查找匹配的种子
            # for torrent in torrents:
            #     if torrent.hashString.lower() == info_hash.lower():
            #         return torrent
            #
            # time.sleep(1)
        except Exception:
            # 如果出错，等待一会儿再试
            await asyncio.sleep(1)

    return None


def create_qbittorrent_torrent_record(downloader, downloader_id, qb_torrent, tmp_file_path):
    """创建qBittorrent种子信息记录"""
    db_torrent = torrentInfoModel(
        id_=str(uuid.uuid4()),
        downloader_id=downloader_id,
        downloader_name=downloader.nickname,
        torrent_id=qb_torrent.hash,
        hash=qb_torrent.hash,
        name=qb_torrent.name,
        save_path=qb_torrent.save_path,
        size=qb_torrent.total_size,
        status=TorrentStatusMapper.convert_qbittorrent_status(qb_torrent.state),
        torrent_file="/config/qbittorrent/BT_backup/" + qb_torrent.hash + ".torrent",
        # 防御性：添加时间戳范围检查，防止负数和溢出；
        # 下载器侧 added_on 缺失/为 0 时以本地时间兜底（种子刚添加，入库时间即添加时间），
        # 避免"添加时间为空"（同步链路 12 小时全量快照前无自愈）
        added_date=(
            datetime.fromtimestamp(qb_torrent.added_on)
            if qb_torrent.added_on > 0 and qb_torrent.added_on <= 2147483647
            else datetime.now()
        ),
        completed_date=(
            datetime.fromtimestamp(qb_torrent.completion_on)
            if qb_torrent.completion_on and qb_torrent.completion_on > 0 and qb_torrent.completion_on <= 2147483647
            else None
        ),
        ratio=normalize_ratio(getattr(qb_torrent, "ratio", None)).value_for_insert(),
        # NULL 表示“无显式单种数值限制”，不能用于向下载器回写设置。
        ratio_limit=normalize_ratio_limit(getattr(qb_torrent, "ratio_limit", None)).value_for_insert(),
        tags=",".join(qb_torrent.tags) if qb_torrent.tags else "",
        category=qb_torrent.category,
        super_seeding="1" if qb_torrent.super_seeding else "0",
        enabled=1,
        create_time=(
            datetime.fromtimestamp(qb_torrent.added_on)
            if qb_torrent.added_on > 0 and qb_torrent.added_on <= 2147483647
            else datetime.now()
        ),
        create_by="admin",
        update_time=(
            datetime.fromtimestamp(qb_torrent.added_on)
            if qb_torrent.added_on > 0 and qb_torrent.added_on <= 2147483647
            else datetime.now()
        ),
        update_by="admin",
        dr=0,  # 🔧 修复：添加缺失的 dr 参数
        progress=0,  # 🔧 修复：添加缺失的 progress 参数
    )
    return db_torrent


def create_transmission_torrent_record(downloader, downloader_id, tr_torrent):
    db_torrent = torrentInfoModel(
        id_=str(uuid.uuid4()),
        downloader_id=downloader_id,
        downloader_name=downloader.nickname,
        torrent_id=tr_torrent.id,
        hash=tr_torrent.hashString,
        name=tr_torrent.name,
        save_path=tr_torrent.download_dir,
        size=tr_torrent.total_size,
        status=TorrentStatusMapper.resolve_transmission_status(tr_torrent.status, tr_torrent.error),
        error_reason=TorrentStatusMapper.extract_transmission_error_reason(tr_torrent),
        torrent_file=tr_torrent.torrent_file,
        added_date=tr_torrent.added_date,
        completed_date=tr_torrent.done_date if tr_torrent.done_date else None,
        # 修复历史错位：原代码把 seed_ratio_limit（比率限制）赋给了 ratio（实际比率）字段。
        # ratio = 实际上传比率（uploadRatio 的 snake_case），ratio_limit = 种子比率限制；
        # seed_ratio_limit 为 None 表示 TR "无限制"，正好映射 Float 列的 NULL。
        ratio=normalize_ratio(getattr(tr_torrent, "ratio", None)).value_for_insert(),
        ratio_limit=normalize_ratio_limit(getattr(tr_torrent, "seed_ratio_limit", None)).value_for_insert(),
        tags=",".join(tr_torrent.labels) if hasattr(tr_torrent, "labels") and tr_torrent.labels else "",
        category="",
        super_seeding="",
        enabled=1,
        create_time=tr_torrent.added_date,
        create_by="admin",
        update_time=tr_torrent.added_date,
        update_by="admin",
        dr=0,  # 🔧 修复：添加缺失的 dr 参数
        progress=0,  # 🔧 修复：添加缺失的 progress 参数
    )
    return db_torrent


# ==================== 审计日志辅助函数 ====================


async def _write_audit_log_async(
    operation_type: str,
    operator: str,
    torrent_info_id: str,
    operation_detail: Dict[str, Any],
    torrent_name: Optional[str],
    torrent_hash: Optional[str],
    downloader_id: str,
    operation_result: str,
    error_message: Optional[str] = None,
    new_value: Optional[Dict[str, Any]] = None,
    old_value: Optional[Dict[str, Any]] = None,
    audit_info: Optional[Dict[str, str]] = None,
):
    """异步写入审计日志的辅助函数"""
    try:
        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 构建完整的操作详情
            full_detail = operation_detail.copy()
            if torrent_name:
                full_detail["torrent_name"] = torrent_name
            if torrent_hash:
                full_detail["torrent_hash"] = torrent_hash

            await audit_service.log_operation(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=full_detail,
                old_value=old_value,
                new_value=new_value,
                operation_result=operation_result,
                error_message=error_message,
                downloader_id=downloader_id,
                **(audit_info or {}),
            )
    except Exception as audit_error:
        logging.error(f"记录审计日志失败: {str(audit_error)}", exc_info=True)


def _safe_write_audit_log(
    operation_type: str,
    operator: str,
    torrent_info_id: str = "",
    operation_detail: Optional[Dict[str, Any]] = None,
    torrent_name: Optional[str] = None,
    torrent_hash: Optional[str] = None,
    downloader_id: str = "",
    operation_result: str = "success",
    error_message: Optional[str] = None,
    new_value: Optional[Dict[str, Any]] = None,
    old_value: Optional[Dict[str, Any]] = None,
    audit_info: Optional[Dict[str, str]] = None,
):
    """
    安全地写入审计日志（带异常处理和日志记录）

    修复CRITICAL #4: asyncio.create_task的异常会被静默忽略
    使用此包装函数确保审计日志异常不会丢失，同时记录到日志文件中
    """
    operation_detail = operation_detail or {}
    try:
        asyncio.create_task(
            _write_audit_log_async(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=operation_detail,
                torrent_name=torrent_name,
                torrent_hash=torrent_hash,
                downloader_id=downloader_id,
                operation_result=operation_result,
                error_message=error_message,
                new_value=new_value,
                old_value=old_value,
                audit_info=audit_info,
            )
        )
    except Exception as e:
        # 记录创建任务失败（极少发生）
        logging.error(
            f"创建审计日志任务失败 [operation_type={operation_type}, torrent_info_id={torrent_info_id}]: {str(e)}",
            exc_info=True,
        )
