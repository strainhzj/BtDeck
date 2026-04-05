import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.database import get_db
from app.services.audit_service import extract_audit_info_from_request
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.torrents.models import TorrentInfo as torrentInfoModel
from app.api.endpoints.torrent_helpers import _safe_write_audit_log

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 状态控制请求模型 ====================

class PauseTorrentsRequest(BaseModel):
    """暂停种子请求"""
    downloader_id: str = Field(..., description="下载器ID")
    hashes: List[str] = Field(..., description="种子hash列表", min_items=1, max_items=100)


class ResumeTorrentsRequest(BaseModel):
    """恢复/开始种子请求"""
    downloader_id: str = Field(..., description="下载器ID")
    hashes: List[str] = Field(..., description="种子hash列表", min_items=1, max_items=100)


class RecheckTorrentsRequest(BaseModel):
    """重新检查种子请求"""
    downloader_id: str = Field(..., description="下载器ID")
    hashes: List[str] = Field(..., description="种子hash列表", min_items=1, max_items=100)


# ==================== 暂停种子 ====================

@router.post("/pause", description="暂停种子接口",
             response_model=CommonResponse)
async def pause_torrents(
        request: Request,
        req_data: PauseTorrentsRequest,
        db: Session = Depends(get_db)
):
    """
    批量暂停种子

    功能：
    - 支持批量暂停多个种子
    - 指定下载器ID，根据下载器类型调用不同API
    - 使用缓存中的客户端连接，避免重复创建
    - 严格模式：任何一个失败整体回滚
    - 立即更新数据库状态为paused
    - 记录审计日志

    修复CRITICAL问题：
    - #1: 空指针解引用 - 添加None检查
    - #2: 资源泄漏 - 使用缓存连接，不手动logout
    - #3: 数据一致性 - 先执行API后更新数据库
    - #4: 审计日志异常 - 使用_safe_write_audit_log
    - #5: 下载器类型判断 - 使用枚举类型而非字符串比较

    请求格式：
    {
        "downloader_id": "下载器ID",
        "hashes": ["hash1", "hash2", ...]
    }
    """
    # 从请求模型中获取参数
    downloader_id = req_data.downloader_id
    hashes = req_data.hashes

    result = CommonResponse(
        status="success",
        msg="暂停成功",
        code="200",
        data={"success_count": len(hashes), "failed_items": []}
    )

    # ========== 验证参数 ==========
    if not hashes or len(hashes) == 0:
        result.status = "failed"
        result.msg = "参数错误：hashes列表不能为空"
        result.code = "400"
        return result

    try:
        # ========== 从缓存中获取下载器 ==========
        app = request.app
        if not hasattr(app.state, 'store'):
            result.status = "failed"
            result.msg = "下载器缓存未初始化"
            result.code = "500"
            return result

        cached_downloaders = app.state.store.get_snapshot_sync()

        # 根据 downloader_id 查找对应的下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        if not downloader_vo:
            result.status = "failed"
            result.msg = f"下载器不在缓存中 [downloader_id={downloader_id}]"
            result.code = "404"
            return result

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            result.status = "failed"
            result.msg = f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]"
            result.code = "503"
            return result

        # 获取缓存的客户端连接
        client = downloader_vo.client
        if not client:
            result.status = "failed"
            result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
            result.code = "500"
            return result

        # ========== 查询种子信息 ==========
        # 只查询指定下载器且未删除的种子（dr=0）
        torrent_records = db.query(torrentInfoModel).filter(
            torrentInfoModel.hash.in_(hashes),
            torrentInfoModel.downloader_id == downloader_id,
            torrentInfoModel.dr == 0  # 只操作未删除的种子
        ).all()

        if not torrent_records:
            result.status = "failed"
            result.msg = "未找到任何种子记录"
            result.code = "404"
            return result

        # 提取hash列表
        group_hashes = [r.hash for r in torrent_records]

        # ========== 执行暂停操作 ==========
        try:
            # 使用枚举类型判断下载器类型
            downloader_type_enum = downloader_vo.type_enum if hasattr(downloader_vo, 'type_enum') else None

            if downloader_vo.downloader_type == 0 or (downloader_type_enum and downloader_type_enum.is_qbittorrent()):
                # qBittorrent 下载器
                client.torrents_pause(torrent_hashes=group_hashes)

            elif downloader_vo.downloader_type == 1 or (
                    downloader_type_enum and downloader_type_enum.is_transmission()):
                # Transmission 下载器
                client.stop_torrent(group_hashes)

            else:
                error_msg = f"不支持的下载器类型: {downloader_vo.downloader_type}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 修复CRITICAL #3: API调用成功后再更新数据库
            for record in torrent_records:
                old_status = record.status
                record.status = "paused"
                db.add(record)

                # 修复CRITICAL #4: 使用安全包装记录审计日志
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.PAUSE,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_name": downloader_vo.nickname,
                        "downloader_type": downloader_vo.downloader_type
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    old_value={"status": old_status},
                    new_value={"status": "paused"},
                    operation_result=AuditOperationResult.SUCCESS,
                    audit_info=audit_info
                )

            # 提交数据库事务
            db.commit()

            result.msg = f"成功暂停 {len(torrent_records)} 个种子"
            result.data = {
                "success_count": len(torrent_records),
                "failed_items": []
            }

        except Exception as e:
            # 严格模式：任何失败都回滚
            db.rollback()
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"暂停种子失败 [downloader_id={downloader_id}]: {error_detail}")

            result.status = "failed"
            result.msg = f"暂停失败：{error_detail}"
            result.code = "500"
            result.data = {
                "success_count": 0,
                "failed_items": [{
                    "hash": r.hash,
                    "name": r.name,
                    "error": error_detail
                } for r in torrent_records]
            }

            # 记录失败的审计日志
            for record in torrent_records:
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.PAUSE,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_type": downloader_vo.downloader_type,
                        "exception_type": type(e).__name__
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    operation_result=AuditOperationResult.FAILED,
                    error_message=error_detail,
                    audit_info=audit_info
                )

            return result
        # 注意：不再需要 finally 块手动释放连接，因为使用的是缓存连接

    except Exception as e:
        db.rollback()
        error_detail = f"{type(e).__name__}: {str(e)}"
        logger.error(f"暂停种子异常: {error_detail}")

        result.status = "failed"
        result.msg = f"操作异常：{error_detail}"
        result.code = "500"

    return result


