from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse

from app.user.requestVO import ChangePasswordRequest, TwofactorVerifyRequest, VerifyPasswordFor2FARequest
from app.api.responseVO import CommonResponse
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.auth import utils
from app.auth.dependencies import require_authenticated_user, AuthenticatedUserInfo
import app.auth.security as security
from app.auth import models
from typing import Annotated, Optional

# qrcode/PIL 延迟导入：仅 2FA 二维码接口需要；顶层导入会把 PIL 拖进完整启动链
# （Android 16KB 环境自建 pillow 兼容 wheel 攻破前会阻断服务端启动，桌面零差异）
from io import BytesIO
import base64
import logging
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)


def _decode_password(value: str) -> str:
    """兼容前端 base64 编码的密码输入。

    前端 changePassword 传 window.btoa() 后的串（契约见 ChangePasswordRequest
    注释），但登录/其他入口传明文。这里先尝试严格 base64 解码，仅当解码结果
    为可打印 ASCII 时才采用，否则按明文处理（如 "test" 恰为 4 字符合法
    base64 但解码出二进制乱码 → 回退明文）。
    """
    if not value:
        return value
    try:
        raw = base64.b64decode(value, validate=True)
        if raw and all(32 <= b < 127 for b in raw):
            return raw.decode("utf-8")
    except Exception:
        pass
    return value


