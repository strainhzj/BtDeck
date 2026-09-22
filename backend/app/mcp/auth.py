"""MCP transport 认证接线（feature mcp-service-capabilities-2026-08-28 W2）。

计划 §4.4：MCP transport 只负责从授权 header 提取 Bearer token，token →
principal 全链校验复用协议无关内核 ``app/auth/principal.py``（HTTP 侧
``app/auth/dependencies.py`` 现有语义不动）。拒绝原因码经 errors.py 的
``PRINCIPAL_REASON_TO_ERROR`` 映射为稳定错误码（G3）。

token 提取复用 ``app.auth.dependencies._extract_access_token``（X-Access-Token
与 Authorization: Bearer 双兼容，不在本文件手写解析——BTD201 同源纪律）；
该函数只依赖 starlette Request 的 ``headers`` 接口，MCP streamable HTTP 的
``request_context.request`` 恰是同一类型（SDK transport 注入，见 server.py）。

W5 新增服务密钥路径：token 以 ``btdmcp_`` 开头时走 ``mcp.apikey.v1`` 的
SHA-256 哈希校验 + 归属用户状态校验（长期有效，供外部 agent 对接）；其余
仍走 JWT 全链。两条路径共用 principal 内核的用户状态校验与原因码体系。
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.auth.dependencies import _extract_access_token
from app.auth.principal import (
    AuthenticatedPrincipal,
    PrincipalAuthenticationError,
    authenticate_access_token,
    build_principal_for_username,
)
from app.mcp.contracts import looks_like_mcp_api_key
from app.mcp.errors import PRINCIPAL_REASON_TO_ERROR, McpErrorCode, McpToolError
from app.services.mcp_apikey_service import McpApiKeyService

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

    W5 起两条认证路径并存（按形态路由，fail-closed）：

    - ``btdmcp_`` 前缀（服务密钥，长期有效，供外部 agent）：哈希校验 +
      归属用户状态校验（见 `_authenticate_api_key`）；
    - 其余（Web 会话 JWT）：既有 `authenticate_access_token` 全链。

    未知原因码兜底 AUTH_TOKEN_INVALID（fail-closed：映射表未登记的新拒绝
    原因不允许演变为放行或裸异常）。
    """
    if looks_like_mcp_api_key(token):
        return _authenticate_api_key(token, db)
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


def _authenticate_api_key(token: Optional[str], db: Session) -> AuthenticatedPrincipal:
    """服务密钥路径：哈希校验 → 归属用户状态校验（与 JWT 路径同原因码体系）。

    密钥无效/不存在/行损坏 ⇒ AUTH_API_KEY_INVALID（与 JWT 失败分开，便于
    agent 侧区分「密钥需刷新」与「会话过期」）；归属用户不存在/禁用/强制
    改密 ⇒ 既有 USER_* 原因码（principal 内核同源语义）。
    """
    owner = McpApiKeyService(db).resolve_owner(token or "")
    if not owner:
        raise McpToolError(McpErrorCode.AUTH_API_KEY_INVALID)
    try:
        # 不传原始密钥进主体对象（凭据不驻留）；payload 仅作溯源标记
        return build_principal_for_username(owner, db, payload={"sub": owner, "auth_method": "api_key"})
    except PrincipalAuthenticationError as exc:
        raw_code = PRINCIPAL_REASON_TO_ERROR.get(exc.reason)
        code = McpErrorCode(raw_code) if raw_code is not None else McpErrorCode.AUTH_API_KEY_INVALID
        raise McpToolError(code) from exc
