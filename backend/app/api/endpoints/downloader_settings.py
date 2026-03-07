# -*- coding: utf-8 -*-
"""
下载器设置管理API

提供下载器配置的CRUD和应用接口

⚠️ 废弃说明:
1. 高级设置功能（advanced_settings相关字段）已废弃，不再推荐使用
2. 原因: qBittorrent客户端对高级设置支持不完整，部分字段无法生效
3. 前端UI已隐藏高级设置页签，但后端接口保留以避免破坏现有功能
4. 数据库中的advanced_settings数据保留，但不再使用
5. 未来版本可能会完全移除此功能
"""
import logging
import json
from typing import Optional
from datetime import datetime, time as dt_time

from fastapi import APIRouter, Depends, Request, Path
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth import utils
from app.database import get_db
from app.services.downloader_settings_manager import DownloaderSettingsManager
from app.downloader.models import BtDownloaders
from app.utils.encryption import encrypt_password, decrypt_password
from app.models.setting_templates import DownloaderTypeEnum

router = APIRouter()
logger = logging.getLogger(__name__)


# ========== 辅助函数 ==========

def get_current_user_id(token: str) -> Optional[int]:
    """
    从JWT token中获取用户ID

    Args:
        token: JWT访问令牌

    Returns:
        Optional[int]: 用户ID，失败返回None
    """
    try:
        decoded = utils.verify_access_token(token)
        user_id = decoded.get("user_id")
        return int(user_id) if user_id else None
    except Exception as e:
        logger.error(f"获取用户ID失败: {e}")
        return None


def verify_downloader_exists(db: Session, downloader_id: str) -> bool:
    """
    验证下载器是否存在

    Args:
        db: 数据库会话
        downloader_id: 下载器ID

    Returns:
        bool: 存在返回True，否则返回False
    """
    try:
        sql = """
            SELECT COUNT(*) as count FROM bt_downloaders
            WHERE downloader_id = :downloader_id AND dr = 0
        """
        result = db.execute(text(sql), {"downloader_id": downloader_id}).fetchone()
        return result.count > 0 if result else False
    except Exception as e:
        logger.error(f"验证下载器存在性失败: {e}")
        return False


def encrypt_password_if_provided(password: Optional[str]) -> Optional[str]:
    """
    如果提供了密码，则进行SM4加密

    Args:
        password: 明文密码

    Returns:
        Optional[str]: 加密后的密码，如果输入为None则返回None
    """
    if password:
        try:
            return encrypt_password(password)
        except Exception as e:
            logger.error(f"密码加密失败: {e}")
            raise ValueError(f"密码加密失败: {e}")
    return None


def normalize_hhmm_time(value) -> str:
    """
    规范化时间值为 HH:MM 字符串。
    支持 str("HH:MM") 和 datetime.time。
    """
    if isinstance(value, dt_time):
        return value.strftime("%H:%M")

    if isinstance(value, str):
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")

    raise ValueError("时间格式错误，应为 HH:mm")


def coerce_sqlite_time(value) -> str:
    """
    最终入库前兜底转换，确保 SQLite 绑定参数一定是字符串。
    """
    if isinstance(value, dt_time):
        return value.strftime("%H:%M")
    if isinstance(value, str):
        # 允许 HH:MM / HH:MM:SS，统一落库为 HH:MM
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).strftime("%H:%M")
            except ValueError:
                continue
    raise ValueError("时间格式错误，应为 HH:mm 或 HH:mm:ss")

def normalize_weekdays(weekdays) -> str:
    """
    标准化星期列表为数据库存储字符串（0-6，周一=0）。
    兼容旧格式：1-7（周一=1，周日=7）。
    """
    if not isinstance(weekdays, list) or len(weekdays) == 0:
        raise ValueError("weekdays 必须是非空数组")

    # 判断是否为 1-7 格式
    has_legacy_value = any(isinstance(day, int) and day == 7 for day in weekdays)
    has_out_of_range = any(isinstance(day, int) and day > 6 for day in weekdays)
    use_legacy = has_legacy_value or has_out_of_range

    normalized = []
    for day in weekdays:
        if not isinstance(day, int):
            raise ValueError("weekdays 只能包含整数")
        if use_legacy:
            if day < 1 or day > 7:
                raise ValueError("weekdays 值必须在 1-7 之间")
            normalized.append(day - 1)  # 1-7 -> 0-6
        else:
            if day < 0 or day > 6:
                raise ValueError("weekdays 值必须在 0-6 之间")
            normalized.append(day)

    # 去重并排序
    normalized = sorted(set(normalized))
    return "".join(str(day) for day in normalized)


def parse_days_of_week(days_of_week: str) -> list:
    """将数据库 days_of_week 字符串转换为前端使用的数字列表（0-6，周一=0）。"""
    if not days_of_week:
        return []
    result = []
    for day_char in days_of_week:
        if day_char.isdigit():
            value = int(day_char)
            if value == 7:
                value = 6
            if 0 <= value <= 6:
                result.append(value)
    return sorted(set(result))


# ========== API端点 ==========

