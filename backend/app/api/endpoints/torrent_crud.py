import asyncio
import logging
import os
import tempfile
import uuid
from typing import List, Optional

import urllib3
from fastapi import APIRouter, Depends, Request, Query, UploadFile, File
from fastapi import Form, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.database import get_db, AsyncSessionLocal
from app.auth.dependencies import require_authenticated_user
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo
from qbittorrentapi.exceptions import APIError
from transmission_rpc import TransmissionError
from app.services.audit_service import extract_audit_info_from_request, get_audit_service

# Import from new split modules
from app.api.endpoints.torrent_helpers import (
    calculate_info_hash,
    get_transmission_torrent_info,
    create_qbittorrent_torrent_record,
    create_transmission_torrent_record,
    get_torrent_infos,
)
from app.core.reannounce_config_operations import extract_domains_from_trackers
from app.api.endpoints.torrent_speed import get_active_keys_snapshot
from app.api.endpoints.torrent_sync import qb_add_torrents, tr_add_torrents
from app.services.torrent_crud_service import get_torrent_info
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.services.torrent_batch_add_service import (
    TorrentBatchAddOptions,
    cleanup_staged_files,
    process_torrent_batch_job,
    register_torrent_batch_task,
    stage_torrent_file,
)
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult

logger = logging.getLogger(__name__)
router = APIRouter()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 单次下载器 API 调用超时（秒）：与 tracker.py 切片同风格；qB/TR add 及轮询单次调用
# 沿用 30s 预算（原 qbittorrentapi / transmission_rpc HTTP 默认超时），轮询循环本身
# （30 次 × sleep 1s）由端点既有逻辑控制，不因 runtime timeout 改变重试语义。
_QB_CALL_TIMEOUT = 30.0
_TR_CALL_TIMEOUT = 30.0


# ==================== 种子操作请求模型 ====================


class TorrentOperationRequest(BaseModel):
    """种子操作请求（统一基类）"""

    hashes: List[str] = Field(..., description="种子hash列表", min_length=1, max_length=100)
    operator: Optional[str] = Field(default="admin", description="操作人")


@router.post("/list", response_model=CommonResponse)
def torrent_list(
    request: Request,
    _user=Depends(require_authenticated_user),
    name: str = Query(default="default", alias="name", description="种子名称"),
    db: Session = Depends(get_db),
):
    """
    同步下载器中的种子数据到数据库
    """
    try:
        # 查询启用的下载器（返回完整模型实例，以支持@property属性访问）
        downloaders = (
            db.query(BtDownloaders)
            .filter(BtDownloaders.dr == 0, BtDownloaders.enabled.is_(True), BtDownloaders.status == "1")
            .all()
        )

        if not downloaders:
            return CommonResponse(status="success", msg="未找到可用的下载器", code="200", data=[])

        synced_count = 0
        errors = []

        # 处理每个下载器
        for downloader in downloaders:
            try:
                if downloader.is_qbittorrent:
                    qb_add_torrents(db, [downloader], app=request.app)
                    synced_count += 1
                    logger.info(f"成功同步qBittorrent下载器: {downloader.nickname}")
                elif downloader.is_transmission:
                    tr_add_torrents(db, [downloader], app=request.app)
                    synced_count += 1
                    logger.info(f"成功同步Transmission下载器: {downloader.nickname}")
                else:
                    errors.append(f"不支持的下载器类型: {downloader.downloader_type}")

            except Exception as e:
                error_msg = f"同步下载器 {downloader.nickname} 失败: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # 构建响应消息
        if errors:
            msg = f"同步完成，成功: {synced_count}，失败: {len(errors)}"
            if errors:
                msg += f"。错误详情: {'; '.join(errors[:3])}"  # 只显示前3个错误
        else:
            msg = f"同步成功，共处理 {synced_count} 个下载器"

        return CommonResponse(
            status="success",
            msg=msg,
            code="200",
            data={
                "synced_count": synced_count,
                "total_count": len(downloaders),
                "errors": errors if len(errors) <= 5 else errors[:5],  # 限制返回的错误数量
            },
        )

    except SQLAlchemyError as e:
        logger.error(f"数据库操作失败: {str(e)}")
        return CommonResponse(status="error", msg=f"数据库操作失败: {str(e)}", code="500", data=None)
    except Exception as e:
        logger.error(f"同步过程中发生未知错误: {str(e)}")
        return CommonResponse(status="error", msg=f"同步失败: {str(e)}", code="500", data=None)


