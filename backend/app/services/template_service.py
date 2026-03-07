# -*- coding: utf-8 -*-
"""
模板服务类

提供配置模板的业务逻辑封装，包括CRUD操作、验证、应用和冲突检测等功能。
"""
import json
import logging
from datetime import datetime, time
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.setting_templates import SettingTemplate, DownloaderTypeEnum
from app.models.downloader_settings import DownloaderSetting
from app.models.speed_schedule_rules import SpeedScheduleRule
from app.downloader.models import BtDownloaders
from app.services.downloader_settings_manager import DownloaderSettingsManager

logger = logging.getLogger(__name__)


def normalize_schedule_time(value) -> str:
    """Normalize schedule time to HH:MM string for SQLite compatibility."""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, str):
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(value, fmt).strftime("%H:%M")
            except ValueError:
                continue
    raise ValueError(f"invalid schedule time: {value}")


class TemplateService:
    """
    模板服务类

    封装所有模板相关的业务逻辑，提供：
    - 模板CRUD操作
    - 模板验证
    - 模板应用（包含分时段规则）
    - 冲突检测
    """

    def __init__(self, db: Session):
        """
        初始化模板服务

        Args:
            db: SQLAlchemy数据库会话
        """
        self.db = db

    # ========== CRUD操作 ==========

    def create_template(self, user_id: int, data: dict) -> dict:
        """
        创建用户自定义模板

        Args:
            user_id: 用户ID
            data: 模板数据字典，包含：
                - name: 模板名称
                - description: 模板描述
                - downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）
                - template_config: 模板配置

        Returns:
            dict: 创建的模板数据

        Raises:
            ValueError: 参数验证失败
            Exception: 数据库操作失败
        """
        # 参数验证
        name = data.get("name")
        if not name or not isinstance(name, str) or len(name) > 100:
            raise ValueError("模板名称不能为空且长度不能超过100")

        description = data.get("description")
        if description and len(description) > 500:
            raise ValueError("模板描述长度不能超过500")

        downloader_type = data.get("downloader_type")
        if downloader_type not in [0, 1]:
            raise ValueError("下载器类型必须是0（qBittorrent）或1（Transmission）")

        template_config = data.get("template_config")
        if not template_config or not isinstance(template_config, dict):
            raise ValueError("模板配置不能为空且必须是JSON对象")

        # 检查模板名称是否已存在
        existing = self.db.query(SettingTemplate).filter_by(name=name).first()
        if existing:
            raise ValueError(f"模板名称 '{name}' 已存在")

        # 验证模板配置
        is_valid, error_msg = self.validate_template(template_config, downloader_type)
        if not is_valid:
            raise ValueError(f"模板配置验证失败: {error_msg}")

        # 序列化模板配置
        try:
            template_config_json = json.dumps(template_config, ensure_ascii=False)
        except Exception as e:
            raise ValueError(f"模板配置序列化失败: {str(e)}")

        # 处理路径映射配置
        path_mapping_json = None
        path_mapping_data = data.get("path_mapping")
        if path_mapping_data:
            if not isinstance(path_mapping_data, dict):
                raise ValueError("路径映射配置必须是JSON对象")
            try:
                path_mapping_json = json.dumps(path_mapping_data, ensure_ascii=False)
            except Exception as e:
                raise ValueError(f"路径映射配置序列化失败: {str(e)}")

        # 创建模板
        template = SettingTemplate(
            name=name,
            description=description,
            downloader_type=downloader_type,
            template_config=template_config_json,
            path_mapping=path_mapping_json,  # 新增: 路径映射
            is_system_default=False,
            created_by=user_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)

        logger.info(f"创建模板成功: name={name}, user_id={user_id}")

        return template.to_dict()

    def update_template(self, template_id: int, user_id: int, data: dict) -> dict:
        """
        更新模板

        Args:
            template_id: 模板ID
            user_id: 用户ID
            data: 更新数据字典

        Returns:
            dict: 更新后的模板数据

        Raises:
            ValueError: 参数验证失败或权限不足
            Exception: 数据库操作失败
        """
        # 查询模板
        template = self.db.query(SettingTemplate).filter_by(id=template_id).first()
        if not template:
            raise ValueError("模板不存在")

        # 检查是否是系统默认模板
        if template.is_system_default:
            raise ValueError("系统默认模板不能修改")

        # 检查用户权限
        if template.created_by != user_id:
            raise ValueError("无权修改此模板")

        # 构建更新字段
        update_fields = {}
        updated = False

        if "name" in data:
            name = data["name"]
            if not name or len(name) > 100:
                raise ValueError("模板名称长度不能超过100")
            # 检查名称是否重复
            existing = self.db.query(SettingTemplate).filter(
                SettingTemplate.name == name,
                SettingTemplate.id != template_id
            ).first()
            if existing:
                raise ValueError(f"模板名称 '{name}' 已存在")
            update_fields["name"] = name
            updated = True

        if "description" in data:
            description = data["description"]
            if description and len(description) > 500:
                raise ValueError("模板描述长度不能超过500")
            update_fields["description"] = description
            updated = True

        if "downloader_type" in data:
            downloader_type = data["downloader_type"]
            if downloader_type not in [0, 1]:
                raise ValueError("下载器类型必须是0（qBittorrent）或1（Transmission）")
            update_fields["downloader_type"] = downloader_type
            updated = True

        if "template_config" in data:
            template_config = data["template_config"]
            if not isinstance(template_config, dict):
                raise ValueError("模板配置必须是JSON对象")

            # 验证模板配置
            is_valid, error_msg = self.validate_template(
                template_config,
                data.get("downloader_type", template.downloader_type)
            )
            if not is_valid:
                raise ValueError(f"模板配置验证失败: {error_msg}")

            try:
                update_fields["template_config"] = json.dumps(template_config, ensure_ascii=False)
                updated = True
            except Exception as e:
                raise ValueError(f"模板配置序列化失败: {str(e)}")

        if not updated:
            raise ValueError("没有要更新的字段")

        # 执行更新
        update_fields["updated_at"] = datetime.now()
        for key, value in update_fields.items():
            setattr(template, key, value)

        self.db.commit()
        self.db.refresh(template)

        logger.info(f"更新模板成功: template_id={template_id}, user_id={user_id}")

        return template.to_dict()

    def delete_template(self, template_id: int, user_id: int) -> bool:
        """
        删除模板

        Args:
            template_id: 模板ID
            user_id: 用户ID

        Returns:
            bool: 删除成功返回True

        Raises:
            ValueError: 参数验证失败或权限不足
            Exception: 数据库操作失败
        """
        # 查询模板
        template = self.db.query(SettingTemplate).filter_by(id=template_id).first()
        if not template:
            raise ValueError("模板不存在")

        # 检查是否是系统默认模板
        if template.is_system_default:
            raise ValueError("系统默认模板不能删除")

        # 检查用户权限
        if template.created_by != user_id:
            raise ValueError("无权删除此模板")

        # 执行删除
        self.db.delete(template)
        self.db.commit()

        logger.info(f"删除模板成功: template_id={template_id}, user_id={user_id}")

        return True

    def get_template(self, template_id: int, user_id: Optional[int] = None) -> dict:
        """
        获取模板详情

        Args:
            template_id: 模板ID
            user_id: 用户ID（可选，用于权限验证）

        Returns:
            dict: 模板数据

        Raises:
            ValueError: 模板不存在或权限不足
        """
        template = self.db.query(SettingTemplate).filter_by(id=template_id).first()
        if not template:
            raise ValueError("模板不存在")

        # 检查用户权限（仅对非系统默认模板）
        if not template.is_system_default and user_id and template.created_by != user_id:
            raise ValueError("无权访问此模板")

        return template.to_dict()

    def list_templates(
        self,
        user_id: Optional[int] = None,
        filters: Optional[dict] = None
    ) -> List[dict]:
        """
        列出模板

        Args:
            user_id: 用户ID（可选）
            filters: 过滤条件，可包含：
                - downloader_type: 下载器类型
                - is_system_default: 是否系统默认

        Returns:
            List[dict]: 模板列表
        """
        query = self.db.query(SettingTemplate)

        # 应用过滤条件
        if filters:
            if "downloader_type" in filters:
                query = query.filter(
                    SettingTemplate.downloader_type == filters["downloader_type"]
                )

            if "is_system_default" in filters:
                query = query.filter(
                    SettingTemplate.is_system_default == filters["is_system_default"]
                )

        # 如果指定了user_id，且不包含系统默认模板，则只返回用户的模板
        if user_id and filters and not filters.get("is_system_default", False):
            query = query.filter(SettingTemplate.created_by == user_id)

        templates = query.order_by(SettingTemplate.created_at.desc()).all()

        return [template.to_dict() for template in templates]

    # ========== 模板验证 ==========

    def validate_template(
        self,
        template_data: dict,
        downloader_type: int
    ) -> Tuple[bool, str]:
        """
        验证模板配置的有效性

        Args:
            template_data: 模板配置字典
            downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）

        Returns:
            Tuple[bool, str]: (是否有效, 错误消息)
        """
        # 检查必需字段
        required_fields = ["dl_speed_limit", "ul_speed_limit", "speed_unit"]
        for field in required_fields:
            if field not in template_data:
                return False, f"缺少必需字段: {field}"

        # 验证速度值
        if not isinstance(template_data["dl_speed_limit"], int) or template_data["dl_speed_limit"] < 0:
            return False, "下载速度限制必须是非负整数"

        if not isinstance(template_data["ul_speed_limit"], int) or template_data["ul_speed_limit"] < 0:
            return False, "上传速度限制必须是非负整数"

        # 验证速度单位
        if template_data["speed_unit"] not in [0, 1]:
            return False, "速度单位必须是0(KB/s)或1(MB/s)"

        # 验证分时段规则（如果存在）
        if "schedule_rules" in template_data and template_data["schedule_rules"]:
            rules = template_data["schedule_rules"]
            if not isinstance(rules, list):
                return False, "schedule_rules必须是数组"

            for idx, rule in enumerate(rules):
                # 验证规则字段
                if "start_time" not in rule or "end_time" not in rule:
                    return False, f"分时段规则#{idx+1}缺少时间字段"

                if "days_of_week" not in rule:
                    return False, f"分时段规则#{idx+1}缺少days_of_week字段"

                # 验证days_of_week格式
                days_str = rule["days_of_week"]
                if not self._validate_days_of_week(days_str):
                    return False, f"分时段规则#{idx+1}的days_of_week格式无效"

        # 验证高级配置（如果存在）
        if "advanced_settings" in template_data and template_data["advanced_settings"]:
            advanced = template_data["advanced_settings"]
            if not isinstance(advanced, dict):
                return False, "advanced_settings必须是对象"

            # qBittorrent特有字段验证
            if downloader_type == 0:
                qb_fields = ["max_connec", "max_numconn", "max_uploads"]
                for field in qb_fields:
                    if field in advanced:
                        value = advanced[field]
                        if not isinstance(value, int) or value < 0:
                            return False, f"高级配置字段 {field} 必须是非负整数"

            # Transmission特有字段验证
            elif downloader_type == 1:
                tr_fields = ["peer-limit-global", "peer-limit-per-torrent"]
                for field in tr_fields:
                    if field in advanced:
                        value = advanced[field]
                        if not isinstance(value, int) or value < 0:
                            return False, f"高级配置字段 {field} 必须是非负整数"

        return True, ""

    def _validate_days_of_week(self, days_str: str) -> bool:
        """
        验证days_of_week格式是否正确

        Args:
            days_str: 待验证的字符串

        Returns:
            bool: 格式正确返回True
        """
        if not days_str or len(days_str) > 7:
            return False

        # 检查是否只包含0-6的数字
        import re
        pattern = re.compile(r'^[0-6]{1,7}$')
        if not pattern.match(days_str):
            return False

        # 检查是否有重复
        if len(set(days_str)) != len(days_str):
            return False

        return True

    # ========== 模板应用 ==========

    def apply_template(
        self,
        template_id: int,
        downloader_id: str,
        user_id: Optional[int] = None,
        override: bool = True,
        apply_path_mapping: Optional[bool] = None
    ) -> dict:
        """
        应用模板到下载器

        Args:
            template_id: 模板ID
            downloader_id: 下载器ID
            user_id: 用户ID（可选）
            override: 是否覆盖现有配置
            apply_path_mapping: 是否应用路径映射（None表示询问用户）

        Returns:
            dict: 应用结果，包含：
                - success: 是否成功
                - message: 结果消息
                - downloader_id: 下载器ID
                - has_path_mapping: 是否包含路径映射
                - needs_path_mapping_confirmation: 是否需要用户确认

        Raises:
            ValueError: 参数验证失败
            Exception: 数据库操作失败
        """
        # 查询模板
        template = self.db.query(SettingTemplate).filter_by(id=template_id).first()
        if not template:
            raise ValueError("模板不存在")

        # 查询下载器
        downloader = self.db.query(BtDownloaders).filter(
            BtDownloaders.downloader_id == downloader_id,
            BtDownloaders.dr == 0
        ).first()

        if not downloader:
            raise ValueError("下载器不存在")

        # 检查模板类型与下载器类型是否匹配
        normalized_downloader_type = DownloaderTypeEnum.normalize(downloader.downloader_type)

        # 将 DownloaderTypeEnum 转换为整数进行比较
        template_type_int = template.downloader_type
        downloader_type_int = normalized_downloader_type.value

        if template_type_int != downloader_type_int:
            raise ValueError(
                f"模板类型（{template_type_int}）与下载器类型（{downloader_type_int}）不匹配"
            )

        # 解析模板配置
        try:
            template_config = template.get_config_dict()
        except Exception as e:
            logger.error(f"解析模板配置失败: {e}")
            raise ValueError("模板配置格式错误")

        current_time = datetime.now()

        # 检查是否已有配置
        existing_setting = self.db.query(DownloaderSetting).filter_by(
            downloader_id=downloader_id
        ).first()

        # 如果不覆盖且已有配置，返回提示
        if not override and existing_setting:
            return {
                "success": False,
                "message": "下载器已有配置，请确认是否覆盖",
                "downloader_id": downloader_id,
                "existing_config": True
            }

        # 构建下载器设置数据
        setting_data = {
            "dl_speed_limit": template_config.get("dl_speed_limit", 0),
            "ul_speed_limit": template_config.get("ul_speed_limit", 0),
            "speed_unit": template_config.get("speed_unit", 0),
            "enable_schedule": template_config.get("enable_schedule", False),
            "override_local": template_config.get("override_local", False),
            "username": template_config.get("username"),
            "password": template_config.get("password"),
            "advanced_settings": json.dumps(
                template_config.get("advanced_settings", {}),
                ensure_ascii=False
            ) if template_config.get("advanced_settings") else None,
        }

        if existing_setting:
            # 更新现有配置
            for key, value in setting_data.items():
                if value is not None or key in ["advanced_settings"]:
                    setattr(existing_setting, key, value)
            existing_setting.updated_at = current_time

            # 删除旧的分时段规则
            self.db.query(SpeedScheduleRule).filter_by(
                downloader_setting_id=existing_setting.id
            ).delete()

            logger.info(f"更新下载器配置: downloader_id={downloader_id}")
        else:
            # 创建新配置
            existing_setting = DownloaderSetting(
                downloader_id=downloader_id,
                created_at=current_time,
                updated_at=current_time,
                **setting_data
            )
            self.db.add(existing_setting)
            self.db.flush()  # 获取ID

            logger.info(f"创建下载器配置: downloader_id={downloader_id}")

        # 处理分时段规则（如果存在）
        if "schedule_rules" in template_config and template_config["schedule_rules"]:
            self._create_schedule_rules(
                existing_setting.id,
                template_config["schedule_rules"]
            )

        # 处理路径映射配置（如果存在）
        if template.path_mapping:
            if apply_path_mapping is True:
                # 明确要求应用路径映射
                downloader.path_mapping = template.path_mapping
                logger.info(f"模板路径映射已应用到下载器: {downloader_id}")
            elif apply_path_mapping is False:
                # 明确要求不应用路径映射
                logger.info(f"模板路径映射已跳过: {downloader_id}")
            else:
                # 未指定,返回提示信息
                logger.warning(f"模板包含路径映射但未指定是否应用: {downloader_id}")
                self.db.commit()
                return {
                    "success": False,
                    "message": "模板包含路径映射配置,请确认是否覆盖下载器的现有路径映射",
                    "has_path_mapping": True,
                    "needs_path_mapping_confirmation": True,
                    "downloader_id": downloader_id
                }

        self.db.commit()
        logger.info(f"应用模板到下载器设置表成功: template_id={template_id}, downloader_id={downloader_id}")

        # 应用配置到下载器
        try:
            downloader_obj = BtDownloaders(
                downloader_id=downloader.downloader_id,
                nickname=downloader.nickname,
                host=downloader.host,
                port=downloader.port,
                username=downloader.username,
                password=downloader.password,
                downloader_type=downloader.downloader_type
            )

            manager = DownloaderSettingsManager(downloader_obj)

            # 转换speed_unit：整数0->"KB/s", 1->"MB/s"
            speed_unit_map = {0: "KB/s", 1: "MB/s"}
            template_config_for_apply = template_config.copy()
            if "speed_unit" in template_config_for_apply:
                speed_unit_int = template_config_for_apply["speed_unit"]
                template_config_for_apply["speed_unit"] = speed_unit_map.get(speed_unit_int, "KB/s")

            success = manager.apply_settings(template_config_for_apply)

            if success:
                return {
                    "success": True,
                    "message": f"模板应用成功: {template.name}",
                    "downloader_id": downloader_id
                }
            else:
                return {
                    "success": False,
                    "message": "配置已保存到数据库，但应用失败",
                    "downloader_id": downloader_id
                }

        except Exception as e:
            logger.error(f"应用模板配置到下载器失败: {e}")
            return {
                "success": False,
                "message": f"配置已保存到数据库，但应用失败: {str(e)}",
                "downloader_id": downloader_id
            }

    def _create_schedule_rules(self, downloader_setting_id: int, rules_data: list):
        """
        创建分时段速度规则

        Args:
            downloader_setting_id: 下载器配置ID
            rules_data: 规则数据列表
        """
        for rule_data in rules_data:
            # 解析时间字符串
            try:
                start_time = normalize_schedule_time(rule_data["start_time"])
                end_time = normalize_schedule_time(rule_data["end_time"])
            except ValueError as e:
                logger.error(f"时间格式解析失败: {e}")
                continue

            rule = SpeedScheduleRule(
                downloader_setting_id=downloader_setting_id,
                start_time=start_time,
                end_time=end_time,
                dl_speed_limit=rule_data.get("dl_speed_limit", 0),
                ul_speed_limit=rule_data.get("ul_speed_limit", 0),
                days_of_week=rule_data.get("days_of_week", "0123456"),
                enabled=rule_data.get("enabled", True)
            )

            self.db.add(rule)
            logger.info(f"创建分时段规则: {rule_data['start_time']}-{rule_data['end_time']}")

    # ========== 冲突检测 ==========

    def check_template_conflict(
        self,
        template_id: int,
        downloader_id: str
    ) -> Tuple[bool, str]:
        """
        检测模板应用是否会冲突

        Args:
            template_id: 模板ID
            downloader_id: 下载器ID

        Returns:
            Tuple[bool, str]: (是否有冲突, 冲突消息)
        """
        # 检查下载器是否已有配置
        existing_setting = self.db.query(DownloaderSetting).filter_by(
            downloader_id=downloader_id
        ).first()

        if existing_setting:
            return True, "下载器已有配置，应用模板将覆盖现有设置"

        return False, ""

    # ========== 批量操作 ==========

    def batch_apply_template(
        self,
        template_id: int,
        downloader_ids: List[str],
        user_id: Optional[int] = None,
        override: bool = True
    ) -> List[dict]:
        """
        批量应用模板到多个下载器

        Args:
            template_id: 模板ID
            downloader_ids: 下载器ID列表
            user_id: 用户ID（可选）
            override: 是否覆盖现有配置

        Returns:
            List[dict]: 每个下载器的应用结果
        """
        results = []

        for downloader_id in downloader_ids:
            try:
                result = self.apply_template(
                    template_id=template_id,
                    downloader_id=downloader_id,
                    user_id=user_id,
                    override=override
                )
                results.append({
                    "downloader_id": downloader_id,
                    "success": result["success"],
                    "message": result["message"]
                })
            except Exception as e:
                logger.error(f"批量应用模板失败: downloader_id={downloader_id}, error={e}")
                results.append({
                    "downloader_id": downloader_id,
                    "success": False,
                    "message": f"应用失败: {str(e)}"
                })

        return results
