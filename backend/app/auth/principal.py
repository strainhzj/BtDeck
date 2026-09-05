"""协议无关认证内核（HTTP 与未来 MCP 共用）。

背景（PLANS/mcp-service-capabilities.md §4.4/§10.1-3）：
现有 ``require_authenticated_user`` 纯 token 校验不查 DB，
``get_current_user`` 查 DB 但不校验 ``is_active``/``must_change_password``
（is_active 仅登录时拦截、强制改密仅登录响应标志）。本内核为净新增：
统一 token → principal 并补齐用户状态校验，供 MCP transport / 控制面
等协议无关调用方使用。**现有 HTTP 依赖语义保持不变**，不在本模块内
抛 HTTPException 或构造 CommonResponse。
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.auth import utils as auth_utils
from app.auth.models import User

# 拒绝原因稳定码（MCP 侧映射错误码用；HTTP 侧暂不消费）
REASON_TOKEN_MISSING = "TOKEN_MISSING"
REASON_TOKEN_INVALID = "TOKEN_INVALID"
REASON_USER_NOT_FOUND = "USER_NOT_FOUND"
REASON_USER_INACTIVE = "USER_INACTIVE"
REASON_PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """认证主体：操作者只能来自本对象，禁止取信工具/请求参数中的 user_id。"""

    user_id: Optional[int]
    username: str
    is_active: bool
    must_change_password: bool
    token: str
    payload: Dict[str, Any]


class PrincipalAuthenticationError(Exception):
    """认证失败（携带稳定拒绝原因码与人类可读消息）。"""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def authenticate_access_token(token: Optional[str], db: Session) -> AuthenticatedPrincipal:
    """校验访问 token 并加载用户状态，返回认证主体。

    校验链：token 存在 → JWT/登录密钥一致性（``verify_access_token``）→
    用户存在 → ``is_active`` → ``must_change_password``。任一失败抛
    ``PrincipalAuthenticationError``。

    ``user_id`` 口径：优先取 JWT payload（新 token 携带），旧 token 缺失时
    回退数据库主键——与现有 ``AuthenticatedUserInfo`` 的兼容语义一致。
    """

    if not token:
        raise PrincipalAuthenticationError(REASON_TOKEN_MISSING, "缺少访问令牌")

    payload = auth_utils.verify_access_token(token)
    if not payload:
        raise PrincipalAuthenticationError(REASON_TOKEN_INVALID, "访问令牌无效或已过期")

    username = payload.get("sub")
    if not username or not isinstance(username, str):
        raise PrincipalAuthenticationError(REASON_TOKEN_INVALID, "访问令牌缺少有效主体")

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise PrincipalAuthenticationError(REASON_USER_NOT_FOUND, "用户不存在")

    if not user.is_active:
        raise PrincipalAuthenticationError(REASON_USER_INACTIVE, "用户已禁用")

    if user.must_change_password:
        raise PrincipalAuthenticationError(REASON_PASSWORD_CHANGE_REQUIRED, "用户处于强制改密状态")

    raw_user_id = payload.get("user_id")
    user_id: Optional[int] = None
    if raw_user_id is not None:
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            user_id = None
    if user_id is None:
        user_id = user.id

    return AuthenticatedPrincipal(
        user_id=user_id,
        username=username,
        is_active=True,
        must_change_password=False,
        token=token,
        payload=payload,
    )