# ==================== 恢复/开始种子 ====================

@router.post("/resume", description="恢复/开始种子接口",
             response_model=CommonResponse)
async def resume_torrents(
        request: Request,
        req_data: ResumeTorrentsRequest,
        db: Session = Depends(get_db)
):
    """
    批量恢复/开始种子

    功能：
    - 支持批量恢复多个种子
    - 指定下载器ID，根据下载器类型调用不同API
    - 使用缓存中的客户端连接，避免重复创建
    - 严格模式：任何一个失败整体回滚
    - 立即更新数据库状态（根据进度：100%→seeding, 否则→downloading）
    - 记录审计日志

    修复CRITICAL问题：
    - #1: 空指针解引用 - 添加None检查
    - #2: 资源泄漏 - 使用缓存连接，不手动logout
    - #3: 数据一致性 - 先执行API后更新数据库
    - #4: 审计日志异常 - 使用_safe_write_audit_log
    - #5: 下载器类型判断 - 使用枚举类型而非字符串比较

    请求格式：
    {
        "downloader_id": "下载器ID",
        "hashes": ["hash1", "hash2", ...]
    }
    """
    # 从请求模型中获取参数
    downloader_id = req_data.downloader_id
    hashes = req_data.hashes

    result = CommonResponse(
        status="success",
        msg="开始成功",
        code="200",
        data={"success_count": len(hashes), "failed_items": []}
    )

    # ========== 验证参数 ==========
    if not hashes or len(hashes) == 0:
        result.status = "failed"
        result.msg = "参数错误：hashes列表不能为空"
        result.code = "400"
        return result

    try:
        # ========== 从缓存中获取下载器 ==========
        app = request.app
        if not hasattr(app.state, 'store'):
            result.status = "failed"
            result.msg = "下载器缓存未初始化"
            result.code = "500"
            return result

        cached_downloaders = app.state.store.get_snapshot_sync()

        # 根据 downloader_id 查找对应的下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        if not downloader_vo:
            result.status = "failed"
            result.msg = f"下载器不在缓存中 [downloader_id={downloader_id}]"
            result.code = "404"
            return result

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            result.status = "failed"
            result.msg = f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]"
            result.code = "503"
            return result

        # 获取缓存的客户端连接
        client = downloader_vo.client
        if not client:
            result.status = "failed"
            result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
            result.code = "500"
            return result

        # ========== 查询种子信息 ==========
        # 只查询指定下载器且未删除的种子（dr=0）
        torrent_records = db.query(torrentInfoModel).filter(
            torrentInfoModel.hash.in_(hashes),
            torrentInfoModel.downloader_id == downloader_id,
            torrentInfoModel.dr == 0  # 只操作未删除的种子
        ).all()

        if not torrent_records:
            result.status = "failed"
            result.msg = "未找到任何种子记录"
            result.code = "404"
            return result

        # 提取hash列表
        group_hashes = [r.hash for r in torrent_records]

        # ========== 执行恢复操作 ==========
        try:
            # 使用枚举类型判断下载器类型
            if downloader_vo.downloader_type == 0:
                # qBittorrent 下载器
                client.torrents_resume(torrent_hashes=group_hashes)

            elif downloader_vo.downloader_type == 1:
                # Transmission 下载器
                client.start_torrent(group_hashes)

            else:
                error_msg = f"不支持的下载器类型: {downloader_vo.downloader_type}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 修复CRITICAL #3: API调用成功后再更新数据库
            for record in torrent_records:
                old_status = record.status

                # 修复CRITICAL #1: 添加None检查避免空指针解引用
                if record.progress is not None and record.progress >= 100.0:
                    new_status = "seeding"
                else:
                    new_status = "downloading"

                record.status = new_status
                db.add(record)

                # 修复CRITICAL #4: 使用安全包装记录审计日志
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.RESUME,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_name": downloader_vo.nickname,
                        "downloader_type": downloader_vo.downloader_type,
                        "progress": record.progress
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    old_value={"status": old_status},
                    new_value={"status": new_status},
                    operation_result=AuditOperationResult.SUCCESS,
                    audit_info=audit_info
                )

            # 提交数据库事务
            db.commit()

            result.msg = f"成功开始 {len(torrent_records)} 个种子"
            result.data = {
                "success_count": len(torrent_records),
                "failed_items": []
            }

        except Exception as e:
            # 严格模式：任何失败都回滚
            db.rollback()
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"恢复种子失败 [downloader_id={downloader_id}]: {error_detail}")

            result.status = "failed"
            result.msg = f"恢复失败：{error_detail}"
            result.code = "500"
            result.data = {
                "success_count": 0,
                "failed_items": [{
                    "hash": r.hash,
                    "name": r.name,
                    "error": error_detail
                } for r in torrent_records]
            }

            # 记录失败的审计日志
            for record in torrent_records:
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.RESUME,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_type": downloader_vo.downloader_type,
                        "exception_type": type(e).__name__
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    operation_result=AuditOperationResult.FAILED,
                    error_message=error_detail,
                    audit_info=audit_info
                )

            return result
        # 注意：不再需要 finally 块手动释放连接，因为使用的是缓存连接

    except Exception as e:
        db.rollback()
        error_detail = f"{type(e).__name__}: {str(e)}"
        logger.error(f"恢复种子异常: {error_detail}")

        result.status = "failed"
        result.msg = f"操作异常：{error_detail}"
        result.code = "500"

    return result


