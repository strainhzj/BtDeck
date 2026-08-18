from datetime import datetime, timedelta

import yaml
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import models, security, utils
from app.auth.login_throttle import login_throttle
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
        client_ip = request.client.host if request else None

        # 登录限流（W9）：阶梯锁定中的键直接拒绝，不写日志防灌库。
        # 密码与 TOTP 失败共用同一计数（见 login_throttle 模块说明）。
        if login_throttle.check_locked(request_user.username, client_ip):
            return CommonResponse(code="429", msg="尝试次数过多，请稍后再试", status="error", data=[])

        user = db.query(models.User).filter(models.User.username == request_user.username).first()

        login_log = models.LoginLog(
            username=request_user.username,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent") if request else None,
            user_id=_safe_int(user.id) if user else None,
            success=False,
        )

        if not user or not security.verify_password(request_user.password, user.password):
            login_throttle.record_failure(request_user.username, client_ip)
            db.add(login_log)
            db.commit()
            return CommonResponse(code="401", msg="用户名或密码错误", status="error", data=[])

        # 旧格式密码自动升级为 bcrypt（W8）：条件更新仅当库中仍是本次
        # 验证时的旧值才覆盖——避免与并发改密交错时把新密码回滚成旧密码
        if not security.is_bcrypt_hash(user.password):
            from sqlalchemy import text as _sa_text

            db.execute(
                _sa_text("UPDATE users SET password = :new_hash WHERE id = :uid AND password = :old_val"),
                {
                    "new_hash": security.get_password_hash(request_user.password),
                    "uid": user.id,
                    "old_val": user.password,
                },
            )
            db.commit()

        if user.two_factor_flag == "1":
            if not request_user.twofa_code:
                db.add(login_log)
                db.commit()
                return CommonResponse(code="400", msg="请填写两步验证码", status="error", data=[])

            if not utils.verify_totp(user.two_factor_secret, request_user.twofa_code):
                # TOTP 失败与密码失败共用同一限流计数（6 位数字空间小，
                # 单独不限流等于可爆破）
                login_throttle.record_failure(request_user.username, client_ip)
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

        login_throttle.record_success(request_user.username, client_ip)

        token_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
            # 首登/默认口令强制改密标志（W9）：前端守卫据此强制跳转改密页
            "must_change_password": bool(getattr(user, "must_change_password", False)),
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
    - 使用即轮换：条件 UPDATE 原子撤销旧记录（并发同值刷新只有一个能成功，
      消除"读-改-写"窗口下的双成功），换发新记录
    - 已撤销/过期/不存在一律 401（前端据此走登出）
    """
    try:
        token_hash = utils.hash_refresh_token(refresh_request.refresh_token)
        now = datetime.utcnow()

        # 原子轮换（对齐 cuser.logout 的条件 update 先例）：撤销动作与
        # 有效性判定合并为单条条件 UPDATE，rowcount=0 即令牌无效/已撤销/已过期
        rowcount = (
            db.query(models.RefreshToken)
            .filter(
                models.RefreshToken.token_hash == token_hash,
                models.RefreshToken.revoked_at.is_(None),
                models.RefreshToken.expires_at > now,
            )
            .update({models.RefreshToken.revoked_at: now}, synchronize_session=False)
        )
        if rowcount == 0:
            return CommonResponse(code="401", msg="refresh token 无效、已撤销或已过期", status="error", data=[])

        record = db.query(models.RefreshToken).filter(models.RefreshToken.token_hash == token_hash).first()
        if record is None:
            # 条件更新成功后记录必存在；防御并发删除等异常场景
            return CommonResponse(code="401", msg="refresh token 无效、已撤销或已过期", status="error", data=[])

        user = db.query(models.User).filter(models.User.id == record.user_id).first()
        if not user or not user.is_active:
            # 本分支 401 不 commit，上面的撤销随事务回滚丢弃——无害：
            # 停用用户此后同样换不出新令牌，无需额外持久化撤销
            return CommonResponse(code="401", msg="用户不存在或已停用", status="error", data=[])

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
                # ASGI 规范允许 request.client 为 None（如测试构造的裸请求）
                ip_address=request.client.host if (request and request.client) else None,
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