@router.post("/add", response_model=CommonResponse)
async def create_torrent(
    request: Request,
    _user=Depends(require_authenticated_user),
    downloader_id: Optional[str] = Form(..., description="所属下载器主键"),
    save_path: Optional[str | None] = Form(..., description="种子文件保存路径"),
    tags: Optional[str | None] = Form("", description="标签"),
    category: Optional[str | None] = Form("", description="分类"),
    paused: Optional[bool] = Form(False, description="是否暂停,0代表false，1代表true"),
    skip_hash_check: Optional[bool | None] = Form(False, description="是否跳过校验,0代表false，1代表true"),
    is_sequential_download: Optional[bool | None] = Form(False, description="是否按顺序下载,0代表false，1代表true"),
    is_first_last_piece_priority: Optional[bool | None] = Form(
        False, description="是否先下载首尾文件块,0代表false，1代表true"
    ),
    upload_limit: Optional[str | int | None] = Form(False, description="上传速度，单位bytes/second"),
    download_limit: Optional[str | int | None] = Form(False, description="下载速度，单位bytes/second"),
    torrent_file: Optional[UploadFile] = File(description="种子文件"),
    db: Session = Depends(get_db),
):
    # """创建新的种子信息"""
    result: CommonResponse[None] = CommonResponse(status="success", msg="种子添加成功", data=None, code="200")

    # ========== 从 app.state.store 获取缓存的下载器（强制规范） ==========
    # 步骤1：获取 app 对象并检查缓存初始化
    app = request.app

    if not hasattr(app.state, "store"):
        result.code = "500"
        result.msg = "下载器缓存未初始化"
        result.status = "failed"
        return result

    # 步骤2：从缓存获取下载器
    # 🔧 修复：使用异步版本 get_snapshot() 避免线程问题
    cached_downloaders = await app.state.store.get_snapshot()
    downloader_vo = next((d for d in cached_downloaders if d.downloader_id == downloader_id), None)

    # 步骤3：验证下载器有效性
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

    # 步骤4：获取并验证客户端连接
    client = downloader_vo.client

    if not client:
        result.code = "500"
        result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
        result.status = "failed"
        return result

    # mypy 收窄：能通过下载器缓存匹配即证明 downloader_id 非空（Form 参数类型为 Optional[str]），
    # 后续 call_downloader_api / get_transmission_torrent_info 均要求 str。
    assert downloader_id is not None

    # 使用缓存的下载器对象（替换原来的数据库查询）
    downloader = downloader_vo
    if torrent_file:
        # 保存文件到临时位置
        file_content = await torrent_file.read()

        # 将文件写入操作放到线程池中执行
        def write_temp_file(content):
            """安全地写入临时文件"""
            try:
                tmp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".torrent")
                tmp_file.write(content)
                tmp_file.flush()  # 确保数据写入磁盘
                os.fsync(tmp_file.fileno())  # 强制同步
                tmp_file.close()
                return tmp_file.name
            except Exception as e:
                logging.error(f"写入临时文件失败: {str(e)}")
                if "tmp_file" in locals():
                    try:
                        tmp_file.close()
                    except OSError as close_err:
                        logging.debug(f"关闭临时文件失败: {close_err}")
                raise

        tmp_file_path = await asyncio.to_thread(write_temp_file, file_content)

        try:
            # 计算文件哈希
            info_hash = await calculate_info_hash(tmp_file_path)

        except Exception as e:
            # 如果出错，删除临时文件
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
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
                # 将文件读取操作放到线程池中执行
                def read_file_data(file_path):
                    with open(file_path, "rb") as f:
                        return f.read()

                file_data = await asyncio.to_thread(read_file_data, tmp_file_path)
                # 将文件数据包装成类似文件对象
                from io import BytesIO

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
                db.query(TorrentInfo)
                .filter(TorrentInfo.hash == info_hash)
                .filter(TorrentInfo.dr == 0)
                .filter(TorrentInfo.downloader_id == downloader_id)
                .first()
            )

            if existing_torrent is None:
                # 不存在：创建新记录
                db_torrent = create_transmission_torrent_record(downloader, downloader_id, tr_torrent)
                db.add(db_torrent)
                db.commit()
                db.refresh(db_torrent)
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
            # handler 暴露内部堆栈信息。与 batch add 端点（本文件 line 645）对齐。
            logging.exception(
                "添加种子失败 [Transmission downloader_id=%s info_hash=%s]",
                downloader_id,
                info_hash if "info_hash" in locals() else "<unknown>",
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
            from io import BytesIO

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
                    "is_sequential_download": is_sequential_download,
                    "is_first_last_piece_priority": is_first_last_piece_priority,
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
                db.query(TorrentInfo)
                .filter(TorrentInfo.hash == info_hash)
                .filter(TorrentInfo.dr == 0)
                .filter(TorrentInfo.downloader_id == downloader_id)
                .first()
            )

            if existing_torrent is None:
                # 不存在：创建新记录
                db_torrent = create_qbittorrent_torrent_record(downloader, downloader_id, qb_torrent, tmp_file_path)
                db.add(db_torrent)
                db.commit()
                db.refresh(db_torrent)
            else:
                # 已存在：使用现有记录
                db_torrent = existing_torrent
        except APIError as e:
            result.code = "500"
            result.msg = str(e)
            return result
        except Exception as e:
            # 兜底：捕获非 APIError 异常（ValueError/TypeError/SQLAlchemy StatementError/
            # 网络层异常等），避免冒泡到全局 500 handler 暴露内部堆栈。
            #
            # ⚠️ prod-hotfix-2026-07-19 真实根因（已复现）：
            # 早期版本 try 块只覆盖 torrents_add/torrents_info 轮询，把
            # create_qbittorrent_torrent_record + db.commit() 留在 try 之外。
            # 当 qBittorrent 返回的种子字段是异常对象（如 added_on/total_size 为
            # ValueError 实例）时，create_qbittorrent_torrent_record 内部的
            # `qb_torrent.added_on > 0` 或 SQLAlchemy Column 类型转换会抛 TypeError，
            # 直接冒泡到 unhandled_exception_handler，前端看到
            # "Object of type ValueError is not JSON serializable"。
            # 本修复把整个分支（含 ORM 写入）纳入 try，与 Transmission 分支（line 221）
            # 及 batch add 端点（本文件 line 505）结构对齐。
            logging.exception(
                "添加种子失败 [qBittorrent downloader_id=%s info_hash=%s]",
                downloader_id,
                info_hash if "info_hash" in locals() else "<unknown>",
            )
            result.status = "failed"
            result.code = "500"
            result.msg = f"添加种子失败: {type(e).__name__}: {e}"
            return result

    # ========== 记录审计日志（异步） ==========
    async def write_audit_log_async():
        """异步写入审计日志的内部函数"""
        try:
            async with AsyncSessionLocal() as async_db:
                audit_service = await get_audit_service(async_db)
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ADD,
                    operator="admin",  # 当前API没有认证，使用默认操作人
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
                    **extract_audit_info_from_request(request),
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


