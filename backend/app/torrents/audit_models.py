"""
种子审计日志模型

用于记录所有种子操作，包括新增、删除、修改tracker、修改标签等。
审计日志对于安全审计、问题排查、用户行为分析都非常重要。
"""
from typing import Any, Optional, Dict
from datetime import datetime
import uuid
import json
import logging

from sqlalchemy import Column, String, Text, DATETIME
from app.database import Base
from app.core.json_parser import safe_json_parse_with_validator

logger = logging.getLogger(__name__)


class TorrentAuditLog(Base):
    """种子审计日志表

    记录所有种子操作，包括：
    - 种子新增
    - 种子删除（等级1-4）
    - 种子还原
    - Tracker信息修改
    - 标签修改
    - 其他重要操作

    操作详情以JSON格式存储在 operation_detail、old_value、new_value 字段中
    """
    __tablename__ = "torrent_audit_log"

    # 主键和基本信息
    log_id = Column(String(36), primary_key=True, index=True, comment="日志主键")
    torrent_info_id = Column(String(36), index=True, comment="关联种子主键")
    operation_type = Column(String(50), index=True, comment="操作类型")
    operation_detail = Column(Text, comment="操作详情（JSON格式）")

    # 变更记录
    old_value = Column(Text, comment="修改前的值（JSON）")
    new_value = Column(Text, comment="修改后的值（JSON）")

    # 操作信息
    operator = Column(String(50), index=True, comment="操作人")
    operation_time = Column(DATETIME, index=True, comment="操作时间")
    operation_result = Column(String(20), comment="操作结果：success/failed/partial")
    error_message = Column(Text, comment="错误信息（如果失败）")

    # 关联信息
    downloader_id = Column(String(36), index=True, comment="下载器ID")
    create_time = Column(DATETIME, comment="日志创建时间")

    # 冗余字段（用于列表显示和搜索，避免关联查询）
    torrent_name = Column(String(255), index=True, nullable=True, comment="种子名称（冗余字段，用于列表显示和搜索）")
    downloader_name = Column(String(100), nullable=True, comment="下载器名称（冗余字段，用于列表显示）")

    # 调试级别详细信息
    ip_address = Column(String(50), index=True, comment="操作来源IP地址")
    user_agent = Column(Text, comment="浏览器/客户端信息")
    request_id = Column(String(36), index=True, comment="请求唯一标识（用于追踪整个请求链路）")
    session_id = Column(String(36), index=True, comment="会话ID（用于关联同一会话的多个操作）")


    @property
    def id(self) -> str:
        """
        提供id属性，指向log_id

        用于兼容需要id属性的外部代码和ORM查询。
        解决query_logs方法中的'id属性访问问题。
        """
        return self.log_id

    def __init__(
        self,
        log_id: Optional[str] = None,
        torrent_info_id: Optional[str] = None,
        operation_type: Optional[str] = None,
        operation_detail: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        operator: Optional[str] = None,
        operation_time: Optional[datetime] = None,
        operation_result: Optional[str] = None,
        error_message: Optional[str] = None,
        downloader_id: Optional[str] = None,
        create_time: Optional[datetime] = None,
        torrent_name: Optional[str] = None,
        downloader_name: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kw: Any
    ):
        super().__init__(**kw)
        self.log_id = log_id or str(uuid.uuid4())
        self.torrent_info_id = torrent_info_id
        self.operation_type = operation_type
        self.operation_detail = operation_detail
        self.old_value = old_value
        self.new_value = new_value
        self.operator = operator
        self.operation_time = operation_time or datetime.now()
        self.operation_result = operation_result
        self.error_message = error_message
        self.downloader_id = downloader_id
        self.create_time = create_time or datetime.now()
        self.torrent_name = torrent_name
        self.downloader_name = downloader_name
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.request_id = request_id
        self.session_id = session_id

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "log_id": self.log_id,
            "torrent_info_id": self.torrent_info_id,
            "operation_type": self.operation_type,
            "operation_detail": self.operation_detail,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "operator": self.operator,
            "operation_time": self.operation_time,
            "operation_result": self.operation_result,
            "error_message": self.error_message,
            "downloader_id": self.downloader_id,
            "create_time": self.create_time,
            "torrent_name": self.torrent_name,
            "downloader_name": self.downloader_name,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "session_id": self.session_id,
        }

    def get_operation_detail_dict(self) -> Dict[str, Any]:
        """
        安全获取操作详情字典

        Returns:
            操作详情字典，解析失败返回空字典
        """
        return self._parse_json_field(self.operation_detail, 'operation_detail')

    def get_old_value_dict(self) -> Dict[str, Any]:
        """
        安全获取旧值字典

        Returns:
            旧值字典，解析失败返回空字典
        """
        return self._parse_json_field(self.old_value, 'old_value')

    def get_new_value_dict(self) -> Dict[str, Any]:
        """
        安全获取新值字典

        Returns:
            新值字典，解析失败返回空字典
        """
        return self._parse_json_field(self.new_value, 'new_value')

    def set_operation_detail(self, detail: Dict[str, Any]) -> bool:
        """
        安全设置操作详情

        Args:
            detail: 操作详情字典

        Returns:
            设置成功返回True，失败返回False
        """
        serialized = self._serialize_json_field(detail, 'operation_detail')
        if serialized is not None:
            self.operation_detail = serialized
            return True
        return False

    def set_old_value(self, value: Any) -> bool:
        """
        安全设置旧值

        Args:
            value: 旧值（任意可序列化对象）

        Returns:
            设置成功返回True，失败返回False
        """
        serialized = self._serialize_json_field(value, 'old_value')
        if serialized is not None:
            self.old_value = serialized
            return True
        return False

    def set_new_value(self, value: Any) -> bool:
        """
        安全设置新值

        Args:
            value: 新值（任意可序列化对象）

        Returns:
            设置成功返回True，失败返回False
        """
        serialized = self._serialize_json_field(value, 'new_value')
        if serialized is not None:
            self.new_value = serialized
            return True
        return False

    def _parse_json_field(self, json_str: Optional[str], field_name: str) -> Dict[str, Any]:
        """
        内部方法：安全解析JSON字段

        Args:
            json_str: JSON字符串
            field_name: 字段名称（用于日志）

        Returns:
            解析后的字典，失败返回空字典
        """
        # 验证函数：确保解析结果是字典类型
        def is_dict(obj: Any) -> bool:
            return isinstance(obj, dict)

        return safe_json_parse_with_validator(
            json_str,
            is_dict,
            default={},
            log_errors=True,
            error_context=f"(审计日志字段: {field_name})"
        )

    def _serialize_json_field(self, value: Any, field_name: str) -> Optional[str]:
        """
        内部方法：安全序列化JSON字段

        Args:
            value: 要序列化的值
            field_name: 字段名称（用于日志）

        Returns:
            JSON字符串，失败返回None
        """
        if value is None:
            return None

        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as e:
            logger.error(f"审计日志字段 {field_name} JSON序列化失败: {e}, 数据类型: {type(value)}")
            return None
