"""协议无关审计上下文。

服务层不再接收 FastAPI ``Request`` 来提取审计信息（IP/User-Agent/
请求与会话标识），改为注入本值对象。HTTP 端点经 ``AuditContext.from_request``
构造；未来 MCP 侧由认证 principal 构造（见 PLANS/mcp-service-capabilities.md
§4.4/§10.3）。字段口径与 ``extract_audit_info_from_request`` 一致。
"""

import logging
from dataclasses import dataclass, fields
from typing import Dict

from fastapi import Request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditContext:
    """请求级审计四元组（缺失字段为空串，与提取函数降级语义一致）。"""

    ip_address: str = ""
    user_agent: str = ""
    request_id: str = ""
    session_id: str = ""

    @classmethod
    def from_request(cls, request: Request) -> "AuditContext":
        """从 FastAPI Request 提取审计信息。

        提取失败仅告警并返回空上下文——审计信息缺失不得影响业务主流程
        （与 TorrentDeletionByLevelService 原 ``_audit_request_info`` 容错一致）。
        """
        try:
            from app.services.audit_service import extract_audit_info_from_request

            info = extract_audit_info_from_request(request)
        except Exception as e:  # noqa: BLE001 - 审计信息缺失不影响主流程
            logger.warning(f"提取请求审计信息失败: {e}")
            return cls()
        return cls(
            ip_address=str(info.get("ip_address", "") or ""),
            user_agent=str(info.get("user_agent", "") or ""),
            request_id=str(info.get("request_id", "") or ""),
            session_id=str(info.get("session_id", "") or ""),
        )

    def as_dict(self) -> Dict[str, str]:
        """展开为 ``**kwargs`` 审计字段（供 ``log_operation`` 直接消费）。"""
        return {f.name: getattr(self, f.name) for f in fields(self)}
