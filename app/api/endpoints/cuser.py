from fastapi import APIRouter, Depends, HTTPException, status, Request, Path
from fastapi.responses import StreamingResponse

from app.user.requestVO import ChangePasswordRequest, TwofactorVerifyRequest, VerifyPasswordFor2FARequest
from app.api.responseVO import CommonResponse
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.auth import utils
import app.auth.security as security
from app.auth import models
from typing import Annotated
import qrcode
from qrcode.image.pil import PilImage
from io import BytesIO
import base64
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/info", summary="获取用户信息", response_model=CommonResponse)
def get_user_info(
        req: Request,
        db: Session = Depends(get_db)
):
    try:
        token = req.headers.get("x-access-token")
        if not token:
            response = CommonResponse(
                status="error",
                msg="Token缺失",
                code="401"
            )
            return response

        # 验证token并获取用户信息
        try:
            payload = utils.verify_access_token(token)
        except Exception as e:
            response = CommonResponse(
                status="error",
                msg=f"Token验证失败: {str(e)}",
                code="401"
            )
            return response

        # 🔧 防御性检查：verify_access_token 验证失败时可能返回 None
        # 例如：verify_secret 不匹配、token 过期等情况
        if not payload:
            response = CommonResponse(
                status="error",
                msg="Token验证失败或已过期",
                code="401"
            )
            return response

        user_name = payload.get("sub")

        if not user_name:
            response = CommonResponse(
                status="error",
                msg="Token中缺少用户名",
                code="401"
            )
            return response

        # 从数据库获取用户信息
        user = db.query(models.User).filter(models.User.username == user_name).first()
        if not user:
            response = CommonResponse(
                status="error",
                msg="用户不存在",
                code="404"
            )
            return response

        # 构建用户信息响应
        user_info = {
            "user": {
                "userId": str(user.id),  # 添加用户ID
                "roles": ["admin"],  # 简化处理，所有用户都是admin
                "name": user.username,
                "avatar": "https://www.baidu.com/img/PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png",
                "introduction": "系统管理员",
                "twoFactorFlag": user.two_factor_flag  # 添加2FA状态标识
            }
        }

        response = CommonResponse(
            status="success",
            msg="获取用户信息成功",
            code="200",
            data=user_info
        )
        return response

    except Exception as e:
        response = CommonResponse(
            status="error",
            msg=f"获取用户信息失败: {str(e)}",
            code="401"
        )
        return response


@router.post("/changePassword", summary="修改用户密码", response_model=CommonResponse)
def change_password(
        user_request: ChangePasswordRequest,
        req: Request = None,
        db: Session = Depends(get_db)
):
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="400"
        )
        return response
    user = db.query(models.User).filter(models.User.id == user_request.userId).first()
    if not user:
        response = CommonResponse(
            status="error",
            msg="用户id错误",
            code="400"
        )
        return response
    old_password = security.sm4_decrypt(str(user.password))
    if old_password != user_request.old_password.encode("utf-8"):
        response = CommonResponse(
            status="error",
            msg="密码错误",
            code="400"
        )
        return response
    new_password = security.sm4_encrypt(user_request.new_password)
    sql = """update users set password=:password where id=:user_id"""
    try:
        db.execute(text(sql), {"password": new_password, "user_id": user.id})
        db.commit()
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="失败原因：" + str(e),
            code="400"
        )
        return response
    response = CommonResponse(status="success", msg="修改成功", code="200")
    return response


@router.get("/2faVerifyQrCode/{user_id}", summary="生成用户的2fa关联二维码，已启用2fa验证的用户不用调用此接口，返回文件流，即生成二维码图片")
def twofa_verify(
        user_id: Annotated[str, Path(description="用户id")],
        req: Request,
        db: Session = Depends(get_db)
):
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401"
        )
        return response
    user = db.query(models.User).filter(models.User.id == user_id).first()
    # 查找不到用户则不返回
    if not user:
        return ""
    # 用户2fa启用标识为0则返回二维码，1则返回空
    if user.two_factor_flag == "0":
        link = utils.get_totp_uri(str(user.two_factor_secret), str(user.username))
        qr = qrcode.make(
            data=link,
            version=3,  # 新版推荐显式设置版本号
            error_correction=qrcode.ERROR_CORRECT_H,
            box_size=4,
            border=0,
            image_factory=PilImage
        )
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="image/png")
        # return utils.get_totp_uri(str(user.username), secret)
    else:
        return ""

