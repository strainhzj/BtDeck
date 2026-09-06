"""后台批量添加种子服务。

上传请求只负责把文件落到临时文件并提交任务；实际的下载器调用、数据库写入和
完成通知都在后台任务中执行，避免长时间等待阻塞 HTTP 请求。
"""

import asyncio
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional, Sequence

from fastapi import UploadFile
from sqlalchemy.exc import OperationalError

from app.api.endpoints.torrent_helpers import (
    _write_audit_log_async,
    calculate_info_hash,
    create_qbittorrent_torrent_record,
    create_transmission_torrent_record,
)
from app.database import AsyncSessionLocal, SessionLocal
from app.services.notification_service import NotificationService
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType
from app.torrents.models import TorrentInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StagedTorrentFile:
    """已落盘、可交给后台任务处理的种子文件。"""

    file_name: str
    file_path: str


@dataclass(frozen=True)
class TorrentBatchAddOptions:
    """批量添加任务参数的不可变快照。"""

    downloader_id: str
    save_path: Optional[str]
    tags: Optional[str]
    category: Optional[str]
    paused: Optional[bool]
    skip_hash_check: Optional[bool]
    is_sequential_download: Optional[bool]
    is_first_last_piece_priority: Optional[bool]
    upload_limit: Optional[str | int]
    download_limit: Optional[str | int]
    operator: str
    audit_info: Dict[str, str]


async def stage_torrent_file(upload_file: UploadFile) -> StagedTorrentFile:
    """将上传文件以流式方式写入临时文件，避免批量文件全部驻留内存。"""

    file_name = upload_file.filename or "unnamed.torrent"
    await upload_file.seek(0)

    def copy_to_temp_file() -> str:
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".torrent") as temp_file:
                temp_path = temp_file.name
                shutil.copyfileobj(upload_file.file, temp_file, length=1024 * 1024)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            return temp_path
        except Exception:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    logger.debug("清理失败的临时种子文件失败: %s", temp_path, exc_info=True)
            raise

    return StagedTorrentFile(file_name=file_name, file_path=await asyncio.to_thread(copy_to_temp_file))


def cleanup_staged_files(staged_files: Sequence[StagedTorrentFile]) -> None:
    """删除上传阶段或后台任务结束后遗留的临时文件。"""

    for staged_file in staged_files:
        if not os.path.exists(staged_file.file_path):
            continue
        try:
            os.unlink(staged_file.file_path)
        except OSError:
            logger.debug("清理临时种子文件失败: %s", staged_file.file_path, exc_info=True)


def register_torrent_batch_task(app: Any, task: asyncio.Task[Any]) -> None:
    """持有后台任务引用并记录未预期异常，避免任务被垃圾回收或静默失败。"""

    task_set = getattr(app.state, "torrent_batch_tasks", None)
    if task_set is None:
        task_set = set()
        app.state.torrent_batch_tasks = task_set
    task_set.add(task)

    def on_task_done(done_task: asyncio.Task[Any]) -> None:
        task_set.discard(done_task)
        if done_task.cancelled():
            logger.info("批量添加种子任务已取消")
            return
        try:
            done_task.result()
        except Exception:
            logger.exception("批量添加种子后台任务异常退出")

    task.add_done_callback(on_task_done)


def _failed_results(staged_files: Sequence[StagedTorrentFile], error: str) -> List[Dict[str, Any]]:
    return [
        {"file_name": staged_file.file_name, "success": False, "info_id": None, "error": error}
        for staged_file in staged_files
    ]


# SQLite 写锁冲突错误码：SQLITE_BUSY=5 / SQLITE_BUSY_RECOVERY=517 / SQLITE_BUSY_SNAPSHOT=518。
# BUSY_SNAPSHOT 表示陈旧读快照升级写事务失败，busy_timeout 对其无效（重试也无意义，
# 唯一出路是 rollback 后重开快照），这正是批量添加偶发 "database is locked" 的根因。
_SQLITE_BUSY_ERROR_CODES = (5, 517, 518)
# 写锁冲突有界重试：5 次 × 0.2s 起步线性退避，总等待约 3s，远小于 busy_timeout=15s 兜底。
_LOCKED_RETRY_MAX = 5
_LOCKED_RETRY_BASE_DELAY_SECONDS = 0.2


def _sqlite_error_code(exc: BaseException) -> Optional[int]:
    """提取 sqlite3 原生错误码（Python>=3.11 经 exc.orig.sqlite_errorcode 暴露）。

    用于事后鉴别锁冲突类型（BUSY=5 与 BUSY_SNAPSHOT=518），旧运行时无该属性时返回 None。
    """
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlite_errorcode", None)
    if code is None:
        return None
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def _is_sqlite_locked_error(exc: BaseException) -> bool:
    """判定是否为 SQLite 写锁冲突（决定是否走有界重试）。"""
    if not isinstance(exc, OperationalError):
        return False
    code = _sqlite_error_code(exc)
    if code is not None:
        return code in _SQLITE_BUSY_ERROR_CODES
    return "database is locked" in str(exc).lower()


