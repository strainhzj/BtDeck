"""
审计日志服务（同步版本）

提供审计日志的记录、查询、归档等功能。
这是审计日志系统的独立调用入口，所有模块都通过这个服务记录审计日志。
使用同步数据库会话，与项目的数据库架构一致。
"""
import os
import json
import shutil
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from sqlalchemy import and_, or_, desc
from sqlalchemy.orm import Session
from fastapi import Request, Depends

from app.core.json_parser import safe_json_parse
from app.torrents.audit_models import TorrentAuditLog
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.database import get_db

logger = logging.getLogger(__name__)


class AuditLogServiceSync:
    """审计日志服务（同步版本）

    提供审计日志的记录、查询、导出、归档等功能。
    这是审计日志系统的独立调用入口，所有模块都通过这个服务记录审计日志。
    使用同步数据库会话，与项目的数据库架构一致。
    """

    def __init__(self, db_session: Session):
        """初始化审计日志服务

        Args:
            db_session: 数据库会话（同步）
        """
        self.db_session = db_session

    def log_operation(
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
            self.db_session.commit()
            self.db_session.refresh(audit_log)

            logger.debug(f"记录审计日志成功: {operation_type} - {operator} - {torrent_info_id}")
            return audit_log

        except Exception as e:
            logger.error(f"记录审计日志失败: {str(e)}")
            self.db_session.rollback()
            return None

    def query_logs(
        self,
        torrent_info_id: Optional[str] = None,
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
        """查询审计日志（分页）

        Args:
            torrent_info_id: 种子信息ID
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
            包含list、total、page、pageSize的字典
        """
        try:
            # 构建查询条件
            query = self.db_session.query(TorrentAuditLog)

            conditions = []
            if torrent_info_id:
                conditions.append(TorrentAuditLog.torrent_info_id == torrent_info_id)
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
                query = query.filter(and_(*conditions))

            # 按时间倒序排列
            query = query.order_by(desc(TorrentAuditLog.operation_time))

            # 总数
            total = query.count()

            # 分页
            offset = (page - 1) * page_size
            logs = query.offset(offset).limit(page_size).all()

            # 转换为字典列表
            logs_list = []
            for log in logs:
                log_dict = {
                    "id": log.id,
                    "torrent_info_id": log.torrent_info_id,
                    "operation_type": log.operation_type,
                    "operation_detail": safe_json_parse(log.operation_detail, None),
                    "old_value": safe_json_parse(log.old_value, None),
                    "new_value": safe_json_parse(log.new_value, None),
                    "operator": log.operator,
                    "operation_time": log.operation_time.isoformat() if log.operation_time else None,
                    "operation_result": log.operation_result,
                    "error_message": log.error_message,
                    "downloader_id": log.downloader_id,
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                    "request_id": log.request_id,
                    "session_id": log.session_id
                }
                logs_list.append(log_dict)

            return {
                "list": logs_list,
                "total": total,
                "page": page,
                "pageSize": page_size
            }

        except Exception as e:
            logger.error(f"查询审计日志失败: {str(e)}")
            return {
                "list": [],
                "total": 0,
                "page": page,
                "pageSize": page_size
            }

    def get_statistics(
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
            # 构建查询条件
            query = self.db_session.query(TorrentAuditLog)

            if start_time:
                query = query.filter(TorrentAuditLog.operation_time >= start_time)
            if end_time:
                query = query.filter(TorrentAuditLog.operation_time <= end_time)

            # 总数
            total = query.count()

            # 按操作类型统计
            operation_type_stats = {}
            for op_type in AuditOperationType:
                count = query.filter(TorrentAuditLog.operation_type == op_type.value).count()
                if count > 0:
                    operation_type_stats[op_type.value] = count

            # 按操作结果统计
            success_count = query.filter(TorrentAuditLog.operation_result == AuditOperationResult.SUCCESS).count()
            failed_count = query.filter(TorrentAuditLog.operation_result == AuditOperationResult.FAILED).count()
            partial_count = query.filter(TorrentAuditLog.operation_result == AuditOperationResult.PARTIAL).count()

            # 按操作人统计（Top 10）
            operator_stats = {}
            from sqlalchemy import func
            operator_query = query.with_entities(
                TorrentAuditLog.operator,
                func.count(TorrentAuditLog.id).label('count')
            ).group_by(TorrentAuditLog.operator).order_by(
                desc('count')
            ).limit(10).all()

            for operator, count in operator_query:
                operator_stats[operator] = count

            return {
                "total": total,
                "operation_type_stats": operation_type_stats,
                "operation_result_stats": {
                    "success": success_count,
                    "failed": failed_count,
                    "partial": partial_count
                },
                "top_operators": operator_stats
            }

        except Exception as e:
            logger.error(f"获取审计日志统计失败: {str(e)}")
            return {}

    def archive_logs(
        self,
        end_time: datetime,
        archive_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """归档审计日志

        将指定时间之前的审计日志导出到归档文件，并从主数据库中删除。

        Args:
            end_time: 归档截止时间
            archive_path: 归档文件路径（可选，默认自动生成）

        Returns:
            包含success、message、archived_count、file_path的字典
        """
        try:
            # 查询需要归档的日志
            query = self.db_session.query(TorrentAuditLog).filter(
                TorrentAuditLog.operation_time < end_time
            )

            # 获取总数
            total = query.count()
            if total == 0:
                return {
                    "success": False,
                    "message": "没有需要归档的日志",
                    "archived_count": 0,
                    "file_path": None
                }

            # 获取所有日志
            logs = query.all()

            # 生成归档文件路径
            if not archive_path:
                archive_dir = Path("data/audit_logs_archive")
                archive_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                archive_path = archive_dir / f"audit_logs_archive_{timestamp}.json"

            # 导出为JSON
            logs_data = []
            for log in logs:
                log_dict = {
                    "id": log.id,
                    "torrent_info_id": log.torrent_info_id,
                    "operation_type": log.operation_type,
                    "operation_detail": safe_json_parse(log.operation_detail, None),
                    "old_value": safe_json_parse(log.old_value, None),
                    "new_value": safe_json_parse(log.new_value, None),
                    "operator": log.operator,
                    "operation_time": log.operation_time.isoformat() if log.operation_time else None,
                    "operation_result": log.operation_result,
                    "error_message": log.error_message,
                    "downloader_id": log.downloader_id,
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                    "request_id": log.request_id,
                    "session_id": log.session_id
                }
                logs_data.append(log_dict)

            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump(logs_data, f, ensure_ascii=False, indent=2)

            # 删除已归档的日志
            query.delete(synchronize_session=False)
            self.db_session.commit()

            logger.info(f"归档审计日志成功: {total} 条记录已归档到 {archive_path}")

            return {
                "success": True,
                "message": f"成功归档 {total} 条日志",
                "archived_count": total,
                "file_path": str(archive_path)
            }

        except Exception as e:
            logger.error(f"归档审计日志失败: {str(e)}")
            self.db_session.rollback()
            return {
                "success": False,
                "message": f"归档失败: {str(e)}",
                "archived_count": 0,
                "file_path": None
            }

    def export_logs_to_csv(
        self,
        logs: List[Dict[str, Any]],
        output_path: str
    ) -> bool:
        """导出日志到CSV文件

        Args:
            logs: 日志列表
            output_path: 输出文件路径

        Returns:
            是否成功
        """
        try:
            import csv

            # 定义字段
            fieldnames = [
                'id', 'torrent_info_id', 'operation_type', 'operator',
                'operation_time', 'operation_result', 'error_message',
                'downloader_id', 'ip_address', 'request_id', 'session_id'
            ]

            # 写入CSV
            with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for log in logs:
                    row = {
                        'id': log.get('id'),
                        'torrent_info_id': log.get('torrent_info_id'),
                        'operation_type': log.get('operation_type'),
                        'operator': log.get('operator'),
                        'operation_time': log.get('operation_time'),
                        'operation_result': log.get('operation_result'),
                        'error_message': log.get('error_message'),
                        'downloader_id': log.get('downloader_id'),
                        'ip_address': log.get('ip_address'),
                        'request_id': log.get('request_id'),
                        'session_id': log.get('session_id')
                    }
                    writer.writerow(row)

            logger.info(f"导出审计日志到CSV成功: {output_path}")
            return True

        except Exception as e:
            logger.error(f"导出审计日志到CSV失败: {str(e)}")
            return False

    def export_logs_to_excel(
        self,
        logs: List[Dict[str, Any]],
        output_path: str
    ) -> bool:
        """导出日志到Excel文件

        Args:
            logs: 日志列表
            output_path: 输出文件路径

        Returns:
            是否成功
        """
        try:
            import pandas as pd

            # 准备数据
            data = []
            for log in logs:
                row = {
                    'ID': log.get('id'),
                    '种子ID': log.get('torrent_info_id'),
                    '操作类型': log.get('operation_type'),
                    '操作人': log.get('operator'),
                    '操作时间': log.get('operation_time'),
                    '操作结果': log.get('operation_result'),
                    '错误信息': log.get('error_message'),
                    '下载器ID': log.get('downloader_id'),
                    'IP地址': log.get('ip_address'),
                    '请求ID': log.get('request_id'),
                    '会话ID': log.get('session_id')
                }
                data.append(row)

            # 创建DataFrame
            df = pd.DataFrame(data)

            # 写入Excel
            df.to_excel(output_path, index=False, engine='openpyxl')

            logger.info(f"导出审计日志到Excel成功: {output_path}")
            return True

        except ImportError:
            logger.error("导出Excel失败: 未安装pandas或openpyxl")
            return False
        except Exception as e:
            logger.error(f"导出审计日志到Excel失败: {str(e)}")
            return False


# 依赖注入函数
def get_audit_service_sync(db: Session = Depends(get_db)) -> AuditLogServiceSync:
    """获取审计日志服务实例（依赖注入）

    Args:
        db: 数据库会话

    Returns:
        AuditLogServiceSync实例
    """
    return AuditLogServiceSync(db)
