# app/auth/dependencies.py
from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.auth.models import User
from app.config import settings
from datetime import datetime

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
