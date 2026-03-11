from datetime import timedelta

import yaml
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import models, security, utils
from app.auth.request import UserLogin
from app.config import settings
from app.core.config import settings as app_settings
from app.database import get_db

router = APIRouter()


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@router.post('/login', summary='用户登录', tags=['login'], response_model=CommonResponse)
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
            user_agent=request.headers.get('user-agent') if request else None,
            user_id=_safe_int(user.id) if user else None,
            success=False,
        )

        if not user or not security.verify_password(request_user.password, user.password):
            db.add(login_log)
            db.commit()
            return CommonResponse(code='401', msg='用户名或密码错误', status='error', data=[])

        if user.two_factor_flag == '1':
            if not request_user.twofa_code:
                db.add(login_log)
                db.commit()
                return CommonResponse(code='400', msg='请填写两步验证码', status='error', data=[])

            if not utils.verify_totp(user.two_factor_secret, request_user.twofa_code):
                db.add(login_log)
                db.commit()
                return CommonResponse(code='401', msg='验证码错误，请重试', status='error', data=[])

        with open(app_settings.YAML_PATH, 'r') as f:
            new_config = yaml.load(f, Loader=yaml.SafeLoader)

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = utils.create_access_token(
            data={
                'sub': user.username,
                'user_id': str(user.id),
                'is_admin': '1',
                'verify_secret': new_config['security']['login_status_secret'],
            },
            expires_delta=access_token_expires,
        )

        login_log.success = True
        db.add(login_log)
        db.commit()

        token_data = {
            'access_token': access_token,
            'token_type': 'bearer',
            'user_id': user.id,
        }
        return CommonResponse(code='200', msg='登录成功', status='success', data=[token_data])

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return CommonResponse(code='500', msg=f'系统异常: {str(e)}', status='error', data=[])

