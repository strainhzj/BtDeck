"""
审计日志服务（异步版本）

提供审计日志的记录、查询、归档等功能。
这是审计日志系统的独立调用入口，所有模块都通过这个服务记录审计日志。

性能优化特性：
- 异步数据库操作，不阻塞主业务
- 批量插入优化
- 连接池管理
- 失败重试机制
"""
import os
import json
import uuid
import shutil
import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from sqlalchemy import and_, or_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request, Depends

from app.torrents.audit_models import TorrentAuditLog
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.database import get_async_db

logger = logging.getLogger(__name__)


class AuditLogService:
    """审计日志服务（异步版本）

    提供审计日志的记录、查询、导出、归档等功能。
    这是审计日志系统的独立调用入口，所有模块都通过这个服务记录审计日志。

    性能优化：
    - 使用异步数据库操作，不阻塞主业务
    - 批量操作优化
    - 连接池管理
    - 失败重试机制
    """

    def __init__(self, db_session: AsyncSession, max_retries: int = 3, retry_delay: float = 0.1):
        """初始化审计日志服务

        Args:
            db_session: 数据库会话（异步）
            max_retries: 失败重试次数（默认3次）
            retry_delay: 重试延迟（秒）
        """
        self.db_session = db_session
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def log_operation(
        self,
        operation_type: str,
        operator: str,
        torrent_info_id: Optional[str] = None,
        operation_detail: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        operation_result: str = AuditOperationResult.SUCCESS,
        error_message: Optional[str] = None,
        downloader_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[TorrentAuditLog]:
        """记录单个操作日志（调试级别详细程度）

        Args:
            operation_type: 操作类型（使用 AuditOperationType 枚举）
            operator: 操作人
            torrent_info_id: 关联种子ID（可选）
            operation_detail: 操作详情（字典）
            old_value: 修改前的值（字典）
            new_value: 修改后的值（字典）
            operation_result: 操作结果（success/failed/partial）
            error_message: 错误信息
            downloader_id: 下载器ID
            ip_address: 操作来源IP地址
            user_agent: 浏览器/客户端信息
            request_id: 请求唯一标识（用于追踪整个请求链路）
            session_id: 会话ID（用于关联同一会话的多个操作）

        Returns:
            TorrentAuditLog对象，失败返回None
        """
        # 使用重试机制
        for attempt in range(self.max_retries):
            try:
                # 生成请求ID（如果未提供）
                if not request_id:
                    request_id = f"req_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

                # 🔥 自动提取 torrent_name 和 downloader_name（冗余字段优化）
                # 从 operation_detail 中提取，避免列表查询时关联数据库
                extracted_torrent_name = None
                extracted_downloader_name = None

                if operation_detail and isinstance(operation_detail, dict):
                    extracted_torrent_name = operation_detail.get('torrent_name')
                    extracted_downloader_name = operation_detail.get('downloader_name')

                # 创建审计日志对象
                audit_log = TorrentAuditLog(
                    torrent_info_id=torrent_info_id,
                    operation_type=operation_type,
                    operation_detail=json.dumps(operation_detail, ensure_ascii=False, default=str) if operation_detail else None,
                    old_value=json.dumps(old_value, ensure_ascii=False, default=str) if old_value else None,
                    new_value=json.dumps(new_value, ensure_ascii=False, default=str) if new_value else None,
                    operator=operator,
                    operation_time=datetime.now(),
                    operation_result=operation_result,
                    error_message=error_message,
                    downloader_id=downloader_id,
                    torrent_name=extracted_torrent_name,  # 🔥 冗余字段
                    downloader_name=extracted_downloader_name,  # 🔥 冗余字段
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_id=request_id,
                    session_id=session_id
                )

                # 写入数据库
                self.db_session.add(audit_log)
                await self.db_session.commit()

                # 刷新以获取数据库生成的值
                await self.db_session.refresh(audit_log)

                logger.debug(f"审计日志记录成功: {operation_type} - {operator} - {torrent_info_id}")
                return audit_log

            except Exception as e:
                logger.error(f"记录审计日志失败 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                await self.db_session.rollback()

                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    # 最后一次尝试失败，返回None
                    return None

    async def log_batch_operations(
        self,
        operations: List[Dict[str, Any]],
        operator: str
    ) -> int:
        """批量记录操作日志（性能优化版本）

        使用批量插入优化，大幅提升性能。

        Args:
            operations: 操作列表，每个操作包含：
                - operation_type: 操作类型
                - torrent_info_id: 种子ID（可选）
                - operation_detail: 操作详情（可选）
                - old_value: 旧值（可选）
                - new_value: 新值（可选）
                - operation_result: 操作结果（可选）
                - error_message: 错误信息（可选）
                - downloader_id: 下载器ID（可选）
                - ip_address: IP地址（可选）
                - user_agent: User-Agent（可选）
                - request_id: 请求ID（可选）
                - session_id: 会话ID（可选）
            operator: 操作人

        Returns:
            成功记录的数量
        """
        if not operations:
            return 0

        try:
            # 准备批量插入的数据
            current_time = datetime.now()
            log_entries = []

            for op in operations:
                log_id = str(uuid.uuid4())  # 需要导入 uuid
                request_id = op.get('request_id') or f"req_{current_time.strftime('%Y%m%d%H%M%S%f')}"

                # 🔥 自动提取 torrent_name 和 downloader_name（冗余字段优化）
                # 从 operation_detail 中提取，避免列表查询时关联数据库
                operation_detail = op.get('operation_detail')
                extracted_torrent_name = None
                extracted_downloader_name = None

                if operation_detail and isinstance(operation_detail, dict):
                    extracted_torrent_name = operation_detail.get('torrent_name')
                    extracted_downloader_name = operation_detail.get('downloader_name')

                log_entry = {
                    "log_id": log_id,
                    "torrent_info_id": op.get('torrent_info_id'),
                    "operation_type": op.get('operation_type'),
                    "operation_detail": json.dumps(op.get('operation_detail'), ensure_ascii=False, default=str) if op.get('operation_detail') else None,
                    "old_value": json.dumps(op.get('old_value'), ensure_ascii=False, default=str) if op.get('old_value') else None,
                    "new_value": json.dumps(op.get('new_value'), ensure_ascii=False, default=str) if op.get('new_value') else None,
                    "operator": operator,
                    "operation_time": current_time,
                    "operation_result": op.get('operation_result', AuditOperationResult.SUCCESS),
                    "error_message": op.get('error_message'),
                    "downloader_id": op.get('downloader_id'),
                    "torrent_name": extracted_torrent_name,  # 🔥 冗余字段
                    "downloader_name": extracted_downloader_name,  # 🔥 冗余字段
                    "ip_address": op.get('ip_address'),
                    "user_agent": op.get('user_agent'),
                    "request_id": request_id,
                    "session_id": op.get('session_id'),
                    "create_time": current_time
                }
                log_entries.append(log_entry)

            # 使用批量插入优化
            await self.db_session.execute(
                TorrentAuditLog.__table__.insert(),
                log_entries
            )
            await self.db_session.commit()

            logger.info(f"批量记录审计日志完成: {len(log_entries)}/{len(operations)}")
            return len(log_entries)

        except Exception as e:
            logger.error(f"批量记录审计日志失败: {str(e)}")
            await self.db_session.rollback()
            return 0

    async def query_logs(
        self,
        torrent_info_id: Optional[str] = None,
        torrent_name: Optional[str] = None,
        operation_type: Optional[str] = None,
        operator: Optional[str] = None,
        downloader_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        operation_result: Optional[str] = None,
        ip_address: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """查询审计日志（支持分页和筛选）

        Args:
            torrent_info_id: 种子信息ID
            torrent_name: 种子名称（支持模糊搜索）
            operation_type: 操作类型
            operator: 操作人
            downloader_id: 下载器ID
            start_time: 开始时间
            end_time: 结束时间
            operation_result: 操作结果
            ip_address: IP地址
            request_id: 请求ID
            session_id: 会话ID
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            {
                "total": 总数量,
                "page": 当前页码,
                "pageSize": 每页数量,
                "list": [审计日志列表]
            }
        """
        try:
            # 构建基础查询
            query = select(TorrentAuditLog)

            # 构建筛选条件
            conditions = []

            if torrent_info_id:
                conditions.append(TorrentAuditLog.torrent_info_id == torrent_info_id)

            if torrent_name:
                # 🔥 支持 torrent_name 模糊搜索（使用 LIKE）
                conditions.append(TorrentAuditLog.torrent_name.like(f'%{torrent_name}%'))

            if operation_type:
                conditions.append(TorrentAuditLog.operation_type == operation_type)

            if operator:
                conditions.append(TorrentAuditLog.operator == operator)

            if downloader_id:
                conditions.append(TorrentAuditLog.downloader_id == downloader_id)

            if start_time:
                conditions.append(TorrentAuditLog.operation_time >= start_time)

            if end_time:
                conditions.append(TorrentAuditLog.operation_time <= end_time)

            if operation_result:
                conditions.append(TorrentAuditLog.operation_result == operation_result)

            if ip_address:
                conditions.append(TorrentAuditLog.ip_address == ip_address)

            if request_id:
                conditions.append(TorrentAuditLog.request_id == request_id)

            if session_id:
                conditions.append(TorrentAuditLog.session_id == session_id)

            if conditions:
                query = query.where(and_(*conditions))

            # 获取总数
            count_query = select(func.count()).select_from(query.subquery())
            count_result = await self.db_session.execute(count_query)
            total = count_result.scalar_one()  # scalar_one() 是同步方法，不需要 await

            # 排序和分页
            query = query.order_by(desc(TorrentAuditLog.operation_time))
            offset = (page - 1) * page_size
            query = query.limit(page_size).offset(offset)

            # 执行查询
            result = await self.db_session.execute(query)
            logs = result.scalars().all()  # scalars() 是同步方法，不需要 await

            # 转换为字典列表
            log_list = [log.to_dict() for log in logs]

            return {
                "total": total,
                "page": page,
                "pageSize": page_size,
                "list": log_list
            }

        except Exception as e:
            logger.error(f"查询审计日志失败: {str(e)}")
            return {
                "total": 0,
                "page": page,
                "pageSize": page_size,
                "list": []
            }

    async def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """获取审计日志统计信息

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息字典
        """
        try:
            query = select(TorrentAuditLog)

            # 时间范围筛选
            conditions = []
            if start_time:
                conditions.append(TorrentAuditLog.operation_time >= start_time)
            if end_time:
                conditions.append(TorrentAuditLog.operation_time <= end_time)

            if conditions:
                query = query.where(and_(*conditions))

            # 执行查询
            result = await self.db_session.execute(query)
            logs = result.scalars().all()  # scalars() 是同步方法，不需要 await

            # 统计信息
            total_count = len(logs)
            operation_type_stats = {}
            operator_stats = {}
            result_stats = {}

            for log in logs:
                # 操作类型统计
                op_type = log.operation_type or "unknown"
                operation_type_stats[op_type] = operation_type_stats.get(op_type, 0) + 1

                # 操作人统计
                operator = log.operator or "unknown"
                operator_stats[operator] = operator_stats.get(operator, 0) + 1

                # 结果统计
                result = log.operation_result or "unknown"
                result_stats[result] = result_stats.get(result, 0) + 1

            return {
                "total_count": total_count,
                "operation_type_stats": operation_type_stats,
                "operator_stats": operator_stats,
                "result_stats": result_stats
            }

        except Exception as e:
            logger.error(f"获取审计日志统计失败: {str(e)}")
            return {
                "total_count": 0,
                "operation_type_stats": {},
                "operator_stats": {},
                "result_stats": {}
            }

    async def archive_logs(
        self,
        end_time: datetime,
        archive_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """归档审计日志

        将指定时间之前的审计日志导出到归档文件，并从主数据库中删除。

        Args:
            end_time: 归档截止时间（此时间之前的日志将被归档）
            archive_path: 归档文件路径（默认使用 data/audit_logs_archive/YYYYMMDD_HHMMSS.json）

        Returns:
            归档结果：
            {
                "success": True/False,
                "archived_count": 归档数量,
                "archive_path": "归档文件路径",
                "message": "结果消息"
            }
        """
        try:
            # 查询需要归档的日志
            query = select(TorrentAuditLog).where(
                TorrentAuditLog.operation_time < end_time
            )

            result = await self.db_session.execute(query)
            logs_to_archive = result.scalars().all()

            if not logs_to_archive:
                return {
                    "success": True,
                    "archived_count": 0,
                    "archive_path": None,
                    "message": "没有需要归档的日志"
                }

            # 生成归档文件路径
            if not archive_path:
                archive_dir = Path("data/audit_logs_archive")
                archive_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                archive_path = archive_dir / f"audit_logs_{timestamp}.json"

            # 导出为JSON
            archive_data = {
                "archive_time": datetime.now().isoformat(),
                "end_time": end_time.isoformat(),
                "log_count": len(logs_to_archive),
                "logs": [log.to_dict() for log in logs_to_archive]
            }

            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump(archive_data, f, ensure_ascii=False, indent=2, default=str)

            # 从主数据库删除已归档的日志
            for log in logs_to_archive:
                await self.db_session.delete(log)

            await self.db_session.commit()

            # 记录归档操作
            await self.log_operation(
                operation_type=AuditOperationType.ARCHIVE_LOGS,
                operator="system",
                operation_detail={
                    "archived_count": len(logs_to_archive),
                    "archive_path": str(archive_path),
                    "end_time": end_time.isoformat()
                }
            )

            logger.info(f"审计日志归档成功: {len(logs_to_archive)} 条日志已归档到 {archive_path}")

            return {
                "success": True,
                "archived_count": len(logs_to_archive),
                "archive_path": str(archive_path),
                "message": f"成功归档 {len(logs_to_archive)} 条日志"
            }

        except Exception as e:
            logger.error(f"归档审计日志失败: {str(e)}")
            await self.db_session.rollback()

            return {
                "success": False,
                "archived_count": 0,
                "archive_path": None,
                "message": f"归档失败: {str(e)}"
            }

    async def export_logs_to_csv(
        self,
        logs: List[Dict[str, Any]],
        output_path: str
    ) -> bool:
        """导出审计日志为CSV格式

        Args:
            logs: 审计日志字典列表
            output_path: 输出文件路径

        Returns:
            成功返回True，失败返回False
        """
        try:
            import csv

            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)

                # 写入表头
                writer.writerow([
                    '日志ID', '种子ID', '操作类型', '操作人', '操作时间',
                    '操作结果', '错误信息', '下载器ID', 'IP地址', 'User-Agent',
                    '请求ID', '会话ID', '操作详情', '旧值', '新值'
                ])

                # 写入数据
                for log_dict in logs:
                    # 安全的字典访问，确保每个键都有值
                    writer.writerow([
                        log_dict.get('log_id', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('torrent_info_id', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('operation_type', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('operator', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('operation_time', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('operation_result', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('error_message', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('downloader_id', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('ip_address', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('user_agent', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('request_id', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('session_id', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('operation_detail', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('old_value', '') if isinstance(log_dict, dict) else '',
                        log_dict.get('new_value', '') if isinstance(log_dict, dict) else ''
                    ])

            logger.info(f"审计日志导出CSV成功: {output_path}")
            return True

        except Exception as e:
            logger.error(f"导出审计日志CSV失败: {str(e)}")
            return False

    async def export_logs_to_excel(
        self,
        logs: List[Dict[str, Any]],
        output_path: str
    ) -> bool:
        """导出审计日志为Excel格式

        Args:
            logs: 审计日志字典列表
            output_path: 输出文件路径

        Returns:
            成功返回True，失败返回False
        """
        try:
            import pandas as pd

            # 转换为DataFrame
            data = []
            for log_dict in logs:
                # 安全的字典访问
                if not isinstance(log_dict, dict):
                    logger.warning(f"跳过非字典类型的日志项: {type(log_dict)}")
                    continue

                data.append({
                    '日志ID': log_dict.get('log_id', ''),
                    '种子ID': log_dict.get('torrent_info_id', ''),
                    '操作类型': log_dict.get('operation_type', ''),
                    '操作人': log_dict.get('operator', ''),
                    '操作时间': log_dict.get('operation_time', ''),
                    '操作结果': log_dict.get('operation_result', ''),
                    '错误信息': log_dict.get('error_message', ''),
                    '下载器ID': log_dict.get('downloader_id', ''),
                    'IP地址': log_dict.get('ip_address', ''),
                    'User-Agent': log_dict.get('user_agent', ''),
                    '请求ID': log_dict.get('request_id', ''),
                    '会话ID': log_dict.get('session_id', ''),
                    '操作详情': log_dict.get('operation_detail', ''),
                    '旧值': log_dict.get('old_value', ''),
                    '新值': log_dict.get('new_value', '')
                })

            df = pd.DataFrame(data)

            # 导出为Excel
            df.to_excel(output_path, index=False, engine='openpyxl')

            logger.info(f"审计日志导出Excel成功: {output_path}")
            return True

        except ImportError:
            logger.error("导出Excel失败: 缺少 pandas 或 openpyxl 库")
            return False
        except Exception as e:
            logger.error(f"导出审计日志Excel失败: {str(e)}")
            return False


# 依赖注入函数
async def get_audit_service(
    db_session: AsyncSession = Depends(get_async_db)
) -> AuditLogService:
    """获取审计日志服务（依赖注入）

    Args:
        db_session: 数据库会话（异步）

    Returns:
        审计日志服务实例
    """
    return AuditLogService(db_session)


# 辅助函数：从Request对象提取审计信息
def extract_audit_info_from_request(request: Request) -> Dict[str, str]:
    """从Request对象提取审计信息

    Args:
        request: FastAPI Request对象

    Returns:
        包含审计信息的字典：
        {
            "ip_address": "客户端IP地址",
            "user_agent": "User-Agent字符串",
            "request_id": "请求ID（如果存在）",
            "session_id": "会话ID（如果存在）"
        }
    """
    # 获取客户端IP
    # 优先从 X-Forwarded-For 获取，然后从 X-Real-IP，最后从 client.host
    # 安全地提取客户端IP地址
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else ""
    if not ip_address:
        ip_address = request.headers.get("X-Real-IP", "")
    if not ip_address and request.client:
        ip_address = request.client.host

    # 获取 User-Agent
    user_agent = request.headers.get("User-Agent", "")

    # 获取请求ID（如果存在）
    request_id = request.headers.get("X-Request-ID", "")

    # 获取会话ID（从Cookie中）
    session_id = ""
    session_cookie = request.cookies.get("session")
    if session_cookie:
        session_id = session_cookie

    return {
        "ip_address": ip_address,
        "user_agent": user_agent,
        "request_id": request_id,
        "session_id": session_id
    }
