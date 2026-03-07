# -*- coding: utf-8 -*-
"""
分时段限速服务
"""
from datetime import datetime
from typing import List, Dict
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

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

        results = db.execute(text(sql), {
            "setting_id": downloader_setting_id,
            "weekday_pattern": f"%{current_weekday}%",
            "legacy_pattern": f"%{legacy_weekday}%",
            "current_time": current_time_str
        }).fetchall()

        return [dict(row._mapping) for row in results]

    @staticmethod
    def calculate_effective_speed(rules: List[Dict]) -> Dict:
        """
        根据生效规则计算当前应应用的速度
        """
        result = {
            "dl_speed": 0,
            "dl_unit": 0,
            "ul_speed": 0,
            "ul_unit": 0
        }

        # sort_order 数字越小优先级越高，优先级高的先命中并固定
        for rule in rules:
            if result["dl_speed"] == 0 and rule.get("dl_speed_limit", 0) > 0:
                result["dl_speed"] = rule["dl_speed_limit"]
                result["dl_unit"] = rule.get("dl_speed_unit", 0)

            if result["ul_speed"] == 0 and rule.get("ul_speed_limit", 0) > 0:
                result["ul_speed"] = rule["ul_speed_limit"]
                result["ul_unit"] = rule.get("ul_speed_unit", 0)

        return result

    @staticmethod
    def apply_to_downloader(db: Session, downloader_id: str, downloader_setting_id: int) -> bool:
        """
        将生效规则应用到下载器
        """
        try:
            current_time = datetime.now()
            active_rules = SpeedScheduleService.get_active_rules(db, downloader_setting_id, current_time)
            speed_config = SpeedScheduleService.calculate_effective_speed(active_rules)

            from app.services.downloader_settings_manager import DownloaderSettingsManager
            from app.downloader.models import BtDownloaders

            downloader_sql = """
                SELECT downloader_id, nickname, host, port, username, password, downloader_type
                FROM bt_downloaders
                WHERE downloader_id = :downloader_id
            """
            downloader_result = db.execute(
                text(downloader_sql),
                {"downloader_id": downloader_id}
            ).fetchone()

            if not downloader_result:
                return False

            downloader = BtDownloaders(
                downloader_id=downloader_result.downloader_id,
                nickname=downloader_result.nickname,
                host=downloader_result.host,
                port=downloader_result.port,
                username=downloader_result.username,
                password=downloader_result.password,
                downloader_type=downloader_result.downloader_type
            )

            manager = DownloaderSettingsManager(downloader)

            unit_map = {0: "KB/s", 1: "MB/s"}
            settings_dict = {
                "dl_speed_limit": speed_config["dl_speed"],
                "dl_speed_unit": unit_map.get(speed_config["dl_unit"], "KB/s"),
                "ul_speed_limit": speed_config["ul_speed"],
                "ul_speed_unit": unit_map.get(speed_config["ul_unit"], "KB/s"),
                "override_local": True
            }

            return manager.apply_settings(settings_dict)

        except Exception as e:
            logger.error(f"应用分时段限速失败: {e}")
            return False
