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
    def get_active_rules(db: Session, downloader_setting_id: int, current_time: datetime) -> List[Dict]:
        """
        获取当前时间生效的规则
        """
        current_weekday = str(current_time.weekday())  # 0=周一, 6=周日
        current_time_str = current_time.strftime("%H:%M")

        legacy_weekday = str(current_time.weekday() + 1)
        sql = """
            SELECT id, sort_order, start_time, end_time,
                   dl_speed_limit, dl_speed_unit,
                   ul_speed_limit, ul_speed_unit
            FROM speed_schedule_rules
            WHERE downloader_setting_id = :setting_id
              AND enabled = 1
              AND (days_of_week LIKE :weekday_pattern OR days_of_week LIKE :legacy_pattern)
              AND start_time <= :current_time
              AND end_time >= :current_time
            ORDER BY sort_order ASC, created_at ASC
        """

        results = db.execute(
            text(sql),
            {
                "setting_id": downloader_setting_id,
                "weekday_pattern": f"%{current_weekday}%",
                "legacy_pattern": f"%{legacy_weekday}%",
                "current_time": current_time_str,
            },
        ).fetchall()

        return [dict(row._mapping) for row in results]

    @staticmethod
    def calculate_effective_speed(rules: List[Dict], base_speed: Optional[Dict] = None) -> Dict:
        """
        根据生效规则计算当前应应用的速度。

        全局限速是基线；规则中大于 0 的方向才覆盖基线。这样未命中规则或
        某个方向未启用时，会恢复对应全局限速，而不是错误切换为不限速。
        """
        result = {
            "dl_speed": (base_speed or {}).get("dl_speed", 0),
            "dl_unit": (base_speed or {}).get("dl_unit", 0),
            "ul_speed": (base_speed or {}).get("ul_speed", 0),
            "ul_unit": (base_speed or {}).get("ul_unit", 0),
        }
        dl_overridden = False
        ul_overridden = False

        # sort_order 数字越小优先级越高，优先级高的先命中并固定
        for rule in rules:
            if not dl_overridden and rule.get("dl_speed_limit", 0) > 0:
                result["dl_speed"] = rule["dl_speed_limit"]
                result["dl_unit"] = rule.get("dl_speed_unit", 0)
                dl_overridden = True

            if not ul_overridden and rule.get("ul_speed_limit", 0) > 0:
                result["ul_speed"] = rule["ul_speed_limit"]
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
            "dl_speed": row.dl_speed_limit,
            "dl_unit": row.dl_speed_unit,
            "ul_speed": row.ul_speed_limit,
            "ul_unit": row.ul_speed_unit,
        }

    @staticmethod
    def apply_to_downloader(db: Session, downloader_id: str, downloader_setting_id: int) -> bool:
        """
        将生效规则应用到下载器
        """
        try:
            current_time = datetime.now()
            active_rules = SpeedScheduleService.get_active_rules(db, downloader_setting_id, current_time)
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