@router.get("/2faVerifyCode/{user_id}", summary="返回二次验证的关联码，用于让用户手动添加二次验证",response_model=str,response_description="返回字符串")
def twofa_verify(
        user_id: Annotated[str, Path(description="用户id")],
        req: Request,
        db: Session = Depends(get_db)
):
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401"
        )
        return response
    user = db.query(models.User).filter(models.User.id == user_id).first()
    # 查找不到用户则不返回
    if not user:
        return ""
    return str(user.two_factor_secret)

@router.post("/update2faFlg/{user_id}", summary="修改用户的2fa启用状态", response_model=CommonResponse)
def update_twofa_flag(
        user_id: Annotated[str, Path(description="用户id")],
        user_request: TwofactorVerifyRequest,
        req: Request = None,
        db: Session = Depends(get_db)
):
    try:
        token = req.headers.get("x-access-token")
        utils.verify_access_token(token)
    except Exception as e:
        response = CommonResponse(
            status="error",
            msg="token验证失败，失败原因：" + str(e),
            code="401"
        )
        return response
    response = ""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    # 查找不到用户则抛出异常
    if not user:
        response = CommonResponse(
            status="error",
            msg="用户id错误",
            code="400"
        )
        return response
    sql = """update users set two_factor_flag=case when :two_factor_flag is not null then :two_factor_flag else two_factor_flag end,two_factor_secret=case when :two_factor_secret is not null then :two_factor_secret else two_factor_secret end where id=:user_id"""
    if user_request.twofaFlag == "1" and user.two_factor_flag == "1":
        response = CommonResponse(status="error", msg="用户已经启用2fa验证", code="400")
    if user_request.twofaFlag == "0" and user.two_factor_flag == "1":
        # 停用2FA：需要同时验证密码和2FA验证码

        # 1. 验证密码
        if not user_request.password or len(user_request.password) == 0:
            response = CommonResponse(
                status="error",
                msg="停用2fa验证需要提供当前密码",
                code="401"
            )
            return response

        logger.info(f"[停用2FA] 开始验证密码，userId={user.id}, username={user.username}")
        if not security.verify_password(user_request.password, user.password):
            logger.warning(f"[停用2FA] 密码验证失败，userId={user.id}, username={user.username}")
            response = CommonResponse(
                status="error",
                msg="密码错误",
                code="401"
            )
            return response
        logger.info(f"[停用2FA] 密码验证成功，userId={user.id}, username={user.username}")

        # 2. 验证2FA验证码
        if not user_request.twoFactorCode or len(user_request.twoFactorCode) == 0:
            response = CommonResponse(
                status="error",
                msg="停用2fa验证需要提供2fa验证码",
                code="401"
            )
            return response

        logger.info(f"[停用2FA] 开始验证2FA码，userId={user.id}, code={user_request.twoFactorCode}")
        if not utils.verify_totp(str(user.two_factor_secret), user_request.twoFactorCode):
            logger.warning(f"[停用2FA] 2FA验证码错误，userId={user.id}, username={user.username}")
            response = CommonResponse(
                status="error",
                msg="双因素验证码错误",
                code="401"
            )
            return response
        logger.info(f"[停用2FA] 2FA验证码正确，userId={user.id}, username={user.username}")

        # 3. 停用2FA：清空secret，设置flag为0
        try:
            # 清空two_factor_secret为NULL，设置two_factor_flag为0
            update_sql = """UPDATE users SET two_factor_flag = '0', two_factor_secret = NULL WHERE id = :user_id"""
            db.execute(text(update_sql), {"user_id": user.id})
            db.commit()
            logger.info(f"[停用2FA] 停用成功，userId={user.id}, username={user.username}")
            response = CommonResponse(status="success", msg="双因素认证已停用", code="200")
        except Exception as e:
            logger.error(f"[停用2FA] 停用失败，userId={user.id}, error={str(e)}")
            response = CommonResponse(status="error", msg=str(e), code="400")
    if user_request.twofaFlag == "0" and user.two_factor_flag == "0":
        # 用户已经是停用状态，视为成功
        response = CommonResponse(status="success", msg="用户已经停用2fa验证", code="200")
    if user_request.twofaFlag == "1" and user.two_factor_flag == "0":
        # 启用2FA时必须验证TOTP码
        if not user_request.twoFactorCode or len(user_request.twoFactorCode) == 0:
            response = CommonResponse(
                status="error",
                msg="启用2fa验证需要提供验证码",
                code="401"
            )
            return response

        # 添加调试日志
        logger.info(f"开始验证TOTP: user_id={user.id}, secret存在={bool(user.two_factor_secret)}, secret前4位={str(user.two_factor_secret)[:4] if user.two_factor_secret else None}, token={user_request.twoFactorCode}")
        if not utils.verify_totp(str(user.two_factor_secret), user_request.twoFactorCode):
            logger.error(f"TOTP验证失败: user_id={user.id}, token={user_request.twoFactorCode}")
            response = CommonResponse(
                status="error",
                msg="验证码错误，请检查认证器应用中的6位数字",
                code="401"
            )
            return response

        try:
            db.execute(text(sql), {"two_factor_flag": "1", "two_factor_secret": None, "user_id": user.id})
            db.commit()
            response = CommonResponse(status="success", msg="启用双因素认证成功", code="200")
        except Exception as e:
            response = CommonResponse(status="error", msg=str(e), code="400")
    return response


