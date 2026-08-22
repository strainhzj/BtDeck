# -*- coding: utf-8 -*-
"""
分时段限速服务
"""

from datetime import datetime
from typing import Dict, List, Optional
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import SpeedUnitEnum

logger = logging.getLogger(__name__)


class SpeedScheduleService:
    @staticmethod
    def _coerce_speed_limit(value: object) -> int:
        """将 SQLite/表单中的速度值统一为非负整数。"""

        try:
            return max(0, int(str(value)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _is_active_on_weekday(days_of_week: object, weekday: int) -> bool:
        """按当前 0-6 格式匹配星期，并兼容含 7 的旧 1-7 格式。"""

        days = str(days_of_week or "")
        if not days:
            return False
        if "7" in days:
            return str(weekday + 1) in days
        return str(weekday) in days

    @staticmethod
    def get_active_rules(db: Session, downloader_setting_id: int, current_time: datetime) -> List[Dict]:
        """
        获取当前时间生效的规则
        """
        current_time_str = current_time.strftime("%H:%M")

        sql = """
            SELECT id, sort_order, start_time, end_time,
                   dl_speed_limit, dl_speed_unit,
                   ul_speed_limit, ul_speed_unit, days_of_week
            FROM speed_schedule_rules
            WHERE downloader_setting_id = :setting_id
              AND enabled = 1
              AND start_time <= :current_time
              AND end_time >= :current_time
            ORDER BY sort_order ASC, created_at ASC
        """

        results = db.execute(
            text(sql),
            {
                "setting_id": downloader_setting_id,
                "current_time": current_time_str,
            },
        ).fetchall()

        active_rules = []
        for row in results:
            rule = dict(row._mapping)
            if SpeedScheduleService._is_active_on_weekday(rule.get("days_of_week"), current_time.weekday()):
                active_rules.append(rule)
        return active_rules

    @staticmethod
    def calculate_effective_speed(rules: List[Dict], base_speed: Optional[Dict] = None) -> Dict:
        """
        根据生效规则计算当前应应用的速度。

        全局限速是基线；规则中大于 0 的方向才覆盖基线。这样未命中规则或
        某个方向未启用时，会恢复对应全局限速，而不是错误切换为不限速。
        """
        result = {
            "dl_speed": SpeedScheduleService._coerce_speed_limit((base_speed or {}).get("dl_speed", 0)),
            "dl_unit": (base_speed or {}).get("dl_unit", 0),
            "ul_speed": SpeedScheduleService._coerce_speed_limit((base_speed or {}).get("ul_speed", 0)),
            "ul_unit": (base_speed or {}).get("ul_unit", 0),
        }
        dl_overridden = False
        ul_overridden = False

        # sort_order 数字越小优先级越高，优先级高的先命中并固定
        for rule in rules:
            dl_speed_limit = SpeedScheduleService._coerce_speed_limit(rule.get("dl_speed_limit", 0))
            ul_speed_limit = SpeedScheduleService._coerce_speed_limit(rule.get("ul_speed_limit", 0))
            if not dl_overridden and dl_speed_limit > 0:
                result["dl_speed"] = dl_speed_limit
                result["dl_unit"] = rule.get("dl_speed_unit", 0)
                dl_overridden = True

            if not ul_overridden and ul_speed_limit > 0:
                result["ul_speed"] = ul_speed_limit
                result["ul_unit"] = rule.get("ul_speed_unit", 0)
                ul_overridden = True

        return result

    @staticmethod
    def get_global_speed_settings(db: Session, downloader_setting_id: int) -> Dict:
        """读取分时段规则之外的全局限速基线。"""
        row = db.execute(
            text(
                """
                SELECT dl_speed_limit, dl_speed_unit, ul_speed_limit, ul_speed_unit
                FROM downloader_settings
                WHERE id = :setting_id
                """
            ),
            {"setting_id": downloader_setting_id},
        ).fetchone()
        if not row:
            return {"dl_speed": 0, "dl_unit": 0, "ul_speed": 0, "ul_unit": 0}

        return {
            "dl_speed": SpeedScheduleService._coerce_speed_limit(row.dl_speed_limit),
            "dl_unit": row.dl_speed_unit,
            "ul_speed": SpeedScheduleService._coerce_speed_limit(row.ul_speed_limit),
            "ul_unit": row.ul_speed_unit,
        }

    @staticmethod
    def is_schedule_enabled(db: Session, downloader_setting_id: int) -> bool:
        row = db.execute(
            text("SELECT enable_schedule FROM downloader_settings WHERE id = :setting_id"),
            {"setting_id": downloader_setting_id},
        ).fetchone()
        if not row:
            return False
        value = getattr(row, "enable_schedule", None)
        if value is None:
            try:
                value = row[0]
            except (IndexError, KeyError, TypeError):
                # 兼容只返回下载器字段的旧测试/调用方；真实 SQL Row 会有该列。
                value = True
        return bool(value)

    @staticmethod
    def apply_to_downloader(db: Session, downloader_id: str, downloader_setting_id: int) -> bool:
        """
        将生效规则应用到下载器
        """
        try:
            current_time = datetime.now()
            schedule_enabled = SpeedScheduleService.is_schedule_enabled(db, downloader_setting_id)
            active_rules = (
                SpeedScheduleService.get_active_rules(db, downloader_setting_id, current_time)
                if schedule_enabled
                else []
            )
            base_speed = SpeedScheduleService.get_global_speed_settings(db, downloader_setting_id)
            speed_config = SpeedScheduleService.calculate_effective_speed(active_rules, base_speed=base_speed)

            from app.services.downloader_settings_manager import DownloaderSettingsManager
            from app.downloader.models import BtDownloaders

            downloader_sql = """
                SELECT downloader_id, nickname, host, port, username, password, downloader_type
                FROM bt_downloaders
                WHERE downloader_id = :downloader_id
            """
            downloader_result = db.execute(text(downloader_sql), {"downloader_id": downloader_id}).fetchone()

            if not downloader_result:
                return False

            downloader = BtDownloaders(
                downloader_id=downloader_result.downloader_id,
                nickname=downloader_result.nickname,
                host=downloader_result.host,
                port=downloader_result.port,
                username=downloader_result.username,
                password=downloader_result.password,
                downloader_type=downloader_result.downloader_type,
            )

            manager = DownloaderSettingsManager(downloader)

            settings_dict = {
                "dl_speed_limit": speed_config["dl_speed"],
                "dl_speed_unit": SpeedUnitEnum.from_value(speed_config["dl_unit"]).to_string(),
                "ul_speed_limit": speed_config["ul_speed"],
                "ul_speed_unit": SpeedUnitEnum.from_value(speed_config["ul_unit"]).to_string(),
                "override_local": True,
            }

            return manager.apply_settings(settings_dict)

        except Exception as e:
            logger.error(f"应用分时段限速失败: {e}")
            return False
