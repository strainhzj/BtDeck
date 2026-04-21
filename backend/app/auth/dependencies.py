# app/auth/dependencies.py
from fastapi import Depends, HTTPException, status, Cookie, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import Optional, Union
from app.database import get_db
from app.auth.models import User
from app.config import settings
from app.auth import utils as auth_utils
from app.api.responseVO import CommonResponse
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


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
    统一的Token验证依赖注入函数

    从请求头中获取 x-access-token,验证其有效性。
    验证失败时返回错误响应,成功时返回None。

    使用示例:
        @router.post("/endpoint")
        async def endpoint(
            auth_error: Union[CommonResponse, None] = Depends(verify_token_dependency),
            db: Session = Depends(get_db)
        ):
            if auth_error:
                return auth_error
            # ... 业务逻辑
    """
    token = request.headers.get("x-access-token")
    if not token:
        logger.info(f"Token缺失: {request.url}")
        return CommonResponse(status="error", msg="Token缺失", code="401")

    try:
        user_info = auth_utils.verify_access_token(token)
        if not user_info:
            logger.info(f"Token验证失败: {request.url}")
            return CommonResponse(status="error", msg="token验证失败", code="401")
        # 将用户信息存储到request.state中供后续使用
        request.state.user_info = user_info
    except Exception as e:
        logger.info(f"Token验证异常: {str(e)}, url: {request.url}")
        return CommonResponse(status="error", msg="token验证失败", code="401")

    return None
