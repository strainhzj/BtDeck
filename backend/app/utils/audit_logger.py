"""
审计日志模块 - 删除操作审计记录器

提供独立的审计日志文件系统，用于长期保存和合规要求。
审计日志使用结构化格式，便于日志分析工具解析和人工审查。

主要功能:
- 结构化日志格式 (人工可读 + 机器可解析)
- 自动日志文件滚动 (按天滚动，保留30天)
- 特殊字符安全处理
- 单例模式确保全局唯一实例

作者: btpManager Team
版本: v1.0
创建时间: 2025-01-15
最后更新: 2025-02-14
"""

import logging
import os
import re
import gzip
import shutil
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from threading import Lock


class _AuditLoggerSingleton:
    """
    审计日志记录器单例类

    使用单例模式确保全局只有一个实例，避免重复创建和资源浪费。
    """

    _instance: Optional['_AuditLoggerSingleton'] = None
    _lock: Lock = Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        log_dir: str = "logs/audit",
        enable_compression: bool = True,
        compression_days: int = 7
    ):
        """
        初始化审计日志记录器

        Args:
            log_dir: 日志文件目录（相对于后端项目根目录）
            enable_compression: 是否启用gzip压缩旧日志
            compression_days: 超过多少天的日志进行gzip压缩
        """
        # 确保只初始化一次
        if hasattr(self, '_initialized'):
            return

        self.log_dir = log_dir
        self.enable_compression = enable_compression
        self.compression_days = compression_days

        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)

        # 创建logger
        self.logger = logging.getLogger("audit.deletion")
        self.logger.setLevel(logging.INFO)

        # 防止重复添加handler
        if not self.logger.handlers:
            # 配置文件处理器（按天滚动）
            log_file = os.path.join(
                self.log_dir,
                f"deletion_{datetime.now():%Y-%m-%d}.log"
            )
            handler = TimedRotatingFileHandler(
                log_file,
                when='midnight',
                interval=1,
                backupCount=30,
                encoding='utf-8'
            )

            # 设置结构化格式
            formatter = _AuditFormatter()
            handler.setFormatter(formatter)

            self.logger.addHandler(handler)

            # 添加文件滚动后的压缩回调
            if self.enable_compression:
                handler.rotator = _CompressingRotator(
                    compression_days=self.compression_days
                )

        self._initialized = True

    def _sanitize_special_chars(self, text: str) -> str:
        """
        清理特殊字符，确保日志格式安全

        替换规则:
        - / → \\
        - \\ → /
        - | → !
        - " → '
        - \n → \\n
        - \r → \\r
        - \t → \\t

        Args:
            text: 原始文本

        Returns:
            清理后的安全文本
        """
        if not text:
            return ""

        # 顺序很重要，先处理转义字符
        replacements = [
            ('\\', '/'),   # 先交换反斜杠
            ('/', '\\'),   # 再交换正斜杠
            ('|', '!'),
            ('"', "'"),
            ('\n', '\\n'),
            ('\r', '\\r'),
            ('\t', '\\t'),
        ]

        result = text
        for old, new in replacements:
            result = result.replace(old, new)

        return result

    def _format_timestamp(self) -> str:
        """
        格式化时间戳（本地时区 + UTC标记）

        格式: [2025-01-15 10:23:45 UTC+8]

        Returns:
            格式化的时间戳字符串
        """
        # 获取本地时间
        local_now = datetime.now()

        # 获取UTC偏移量（秒）
        utc_offset_seconds = datetime.now(timezone.utc).astimezone().utcoffset().total_seconds()
        utc_offset_hours = utc_offset_seconds // 3600

        # 格式化时间戳
        timestamp_str = local_now.strftime("%Y-%m-%d %H:%M:%S")

        # 添加UTC标记
        if utc_offset_hours >= 0:
            utc_marker = f"UTC+{utc_offset_hours}"
        else:
            utc_marker = f"UTC{utc_offset_hours}"

        return f"[{timestamp_str} {utc_marker}]"

    def log_deletion(
        self,
        downloader_info: Dict[str, Any],
        torrent_info: Dict[str, Any],
        operator_info: Dict[str, Any],
        caller_source: str,
        validation_result: Dict[str, Any],
        deletion_status: str,
        error_message: Optional[str] = None,
        duration: Optional[float] = None
    ):
        """
        记录删除操作审计日志

        Args:
            downloader_info: 下载器信息 {"id": 1, "nickname": "qb1", "type": "qBittorrent"}
            torrent_info: 种子信息 {"hash": "...", "name": "...", "size": ...}
            operator_info: 操作者信息 {"id": 1, "name": "admin", "ip": "...", "user_agent": "..."}
            caller_source: 调用来源 "API删除", "定时任务删除", "回收站清理"
            validation_result: 验证结果 {"status": "pass", "safety": "基础", ...}
            deletion_status: 删除状态 "success", "partial", "failed"
            error_message: 错误信息（可选）
            duration: 操作耗时（秒，可选）
        """
        # 确定日志等级
        if deletion_status == "success":
            log_level = logging.INFO
            status_text = "SUCCESS"
        elif deletion_status == "partial":
            log_level = logging.WARNING
            status_text = "PARTIAL"
        else:  # failed
            log_level = logging.ERROR
            status_text = "FAILED"

        # 构建结构化日志消息
        log_parts = []

        # 1. 时间戳
        log_parts.append(self._format_timestamp())

        # 2. 操作类型和状态
        log_parts.append(f"DELETE | {status_text}")

        # 3. 下载器信息
        downloader_id = downloader_info.get("id", "?")
        downloader_nickname = self._sanitize_special_chars(
            str(downloader_info.get("nickname", ""))
        )
        downloader_type = self._sanitize_special_chars(
            str(downloader_info.get("type", ""))
        )
        log_parts.append(
            f"downloader: {downloader_nickname} (id:{downloader_id}, type:{downloader_type})"
        )

        # 4. 种子信息
        torrent_hash = torrent_info.get("hash", "")[:40]  # 限制长度
        torrent_name = self._sanitize_special_chars(
            str(torrent_info.get("name", ""))
        )
        torrent_size = torrent_info.get("size", 0)

        # 格式化文件大小
        if torrent_size >= 1024**3:
            size_str = f"{torrent_size / (1024**3):.2f}GB"
        elif torrent_size >= 1024**2:
            size_str = f"{torrent_size / (1024**2):.2f}MB"
        else:
            size_str = f"{torrent_size}B"

        log_parts.append(
            f"torrent: {torrent_hash} (name:{torrent_name}, size:{size_str})"
        )

        # 5. 操作者信息
        operator_id = operator_info.get("id")
        operator_name = self._sanitize_special_chars(
            str(operator_info.get("name", ""))
        )
        operator_ip = operator_info.get("ip")
        operator_ua = self._sanitize_special_chars(
            str(operator_info.get("user_agent", ""))
        )

        if operator_id is not None:
            log_parts.append(
                f"operator: {operator_name} (id:{operator_id}, ip:{operator_ip}, ua:{operator_ua[:50]})"
            )
        else:
            # 系统操作者（定时任务、回收站清理）
            log_parts.append(
                f"operator: {operator_name} (system)"
            )

        # 6. 调用来源
        caller_sanitized = self._sanitize_special_chars(caller_source)
        log_parts.append(f"source: {caller_sanitized}")

        # 7. 验证结果
        v_status = validation_result.get("status", "?")
        v_safety = validation_result.get("safety", "?")
        v_seed_status = validation_result.get("seed_status", "")
        v_added_time = validation_result.get("added_time", "")
        v_files_exist = validation_result.get("files_exist", False)
        v_active = validation_result.get("active", False)
        v_progress = validation_result.get("progress", 0)

        validation_parts = [f"status:{v_status}", f"safety:{v_safety}"]
        if v_seed_status:
            validation_parts.append(f"seed_status:{v_seed_status}")
        if v_added_time:
            validation_parts.append(f"added_time:{v_added_time}")
        if v_files_exist is not False:
            validation_parts.append(f"files:{v_files_exist}")
        if v_active is not False:
            validation_parts.append(f"active:{v_active}")
        if v_progress:
            validation_parts.append(f"progress:{v_progress}%")

        log_parts.append(f"validation: {', '.join(validation_parts)}")

        # 8. 文件标志
        files_flag = validation_result.get("files_exist", False)
        log_parts.append(f"files: {str(files_flag).lower()}")

        # 9. 耗时
        if duration is not None:
            log_parts.append(f"duration: {duration:.2f}s")

        # 10. 错误信息（如果有）
        if error_message:
            error_sanitized = self._sanitize_special_chars(error_message)
            log_parts.append(f"error: {error_sanitized}")

        # 使用 | 分隔符连接所有部分
        log_message = " | ".join(log_parts)

        # 记录日志
        self.logger.log(log_level, log_message)