# ==================== 重新检查种子 ====================

@router.post("/recheck", description="重新检查种子接口",
             response_model=CommonResponse)
async def recheck_torrents(
        request: Request,
        req_data: RecheckTorrentsRequest,
        db: Session = Depends(get_db)
):
    """
    批量重新检查种子

    功能：
    - 支持批量重新检查多个种子
    - 指定下载器ID，根据下载器类型调用不同API
    - 使用缓存中的客户端连接，避免重复创建
    - 严格模式：任何一个失败整体回滚
    - Transmission每次最多3个种子（用户自定义）
    - 立即更新数据库状态为checking
    - 记录审计日志

    修复CRITICAL问题：
    - #1: 资源泄漏 - 使用缓存连接，不手动logout
    - #2: 数据一致性 - 先执行API后更新数据库
    - #3: 审计日志异常 - 使用_safe_write_audit_log
    - #4: 下载器类型判断 - 使用枚举类型而非字符串比较

    请求格式：
    {
        "downloader_id": "下载器ID",
        "hashes": ["hash1", "hash2", ...]
    }
    """
    # 从请求模型中获取参数
    downloader_id = req_data.downloader_id
    hashes = req_data.hashes

    result = CommonResponse(
        status="success",
        msg="重新检查成功",
        code="200",
        data={"success_count": len(hashes), "failed_items": []}
    )

    # ========== 验证参数 ==========
    if not hashes or len(hashes) == 0:
        result.status = "failed"
        result.msg = "参数错误：hashes列表不能为空"
        result.code = "400"
        return result

    # Transmission并发限制（用户自定义：每次最多3个）
    MAX_CONCURRENT_RECHECK = 3

    try:
        # ========== 从缓存中获取下载器 ==========
        app = request.app
        if not hasattr(app.state, 'store'):
            result.status = "failed"
            result.msg = "下载器缓存未初始化"
            result.code = "500"
            return result

        cached_downloaders = app.state.store.get_snapshot_sync()

        # 根据 downloader_id 查找对应的下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        if not downloader_vo:
            result.status = "failed"
            result.msg = f"下载器不在缓存中 [downloader_id={downloader_id}]"
            result.code = "404"
            return result

        # 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            result.status = "failed"
            result.msg = f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]"
            result.code = "503"
            return result

        # 获取缓存的客户端连接
        client = downloader_vo.client
        if not client:
            result.status = "failed"
            result.msg = f"下载器客户端连接不存在 [downloader_id={downloader_id}]"
            result.code = "500"
            return result

        # ========== 查询种子信息 ==========
        # 只查询指定下载器且未删除的种子（dr=0）
        torrent_records = db.query(torrentInfoModel).filter(
            torrentInfoModel.hash.in_(hashes),
            torrentInfoModel.downloader_id == downloader_id,
            torrentInfoModel.dr == 0  # 只操作未删除的种子
        ).all()

        if not torrent_records:
            result.status = "failed"
            result.msg = "未找到任何种子记录"
            result.code = "404"
            return result

        # Transmission并发限制检查
        if downloader_vo.downloader_type == 1 and len(torrent_records) > MAX_CONCURRENT_RECHECK:
            error_msg = f"Transmission重检限制：每次最多{MAX_CONCURRENT_RECHECK}个种子，当前{len(torrent_records)}个"
            logger.error(error_msg)
            result.status = "failed"
            result.msg = error_msg
            result.code = "400"
            return result

        # 提取hash列表
        group_hashes = [r.hash for r in torrent_records]

        # ========== 执行重检操作 ==========
        try:
            # 使用枚举类型判断下载器类型
            if downloader_vo.downloader_type == 0:
                # qBittorrent 下载器
                client.torrents_recheck(torrent_hashes=group_hashes)

            elif downloader_vo.downloader_type == 1:
                # Transmission 下载器
                client.verify_torrent(group_hashes)

            else:
                error_msg = f"不支持的下载器类型: {downloader_vo.downloader_type}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 修复CRITICAL #2: API调用成功后再更新数据库
            for record in torrent_records:
                old_status = record.status
                record.status = "checking"
                db.add(record)

                # 修复CRITICAL #3: 使用安全包装记录审计日志
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.RECHECK,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_name": downloader_vo.nickname,
                        "downloader_type": downloader_vo.downloader_type
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    old_value={"status": old_status},
                    new_value={"status": "checking"},
                    operation_result=AuditOperationResult.SUCCESS,
                    audit_info=audit_info
                )

            # 提交数据库事务
            db.commit()

            result.msg = f"成功重检 {len(torrent_records)} 个种子"
            result.data = {
                "success_count": len(torrent_records),
                "failed_items": []
            }

        except Exception as e:
            # 严格模式：任何失败都回滚
            db.rollback()
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"重新检查种子失败 [downloader_id={downloader_id}]: {error_detail}")

            result.status = "failed"
            result.msg = f"重检失败：{error_detail}"
            result.code = "500"
            result.data = {
                "success_count": 0,
                "failed_items": [{
                    "hash": r.hash,
                    "name": r.name,
                    "error": error_detail
                } for r in torrent_records]
            }

            # 记录失败的审计日志
            for record in torrent_records:
                audit_info = extract_audit_info_from_request(request)
                _safe_write_audit_log(
                    operation_type=AuditOperationType.RECHECK,
                    operator="admin",
                    torrent_info_id=record.info_id,
                    operation_detail={
                        "downloader_id": downloader_id,
                        "downloader_type": downloader_vo.downloader_type,
                        "exception_type": type(e).__name__
                    },
                    torrent_name=record.name,
                    torrent_hash=record.hash,
                    downloader_id=downloader_id,
                    operation_result=AuditOperationResult.FAILED,
                    error_message=error_detail,
                    audit_info=audit_info
                )

            return result
        # 注意：不再需要 finally 块手动释放连接，因为使用的是缓存连接

    except Exception as e:
        db.rollback()
        error_detail = f"{type(e).__name__}: {str(e)}"
        logger.error(f"重新检查种子异常: {error_detail}")

        result.status = "failed"
        result.msg = f"操作异常：{error_detail}"
        result.code = "500"

    return result
