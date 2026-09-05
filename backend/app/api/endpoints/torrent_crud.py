import asyncio
import logging
import uuid
from typing import List, Optional

import urllib3
from fastapi import APIRouter, Depends, Request, Query, UploadFile, File
from fastapi import Form
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.database import get_db
from app.auth.dependencies import require_authenticated_user
from app.downloader.models import BtDownloaders
from app.torrents.models import TrackerInfo
from app.services.audit_context import AuditContext
from app.services.audit_service import extract_audit_info_from_request
from app.services.torrent_add_service import TorrentAddParams, TorrentAddService

# Import from new split modules
from app.api.endpoints.torrent_helpers import (
    get_torrent_infos,
    convert_to_vo,
)
from app.core.reannounce_config_operations import extract_domains_from_trackers
from app.api.endpoints.torrent_speed import get_active_keys_snapshot
from app.api.endpoints.torrent_sync import qb_add_torrents, tr_add_torrents
from app.services.torrent_crud_service import get_torrent_info
from app.services.torrent_batch_add_service import (
    TorrentBatchAddOptions,
    cleanup_staged_files,
    process_torrent_batch_job,
    register_torrent_batch_task,
    stage_torrent_file,
)

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
    """创建新的种子信息（协议无关 TorrentAddService 的 HTTP 薄壳）。"""
    file_content = await torrent_file.read() if torrent_file else None

    service = TorrentAddService(db, store=getattr(request.app.state, "store", None))
    result = await service.add_torrent(
        TorrentAddParams(
            downloader_id=downloader_id,
            save_path=save_path,
            tags=tags,
            category=category,
            paused=paused,
            skip_hash_check=skip_hash_check,
            is_sequential_download=is_sequential_download,
            is_first_last_piece_priority=is_first_last_piece_priority,
            upload_limit=upload_limit,
            download_limit=download_limit,
        ),
        torrent_content=file_content,
        audit_context=AuditContext.from_request(request),
    )
    return CommonResponse(status=result.status, msg=result.msg, code=result.code, data=None)


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
    """根据复合主键获取种子信息

    ORM 实体不能直接作为响应返回：response_model=CommonResponse 下 Pydantic 无法
    从 ORM 属性构造信封，实测响应为全 null（status/msg/code/data 均 null）。
    必须经 convert_to_vo（与 getList 同源转换）包装为信封。
    """
    torrent = get_torrent_info(db, info_id, downloader_id)
    if not torrent:
        return CommonResponse(status="error", msg="Torrent not found", code="404", data=None)
    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data=convert_to_vo(torrent),
    )


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
