from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Optional, Union

from fastapi import Depends, HTTPException, status, Cookie, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.models import User
from app.core.config import settings
from app.auth import utils as auth_utils
from app.api.responseVO import CommonResponse

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUserInfo:
    """统一认证依赖返回的用户信息，供迁移后的 endpoint 直接注入使用。"""

    username: str
    payload: dict
    token: str
    # 从 JWT payload 解析的业务用户ID（可选）。
    # 不强制存在：旧 token 可能不含 user_id（verify_access_token 的
    # required_fields 不含 user_id，保持向后兼容），此时为 None。
    # endpoint 取用时需兼容 None（与原 get_current_user_id 兜底行为一致）。
    user_id: Optional[int] = None


def _auth_error_response(message: str = "token验证失败") -> CommonResponse:
    """统一认证失败响应格式，兼容现有 CommonResponse API 约定。"""
    return CommonResponse(status="error", msg=message, code="401", data=None)


def _extract_access_token(request: Request) -> Optional[str]:
    """兼容 X-Access-Token 与 Authorization: Bearer 两种调用方式。"""
    x_access_token = request.headers.get("x-access-token")
    if x_access_token:
        return x_access_token

    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return None


def _authenticate_request(request: Request) -> Optional[AuthenticatedUserInfo]:
    """解析并校验请求 token，成功时写入 request.state.user_info。"""
    token = _extract_access_token(request)
    if not token:
        return None

    payload = auth_utils.verify_access_token(token)
    if not payload:
        return None

    # 兜底解析 user_id：新 token 含此字段，旧 token 可能缺失，统一兼容 None。
    raw_user_id = payload.get("user_id")
    user_id: Optional[int] = None
    if raw_user_id is not None:
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            user_id = None

    user_info = AuthenticatedUserInfo(
        username=str(payload.get("sub")),
        payload=payload,
        token=token,
        user_id=user_id,
    )
    request.state.user_info = user_info
    return user_info


async def require_authenticated_user(request: Request) -> AuthenticatedUserInfo:
    """
    新的统一认证 dependency。

    迁移方式：
        user_info: AuthenticatedUserInfo = Depends(require_authenticated_user)

    第一阶段仅新增依赖，不批量替换现有 endpoint；后续迁移时可移除各文件中
    手写的 request.headers.get("x-access-token") 与 verify_access_token 逻辑。
    """
    user_info = _authenticate_request(request)
    if user_info:
        return user_info

    logger.info("Token验证失败: %s", request.url)
    response = _auth_error_response()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=response.model_dump())


def get_current_user(
        db: Session = Depends(get_db),
        token: Optional[str] = Cookie(None),
        auth_header: Optional[str] = Depends(oauth2_scheme)
):
    """从Cookie或Authorization头中获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 优先使用Cookie中的token
    token_to_use = token if token else auth_header
    if not token_to_use:
        raise credentials_exception

    try:
        payload = jwt.decode(token_to_use, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception

        # 检查令牌是否过期
        exp = payload.get("exp")
        if not exp or datetime.fromtimestamp(exp) < datetime.utcnow():
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


async def verify_token_dependency(request: Request) -> Union[CommonResponse, None]:
    """
    统一的Token验证依赖注入函数（已弃用）

    .. deprecated:: v1.0.5-audit
        所有端点已迁移至 :func:`require_authenticated_user`。该依赖保留仅用于过渡兼容，
        请勿在新代码中使用。

    从请求头中获取 X-Access-Token 或 Authorization: Bearer,验证其有效性。
    验证失败时返回错误响应,成功时返回None。

    使用示例（已废弃，请改用 require_authenticated_user）:
        @router.post("/endpoint")
        async def endpoint(
            _user=Depends(require_authenticated_user),  # 推荐
            db: Session = Depends(get_db)
        ):
            # ... 业务逻辑
    """
    import warnings

    warnings.warn(
        "verify_token_dependency 已弃用，请改用 require_authenticated_user",
        DeprecationWarning,
        stacklevel=2,
    )
    token = _extract_access_token(request)
    user_info = _authenticate_request(request)
    if not user_info:
        if token:
            logger.info(f"Token验证失败: {request.url}")
            return _auth_error_response()
        logger.info(f"Token缺失: {request.url}")
        return _auth_error_response("Token缺失")

    return None