@router.post("/add-batch", response_model=CommonResponse)
async def create_torrents_batch(
    request: Request,
    _user=Depends(require_authenticated_user),
    torrent_files: List[UploadFile] = File(..., description="种子文件列表，数量不限"),
    downloader_id: Optional[str] = Form(..., description="所属下载器主键"),
    save_path: Optional[str | None] = Form(..., description="种子文件保存路径"),
    tags: Optional[str | None] = Form("", description="标签"),
    category: Optional[str | None] = Form("", description="分类"),
    paused: Optional[bool] = Form(False, description="是否暂停"),
    skip_hash_check: Optional[bool | None] = Form(False, description="是否跳过校验"),
    is_sequential_download: Optional[bool | None] = Form(False, description="是否顺序下载"),
    is_first_last_piece_priority: Optional[bool | None] = Form(False, description="是否优先首尾文件块"),
    upload_limit: Optional[str | int | None] = Form(False, description="上传速度，单位 bytes/second"),
    download_limit: Optional[str | int | None] = Form(False, description="下载速度，单位 bytes/second"),
    db: Session = Depends(get_db),
):
    """提交后台批量添加任务，处理结果通过通知中心告知用户。"""

    if not torrent_files:
        return CommonResponse(status="error", msg="请至少选择一个种子文件", code="400", data=None)
    if request is None:
        return CommonResponse(status="error", msg="请求上下文不可用", code="500", data=None)

    app = request.app
    if not hasattr(app.state, "store"):
        return CommonResponse(status="error", msg="下载器缓存未初始化", code="500", data=None)

    cached_downloaders = await app.state.store.get_snapshot()
    downloader = next((item for item in cached_downloaders if item.downloader_id == downloader_id), None)
    if downloader is None:
        return CommonResponse(
            status="error", msg=f"下载器不在缓存中 [downloader_id={downloader_id}]", code="404", data=None
        )
    if (getattr(downloader, "fail_time", 0) or 0) > 0:
        return CommonResponse(status="error", msg="下载器已失效，无法提交批量任务", code="503", data=None)
    if not getattr(downloader, "client", None):
        return CommonResponse(status="error", msg="下载器客户端连接不存在", code="500", data=None)

    staged_files = []
    try:
        for torrent_file in torrent_files:
            staged_files.append(await stage_torrent_file(torrent_file))
    except Exception as exc:
        cleanup_staged_files(staged_files)
        logger.exception("批量种子上传暂存失败")
        return CommonResponse(status="error", msg=f"种子文件暂存失败: {exc}", code="500", data=None)
    finally:
        for torrent_file in torrent_files:
            try:
                await torrent_file.close()
            except Exception:
                logger.debug("关闭上传种子文件失败", exc_info=True)

    try:
        audit_info = extract_audit_info_from_request(request)
    except Exception:
        audit_info = {}
    operator = getattr(_user, "username", None)
    if not operator and isinstance(_user, dict):
        operator = _user.get("username")

    task_id = uuid.uuid4().hex
    options = TorrentBatchAddOptions(
        downloader_id=downloader_id or "",
        save_path=save_path,
        tags=tags,
        category=category,
        paused=paused,
        skip_hash_check=skip_hash_check,
        is_sequential_download=is_sequential_download,
        is_first_last_piece_priority=is_first_last_piece_priority,
        upload_limit=upload_limit if upload_limit is not False else None,
        download_limit=download_limit if download_limit is not False else None,
        operator=str(operator or "admin"),
        audit_info=audit_info,
    )

    try:
        task = asyncio.create_task(
            process_torrent_batch_job(app, task_id, staged_files, options),
            name=f"torrent_batch_add:{task_id}",
        )
        register_torrent_batch_task(app, task)
    except Exception as exc:
        cleanup_staged_files(staged_files)
        logger.exception("创建批量添加种子后台任务失败")
        return CommonResponse(status="error", msg=f"创建后台任务失败: {exc}", code="500", data=None)

    return CommonResponse(
        status="accepted",
        msg=f"已提交后台处理，共 {len(staged_files)} 个种子，完成后将在通知中心提示",
        code="202",
        data={"task_id": task_id, "status": "queued", "total": len(staged_files)},
    )