async def _insert_torrent_record_with_retry(db: Any, record_factory: Callable[[], Any]) -> Any:
    """以短事务插入单条新种子记录，对 SQLite 写锁冲突做有界重试。

    WAL 模式下，若会话携带有已陈旧的读事务（期间其他连接提交过写入），commit 升级
    写事务会立即返回 BUSY_SNAPSHOT（"database is locked"，busy_timeout 不生效）；
    正确处置是 rollback 丢弃陈旧快照后重开事务重试。每次重试用 record_factory 重建
    ORM 实例：rollback 会 expunge 尚未提交的 pending 对象，复用旧实例会因带主键被
    视作 persistent 而静默不产生 INSERT。非锁冲突错误不重试，直接上抛。
    """
    db_torrent: Any = None
    for attempt in range(1, _LOCKED_RETRY_MAX + 1):
        db_torrent = record_factory()
        db.add(db_torrent)
        try:
            db.commit()
            break
        except OperationalError as exc:
            db.rollback()
            if not _is_sqlite_locked_error(exc) or attempt == _LOCKED_RETRY_MAX:
                raise
            logger.warning(
                "新种子记录落库遇到 SQLite 写锁冲突，回滚后重试（第 %s/%s 次，sqlite_errorcode=%s）",
                attempt,
                _LOCKED_RETRY_MAX,
                _sqlite_error_code(exc),
            )
            await asyncio.sleep(_LOCKED_RETRY_BASE_DELAY_SECONDS * attempt)
    db.refresh(db_torrent)
    return db_torrent


async def _wait_for_transmission_torrent(client: Any, info_hash: str, retries: int = 30) -> Any:
    """在线程中执行 Transmission RPC，避免同步 SDK 调用阻塞事件循环。"""

    for _ in range(retries):
        try:
            torrents = await asyncio.to_thread(client.get_torrents, info_hash)
            if torrents:
                return torrents[0]
        except Exception:
            logger.debug("等待 Transmission 种子信息失败，将重试", exc_info=True)
        await asyncio.sleep(1)
    return None


async def _add_one_torrent(
    db: Any,
    downloader: Any,
    client: Any,
    staged_file: StagedTorrentFile,
    options: TorrentBatchAddOptions,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "file_name": staged_file.file_name,
        "success": False,
        "info_id": None,
        "error": None,
    }

    try:
        # 根修：先结束上一颗种子遗留的读事务（由上一轮 db.refresh() 的 SELECT 开启，
        # 会话跨整批复用）。否则本轮 add/轮询等秒级网络调用都在陈旧读快照内进行，
        # commit 升级写事务时若窗口内有其他写者（如异步审计日志）提交过，
        # WAL 下立即报 BUSY_SNAPSHOT（"database is locked"，busy_timeout 不生效）。
        db.rollback()
        info_hash = await calculate_info_hash(staged_file.file_path)
        downloader_type = int(downloader.downloader_type)

        if downloader_type == 1:
            file_data = await asyncio.to_thread(_read_file_data, staged_file.file_path)
            await asyncio.to_thread(
                client.add_torrent,
                BytesIO(file_data),
                paused=options.paused,
                download_dir=options.save_path if options.save_path else None,
            )
            torrent = await _wait_for_transmission_torrent(client, info_hash)
            if not torrent:
                raise RuntimeError("获取 Transmission 种子信息超时")

            db_torrent = (
                db.query(TorrentInfo)
                .filter(TorrentInfo.hash == info_hash)
                .filter(TorrentInfo.dr == 0)
                .filter(TorrentInfo.downloader_id == options.downloader_id)
                .first()
            )
            if db_torrent is None:
                db_torrent = await _insert_torrent_record_with_retry(
                    db, lambda: create_transmission_torrent_record(downloader, options.downloader_id, torrent)
                )

        elif downloader_type == 0:
            file_data = await asyncio.to_thread(_read_file_data, staged_file.file_path)
            await asyncio.to_thread(
                client.torrents_add,
                torrent_files=BytesIO(file_data),
                save_path=options.save_path,
                is_stopped=options.paused,
                tags=options.tags,
                category=options.category,
                is_skip_checking=options.skip_hash_check,
                is_sequential_download=options.is_sequential_download,
                is_first_last_piece_priority=options.is_first_last_piece_priority,
                upload_limit=options.upload_limit,
                download_limit=options.download_limit,
            )

            qb_torrent = None
            for _ in range(30):
                torrents = await asyncio.to_thread(client.torrents_info, torrent_hashes=info_hash)
                if torrents:
                    qb_torrent = torrents[0]
                    break
                await asyncio.sleep(1)
            if qb_torrent is None:
                raise RuntimeError("种子添加到 qBittorrent 后无法获取信息")

            db_torrent = (
                db.query(TorrentInfo)
                .filter(TorrentInfo.hash == info_hash)
                .filter(TorrentInfo.dr == 0)
                .filter(TorrentInfo.downloader_id == options.downloader_id)
                .first()
            )
            if db_torrent is None:
                db_torrent = await _insert_torrent_record_with_retry(
                    db,
                    lambda: create_qbittorrent_torrent_record(
                        downloader, options.downloader_id, qb_torrent, staged_file.file_path
                    ),
                )
        else:
            raise ValueError(f"不支持的下载器类型: {downloader.downloader_type}")

        result["success"] = True
        result["info_id"] = db_torrent.info_id

        audit_detail = {
            "torrent_name": db_torrent.name,
            "torrent_hash": db_torrent.hash,
            "downloader_id": options.downloader_id,
            "downloader_name": downloader.nickname,
            "save_path": options.save_path,
            "tags": options.tags,
            "category": options.category,
            "paused": options.paused,
            "file_size": db_torrent.size,
        }
        asyncio.create_task(
            _write_audit_log_async(
                operation_type=AuditOperationType.ADD,
                operator=options.operator,
                torrent_info_id=str(db_torrent.info_id),
                operation_detail=audit_detail,
                torrent_name=db_torrent.name,
                torrent_hash=db_torrent.hash,
                downloader_id=options.downloader_id,
                operation_result=AuditOperationResult.SUCCESS,
                new_value={"status": "added"},
                audit_info=options.audit_info,
            )
        )
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            logger.debug("批量添加失败后的数据库回滚失败", exc_info=True)
        error_text = str(exc)
        error_code = _sqlite_error_code(exc)
        if error_code is not None:
            # 观测：把 sqlite 原生错误码透传到通知中心与日志（BUSY=5/BUSY_RECOVERY=517/
            # BUSY_SNAPSHOT=518），复发时可直接鉴别锁冲突类型，无需翻查底层环境。
            error_text = f"{error_text}（sqlite_errorcode={error_code}）"
        logger.warning(
            "批量添加种子失败：file=%s sqlite_errorcode=%s error=%s",
            staged_file.file_name,
            error_code,
            exc,
        )
        result["error"] = error_text

    return result