@router.post("/logout", summary="用户登出", response_model=CommonResponse)
def logout(
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    用户登出端点：撤销该用户全部未过期 refresh token（双令牌体系 W6-1）。

    access token 仍为无状态 JWT（到期前有效），但 refresh 撤销后 401 无法
    续期，前端将在下一次 401 时登出，令牌生命周期收敛到可撤销。
    """
    logger.info("用户登出: %s", user_info.username)
    user_id = getattr(user_info, "user_id", None)
    if user_id is not None:
        db.query(models.RefreshToken).filter(
            models.RefreshToken.user_id == user_id,
            models.RefreshToken.revoked_at.is_(None),
        ).update({models.RefreshToken.revoked_at: datetime.utcnow()})
        db.commit()
        logger.info("已撤销用户 %s 的 refresh token", user_info.username)
    else:
        logger.warning("登出时 user_id 缺失（旧 token），跳过 refresh 撤销")
    return CommonResponse(status="success", msg="登出成功", code="200", data=None)


@router.post("/info", summary="获取用户信息", response_model=CommonResponse)
def get_user_info(
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user), db: Session = Depends(get_db)
):
    try:
        user_name = user_info.username

        if not user_name:
            return CommonResponse(status="error", msg="Token中缺少用户名", code="401")

        # 从数据库获取用户信息
        user = db.query(models.User).filter(models.User.username == user_name).first()
        if not user:
            return CommonResponse(status="error", msg="用户不存在", code="404")

        # 构建用户信息响应
        user_data = {
            "user": {
                "userId": str(user.id),  # 添加用户ID
                "roles": ["admin"],  # 简化处理，所有用户都是admin
                "name": user.username,
                "avatar": "https://www.baidu.com/img/PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png",
                "introduction": "系统管理员",
                "twoFactorFlag": user.two_factor_flag,  # 添加2FA状态标识
                # 强制改密标志实时下发（安全修复 W9 补全）：此前仅登录响应
                # 携带，F5/新会话期间后端置位的标志守卫读不到，可被刷新绕过
                "mustChangePassword": bool(getattr(user, "must_change_password", False)),
            }
        }

        return CommonResponse(status="success", msg="获取用户信息成功", code="200", data=user_data)

    except Exception as e:
        # 服务端异常兜底必须是 5xx：业务 code 401 会被前端当认证失败处理
        # （静默续期→重放→登出），DB 抖动会误踢在线用户
        return CommonResponse(status="error", msg=f"获取用户信息失败: {str(e)}", code="500")


@router.post("/changePassword", summary="修改用户密码", response_model=CommonResponse)
def change_password(
    user_request: ChangePasswordRequest,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    # 绑定本人（安全修复 W8/W9）：忽略请求体 userId，一律操作 token 对应用户
    # ——历史实现按 body userId 查询，任何已认证用户可改任意人密码
    user_id = getattr(user_info, "user_id", None)
    if user_id is None:
        return CommonResponse(status="error", msg="token 缺少用户标识", code="401")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return CommonResponse(status="error", msg="用户不存在", code="400")

    # 旧密码校验：走 verify_password 双读（bcrypt 或旧 AES-ECB 格式）——
    # 历史实现直调 sm4_decrypt，bcrypt 化后会直接 500 且新密码回写旧格式。
    # 输入按契约先做 base64 兼容解码（前端 btoa）。
    if not security.verify_password(_decode_password(str(user_request.oldPassword)), str(user.password)):
        return CommonResponse(status="error", msg="密码错误", code="400")

    new_password = security.get_password_hash(_decode_password(str(user_request.newPassword)))
    sql = """update users set password=:password, must_change_password=0 where id=:user_id"""
    try:
        db.execute(text(sql), {"password": new_password, "user_id": user.id})
        # 改密后撤销该用户全部 refresh token（安全修复 W9）：旧 token 不再能续期
        db.query(models.RefreshToken).filter(
            models.RefreshToken.user_id == user.id,
            models.RefreshToken.revoked_at.is_(None),
        ).update({models.RefreshToken.revoked_at: datetime.utcnow()})
        db.commit()
    except Exception as e:
        return CommonResponse(status="error", msg="失败原因：" + str(e), code="400")
    return CommonResponse(status="success", msg="修改成功", code="200")


def _is_self(user_id: str, user_info: AuthenticatedUserInfo) -> bool:
    """2FA 端点本人校验（安全修复 W10）：路径/body userId 必须等于 token 用户。

    历史实现仅要求登录态，任意已认证用户可读取/重置他人 TOTP secret。
    """
    token_user_id = getattr(user_info, "user_id", None)
    return token_user_id is not None and str(token_user_id) == str(user_id)


def _generate_totp_qr_png(totp_uri: str) -> Optional[bytes]:
    """生成 TOTP 二维码 PNG 字节。

    Pillow 在 Android 服务端形态被 ANDROID-DROP（自建 wheel 攻坚期不可用），
    缺失时返回 None 由调用方降级为手动录入密钥，不阻断 2FA 绑定。
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage
    except ImportError:
        return None
    qr = qrcode.make(
        data=totp_uri,
        version=3,  # 新版推荐显式设置版本号
        error_correction=qrcode.ERROR_CORRECT_H,
        box_size=4,
        border=0,
        image_factory=PilImage,
    )
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


@router.get(
    "/2faVerifyQrCode/{user_id}",
    summary="生成用户的2fa关联二维码，已启用2fa验证的用户不用调用此接口，返回文件流，即生成二维码图片",
)
def twofa_verify_qrcode(
    user_id: Annotated[str, Path(description="用户id")],
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if not _is_self(user_id, user_info):
        return ""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    # 查找不到用户则不返回
    if not user:
        return ""
    # 用户2fa启用标识为0则返回二维码，1则返回空
    if user.two_factor_flag == "0":
        qr_png = _generate_totp_qr_png(utils.get_totp_uri(str(user.two_factor_secret), str(user.username)))
        if qr_png is None:
            # Pillow 缺失（Android 服务端形态）：明确信封替代裸 500，指引手动录入
            return CommonResponse(
                status="error",
                msg="当前环境未安装二维码图像依赖（Pillow），请改用手动录入密钥方式绑定",
                code="503",
            )
        return StreamingResponse(BytesIO(qr_png), media_type="image/png")
        # return utils.get_totp_uri(str(user.username), secret)
    else:
        return ""


@router.get(
    "/2faVerifyCode/{user_id}",
    summary="返回二次验证的关联码，用于让用户手动添加二次验证",
    response_model=str,
    response_description="返回字符串",
)
def twofa_verify_code(
    user_id: Annotated[str, Path(description="用户id")],
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if not _is_self(user_id, user_info):
        return ""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    # 查找不到用户则不返回
    if not user:
        return ""
    return str(user.two_factor_secret)


@router.post("/update2faFlg/{user_id}", summary="修改用户的2fa启用状态", response_model=CommonResponse)
def update_twofa_flag(
    user_id: Annotated[str, Path(description="用户id")],
    user_request: TwofactorVerifyRequest,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if not _is_self(user_id, user_info):
        return CommonResponse(status="error", msg="无权操作其他用户的2FA设置", code="403")
    # 兜底：twofaFlag 非法时返回统一错误信封（原返回裸字符串破坏响应契约）
    response: CommonResponse = CommonResponse(status="error", msg="无效的2FA操作", code="400")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    # 查找不到用户则抛出异常
    if not user:
        return CommonResponse(status="error", msg="用户id错误", code="400")
    sql = """update users set two_factor_flag=case when :two_factor_flag is not null then :two_factor_flag else two_factor_flag end,two_factor_secret=case when :two_factor_secret is not null then :two_factor_secret else two_factor_secret end where id=:user_id"""
    if user_request.twofaFlag == "1" and user.two_factor_flag == "1":
        response = CommonResponse(status="error", msg="用户已经启用2fa验证", code="400")
    if user_request.twofaFlag == "0" and user.two_factor_flag == "1":
        # 停用2FA：需要同时验证密码和2FA验证码

        # 1. 验证密码（输入错误用 400：业务 401 会触发前端认证失败链路误登出）
        if not user_request.password or len(user_request.password) == 0:
            return CommonResponse(status="error", msg="停用2fa验证需要提供当前密码", code="400")

        logger.info(f"[停用2FA] 开始验证密码，userId={user.id}, username={user.username}")
        if not security.verify_password(user_request.password, user.password or ""):
            logger.warning(f"[停用2FA] 密码验证失败，userId={user.id}, username={user.username}")
            return CommonResponse(status="error", msg="密码错误", code="400")
        logger.info(f"[停用2FA] 密码验证成功，userId={user.id}, username={user.username}")

        # 2. 验证2FA验证码
        if not user_request.twoFactorCode or len(user_request.twoFactorCode) == 0:
            return CommonResponse(status="error", msg="停用2fa验证需要提供2fa验证码", code="400")

        logger.info(f"[停用2FA] 开始验证2FA码，userId={user.id}")
        if not utils.verify_totp(str(user.two_factor_secret), user_request.twoFactorCode):
            logger.warning(f"[停用2FA] 2FA验证码错误，userId={user.id}, username={user.username}")
            return CommonResponse(status="error", msg="双因素验证码错误", code="400")
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
            return CommonResponse(status="error", msg="启用2fa验证需要提供验证码", code="400")

        # 添加调试日志（脱敏：不打印 secret 片段与验证码明文）
        logger.info(f"开始验证TOTP: user_id={user.id}, secret存在={bool(user.two_factor_secret)}")
        if not utils.verify_totp(str(user.two_factor_secret), user_request.twoFactorCode):
            logger.warning(f"TOTP验证失败: user_id={user.id}")
            return CommonResponse(status="error", msg="验证码错误，请检查认证器应用中的6位数字", code="400")

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
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    验证用户密码并返回2FA二维码（用于绑定双因素认证）

    流程：
    1. 验证Token
    2. 验证用户密码
    3. 生成2FA二维码
    4. 返回base64编码的二维码图片和secret

    安全特性：
    - 密码验证失败返回400（业务输入错误；401 会触发前端认证失败链路误登出）
    - 已启用2FA的用户不允许重复绑定
    - 绑定目标必须是 token 对应用户本人（安全修复 W10：历史实现按 body
      userId 操作任意用户，可在途重置他人 2FA）
    """
    try:
        if not _is_self(str(user_request.userId), user_info):
            return CommonResponse(status="error", msg="无权操作其他用户的2FA设置", code="403")

        # 1. 查询用户
        user = db.query(models.User).filter(models.User.id == user_request.userId).first()
        if not user:
            return CommonResponse(status="error", msg="用户不存在", code="404")

        # 3. 检查是否已启用2FA
        if user.two_factor_flag == "1":
            return CommonResponse(status="error", msg="用户已启用双因素认证，无需重复绑定", code="400")

        # 4. 验证密码（使用与登录接口相同的验证逻辑）
        logger.info(f"[2FA密码验证] userId={user_request.userId}, username={user.username}")

        if not security.verify_password(user_request.password, user.password or ""):
            logger.warning(f"[2FA密码验证] 密码验证失败，username={user.username}")
            return CommonResponse(status="error", msg="密码错误", code="400")

        logger.info(f"[2FA密码验证] 密码验证成功，username={user.username}")

        # 5. 确保用户有TOTP secret（首次启用时生成）
        if not user.two_factor_secret:
            new_secret = utils.generate_totp_secret()
            user.two_factor_secret = new_secret
            db.commit()
            db.refresh(user)

        # 6. 生成二维码（Pillow 缺失时降级手动录入：secret 已生成并落库，绑定不中断）
        qr_png = _generate_totp_qr_png(utils.get_totp_uri(str(user.two_factor_secret), str(user.username)))
        if qr_png is not None:
            qr_code_base64 = f"data:image/png;base64,{base64.b64encode(qr_png).decode('utf-8')}"
            qr_available = True
        else:
            qr_code_base64 = ""
            qr_available = False

        # 8. 返回响应（qr_available=False 时前端展示密钥手动录入块）
        return CommonResponse(
            status="success",
            msg="密码验证成功",
            code="200",
            data={
                "qr_code_base64": qr_code_base64,
                "qr_available": qr_available,
                "secret": str(user.two_factor_secret),
            },
        )

    except Exception as e:
        return CommonResponse(status="error", msg=f"验证失败: {str(e)}", code="500")