class _AuditFormatter(logging.Formatter):
    """
    审计日志格式化器

    由于我们已经在 log_deletion 方法中完成了格式化，
    这个格式化器主要用于保持接口一致性。
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录

        Args:
            record: 日志记录对象

        Returns:
            格式化的日志字符串
        """
        # 直接返回消息，因为已经在 log_deletion 中完成格式化
        return record.getMessage()


class _CompressingRotator:
    """
    日志文件压缩处理器

    当日志文件滚动时，自动压缩超过指定天数的旧日志文件。
    """

    def __init__(self, compression_days: int = 7):
        """
        初始化压缩处理器

        Args:
            compression_days: 超过多少天的日志进行gzip压缩
        """
        self.compression_days = compression_days

    def __call__(self, source: str, dest: str):
        """
        当文件滚动时调用

        Args:
            source: 源文件路径
            dest: 目标文件路径
        """
        # 压缩超过指定天数的旧日志
        try:
            if os.path.exists(source):
                # 检查文件是否需要压缩
                file_age_days = self._get_file_age_days(source)

                if file_age_days >= self.compression_days:
                    self._compress_file(source)
        except Exception as e:
            # 压缩失败不影响日志记录
            print(f"Warning: Failed to compress log file: {e}")

    def _get_file_age_days(self, file_path: str) -> int:
        """
        计算文件年龄（天数）

        Args:
            file_path: 文件路径

        Returns:
            文件年龄（天数）
        """
        try:
            file_time = os.path.getmtime(file_path)
            current_time = datetime.now().timestamp()
            age_seconds = current_time - file_time
            return int(age_seconds // (24 * 3600))
        except Exception:
            return 0

    def _compress_file(self, file_path: str):
        """
        压缩单个文件

        Args:
            file_path: 要压缩的文件路径
        """
        try:
            # 读取原文件
            with open(file_path, 'rb') as f_in:
                with open(f"{file_path}.gz", 'wb') as f_out:
                    with gzip.GzipFile(fileobj=f_out, mode='wb') as gzip_file:
                        shutil.copyfileobj(f_in, gzip_file)

            # 删除原文件
            os.remove(file_path)
        except Exception as e:
            print(f"Warning: Failed to compress {file_path}: {e}")


# 导出的单例类
AuditLogger = _AuditLoggerSingleton


# 便捷函数
def get_audit_logger() -> AuditLogger:
    """
    获取审计日志记录器单例

    Returns:
        AuditLogger单例
    """
    return AuditLogger()


async def export_audit_logs_from_db_to_file(
    db_session,
    operation_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 1000
) -> int:
    """
    从数据库导出审计日志到统一格式的日志文件
    
    将数据库中的审计日志按照现有文件日志格式导出，
    用于长期保存和合规审计。
    
    Args:
        db_session: 数据库会话（异步）
        operation_type: 操作类型筛选（可选）
        start_time: 开始时间（可选）
        end_time: 结束时间（可选）
        limit: 导出数量限制（默认1000条）
    
    Returns:
        导出的日志条数
    """
    from sqlalchemy import select
    from app.torrents.audit_models import TorrentAuditLog
    from app.torrents.audit_enums import AuditOperationType
    
    try:
        # 构建查询
        query = select(TorrentAuditLog)
        
        # 筛选条件
        conditions = []
        if operation_type:
            conditions.append(TorrentAuditLog.operation_type == operation_type)
        if start_time:
            conditions.append(TorrentAuditLog.operation_time >= start_time)
        if end_time:
            conditions.append(TorrentAuditLog.operation_time <= end_time)
        
        if conditions:
            from sqlalchemy import and_
            query = query.where(and_(*conditions))
        
        # 限制数量并排序
        query = query.order_by(desc(TorrentAuditLog.operation_time)).limit(limit)
        
        # 执行查询
        result = await db_session.execute(query)
        logs = (await result.scalars()).all()
        
        if not logs:
            logger.info("没有需要导出的审计日志")
            return 0
        
        # 获取审计日志记录器单例
        audit_logger = get_audit_logger()
        
        # 导出数量
        exported_count = 0
        
        # 遍历每条日志，转换为文件格式
        for log in logs:
            try:
                # 根据操作类型决定如何记录
                if log.operation_type in [
                    AuditOperationType.DELETE_L1,
                    AuditOperationType.DELETE_L2,
                    AuditOperationType.DELETE_L3,
                    AuditOperationType.DELETE_L4
                ]:
                    # 删除操作：转换为删除日志格式
                    downloader_info = {
                        "id": log.downloader_id or "?",
                        "nickname": log.downloader_id or "",  # 简化
                        "type": "unknown"
                    }
                    torrent_info = {
                        "hash": log.torrent_info_id or "",
                        "name": "",  # 从operation_detail解析
                        "size": 0
                    }
                    operator_info = {
                        "id": 0,  # 系统操作
                        "name": log.operator or "system",
                        "ip": log.ip_address or "",
                        "user_agent": log.user_agent or ""
                    }
                    validation_result = {
                        "status": "unknown"
                    }
                    deletion_status = log.operation_result or "unknown"
                    
                    # 尝试从operation_detail解析更多信息
                    if log.operation_detail:
                        try:
                            import json
                            detail = json.loads(log.operation_detail)
                            if isinstance(detail, dict):
                                torrent_info["name"] = detail.get("torrent_name", "")
                                torrent_info["size"] = detail.get("torrent_size", 0)
                                validation_result.update(detail.get("validation_result", {}))
                        except:
                            pass
                    
                    # 记录为文件日志
                    audit_logger.log_deletion(
                        downloader_info=downloader_info,
                        torrent_info=torrent_info,
                        operator_info=operator_info,
                        caller_source="DATABASE_EXPORT",
                        validation_result=validation_result,
                        deletion_status=deletion_status,
                        error_message=log.error_message,
                        duration=None
                    )
                else:
                    # 其他操作：记录为通用操作日志
                    log_parts = []
                    log_parts.append(audit_logger._format_timestamp())
                    log_parts.append(f"OPERATION | {log.operation_type or 'UNKNOWN'}")
                    
                    if log.torrent_info_id:
                        log_parts.append(f"torrent: {log.torrent_info_id}")
                    if log.operator:
                        log_parts.append(f"operator: {log.operator}")
                    if log.ip_address:
                        log_parts.append(f"ip: {log.ip_address}")
                    if log.operation_result:
                        log_parts.append(f"result: {log.operation_result}")
                    
                    # 构建日志消息
                    log_message = " | ".join(log_parts)
                    
                    # 确定日志级别
                    if log.operation_result == "success":
                        log_level = logging.INFO
                    elif log.operation_result == "partial":
                        log_level = logging.WARNING
                    else:
                        log_level = logging.ERROR
                    
                    audit_logger.logger.log(log_level, log_message)
                
                exported_count += 1
            
            except Exception as e:
                logger.warning(f"导出审计日志失败 (ID: {log.log_id}): {str(e)}")
                continue
        
        logger.info(f"成功导出 {exported_count}/{len(logs)} 条审计日志到文件")
        return exported_count
    
    except Exception as e:
        logger.error(f"导出审计日志到文件失败: {str(e)}")
        return 0