def _read_file_data(file_path: str) -> bytes:
    with open(file_path, "rb") as file_handle:
        return file_handle.read()


async def _create_completion_notification(
    task_id: str,
    options: TorrentBatchAddOptions,
    results: Sequence[Dict[str, Any]],
) -> None:
    total_count = len(results)
    success_count = sum(1 for item in results if item.get("success"))
    failed_count = total_count - success_count
    if failed_count == 0:
        task_status = "completed"
        priority = "info"
    elif success_count == 0:
        task_status = "failed"
        priority = "error"
    else:
        task_status = "partial"
        priority = "warning"

    failed_list = [
        {"file_name": item.get("file_name", ""), "reason": item.get("error") or "未知错误"}
        for item in results
        if not item.get("success")
    ]
    extra_data = {
        "event": "torrent_batch_add_completed",
        "route": "/torrents",
        "task_id": task_id,
        "task_status": task_status,
        "operation_type": "torrent_batch_add",
        "downloader_id": options.downloader_id,
        "total_count": total_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "failed_list": failed_list,
    }
    content = f"批量添加种子任务完成：共 {total_count} 个，成功 {success_count} 个，失败 {failed_count} 个。"
    if failed_list:
        content += "\n\n失败明细：\n"
        content += "\n".join(f"- {item['file_name'] or '未知文件'}：{item['reason']}" for item in failed_list[:20])
        if len(failed_list) > 20:
            content += f"\n- 其余 {len(failed_list) - 20} 个失败项请展开通知详情查看。"

    try:
        async with AsyncSessionLocal() as db:
            service = NotificationService(db)
            await service.create_notification(
                type="system",
                title="批量添加种子完成",
                content=content,
                priority=priority,
                extra_data=extra_data,
                dedupe_key=f"torrent_batch_add:{task_id}",
            )
    except Exception:
        logger.exception("创建批量添加种子完成通知失败: task_id=%s", task_id)


async def process_torrent_batch_job(
    app: Any,
    task_id: str,
    staged_files: Sequence[StagedTorrentFile],
    options: TorrentBatchAddOptions,
) -> None:
    """执行后台批量任务，并在所有文件处理完后写入通知中心。"""

    results: List[Dict[str, Any]] = []
    try:
        cached_downloaders = await app.state.store.get_snapshot()
        downloader = next(
            (item for item in cached_downloaders if item.downloader_id == options.downloader_id),
            None,
        )
        if downloader is None:
            results = _failed_results(staged_files, "下载器不在缓存中")
        elif (getattr(downloader, "fail_time", 0) or 0) > 0:
            results = _failed_results(staged_files, "下载器已失效")
        elif not getattr(downloader, "client", None):
            results = _failed_results(staged_files, "下载器客户端连接不存在")
        else:
            db = SessionLocal()
            try:
                for staged_file in staged_files:
                    results.append(await _add_one_torrent(db, downloader, downloader.client, staged_file, options))
            finally:
                db.close()
    except Exception as exc:
        logger.exception("批量添加种子任务执行失败: task_id=%s", task_id)
        if not results:
            results = _failed_results(staged_files, str(exc))
        else:
            processed_names = {item.get("file_name") for item in results}
            results.extend(
                _failed_results(
                    [item for item in staged_files if item.file_name not in processed_names],
                    str(exc),
                )
            )
    finally:
        cleanup_staged_files(staged_files)

    await _create_completion_notification(task_id, options, results)