@router.get(
    "/{downloader_id}/settings",
    summary="获取下载器配置",
    response_model=CommonResponse,
    tags=["下载器设置"]
)
def get_downloader_settings(
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    获取指定下载器的配置信息

    返回下载器的速度限制、认证信息、高级配置等
    """
    try:
        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 验证下载器是否存在
        if not verify_downloader_exists(db, downloader_id):
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 3. 查询下载器配置
        sql = """
            SELECT id, downloader_id, dl_speed_limit, ul_speed_limit,
                   dl_speed_unit, ul_speed_unit,
                   enable_schedule, username, password, advanced_settings, override_local,
                   created_at, updated_at
            FROM downloader_settings
            WHERE downloader_id = :downloader_id
        """
        result = db.execute(text(sql), {"downloader_id": downloader_id}).fetchone()

        if not result:
            # 如果不存在配置，返回默认配置
            return CommonResponse(
                status="success",
                msg="获取成功（未配置）",
                code="200",
                data={
                    "id": None,
                    "downloader_id": downloader_id,
                    "dl_speed_limit": 0,
                    "ul_speed_limit": 0,
                    "dl_speed_unit": 0,
                    "ul_speed_unit": 0,
                    "enable_schedule": False,
                    "username": None,
                    "password": None,
                    "advanced_settings": None,
                    "override_local": False,
                    "created_at": None,
                    "updated_at": None,
                    "schedule_rules": []  # 添加空数组
                }
            )

        # 4. 查询分时段限速规则
        schedule_rules_sql = """
            SELECT id, sort_order, start_time, end_time,
                   dl_speed_limit, dl_speed_unit,
                   ul_speed_limit, ul_speed_unit,
                   days_of_week, enabled
            FROM speed_schedule_rules
            WHERE downloader_setting_id = :setting_id
            ORDER BY sort_order ASC, created_at ASC
        """
        schedule_rules_result = db.execute(
            text(schedule_rules_sql),
            {"setting_id": result.id}
        ).fetchall()

        # 转换规则数据为前端期望的格式
        schedule_rules_list = []
        for rule in schedule_rules_result:
            days_list = parse_days_of_week(rule.days_of_week)

            schedule_rules_list.append({
                "id": rule.id,
                "sort_order": rule.sort_order,
                "start_time": rule.start_time,
                "end_time": rule.end_time,
                "weekdays": days_list,
                "download": {
                    "enabled": rule.dl_speed_limit > 0,
                    "speed_limit": rule.dl_speed_limit,
                    "speed_unit": rule.dl_speed_unit
                },
                "upload": {
                    "enabled": rule.ul_speed_limit > 0,
                    "speed_limit": rule.ul_speed_limit,
                    "speed_unit": rule.ul_speed_unit
                },
                "enabled": rule.enabled
            })

        # 5. 解析高级配置JSON
        advanced_settings = None
        if result.advanced_settings:
            try:
                advanced_settings = json.loads(result.advanced_settings)
            except json.JSONDecodeError:
                logger.warning(f"解析高级配置JSON失败: {result.advanced_settings}")

        # 6. 返回配置数据
        return CommonResponse(
            status="success",
            msg="获取成功",
            code="200",
            data={
                "id": result.id,
                "downloader_id": result.downloader_id,
                "dl_speed_limit": result.dl_speed_limit,
                "ul_speed_limit": result.ul_speed_limit,
                "dl_speed_unit": result.dl_speed_unit,
                "ul_speed_unit": result.ul_speed_unit,
                "enable_schedule": bool(result.enable_schedule),
                "username": result.username,
                "password": None,  # 不返回密码
                "advanced_settings": advanced_settings,
                "override_local": bool(result.override_local),
                "created_at": result.created_at if result.created_at else None,
                "updated_at": result.updated_at if result.updated_at else None,
                "schedule_rules": schedule_rules_list  # 添加规则列表
            }
        )

    except Exception as e:
        logger.error(f"获取下载器配置失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.put(
    "/{downloader_id}/settings",
    summary="更新下载器配置",
    response_model=CommonResponse,
    tags=["下载器设置"]
)
async def update_downloader_settings(
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    更新指定下载器的配置信息

    支持更新速度限制、认证信息、高级配置等
    如果配置不存在则创建，如果存在则更新
    """
    try:
        response_data = {"schedule_rules": []}
        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 验证下载器是否存在
        if not verify_downloader_exists(db, downloader_id):
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 3. 获取请求体数据
        try:
            body_data = await req.json()
        except Exception as e:
            logger.error(f"解析请求体失败: {e}")
            return CommonResponse(
                status="error",
                msg=f"请求体格式错误: {str(e)}",
                code="422",
                data=None
            )

        # 4. 参数验证（同时支持驼峰命名和蛇形命名，优先使用驼峰命名）
        dl_speed_limit = body_data.get("dlSpeedLimit") or body_data.get("download_speed_limit", 0)
        ul_speed_limit = body_data.get("ulSpeedLimit") or body_data.get("upload_speed_limit", 0)

        # 速度单位参数处理（支持新旧两种格式）
        # 新格式：dlSpeedUnit/ulSpeedUnit（分别指定）
        # 旧格式：speedUnit（统一指定，向后兼容）
        dl_speed_unit = body_data.get("dlSpeedUnit") or body_data.get("dl_speed_unit")
        ul_speed_unit = body_data.get("ulSpeedUnit") or body_data.get("ul_speed_unit")
        speed_unit_legacy = body_data.get("speedUnit") or body_data.get("speed_unit")

        # 如果使用旧格式，则两个速度单位相同
        if dl_speed_unit is None and speed_unit_legacy is not None:
            dl_speed_unit = speed_unit_legacy
            ul_speed_unit = speed_unit_legacy
        elif dl_speed_unit is None:
            dl_speed_unit = 0  # 默认 KB/s
        if ul_speed_unit is None:
            ul_speed_unit = 0  # 默认 KB/s

        if not isinstance(dl_speed_limit, int) or dl_speed_limit < 0:
            return CommonResponse(
                status="error",
                msg="下载速度限制必须是非负整数",
                code="422",
                data=None
            )

        if not isinstance(ul_speed_limit, int) or ul_speed_limit < 0:
            return CommonResponse(
                status="error",
                msg="上传速度限制必须是非负整数",
                code="422",
                data=None
            )

        if not isinstance(dl_speed_unit, int) or dl_speed_unit not in [0, 1]:
            return CommonResponse(
                status="error",
                msg="下载速度单位必须是0(KB/s)或1(MB/s)",
                code="422",
                data=None
            )

        if not isinstance(ul_speed_unit, int) or ul_speed_unit not in [0, 1]:
            return CommonResponse(
                status="error",
                msg="上传速度单位必须是0(KB/s)或1(MB/s)",
                code="422",
                data=None
            )

        # 5. 提取并验证 schedule_rules 参数
        schedule_rules = body_data.get("schedule_rules")
        parsed_schedule_rules = None

        if schedule_rules is not None:
            # 验证 schedule_rules 必须是列表
            if not isinstance(schedule_rules, list):
                return CommonResponse(
                    status="error",
                    msg="schedule_rules 必须是数组",
                    code="422",
                    data=None
                )

            parsed_schedule_rules = []

            # 验证每条规则的数据格式
            for idx, rule in enumerate(schedule_rules):
                if not isinstance(rule, dict):
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 必须是对象",
                        code="422",
                        data=None
                    )

                if "start_time" not in rule or "end_time" not in rule:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 缺少必填字段: start_time/end_time",
                        code="422",
                        data=None
                    )

                if "weekdays" not in rule:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 缺少必填字段: weekdays",
                        code="422",
                        data=None
                    )

                # 验证时间格式并规范化为 HH:MM 字符串
                try:
                    rule["start_time"] = normalize_hhmm_time(rule["start_time"])
                    rule["end_time"] = normalize_hhmm_time(rule["end_time"])
                except ValueError:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 的时间格式错误，应为 HH:mm",
                        code="422",
                        data=None
                    )

                # 验证时间范围
                if rule["start_time"] >= rule["end_time"]:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 的开始时间必须早于结束时间",
                        code="422",
                        data=None
                    )

                # 验证星期数组
                if not isinstance(rule["weekdays"], list) or len(rule["weekdays"]) == 0:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 的星期选择不能为空",
                        code="422",
                        data=None
                    )

                try:
                    days_of_week_str = normalize_weekdays(rule["weekdays"])
                except ValueError as e:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 的星期格式错误: {str(e)}",
                        code="422",
                        data=None
                    )

                # 兼容新旧格式的速度配置
                download_config = rule.get("download") if isinstance(rule.get("download"), dict) else None
                upload_config = rule.get("upload") if isinstance(rule.get("upload"), dict) else None

                if download_config is None and upload_config is None and "speed_limit" not in rule:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 缺少速度配置",
                        code="422",
                        data=None
                    )

                dl_enabled = bool(download_config.get("enabled", True)) if download_config else True
                ul_enabled = bool(upload_config.get("enabled", True)) if upload_config else True

                if download_config:
                    dl_speed_limit = download_config.get("speed_limit", 0) if dl_enabled else 0
                    dl_speed_unit = download_config.get("speed_unit", 0)
                else:
                    dl_speed_limit = rule.get("speed_limit", 0)
                    dl_speed_unit = rule.get("speed_unit", 0)

                if upload_config:
                    ul_speed_limit = upload_config.get("speed_limit", 0) if ul_enabled else 0
                    ul_speed_unit = upload_config.get("speed_unit", 0)
                else:
                    ul_speed_limit = rule.get("ul_speed_limit", dl_speed_limit)
                    ul_speed_unit = rule.get("ul_speed_unit", dl_speed_unit)

                if not isinstance(dl_speed_limit, int) or dl_speed_limit < 0:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 的下载速度限制必须是非负整数",
                        code="422",
                        data=None
                    )

                if not isinstance(ul_speed_limit, int) or ul_speed_limit < 0:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 的上传速度限制必须是非负整数",
                        code="422",
                        data=None
                    )

                if not isinstance(dl_speed_unit, int) or dl_speed_unit not in [0, 1]:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 的下载速度单位必须是 0(KB/s) 或 1(MB/s)",
                        code="422",
                        data=None
                    )

                if not isinstance(ul_speed_unit, int) or ul_speed_unit not in [0, 1]:
                    return CommonResponse(
                        status="error",
                        msg=f"规则 {idx + 1} 的上传速度单位必须是 0(KB/s) 或 1(MB/s)",
                        code="422",
                        data=None
                    )

                rule_id = rule.get("id")
                try:
                    rule_id = int(rule_id) if rule_id is not None else None
                except (TypeError, ValueError):
                    rule_id = None

                sort_order = rule.get("sort_order", idx)
                try:
                    sort_order = int(sort_order)
                except (TypeError, ValueError):
                    sort_order = idx

                parsed_schedule_rules.append({
                    "id": rule_id,
                    "sort_order": sort_order,
                    "start_time": rule["start_time"],
                    "end_time": rule["end_time"],
                    "dl_speed_limit": dl_speed_limit if dl_enabled else 0,
                    "dl_speed_unit": dl_speed_unit,
                    "ul_speed_limit": ul_speed_limit if ul_enabled else 0,
                    "ul_speed_unit": ul_speed_unit,
                    "days_of_week": days_of_week_str,
                    "enabled": rule.get("enabled", True)
                })

        # 6. 密码加密
        password = body_data.get("password")
        encrypted_password = encrypt_password_if_provided(password)

        # 6. 处理高级配置JSON（支持两种格式：嵌套对象或扁平字段）
        # ⚠️ 【已废弃】高级配置功能已废弃，以下代码仅为向后兼容保留
        #    原因: qBittorrent客户端支持不完整，部分字段无法生效
        #    前端UI已隐藏此功能，未来版本将完全移除
        advanced_settings = body_data.get("advancedSettings") or body_data.get("advanced_settings")

        # 如果没有嵌套对象，尝试收集扁平的高级配置字段
        if not advanced_settings:
            # qBittorrent 高级配置字段
            qbt_advanced_fields = [
                'dht_enabled', 'lsd_enabled', 'utp_enabled',
                'max_connections', 'max_connections_per_torrent',
                'max_uploads', 'max_uploads_per_torrent',
                'max_download_slots', 'max_upload_slots'
            ]

            # Transmission 高级配置字段
            tr_advanced_fields = [
                'download_queue_size', 'seed_queue_size'
            ]

            # 收集存在的高级配置字段
            collected_advanced = {}
            for field in qbt_advanced_fields + tr_advanced_fields:
                # 同时支持驼峰命名和蛇形命名
                value = body_data.get(field)
                if value is not None:
                    collected_advanced[field] = value

            # 如果收集到了高级配置字段，使用它们
            if collected_advanced:
                # 高级配置字段校验
                advanced_validators = {
                    "max_connections": lambda x: isinstance(x, int) and 1 <= x <= 10000,
                    "max_connections_per_torrent": lambda x: isinstance(x, int) and 1 <= x <= 1000,
                    "max_uploads": lambda x: isinstance(x, int) and 1 <= x <= 500,
                    "max_uploads_per_torrent": lambda x: isinstance(x, int) and 1 <= x <= 100,
                    "max_download_slots": lambda x: isinstance(x, int) and 1 <= x <= 100,
                    "max_upload_slots": lambda x: isinstance(x, int) and 1 <= x <= 500,
                    "download_queue_size": lambda x: isinstance(x, int) and 1 <= x <= 1000,
                    "seed_queue_size": lambda x: isinstance(x, int) and 1 <= x <= 1000,
                    "dht_enabled": lambda x: isinstance(x, bool),
                    "lsd_enabled": lambda x: isinstance(x, bool),
                    "utp_enabled": lambda x: isinstance(x, bool),
                }

                for field, value in collected_advanced.items():
                    validator = advanced_validators.get(field)
                    if validator and not validator(value):
                        return CommonResponse(
                            status="error",
                            msg=f"字段 {field} 的值无效: {value}",
                            code="422",
                            data=None
                        )

                advanced_settings = collected_advanced

        # 序列化高级配置为JSON
        advanced_settings_json = None
        if advanced_settings:
            try:
                advanced_settings_json = json.dumps(advanced_settings, ensure_ascii=False)
                logger.info(f"高级配置已序列化: {advanced_settings_json}")
            except Exception as e:
                logger.error(f"序列化高级配置失败: {e}")
                return CommonResponse(
                    status="error",
                    msg=f"高级配置格式错误: {str(e)}",
                    code="422",
                    data=None
                )

        # 7. 检查配置是否已存在
        check_sql = """
            SELECT id FROM downloader_settings WHERE downloader_id = :downloader_id
        """
        existing = db.execute(text(check_sql), {"downloader_id": downloader_id}).fetchone()

        current_time = datetime.now().isoformat()

        if existing:
            # 更新现有配置
            setting_id = existing.id

            update_sql = """
                UPDATE downloader_settings
                SET dl_speed_limit = :dl_speed_limit,
                    ul_speed_limit = :ul_speed_limit,
                    dl_speed_unit = :dl_speed_unit,
                    ul_speed_unit = :ul_speed_unit,
                    enable_schedule = :enable_schedule,
                    username = :username,
                    password = COALESCE(:password, password),
                    advanced_settings = :advanced_settings,
                    override_local = :override_local,
                    updated_at = :updated_at
                WHERE downloader_id = :downloader_id
            """
            db.execute(text(update_sql), {
                "downloader_id": downloader_id,
                "dl_speed_limit": dl_speed_limit,
                "ul_speed_limit": ul_speed_limit,
                "dl_speed_unit": dl_speed_unit,
                "ul_speed_unit": ul_speed_unit,
                "enable_schedule": body_data.get("enableSchedule") or body_data.get("enable_schedule", False),
                "username": body_data.get("username"),
                "password": encrypted_password,
                "advanced_settings": advanced_settings_json,
                "override_local": body_data.get("overrideLocal") or body_data.get("override_local", False),
                "updated_at": current_time
            })

            # 删除旧的分时段规则由后续 parsed_schedule_rules 处理，避免先删后更导致更新失败

        else:
            # 创建新配置
            insert_sql = """
                INSERT INTO downloader_settings
                (downloader_id, dl_speed_limit, ul_speed_limit, dl_speed_unit, ul_speed_unit,
                 enable_schedule, username, password, advanced_settings, override_local,
                 created_at, updated_at)
                VALUES
                (:downloader_id, :dl_speed_limit, :ul_speed_limit, :dl_speed_unit, :ul_speed_unit,
                 :enable_schedule, :username, :password, :advanced_settings, :override_local,
                 :created_at, :updated_at)
            """
            result = db.execute(text(insert_sql), {
                "downloader_id": downloader_id,
                "dl_speed_limit": dl_speed_limit,
                "ul_speed_limit": ul_speed_limit,
                "dl_speed_unit": dl_speed_unit,
                "ul_speed_unit": ul_speed_unit,
                "enable_schedule": body_data.get("enableSchedule") or body_data.get("enable_schedule", False),
                "username": body_data.get("username"),
                "password": encrypted_password,
                "advanced_settings": advanced_settings_json,
                "override_local": body_data.get("overrideLocal") or body_data.get("override_local", False),
                "created_at": current_time,
                "updated_at": current_time
            })

            # 获取新创建记录的 ID
            setting_id = result.lastrowid

        # 保存分时段规则
        if parsed_schedule_rules is not None:
            if len(parsed_schedule_rules) == 0:
                db.execute(
                    text("DELETE FROM speed_schedule_rules WHERE downloader_setting_id = :setting_id"),
                    {"setting_id": setting_id}
                )
            else:
                incoming_ids = [rule["id"] for rule in parsed_schedule_rules if rule["id"] is not None]
                if incoming_ids:
                    placeholders = ", ".join([f":rule_id_{idx}" for idx in range(len(incoming_ids))])
                    params = {"setting_id": setting_id}
                    params.update({f"rule_id_{idx}": rule_id for idx, rule_id in enumerate(incoming_ids)})
                    db.execute(
                        text(
                            f"""
                            DELETE FROM speed_schedule_rules
                            WHERE downloader_setting_id = :setting_id
                              AND id NOT IN ({placeholders})
                            """
                        ),
                        params
                    )
                else:
                    db.execute(
                        text("DELETE FROM speed_schedule_rules WHERE downloader_setting_id = :setting_id"),
                        {"setting_id": setting_id}
                    )

                insert_rules = []
                for idx, rule in enumerate(parsed_schedule_rules):
                    start_db_value = coerce_sqlite_time(rule["start_time"])
                    end_db_value = coerce_sqlite_time(rule["end_time"])
                    logger.info(
                        "[schedule_rule_bind] start=%s(%s), end=%s(%s)",
                        start_db_value, type(start_db_value).__name__,
                        end_db_value, type(end_db_value).__name__
                    )
                    logger.info(
                        "[schedule_rule_sync] rule %s/%s id=%s sort_order=%s",
                        idx + 1,
                        len(parsed_schedule_rules),
                        rule.get("id"),
                        rule.get("sort_order")
                    )

                    if rule["id"] is not None:
                        update_rule_sql = """
                            UPDATE speed_schedule_rules
                            SET sort_order = :sort_order,
                                start_time = :start_time,
                                end_time = :end_time,
                                dl_speed_limit = :dl_speed_limit,
                                dl_speed_unit = :dl_speed_unit,
                                ul_speed_limit = :ul_speed_limit,
                                ul_speed_unit = :ul_speed_unit,
                                days_of_week = :days_of_week,
                                enabled = :enabled
                            WHERE id = :id AND downloader_setting_id = :downloader_setting_id
                        """
                        result = db.execute(text(update_rule_sql), {
                            "id": rule["id"],
                            "downloader_setting_id": setting_id,
                            "sort_order": rule["sort_order"],
                            "start_time": start_db_value,
                            "end_time": end_db_value,
                            "dl_speed_limit": rule["dl_speed_limit"],
                            "dl_speed_unit": rule["dl_speed_unit"],
                            "ul_speed_limit": rule["ul_speed_limit"],
                            "ul_speed_unit": rule["ul_speed_unit"],
                            "days_of_week": rule["days_of_week"],
                            "enabled": rule["enabled"]
                        })
                        if result.rowcount == 0:
                            logger.warning(
                                "[schedule_rule_sync] update affected 0 rows, id=%s setting_id=%s",
                                rule["id"],
                                setting_id
                            )
                            db.rollback()
                            return CommonResponse(
                                status="error",
                                msg=f"分时段规则更新失败, 规则ID不存在或已被删除: {rule['id']}",
                                code="422",
                                data=None
                            )
                    else:
                        insert_rules.append({
                            "downloader_setting_id": setting_id,
                            "sort_order": rule["sort_order"],
                            "start_time": start_db_value,
                            "end_time": end_db_value,
                            "dl_speed_limit": rule["dl_speed_limit"],
                            "dl_speed_unit": rule["dl_speed_unit"],
                            "ul_speed_limit": rule["ul_speed_limit"],
                            "ul_speed_unit": rule["ul_speed_unit"],
                            "days_of_week": rule["days_of_week"],
                            "enabled": rule["enabled"]
                        })

                if insert_rules:
                    insert_rule_sql = """
                        INSERT INTO speed_schedule_rules
                        (downloader_setting_id, sort_order, start_time, end_time,
                         dl_speed_limit, dl_speed_unit,
                         ul_speed_limit, ul_speed_unit,
                         days_of_week, enabled)
                        VALUES
                        (:downloader_setting_id, :sort_order, :start_time, :end_time,
                         :dl_speed_limit, :dl_speed_unit,
                         :ul_speed_limit, :ul_speed_unit,
                         :days_of_week, :enabled)
                    """
                    db.execute(text(insert_rule_sql), insert_rules)
                    logger.info(
                        "[schedule_rule_sync] insert batch success, count=%s",
                        len(insert_rules)
                    )

        # 提交事务
        db.commit()

        schedule_rules_list = None
        try:
            schedule_rules_sql = """
                SELECT id, sort_order, start_time, end_time,
                       dl_speed_limit, dl_speed_unit,
                       ul_speed_limit, ul_speed_unit,
                       days_of_week, enabled
                FROM speed_schedule_rules
                WHERE downloader_setting_id = :setting_id
                ORDER BY sort_order ASC, created_at ASC
            """
            schedule_rules_result = db.execute(
                text(schedule_rules_sql),
                {"setting_id": setting_id}
            ).fetchall()

            schedule_rules_list = []
            for rule in schedule_rules_result:
                days_list = parse_days_of_week(rule.days_of_week)

                schedule_rules_list.append({
                    "id": rule.id,
                    "sort_order": rule.sort_order,
                    "start_time": rule.start_time,
                    "end_time": rule.end_time,
                    "weekdays": days_list,
                    "download": {
                        "enabled": rule.dl_speed_limit > 0,
                        "speed_limit": rule.dl_speed_limit,
                        "speed_unit": rule.dl_speed_unit
                    },
                    "upload": {
                        "enabled": rule.ul_speed_limit > 0,
                        "speed_limit": rule.ul_speed_limit,
                        "speed_unit": rule.ul_speed_unit
                    },
                    "enabled": rule.enabled
                })
        except Exception as e:
            logger.error(f"查询分时段限速规则失败: {e}")

        response_data = {"schedule_rules": schedule_rules_list if schedule_rules_list is not None else []}

        logger.info(
            f"更新下载器配置成功: {downloader_id} (包含 {len(parsed_schedule_rules) if parsed_schedule_rules is not None else 0} 条分时段规则)"
        )

        return CommonResponse(
            status="success",
            msg="保存成功",
            code="200",
            data=response_data
        )

    except ValueError as e:
        db.rollback()
        return CommonResponse(
            status="error",
            msg=str(e),
            code="422",
            data=None
        )
    except Exception as e:
        db.rollback()
        logger.error(f"更新下载器配置失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=response_data
        )