@router.post("/verifyPasswordFor2FA", summary="验证密码并返回2FA二维码", response_model=CommonResponse)
def verify_password_for_2fa(
        user_request: VerifyPasswordFor2FARequest,
        req: Request = None,
        db: Session = Depends(get_db)
):
    """
    验证用户密码并返回2FA二维码（用于绑定双因素认证）

    流程：
    1. 验证Token
    2. 验证用户密码
    3. 生成2FA二维码
    4. 返回base64编码的二维码图片和secret

    安全特性：
    - 密码验证失败返回401
    - 已启用2FA的用户不允许重复绑定
    """
    try:
        # 1. 验证Token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="Token缺失",
                code="401"
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"Token验证失败: {str(e)}",
                code="401"
            )

        # 2. 查询用户
        user = db.query(models.User).filter(models.User.id == user_request.userId).first()
        if not user:
            return CommonResponse(
                status="error",
                msg="用户不存在",
                code="404"
            )

        # 3. 检查是否已启用2FA
        if user.two_factor_flag == "1":
            return CommonResponse(
                status="error",
                msg="用户已启用双因素认证，无需重复绑定",
                code="400"
            )

        # 4. 验证密码（使用与登录接口相同的验证逻辑）
        # 添加调试日志
        logger.info(f"[2FA密码验证] userId={user_request.userId}, username={user.username}")
        logger.info(f"[2FA密码验证] 输入密码长度={len(user_request.password)}")

        if not security.verify_password(user_request.password, user.password):
            logger.warning(f"[2FA密码验证] 密码验证失败，username={user.username}")
            return CommonResponse(
                status="error",
                msg="密码错误",
                code="401"
            )

        logger.info(f"[2FA密码验证] 密码验证成功，username={user.username}")

        # 5. 确保用户有TOTP secret（首次启用时生成）
        if not user.two_factor_secret:
            new_secret = utils.generate_totp_secret()
            user.two_factor_secret = new_secret
            db.commit()
            db.refresh(user)

        # 6. 生成二维码
        link = utils.get_totp_uri(str(user.two_factor_secret), str(user.username))
        qr = qrcode.make(
            data=link,
            version=3,
            error_correction=qrcode.ERROR_CORRECT_H,
            box_size=4,
            border=0,
            image_factory=PilImage
        )

        # 7. 转换为base64
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        buffer.seek(0)
        qr_base64 = base64.b64encode(buffer.read()).decode('utf-8')

        # 8. 返回响应
        return CommonResponse(
            status="success",
            msg="密码验证成功",
            code="200",
            data={
                "qr_code_base64": f"data:image/png;base64,{qr_base64}",
                "secret": str(user.two_factor_secret)
            }
        )

    except Exception as e:
        return CommonResponse(
            status="error",
            msg=f"验证失败: {str(e)}",
            code="500"
        )