@router.get("/torrents/{info_id}/{downloader_id}/{downloader_name}", response_model=CommonResponse)
def get_torrent(
    info_id: str,
    downloader_id: str,
    downloader_name: str,
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """根据复合主键获取种子信息"""
    torrent = get_torrent_info(db, info_id, downloader_id)
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found")
    return torrent


@router.get("/getList")
def get_torrents(
    downloader_id: Optional[str] = Query(None, description="所属下载器主键（支持多选，逗号分隔）", examples=[""]),
    downloader_name_like: Optional[str] = Query(None, description="所属下载器名模糊查询"),
    name_like: Optional[str] = Query(None, description="种子名称模糊查询"),
    save_path_like: Optional[str] = Query(None, description="种子文件保存路径模糊查询"),
    size_min: Optional[str] = Query(None, description="种子大小最小值"),
    size_max: Optional[str] = Query(None, description="种子大小最大值"),
    added_date_min: Optional[str] = Query(None, description="添加时间最小值"),
    added_date_max: Optional[str] = Query(None, description="添加时间最大值"),
    completed_date_min: Optional[str] = Query(None, description="完成时间最小值"),
    completed_date_max: Optional[str] = Query(None, description="完成时间最大值"),
    tags_like: Optional[str] = Query(None, description="标签模糊查询"),
    category_like: Optional[str] = Query(None, description="分类模糊查询"),
    tracker_like: Optional[str] = Query(None, description="tracker地址模糊查询"),
    tracker_domain: Optional[str] = Query(
        None,
        description="Tracker主域名筛选（支持多选，逗号分隔；例如 tracker.example.com）",
    ),
    status: Optional[str] = Query(
        None,
        description="种子状态筛选(支持多选，逗号分隔；error状态满足status='error'或has_tracker_error=True之一即可)",
    ),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100000, description="限制记录数"),
    sort_by: Optional[str] = Query(None, description="排序字段"),
    sort_order: Optional[str] = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
    active_only: bool = Query(False, description="仅显示活动种子（实时速度>0，由活动集合缓存驱动）"),
    same_content_only: bool = Query(
        False,
        description="仅显示名称、大小相同且规范化 InfoHash 至少两个不同值的种子",
    ),
    single_error_only: bool = Query(
        False,
        description="仅显示错误且全局同名同大小内容唯一的种子",
    ),
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """通用查询方法，支持多种过滤条件和排序，返回数据总数和列表"""
    try:
        # 仅显示活动种子：只有完整且未过期的快照可以参与过滤。冷启动、过期或部分下载器
        # 失败都返回 206，前端保留现有列表并先刷新速度快照；权威空集则正常返回 200 空列表。
        active_keys = None
        active_snapshot = None
        if active_only:
            active_snapshot = get_active_keys_snapshot()
            if not active_snapshot.ready:
                response_data = {
                    "total": 0,
                    "list": [],
                    "pageSize": limit,
                    "activeSnapshotReady": False,
                    "activeSnapshotStatus": active_snapshot.status.value,
                }
                return CommonResponse(
                    status="partial",
                    msg="活动种子快照尚未就绪，请刷新速度快照后重试",
                    data=response_data,
                    code="206",
                )
            active_keys = set(active_snapshot.keys)

        # 获取包含总数和数据的查询结果
        result = get_torrent_infos(
            db=db,
            downloader_id=downloader_id,
            downloader_name_like=downloader_name_like,
            name_like=name_like,
            save_path_like=save_path_like,
            size_min=size_min,
            size_max=size_max,
            added_date_min=added_date_min,
            added_date_max=added_date_max,
            completed_date_min=completed_date_min,
            completed_date_max=completed_date_max,
            tags_like=tags_like,
            category_like=category_like,
            status=status,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            tracker=tracker_like,
            tracker_domain=tracker_domain,
            active_keys=active_keys,
            same_content_only=same_content_only,
            single_error_only=single_error_only,
        )

        # 构建响应数据，包含总数和列表
        response_data = {"total": result["total"], "list": result["data"], "pageSize": limit}
        if active_snapshot is not None:
            response_data.update(
                {
                    "activeSnapshotReady": True,
                    "activeSnapshotStatus": active_snapshot.status.value,
                }
            )

        response = CommonResponse(status="success", msg="获取列表成功", data=response_data, code="200")
        return response

    except Exception as e:
        response = CommonResponse(status="failed", msg=f"获取列表失败: {str(e)}", data=None, code="500")
        return response


@router.get("/tracker-domains")
def get_tracker_domains(
    _user=Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """返回由定时 Tracker 同步任务采集到的全部 Tracker 主域名。"""
    try:
        tracker_rows = db.query(TrackerInfo.tracker_url, TrackerInfo.tracker_host).filter(TrackerInfo.dr == 0).all()
        tracker_values = [value for row in tracker_rows for value in (row.tracker_url, row.tracker_host) if value]
        domains = sorted(set(extract_domains_from_trackers(tracker_values)))
        return CommonResponse(
            status="success",
            msg="获取 Tracker 主域名成功",
            code="200",
            data=domains,
        )
    except Exception as exc:
        logger.exception("获取 Tracker 主域名失败")
        return CommonResponse(
            status="failed",
            msg=f"获取 Tracker 主域名失败: {exc}",
            code="500",
            data=None,
        )
