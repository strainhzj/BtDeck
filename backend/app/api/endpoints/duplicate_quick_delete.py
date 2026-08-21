"""
快捷删除重复种子接口

- ``POST /duplicates/quick-delete-preview``：分页预览跨下载器重复种子，分类 kept/to_delete/skipped。
- ``POST /duplicates/quick-delete``：服务端重算全部待删除种子，提交异步删除任务（level=2 只删种子不删文件）。

路由以 prefix="/torrents" 挂载，最终路径 /api/v1/torrents/duplicates/quick-delete[-preview]。
"""

import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user, AuthenticatedUserInfo
from app.database import get_db
from app.services.duplicate_quick_delete_service import (
    classify_duplicates,
    summarize,
    paginate_groups,
    collect_delete_candidates,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _dedupe(ids: List[str]) -> List[str]:
    """去重并剔除空白项（保持顺序）。"""
    return list(dict.fromkeys(i.strip() for i in ids if i and i.strip()))


def _validate(downloader_ids: List[str], keep_downloader_ids: List[str]):
    """校验参数，返回规范化后的 (去重待检测集合, 去重保留集合)。"""
    downloaders = _dedupe(downloader_ids)
    keeps = _dedupe(keep_downloader_ids)
    if len(downloaders) < 2:
        raise HTTPException(status_code=400, detail="待检测下载器至少选择 2 个")
    if len(keeps) < 1:
        raise HTTPException(status_code=400, detail="请至少选择 1 个保留下载器")
    invalid = [k for k in keeps if k not in downloaders]
    if invalid:
        raise HTTPException(status_code=400, detail=f"保留下载器必须属于待检测下载器：{invalid}")
    return downloaders, keeps


class QuickDeletePreviewRequest(BaseModel):
    """快捷删除重复种子预览请求参数"""

    downloader_ids: List[str] = Field(..., description="待检测下载器ID集合（≥2）")
    keep_downloader_ids: List[str] = Field(..., description="保留下载器ID集合（≥1，需为 downloader_ids 子集）")
    page: int = Field(default=1, ge=1, description="页码(从1开始)")
    pageSize: int = Field(default=20, ge=1, le=1000, description="每页记录数")


class QuickDeleteRequest(BaseModel):
    """快捷删除重复种子执行请求参数"""

    downloader_ids: List[str] = Field(..., description="待检测下载器ID集合（≥2）")
    keep_downloader_ids: List[str] = Field(..., description="保留下载器ID集合（≥1，需为 downloader_ids 子集）")
    delete_level: int = Field(default=2, ge=2, le=2, description="删除等级（固定2：只删种子不删文件）")
    notify_on_complete: bool = Field(default=True, description="删除任务完成后发送系统通知")


@router.post("/duplicates/quick-delete-preview", response_model=CommonResponse)
async def quick_delete_preview(
    payload: QuickDeletePreviewRequest,
    current_user: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    分页预览跨下载器重复种子

    返回 hash 分组的重复组列表（分页），并附带不受分页影响的全量汇总：
    total_groups（重复组总数）、total_delete（待删除种子数）、skipped_groups（无保留副本的组数）。
    """
    try:
        downloaders, keeps = _validate(payload.downloader_ids, payload.keep_downloader_ids)
        groups = classify_duplicates(db, downloaders, keeps)
        summary = summarize(groups)
        page_groups, total = paginate_groups(groups, payload.page, payload.pageSize)

        logger.info(
            f"快捷删除重复种子预览成功: 用户={current_user.username}, "
            f"待检测={len(downloaders)}个下载器, 重复组={summary['total_groups']}, "
            f"待删除={summary['total_delete']}"
        )
        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data={
                "total": total,
                "page": payload.page,
                "pageSize": payload.pageSize,
                "total_groups": summary["total_groups"],
                "total_delete": summary["total_delete"],
                "skipped_groups": summary["skipped_groups"],
                "list": page_groups,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"快捷删除重复种子预览失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {str(e)}", code="500", data=None)


@router.post("/duplicates/quick-delete", response_model=CommonResponse)
async def quick_delete(
    request: Request,
    payload: QuickDeleteRequest,
    current_user: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    服务端重算全部待删除重复种子并提交异步删除任务（level=2 保留数据）

    与预览共享分类服务，提交任务时以当前数据为准重新计算待删除集合，
    不依赖前端分页快照，保证删除一致性与不误删保留副本。
    """
    try:
        downloaders, keeps = _validate(payload.downloader_ids, payload.keep_downloader_ids)
        # 提交阶段保留活动项，由任务管理器原子查重并返回跳过数量。
        groups = classify_duplicates(db, downloaders, keeps, exclude_active=False)
        candidates = collect_delete_candidates(groups)

        if not candidates:
            return CommonResponse(
                status="success",
                msg="未发现可删除的重复种子",
                code="200",
                data={
                    "task_id": None,
                    "total_count": 0,
                    "requested_count": 0,
                    "accepted_count": 0,
                    "skipped_count": 0,
                    "skipped_info_ids": [],
                    "delete_level": payload.delete_level,
                },
            )

        from app.database import SessionLocal
        from app.services.deletion_task_manager import get_deletion_task_manager
        from app.services.async_deletion_executor import AsyncDeletionExecutor

        task_manager = get_deletion_task_manager()
        submission = await task_manager.create_task_reserving(
            torrent_info_ids=candidates,
            delete_level=payload.delete_level,
            operator=current_user.username,
        )
        if submission.task_id is None:
            return CommonResponse(
                status="success",
                msg="重复种子均已在删除任务中处理",
                code="200",
                data={
                    "task_id": None,
                    "total_count": 0,
                    "requested_count": submission.requested_count,
                    "accepted_count": 0,
                    "skipped_count": submission.skipped_count,
                    "skipped_info_ids": submission.skipped_info_ids,
                    "delete_level": payload.delete_level,
                },
            )

        task_id = submission.task_id
        executor = AsyncDeletionExecutor(db_session_factory=SessionLocal, request=request)
        asyncio.create_task(
            executor.execute_deletion_task(
                task_id=task_id,
                torrent_info_ids=submission.accepted_info_ids,
                delete_level=payload.delete_level,
                operator=current_user.username,
                request=request,
                notify_on_complete=payload.notify_on_complete,
            )
        )
        logger.info(
            f"提交快捷删除重复种子任务: task_id={task_id}, 用户={current_user.username}, "
            f"接受数={submission.accepted_count}, 跳过数={submission.skipped_count}, "
            f"delete_level={payload.delete_level}, "
            f"notify_on_complete={payload.notify_on_complete}"
        )
        return CommonResponse(
            status="success",
            msg="已提交删除任务，正在后台执行",
            code="200",
            data={
                "task_id": task_id,
                "total_count": submission.accepted_count,
                "requested_count": submission.requested_count,
                "accepted_count": submission.accepted_count,
                "skipped_count": submission.skipped_count,
                "skipped_info_ids": submission.skipped_info_ids,
                "delete_level": payload.delete_level,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交快捷删除重复种子任务失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"提交任务失败: {str(e)}", code="500", data=None)
