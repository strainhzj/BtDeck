# app/auth/router.py
from debugpy.adapter import access_token
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from app.database import get_db
from app.auth import models, security, utils
from app.schemas.auth import UserCreate, TwoFactorResponse, TwoFactorSetup
from app.config import settings
from app.auth.request import UserLogin
from jose import jwt
import qrcode
import io
import base64

router = APIRouter(prefix="/user", tags=["authentication"])

@router.post("/update")
def user_update(requestUser: UserLogin,
                request: Request = None,
                db: Session = Depends(get_db)):
    access_token = request.cookies
    # 解码token
    access_token_decode = jwt.decode(access_token[''], "YM4nwx3QBbZ227i5itqf", settings.ALGORITHM)
    if(utils.verify_totp(access_token)):
        user = db.query(models.User).filter(models.User.username == requestUser.username).first()
        if(requestUser.twofa):
            user.two_factor_secret = utils.generate_totp_secret();
            db.execute("update users set two_factor_secret=0 where username=" + user.username)
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="access_token is expired",
        )


@router.post("/verify-2fa")
def verify_2fa(
        two_factor: TwoFactorResponse,
        response: Response,
        request: Request,
        db: Session = Depends(get_db)
):
    """验证两因素认证码"""
    user = db.query(models.User).filter(models.User.id == two_factor.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 验证TOTP代码
    if not utils.verify_totp(user.two_factor_secret, two_factor.code):
        # 记录失败登录
        login_log = models.LoginLog(
            username=user.username,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            user_id=user.id,
            success=False
        )
        db.add(login_log)
        db.commit()

        raise HTTPException(status_code=400, detail="Invalid authentication code")

    # 创建访问令牌
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = utils.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    #
