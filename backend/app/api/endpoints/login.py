from datetime import datetime, timedelta

import yaml
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import models, security, utils
from app.auth.request import RefreshRequest, UserLogin
from app.core.config import settings
from app.core.config import settings as app_settings
from app.database import get_db

router = APIRouter()


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@router.post("/login", summary="用户登录", tags=["login"], response_model=CommonResponse)
def login(
    request_user: UserLogin,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """用户登录接口，支持可选 TOTP 验证。"""
    try:
        user = db.query(models.User).filter(models.User.username == request_user.username).first()

        login_log = models.LoginLog(
            username=request_user.username,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            user_id=_safe_int(user.id) if user else None,
            success=False,
        )

        if not user or not security.verify_password(request_user.password, user.password):
            db.add(login_log)
            db.commit()
            return CommonResponse(code="401", msg="用户名或密码错误", status="error", data=[])

        if user.two_factor_flag == "1":
            if not request_user.twofa_code:
                db.add(login_log)
                db.commit()
                return CommonResponse(code="400", msg="请填写两步验证码", status="error", data=[])

            if not utils.verify_totp(user.two_factor_secret, request_user.twofa_code):
                db.add(login_log)
                db.commit()
                return CommonResponse(code="401", msg="验证码错误，请重试", status="error", data=[])

        with open(app_settings.YAML_PATH, "r") as f:
            new_config = yaml.load(f, Loader=yaml.SafeLoader)

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = utils.create_access_token(
            data={
                "sub": user.username,
                "user_id": str(user.id),
                "is_admin": "1",
                "verify_secret": new_config["security"]["login_status_secret"],
            },
            expires_delta=access_token_expires,
        )

        # 双令牌体系（W6-1）：签发 refresh token，仅存 SHA-256 哈希
        refresh_token = utils.create_refresh_token()
        db.add(
            models.RefreshToken(
                user_id=user.id,
                token_hash=utils.hash_refresh_token(refresh_token),
                expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
                ip_address=request.client.host if request else None,
                user_agent=request.headers.get("user-agent") if request else None,
            )
        )

        login_log.success = True
        db.add(login_log)
        db.commit()

        token_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
        }
        return CommonResponse(code="200", msg="登录成功", status="success", data=[token_data])

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return CommonResponse(code="500", msg=f"系统异常: {str(e)}", status="error", data=[])


@router.post("/refresh", summary="刷新访问令牌", tags=["login"], response_model=CommonResponse)
def refresh_token(
    refresh_request: RefreshRequest,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """双令牌体系（W6-1）：用 refresh token 换发新 access_token + 新 refresh_token。

    - refresh token 本体不落库：按 SHA-256 哈希查记录
    - 使用即轮换：旧记录置 revoked_at，换发新记录
    - 已撤销/过期/不存在一律 401（前端据此走登出）
    """
    try:
        token_hash = utils.hash_refresh_token(refresh_request.refresh_token)
        record = db.query(models.RefreshToken).filter(models.RefreshToken.token_hash == token_hash).first()

        if not record or record.revoked_at is not None:
            return CommonResponse(code="401", msg="refresh token 无效或已撤销", status="error", data=[])
        if record.expires_at < datetime.utcnow():
            return CommonResponse(code="401", msg="refresh token 已过期", status="error", data=[])

        user = db.query(models.User).filter(models.User.id == record.user_id).first()
        if not user or not user.is_active:
            return CommonResponse(code="401", msg="用户不存在或已停用", status="error", data=[])

        # 使用即轮换：撤销旧记录
        record.revoked_at = datetime.utcnow()

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = utils.create_access_token(
            data={
                "sub": user.username,
                "user_id": str(user.id),
                "is_admin": "1",
                "verify_secret": utils.get_login_secret(),
            },
            expires_delta=access_token_expires,
        )

        new_refresh_token = utils.create_refresh_token()
        db.add(
            models.RefreshToken(
                user_id=user.id,
                token_hash=utils.hash_refresh_token(new_refresh_token),
                expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
                ip_address=request.client.host if request else None,
                user_agent=request.headers.get("user-agent") if request else None,
            )
        )
        db.commit()

        token_data = {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
        }
        return CommonResponse(code="200", msg="刷新成功", status="success", data=[token_data])

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return CommonResponse(code="500", msg=f"系统异常: {str(e)}", status="error", data=[])