@router.put(
    "/{downloader_id}/settings/rules/reorder",
    summary="更新分时段限速规则排序",
    response_model=CommonResponse,
    tags=["下载器设置"]
)
async def reorder_speed_schedule_rules(
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    更新分时段限速规则排序

    请求体：
    {
        "rule_ids": [3, 1, 2]
    }
    """
    try:
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        body_data = await req.json()
        rule_ids = body_data.get("rule_ids", [])

        if not isinstance(rule_ids, list):
            return CommonResponse(
                status="error",
                msg="rule_ids 必须是数组",
                code="422",
                data=None
            )

        if len(rule_ids) == 0:
            return CommonResponse(
                status="success",
                msg="排序更新成功",
                code="200",
                data=None
            )

        # 获取下载器配置ID
        setting_sql = """
            SELECT id FROM downloader_settings WHERE downloader_id = :downloader_id
        """
        setting = db.execute(text(setting_sql), {"downloader_id": downloader_id}).fetchone()

        if not setting:
            return CommonResponse(
                status="error",
                msg="下载器配置不存在",
                code="404",
                data=None
            )

        for idx, rule_id in enumerate(rule_ids):
            try:
                rule_id_int = int(rule_id)
            except (TypeError, ValueError):
                continue

            update_sql = """
                UPDATE speed_schedule_rules
                SET sort_order = :sort_order
                WHERE id = :rule_id AND downloader_setting_id = :setting_id
            """
            db.execute(text(update_sql), {
                "sort_order": idx,
                "rule_id": rule_id_int,
                "setting_id": setting.id
            })

        db.commit()
        return CommonResponse(
            status="success",
            msg="排序更新成功",
            code="200",
            data=None
        )

    except Exception as e:
        db.rollback()
        logger.error(f"更新规则排序失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/{downloader_id}/settings/apply",
    summary="应用配置到下载器",
    response_model=CommonResponse,
    tags=["下载器设置"]
)
def apply_downloader_settings(
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    将保存的配置应用到下载器

    调用下载器SDK的实际API，将配置推送到下载器
    """
    try:
        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 查询下载器信息
        downloader_sql = """
            SELECT downloader_id, nickname, host, port, username, password, downloader_type
            FROM bt_downloaders
            WHERE downloader_id = :downloader_id AND dr = 0
        """
        downloader_result = db.execute(text(downloader_sql), {"downloader_id": downloader_id}).fetchone()

        if not downloader_result:
            return CommonResponse(
                status="error",
                msg="下载器不存在",
                code="404",
                data=None
            )

        # 3. 查询下载器配置
        settings_sql = """
            SELECT dl_speed_limit, ul_speed_limit, dl_speed_unit, ul_speed_unit, enable_schedule,
                   username, password, advanced_settings, override_local
            FROM downloader_settings
            WHERE downloader_id = :downloader_id
        """
        settings_result = db.execute(text(settings_sql), {"downloader_id": downloader_id}).fetchone()

        if not settings_result:
            return CommonResponse(
                status="error",
                msg="下载器配置不存在，请先配置",
                code="404",
                data=None
            )

        # 4. 构建下载器对象（用于初始化DownloaderSettingsManager）
        from app.downloader.models import BtDownloaders

        # 🔧 方案2修复：类型转换 - 确保downloader_type为整数类型
        # 解决数据库VARCHAR字段与业务逻辑Integer类型不匹配问题
        db_downloader_type = downloader_result.downloader_type

        # 定义类型映射表（支持多种格式）
        type_mapping = {
            # 字符串数字 -> 整数
            "0": 0,
            "1": 1,
            # 英文名称 -> 整数
            "qbittorrent": 0,
            "qbt": 0,
            "transmission": 1,
            "tr": 1,
        }

        # 如果是字符串，进行转换
        if isinstance(db_downloader_type, str):
            # 不区分大小写匹配
            normalized_type = type_mapping.get(db_downloader_type.lower())

            if normalized_type is None:
                # 尝试中文名称模糊匹配
                lower_type = db_downloader_type.lower()
                if "qbittorrent" in lower_type or "qbit" in lower_type:
                    normalized_type = 0
                elif "transmission" in lower_type or "trans" in lower_type:
                    normalized_type = 1
                else:
                    # 无法识别的类型，返回错误
                    return CommonResponse(
                        status="error",
                        msg=f"不支持的下载器类型: '{db_downloader_type}' (类型: 字符串)",
                        code="500",
                        data=None
                    )

            logger.info(
                f"下载器类型转换: '{db_downloader_type}' (str) -> {normalized_type} (int)"
            )
            db_downloader_type = normalized_type
        else:
            # 如果是整数，验证有效性
            if db_downloader_type not in [0, 1]:
                return CommonResponse(
                    status="error",
                    msg=f"无效的下载器类型: {db_downloader_type} (期望: 0或1)",
                    code="500",
                    data=None
                )
            logger.debug(f"下载器类型已是整数: {db_downloader_type}")

        downloader = BtDownloaders(
            downloader_id=downloader_result.downloader_id,
            nickname=downloader_result.nickname,
            host=downloader_result.host,
            port=downloader_result.port,
            username=downloader_result.username,
            password=downloader_result.password,  # 从下载器表获取密码
            downloader_type=db_downloader_type  # ✅ 使用转换后的整数类型
        )

        # 5. 初始化设置管理器
        try:
            manager = DownloaderSettingsManager(downloader)
        except Exception as e:
            logger.error(f"初始化下载器管理器失败: {e}")
            return CommonResponse(
                status="error",
                msg=f"初始化下载器管理器失败: {str(e)}",
                code="500",
                data=None
            )

        # 6. 构建配置字典
        # 转换speed_unit：整数0->"KB/s", 1->"MB/s"
        speed_unit_map = {0: "KB/s", 1: "MB/s"}
        dl_speed_unit_str = speed_unit_map.get(settings_result.dl_speed_unit, "KB/s")
        ul_speed_unit_str = speed_unit_map.get(settings_result.ul_speed_unit, "KB/s")

        settings_dict = {
            "dl_speed_limit": settings_result.dl_speed_limit,
            "ul_speed_limit": settings_result.ul_speed_limit,
            "dl_speed_unit": dl_speed_unit_str,
            "ul_speed_unit": ul_speed_unit_str,
            "enable_schedule": bool(settings_result.enable_schedule),
            "override_local": bool(settings_result.override_local),
        }

        # 如果配置中有用户名和密码，则覆盖下载器的默认认证
        if settings_result.username:
            settings_dict["username"] = settings_result.username
        if settings_result.password:
            settings_dict["password"] = settings_result.password  # 已加密的密码

        # 解析高级配置
        # ⚠️ 【已废弃】高级配置功能已废弃，以下代码仅为向后兼容保留
        #    原因: qBittorrent客户端支持不完整，部分字段无法生效
        #    前端UI已隐藏此功能，未来版本将完全移除
        if settings_result.advanced_settings:
            try:
                advanced_settings = json.loads(settings_result.advanced_settings)
                if isinstance(advanced_settings, dict):
                    settings_dict.update(advanced_settings)

                    # qBittorrent字段映射（前端 -> SDK）
                    if downloader_result.downloader_type == 0:
                        qbt_field_map = {
                            "max_connections": "connection_limit",
                            "max_connections_per_torrent": "max_connec_per_torrent",
                            "max_download_slots": "max_active_downloads",
                            "max_upload_slots": "max_active_uploads",
                        }
                        for src_key, dst_key in qbt_field_map.items():
                            if src_key in advanced_settings and dst_key not in settings_dict:
                                settings_dict[dst_key] = advanced_settings[src_key]
                                if src_key in settings_dict:
                                    del settings_dict[src_key]
            except json.JSONDecodeError as e:
                logger.warning(f"解析高级配置JSON失败: {e}")

        logger.info(
            "应用配置: downloader_type=%s settings_keys=%s",
            downloader_result.downloader_type,
            list(settings_dict.keys())
        )
        # 7. 应用配置到下载器
        try:
            success = manager.apply_settings(settings_dict)
            if success:
                return CommonResponse(
                    status="success",
                    msg="配置应用成功",
                    code="200",
                    data=None
                )
            else:
                return CommonResponse(
                    status="error",
                    msg="配置应用失败",
                    code="500",
                    data=None
                )
        except Exception as e:
            logger.error(f"应用配置失败: {e}")
            return CommonResponse(
                status="error",
                msg=f"应用配置失败: {str(e)}",
                code="500",
                data=None
            )

    except Exception as e:
        logger.error(f"应用配置失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )


@router.post(
    "/{downloader_id}/settings/test",
    summary="测试配置有效性",
    response_model=CommonResponse,
    tags=["下载器设置"]
)
async def test_downloader_settings(
    downloader_id: str = Path(..., description="下载器ID"),
    req: Request = None,
    db: Session = Depends(get_db)
):
    """
    测试下载器配置的有效性

    使用页面表单传递的连接参数进行测试，如果页面密码为空则从数据库获取并解密
    """
    try:
        # ✅ P0-4修复: 验证Request对象
        if req is None:
            return CommonResponse(
                status="error",
                msg="请求对象不能为空",
                code="422",
                data=None
            )

        # 1. JWT认证
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未认证",
                code="401",
                data=None
            )

        try:
            utils.verify_access_token(token)
        except Exception as e:
            return CommonResponse(
                status="error",
                msg=f"token验证失败: {str(e)}",
                code="401",
                data=None
            )

        # 2. 获取请求体数据（页面表单数据）
        try:
            body_data = await req.json()
        except Exception as e:
            logger.error(f"解析请求体失败: {e}")
            return CommonResponse(
                status="error",
                msg=f"请求体格式错误: {str(e)}",
                code="422",
                data=None
            )

        # ✅ P0-4修复: 验证body_data类型和内容
        if not body_data or not isinstance(body_data, dict):
            return CommonResponse(
                status="error",
                msg="请求体不能为空且必须为对象类型",
                code="422",
                data=None
            )

        # 3. 从请求体获取连接参数
        test_host = body_data.get("host")
        test_port = body_data.get("port")
        test_username = body_data.get("username")
        test_password = body_data.get("password")  # 页面密码（可能为空）
        test_downloader_type = body_data.get("downloader_type")
        test_is_ssl = body_data.get("is_ssl", "0")

        # 4. ✅ P0-4修复: 增强参数验证
        # 主机地址验证
        if not test_host or not isinstance(test_host, str):
            return CommonResponse(
                status="error",
                msg="主机地址不能为空且必须为字符串",
                code="422",
                data=None
            )

        # 清理主机地址（移除多余空格）
        test_host = test_host.strip()
        if not test_host:
            return CommonResponse(
                status="error",
                msg="主机地址不能为空",
                code="422",
                data=None
            )

        # 端口验证（增强类型检查和范围验证）
        try:
            test_port = int(test_port)
            if test_port < 1 or test_port > 65535:
                return CommonResponse(
                    status="error",
                    msg="端口号必须在1-65535之间",
                    code="422",
                    data=None
                )
        except (ValueError, TypeError):
            return CommonResponse(
                status="error",
                msg="端口必须是有效的数字",
                code="422",
                data=None
            )

        # 用户名验证
        if test_username is None:
            return CommonResponse(
                status="error",
                msg="用户名不能为空",
                code="422",
                data=None
            )

        if not isinstance(test_username, str):
            return CommonResponse(
                status="error",
                msg="用户名必须是字符串",
                code="422",
                data=None
            )

        # 下载器类型验证
        if test_downloader_type is None:
            return CommonResponse(
                status="error",
                msg="下载器类型不能为空",
                code="422",
                data=None
            )

        try:
            test_downloader_type = int(test_downloader_type)
            if test_downloader_type not in [0, 1]:  # 0=qBittorrent, 1=Transmission
                return CommonResponse(
                    status="error",
                    msg="下载器类型必须是0(qBittorrent)或1(Transmission)",
                    code="422",
                    data=None
                )
        except (ValueError, TypeError):
            return CommonResponse(
                status="error",
                msg="下载器类型必须是有效的数字",
                code="422",
                data=None
            )

        # SSL标志验证
        if test_is_ssl is not None:
            try:
                test_is_ssl = int(test_is_ssl)
                if test_is_ssl not in [0, 1]:
                    return CommonResponse(
                        status="error",
                        msg="SSL标志必须是0或1",
                        code="422",
                        data=None
                    )
            except (ValueError, TypeError):
                test_is_ssl = 0  # 默认不使用SSL

        # 5. 密码处理逻辑：如果页面密码为空，从数据库获取并解密
        final_password = test_password
        if not test_password or test_password.strip() == "":
            # 从数据库查询加密的密码
            downloader_sql = """
                SELECT password, username
                FROM bt_downloaders
                WHERE downloader_id = :downloader_id AND dr = 0
            """
            downloader_result = db.execute(
                text(downloader_sql),
                {"downloader_id": downloader_id}
            ).fetchone()

            if not downloader_result:
                return CommonResponse(
                    status="error",
                    msg="下载器不存在",
                    code="404",
                    data=None
                )

            # 解密数据库中的密码
            encrypted_password = downloader_result.password
            if encrypted_password:
                try:
                    final_password = decrypt_password(encrypted_password)
                    logger.debug("使用数据库密码（已解密）进行测试")
                except Exception as e:
                    logger.error(f"密码解密失败: {e}")
                    return CommonResponse(
                        status="error",
                        msg=f"密码解密失败: {str(e)}",
                        code="500",
                        data=None
                    )
            else:
                return CommonResponse(
                    status="error",
                    msg="未提供密码且数据库中无密码",
                    code="422",
                    data=None
                )

        # 6. ✅ 绕过缓存，直接创建客户端进行测试
        try:
            import time
            start_time = time.time()

            # 根据下载器类型创建对应的客户端
            if DownloaderTypeEnum.normalize(test_downloader_type) == DownloaderTypeEnum.QBITTORRENT:  # qBittorrent
                from qbittorrentapi import Client as QBClient
                from qbittorrentapi import LoginFailed

                try:
                    # 构建URL
                    protocol = "https" if int(test_is_ssl) == 1 else "http"
                    url = f"{protocol}://{test_host}:{int(test_port)}"

                    # 创建客户端并测试连接
                    client = QBClient(
                        host=url,
                        username=test_username,
                        password=final_password,
                        VERIFY_WEBUI_CERTIFICATE=False,  # 测试时跳过SSL验证
                        REQUESTS_ARGS={'timeout': 10}  # 10秒超时
                    )

                    # 尝试登录并获取版本信息
                    version = client.app_version()
                    if not version:
                        return CommonResponse(
                            status="success",
                            msg="测试完成",
                            code="200",
                            data={
                                "success": False,
                                "message": "无法获取qBittorrent版本信息，请检查连接参数",
                                "delay": None
                            }
                        )

                    delay = int((time.time() - start_time) * 1000)
                    logger.info(f"qBittorrent测试连接成功: {test_host}:{test_port}, 版本: {version}, 延迟: {delay}ms")

                    return CommonResponse(
                        status="success",
                        msg="测试成功",
                        code="200",
                        data={
                            "success": True,
                            "message": "连接成功",
                            "delay": delay
                        }
                    )

                except LoginFailed as e:
                    logger.error(f"qBittorrent认证失败: {e}")
                    return CommonResponse(
                        status="success",
                        msg="测试完成",
                        code="200",
                        data={
                            "success": False,
                            "message": f"认证失败，请检查用户名和密码: {str(e)}",
                            "delay": None
                        }
                    )
                except Exception as e:
                    logger.error(f"qBittorrent连接失败: {e}")
                    return CommonResponse(
                        status="success",
                        msg="测试完成",
                        code="200",
                        data={
                            "success": False,
                            "message": f"连接失败: {str(e)}",
                            "delay": None
                        }
                    )

            elif DownloaderTypeEnum.normalize(test_downloader_type) == DownloaderTypeEnum.TRANSMISSION:  # Transmission
                from transmission_rpc import Client as TrClient
                from transmission_rpc.error import TransmissionError

                try:
                    # 创建客户端并测试连接
                    # ✅ 修正：Transmission 使用 host 和 port 参数，而不是 url
                    client = TrClient(
                        host=test_host,
                        port=int(test_port),
                        username=test_username,
                        password=final_password,
                        timeout=10  # 10秒超时
                    )

                    # 尝试获取会话信息
                    session = client.get_session()
                    if not session:
                        return CommonResponse(
                            status="success",
                            msg="测试完成",
                            code="200",
                            data={
                                "success": False,
                                "message": "无法获取Transmission会话信息，请检查连接参数",
                                "delay": None
                            }
                        )

                    delay = int((time.time() - start_time) * 1000)
                    version = session.version
                    logger.info(f"Transmission测试连接成功: {test_host}:{test_port}, 版本: {version}, 延迟: {delay}ms")

                    return CommonResponse(
                        status="success",
                        msg="测试成功",
                        code="200",
                        data={
                            "success": True,
                            "message": "连接成功",
                            "delay": delay
                        }
                    )

                except TransmissionError as e:
                    logger.error(f"Transmission连接失败: {e}")
                    return CommonResponse(
                        status="success",
                        msg="测试完成",
                        code="200",
                        data={
                            "success": False,
                            "message": f"连接失败: {str(e)}",
                            "delay": None
                        }
                    )
                except Exception as e:
                    logger.error(f"Transmission连接异常: {e}")
                    return CommonResponse(
                        status="success",
                        msg="测试完成",
                        code="200",
                        data={
                            "success": False,
                            "message": f"连接失败: {str(e)}",
                            "delay": None
                        }
                    )

        except Exception as e:
            logger.error(f"测试连接失败: {e}")
            return CommonResponse(
                status="success",
                msg="测试完成",
                code="200",
                data={
                    "success": False,
                    "message": f"测试失败: {str(e)}",
                    "delay": None
                }
            )

    except Exception as e:
        logger.error(f"测试配置失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"服务器内部错误: {str(e)}",
            code="500",
            data=None
        )
