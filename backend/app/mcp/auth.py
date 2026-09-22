"""MCP transport 认证接线（feature mcp-service-capabilities-2026-08-28 W2）。

计划 §4.4：MCP transport 只负责从授权 header 提取 Bearer token，token →
principal 全链校验复用协议无关内核 ``app/auth/principal.py``（HTTP 侧
``app/auth/dependencies.py`` 现有语义不动）。拒绝原因码经 errors.py 的
``PRINCIPAL_REASON_TO_ERROR`` 映射为稳定错误码（G3）。

token 提取复用 ``app.auth.dependencies._extract_access_token``（X-Access-Token
与 Authorization: Bearer 双兼容，不在本文件手写解析——BTD201 同源纪律）；
该函数只依赖 starlette Request 的 ``headers`` 接口，MCP streamable HTTP 的
``request_context.request`` 恰是同一类型（SDK transport 注入，见 server.py）。
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.auth.dependencies import _extract_access_token
from app.auth.principal import AuthenticatedPrincipal, PrincipalAuthenticationError, authenticate_access_token
from app.mcp.errors import PRINCIPAL_REASON_TO_ERROR, McpErrorCode, McpToolError

logger = logging.getLogger(__name__)


def extract_token_from_request(request: object) -> Optional[str]:
    """从 transport 请求对象提取 token（缺 header / 形态不符返回 None）。"""
    if request is None:
        return None
    try:
        return _extract_access_token(request)  # type: ignore[arg-type]
    except Exception:  # header 面异常一律按无 token 处理，fail-closed
        logger.warning("MCP transport token 提取异常，按未携带处理", exc_info=True)
        return None


def authenticate_token(token: Optional[str], db: Session) -> AuthenticatedPrincipal:
    """token → principal 全链校验；失败按原因码映射为稳定 MCP 错误。

    未知原因码兜底 AUTH_TOKEN_INVALID（fail-closed：映射表未登记的新拒绝
    原因不允许演变为放行或裸异常）。
    """
    try:
        return authenticate_access_token(token, db)
    except PrincipalAuthenticationError as exc:
        # 映射表值为稳定字符串码（W0 契约），此处收敛为枚举成员
        raw_code = PRINCIPAL_REASON_TO_ERROR.get(exc.reason)
        code = McpErrorCode(raw_code) if raw_code is not None else McpErrorCode.AUTH_TOKEN_INVALID
        raise McpToolError(code) from exc
    except McpToolError:
        raise
    except Exception as exc:
        # 认证内核自身的意外异常（DB 故障等）不得外泄细节，也不得放行
        logger.exception("MCP 认证内核意外异常")
        raise McpToolError(McpErrorCode.INTERNAL_ERROR) from exc
