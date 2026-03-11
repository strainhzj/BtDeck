"""
路径映射服务

提供双向路径转换功能，支持下载器内部路径和项目外部路径的映射转换。
主要用于Docker容器、网络存储、权限隔离等场景。

功能特性:
- 支持多个路径映射对
- 最长前缀匹配算法
- 路径标准化(统一使用正斜杠)
- 双向路径转换(internal ↔ external)
- 配置加载和验证
- 动态添加和删除映射

配置格式示例:
{
    "mappings": [
        {
            "name": "Docker下载目录",
            "description": "Docker容器内外路径映射",
            "internal": "/downloads/torrents/",
            "external": "D:/DockerData/Downloads/",
            "type": "docker"
        }
    ],
    "default_mapping": "Docker下载目录"
}
"""

import json
import logging
import platform
from typing import List, Dict, Optional, Tuple
from pathlib import Path, PurePath

logger = logging.getLogger(__name__)


class PathMappingService:
    """路径映射服务

    提供下载器内部路径和项目外部路径的双向转换功能。
    支持多个映射对，使用最长前缀匹配算法。
    """

    def __init__(self, path_mapping_config: Optional[str] = None):
        """
        初始化路径映射服务

        Args:
            path_mapping_config: JSON格式的路径映射配置
        """
        self.mappings: List[Dict] = []
        self.default_mapping: Optional[str] = None

        if path_mapping_config:
            self.load_config(path_mapping_config)

    def load_config(self, config: str):
        """
        加载路径映射配置

        Args:
            config: JSON格式的配置字符串

        Raises:
            ValueError: 配置格式无效时抛出异常
        """
        try:
            config_data = json.loads(config)
            self.mappings = config_data.get("mappings", [])
            self.default_mapping = config_data.get("default_mapping")

            # 验证配置
            self._validate_config()

            logger.info(f"加载路径映射配置成功: {len(self.mappings)}个映射")

        except json.JSONDecodeError as e:
            logger.error(f"路径映射配置JSON格式错误: {str(e)}")
            raise ValueError(f"Invalid JSON format: {str(e)}") from e
        except Exception as e:
            logger.error(f"路径映射配置加载失败: {str(e)}")
            raise ValueError(f"Config loading failed: {str(e)}") from e

    def _validate_config(self):
        """验证配置的有效性"""
        for idx, mapping in enumerate(self.mappings):
            # ✅ P1-2修复: 添加映射结构验证
            if not isinstance(mapping, dict):
                raise ValueError(f"映射 #{idx} 不是字典类型: {type(mapping)}")

            if "internal" not in mapping or "external" not in mapping:
                raise ValueError(f"映射配置缺少internal或external字段: {mapping}")

            # ✅ P1-2修复: 验证字段类型
            internal_value = mapping["internal"]
            external_value = mapping["external"]

            if not isinstance(internal_value, str):
                raise ValueError(f"映射 #{idx} 的 internal 字段必须是字符串类型: {type(internal_value)}")

            if not isinstance(external_value, str):
                raise ValueError(f"映射 #{idx} 的 external 字段必须是字符串类型: {type(external_value)}")

            # 标准化路径
            mapping["internal"] = self._normalize_path(mapping["internal"])
            mapping["external"] = self._normalize_path(mapping["external"])

    def _normalize_path(self, path: str) -> str:
        """
        标准化路径

        - 统一使用正斜杠
        - 移除多余的斜杠
        - 确保目录路径以/结尾
        - 保留UNC路径开头的双斜杠

        Args:
            path: 原始路径

        Returns:
            标准化后的路径
        """
        # ✅ P1-1修复: 添加类型检查，防止非字符串输入导致 AttributeError
        if not path or not isinstance(path, str):
            return ""

        # 替换反斜杠为正斜杠
        path = path.replace("\\", "/")

        # 检查是否是UNC路径(以//开头)
        is_unc = path.startswith("//")

        # 移除多余的斜杠
        while "///" in path:
            path = path.replace("///", "/")

        # 对于非UNC路径，移除双斜杠
        if not is_unc:
            while "//" in path:
                path = path.replace("//", "/")

        # 确保目录路径以/结尾
        if path and not path.endswith("/") and path != "/":
            # 检查是否是文件路径（包含扩展名）
            # ✅ P1-1修复: 添加 try-except 保护 Path 操作
            try:
                if "." not in Path(path).name:
                    path = path + "/"
            except Exception as e:
                logger.debug(f"Path 对象创建失败: {e}, 跳过扩展名检查")
                # 如果 Path 处理失败，保守地添加斜杠
                path = path + "/"

        return path

    @staticmethod
    def _normalize_for_os(path: str) -> str:
        """
        根据操作系统类型规范化UNC路径格式

        Windows UNC路径标准格式: \\server\share\path
        Linux/Unix UNC路径格式: //server/share/path

        Args:
            path: 映射后的路径

        Returns:
            符合操作系统原生格式的路径
        """
        if not path or not isinstance(path, str):
            return path

        # 检测是否是UNC路径（以//开头）
        is_unc = path.startswith("//")

        if not is_unc:
            return path

        is_windows = platform.system() == "Windows"

        if is_windows:
            # Windows系统：确保使用反斜杠
            if "/" in path:
                # 将 // 替换为 \\，将路径中的 / 替换为 \
                normalized = path.replace("/", "\\")
                logger.debug(f"[Windows UNC路径转换] {path} -> {normalized}")
                return normalized
        else:
            # Linux/Unix系统：确保使用正斜杠（已经是标准格式）
            logger.debug(f"[Unix UNC路径] 保持标准格式: {path}")
            return path

        return path

    def internal_to_external(self, internal_path: str) -> str:
        """
        将内部路径转换为外部路径

        Args:
            internal_path: 下载器内部路径

        Returns:
            项目外部路径
        """
        if not internal_path:
            return internal_path

        original_path = internal_path
        internal_path = self._normalize_path(internal_path)

        # 🔍 调试日志：记录路径映射转换的详细信息
        logger.info(
            f"[路径映射转换开始] "
            f"原始路径: {original_path}, "
            f"标准化后: {internal_path}, "
            f"映射数量: {len(self.mappings)}"
        )

        # 查找最长的匹配前缀
        best_match = None
        best_match_len = 0

        for idx, mapping in enumerate(self.mappings):
            # ✅ P0-1修复: 添加映射结构和字段类型验证
            # 验证映射是否为字典类型
            if not isinstance(mapping, dict):
                logger.warning(f"映射 #{idx} 不是字典类型，跳过: {type(mapping)}")
                continue

            # 安全获取字段，避免 KeyError
            internal_prefix = mapping.get("internal")
            external_prefix = mapping.get("external")
            mapping_name = mapping.get("name", f"映射#{idx}")

            # ✅ P0-1修复: 验证字段类型和有效性
            if not isinstance(internal_prefix, str) or not internal_prefix:
                logger.warning(f"映射 #{idx} ({mapping_name}) 的 internal 字段无效: {repr(internal_prefix)}")
                continue

            if not isinstance(external_prefix, str) or not external_prefix:
                logger.warning(f"映射 #{idx} ({mapping_name}) 的 external 字段无效: {repr(external_prefix)}")
                continue

            # 🔍 调试日志：记录每个映射的匹配尝试
            is_match = internal_path.startswith(internal_prefix)
            if is_match:
                prefix_len = len(internal_prefix)
                if prefix_len > best_match_len:
                    best_match = mapping
                    best_match_len = prefix_len
                    logger.info(
                        f"[路径映射匹配] "
                        f"找到更好的匹配: {mapping_name}, "
                        f"internal={internal_prefix}, "
                        f"external={external_prefix}, "
                        f"前缀长度={prefix_len}"
                    )
                else:
                    logger.debug(
                        f"[路径映射跳过] "
                        f"匹配但长度不够: {mapping_name}, "
                        f"internal={internal_prefix}, "
                        f"当前最佳长度={best_match_len}"
                    )
            else:
                # ✅ P1-1修复: 只记录前几个字符的比较，避免日志过长
                # 添加 len() 调用的安全检查
                try:
                    show_input = internal_path[:50] + "..." if len(internal_path) > 50 else internal_path
                    show_prefix = internal_prefix[:50] + "..." if len(internal_prefix) > 50 else internal_prefix
                except (TypeError, AttributeError) as e:
                    logger.warning(f"路径长度检查失败: {e}, 使用默认显示")
                    show_input = str(internal_path)[:50]
                    show_prefix = str(internal_prefix)[:50]

                logger.debug(
                    f"[路径映射不匹配] "
                    f"名称={mapping_name}, "
                    f"internal前缀={show_prefix}, "
                    f"输入路径={show_input}"
                )

        if best_match:
            # 执行路径替换
            external_prefix = best_match["external"]
            relative_path = internal_path[best_match_len:]
            external_path = external_prefix + relative_path

            # 根据操作系统类型规范化UNC路径格式
            external_path = self._normalize_for_os(external_path)

            logger.info(
                f"[路径映射成功] "
                f"映射名称={best_match.get('name', 'unknown')}, "
                f"{internal_path} -> {external_path}, "
                f"相对路径={relative_path}"
            )
            return external_path

        # 没有匹配的映射，返回原路径
        logger.warning(
            f"[路径映射失败] "
            f"未找到匹配的映射，输入路径: {internal_path}, "
            f"映射总数: {len(self.mappings)}, "
            f"返回原路径"
        )
        return internal_path

    def external_to_internal(self, external_path: str) -> str:
        """
        将外部路径转换为内部路径

        Args:
            external_path: 项目外部路径

        Returns:
            下载器内部路径
        """
        if not external_path:
            return external_path

        external_path = self._normalize_path(external_path)

        # 查找最长的匹配前缀
        best_match = None
        best_match_len = 0

        for idx, mapping in enumerate(self.mappings):
            # ✅ P0-2修复: 添加映射结构和字段类型验证
            # 验证映射是否为字典类型
            if not isinstance(mapping, dict):
                logger.warning(f"映射 #{idx} 不是字典类型，跳过: {type(mapping)}")
                continue

            # 安全获取字段，避免 KeyError
            external_prefix = mapping.get("external")
            internal_prefix = mapping.get("internal")
            mapping_name = mapping.get("name", f"映射#{idx}")

            # ✅ P0-2修复: 验证字段类型和有效性
            if not isinstance(external_prefix, str) or not external_prefix:
                logger.debug(f"映射 #{idx} ({mapping_name}) 的 external 字段无效，跳过: {repr(external_prefix)}")
                continue

            if not isinstance(internal_prefix, str) or not internal_prefix:
                logger.debug(f"映射 #{idx} ({mapping_name}) 的 internal 字段无效，跳过: {repr(internal_prefix)}")
                continue

            if external_path.startswith(external_prefix):
                # 检查是否是更长的匹配
                if len(external_prefix) > best_match_len:
                    best_match = mapping
                    best_match_len = len(external_prefix)

        if best_match:
            # 执行路径替换
            internal_prefix = best_match["internal"]
            relative_path = external_path[best_match_len:]
            internal_path = internal_prefix + relative_path

            logger.debug(f"路径转换: {external_path} -> {internal_path}")
            return internal_path

        # 没有匹配的映射，返回原路径
        logger.warning(f"未找到路径映射: {external_path}，返回原路径")
        return external_path

    def get_mappings(self) -> List[Dict]:
        """获取所有映射配置"""
        return self.mappings.copy()

    def add_mapping(
        self,
        name: str,
        internal: str,
        external: str,
        description: Optional[str] = None,
        mapping_type: str = "local"
    ):
        """
        添加新的路径映射

        Args:
            name: 映射名称
            internal: 内部路径
            external: 外部路径
            description: 描述
            mapping_type: 映射类型

        Raises:
            TypeError: 当参数类型不正确时抛出异常
        """
        # ✅ P1-2修复: 添加参数类型验证
        if not isinstance(name, str):
            raise TypeError(f"name 参数必须是字符串类型: {type(name)}")
        if not isinstance(internal, str):
            raise TypeError(f"internal 参数必须是字符串类型: {type(internal)}")
        if not isinstance(external, str):
            raise TypeError(f"external 参数必须是字符串类型: {type(external)}")
        if description is not None and not isinstance(description, str):
            raise TypeError(f"description 参数必须是字符串类型或None: {type(description)}")
        if not isinstance(mapping_type, str):
            raise TypeError(f"mapping_type 参数必须是字符串类型: {type(mapping_type)}")

        mapping = {
            "name": name,
            "internal": self._normalize_path(internal),
            "external": self._normalize_path(external),
            "type": mapping_type
        }

        if description:
            mapping["description"] = description

        self.mappings.append(mapping)
        logger.info(f"添加路径映射: {name}")

    def remove_mapping(self, name: str) -> bool:
        """
        删除路径映射

        Args:
            name: 映射名称

        Returns:
            是否删除成功
        """
        for i, mapping in enumerate(self.mappings):
            if mapping.get("name") == name:
                del self.mappings[i]
                logger.info(f"删除路径映射: {name}")
                return True

        logger.warning(f"未找到路径映射: {name}")
        return False

    def to_json(self) -> str:
        """
        将配置导出为JSON字符串

        Returns:
            JSON格式的配置
        """
        config = {
            "mappings": self.mappings,
            "default_mapping": self.default_mapping
        }

        return json.dumps(config, indent=2, ensure_ascii=False)


class PathMappingConverter:
    """路径映射转换器

    基于路径映射规则（多行文本格式）进行路径转换。
    自动判断转换类型（加/替换），支持批量路径处理。

    规则格式：
        - 多行文本，每行一条规则
        - 源路径{#**#}目标路径
        - 例如：/downloads{#**#}/volume1

    转换类型（自动判断）：
        - 替换：目标路径以源路径结尾 → /downloads{#**#}/volume1/downloads
        - 加：目标路径独立 → /downloads{#**#}/volume1
    """

    RULE_SEPARATOR = "{#**#}"  # 规则分隔符

    def __init__(self, rules_text: Optional[str] = None):
        """
        初始化路径映射转换器

        Args:
            rules_text: 多行文本格式的路径映射规则
        """
        self.rules: List[Dict[str, str]] = []
        if rules_text:
            self.load_rules(rules_text)

    def load_rules(self, rules_text: str) -> None:
        """
        加载路径映射规则

        Args:
            rules_text: 多行文本格式的规则

        Raises:
            ValueError: 规则格式无效时抛出异常
        """
        self.rules = []

        if not rules_text or not rules_text.strip():
            logger.info("路径映射规则为空，不进行路径转换")
            return

        lines = rules_text.strip().split('\n')
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                # 跳过空行
                continue

            if self.RULE_SEPARATOR not in line:
                logger.warning(f"第{line_num}行规则格式错误（缺少分隔符{self.RULE_SEPARATOR}）: {line}")
                continue

            parts = line.split(self.RULE_SEPARATOR)
            if len(parts) != 2:
                logger.warning(f"第{line_num}行规则格式错误（分隔符数量不正确）: {line}")
                continue

            source_path = parts[0].strip()
            target_path = parts[1].strip()

            if not source_path or not target_path:
                logger.warning(f"第{line_num}行规则源路径或目标路径为空: {line}")
                continue

            # 判断转换类型
            conversion_type = self._detect_conversion_type(source_path, target_path)

            rule = {
                "source": source_path,
                "target": target_path,
                "type": conversion_type
            }

            self.rules.append(rule)
            logger.debug(f"加载路径转换规则: {source_path} -> {target_path} ({conversion_type})")

        logger.info(f"成功加载 {len(self.rules)} 条路径映射规则")

    def _detect_conversion_type(self, source: str, target: str) -> str:
        """
        自动判断转换类型

        判断逻辑：
        - 如果 target 以 source 结尾 → 替换
        - 否则 → 加

        Args:
            source: 源路径
            target: 目标路径

        Returns:
            转换类型：'replace'（替换）或 'add'（加）
        """
        # 标准化路径以便比较
        source_norm = self._normalize_path(source)
        target_norm = self._normalize_path(target)

        # 判断目标路径是否以源路径结尾
        if target_norm.endswith(source_norm):
            return "replace"
        else:
            return "add"

    def _normalize_path(self, path: str) -> str:
        """
        标准化路径

        - 统一使用正斜杠
        - 移除尾部斜杠

        Args:
            path: 原始路径

        Returns:
            标准化后的路径
        """
        # 统一使用正斜杠
        normalized = path.replace("\\", "/")

        # 移除尾部斜杠
        normalized = normalized.rstrip("/")

        return normalized

    def convert(self, original_path: str) -> Optional[str]:
        """
        应用路径转换规则

        按配置顺序匹配第一条规则，转换类型：
        - 替换：替换源路径前缀 → target + original_path[len(source):]
        - 加：替换源路径为目标路径（不保留源路径后缀）→ target + relative_path

        注：实际上两种类型都是替换操作，只是目标的含义不同：
        - replace: 目标路径包含源路径，需要保留相对路径
        - add: 目标路径独立，直接替换源路径前缀

        Args:
            original_path: 原始路径

        Returns:
            转换后的路径，如果没有匹配规则则返回None
        """
        # ✅ P0-3修复: 添加输入验证，防止panic
        if not original_path or not isinstance(original_path, str):
            logger.warning(f"无效的原始路径: {original_path} (类型: {type(original_path)})")
            return None

        if not self.rules:
            # 规则为空，表示路径相等（不转换）
            return original_path

        # 标准化原路径
        try:
            normalized_path = self._normalize_path(original_path)
        except Exception as e:
            logger.error(f"路径标准化失败: {e}, 原路径: {original_path}")
            return None

        # 按顺序匹配规则
        for rule in self.rules:
            try:
                source = rule.get("source")
                target = rule.get("target")
                conversion_type = rule.get("type")

                # 验证规则字段完整性
                if not all([source, target, conversion_type]):
                    logger.warning(f"规则字段不完整: source={source}, target={target}, type={conversion_type}")
                    continue

                # 确保所有路径都是字符串类型
                if not isinstance(source, str) or not isinstance(target, str):
                    logger.error(f"规则路径类型错误: source类型={type(source)}, target类型={type(target)}")
                    continue

                # ✅ P0-3修复: 添加长度检查，防止索引越界
                if len(normalized_path) < len(source):
                    continue

                # 检查是否匹配源路径（前缀匹配）
                if normalized_path.startswith(source):
                    # 获取相对路径（移除源路径前缀）
                    relative_path = normalized_path[len(source):]

                    if conversion_type == "replace":
                        # 替换：目标路径包含源路径，需要保留相对路径
                        # 例如：/downloads → /volume1/downloads → /volume1/downloads/movies
                        result = target + relative_path
                    elif conversion_type == "add":
                        # 加：目标路径独立，直接替换源路径前缀
                        # 例如：/mnt/media → /volume2/media → /volume2/media/tv
                        result = target + relative_path
                    else:
                        # 未知类型，不转换
                        logger.warning(f"未知的转换类型: {conversion_type}")
                        continue

                    # ✅ P0-3修复: 验证结果路径有效性
                    if not self._is_valid_path(result):
                        logger.warning(f"生成的路径无效: {result}, 原路径: {original_path}")
                        return None

                    logger.debug(f"路径转换 [{conversion_type}]: {original_path} -> {result}")
                    return result

            except Exception as e:
                logger.error(f"路径转换异常: {e}, 规则: {rule}, 原路径: {original_path}")
                continue

        # 没有匹配的规则，返回原路径
        logger.debug(f"路径 {original_path} 没有匹配的转换规则")
        return None

    def _is_valid_path(self, path: str) -> bool:
        """
        验证路径是否有效

        Args:
            path: 待验证的路径

        Returns:
            路径是否有效
        """
        if not path or not isinstance(path, str):
            return False

        # 检查路径长度（防止超长路径）
        if len(path) > 4096:  # Linux最大路径长度
            logger.warning(f"路径过长: {len(path)} 字符")
            return False

        # 检查是否包含非法字符（根据系统）
        # Windows不允许: < > : " | ? *
        # Linux允许除null外的所有字符
        import platform
        if platform.system() == "Windows":
            illegal_chars = ['<', '>', ':', '"', '|', '?', '*']
            if any(char in path for char in illegal_chars):
                logger.warning(f"路径包含非法字符: {path}")
                return False

        return True

    def convert_batch(self, paths: List[str]) -> List[Optional[str]]:
        """
        批量转换路径

        Args:
            paths: 原始路径列表

        Returns:
            转换后的路径列表，未匹配的路径对应位置为None
        """
        return [self.convert(path) for path in paths]

    def get_rules(self) -> List[Dict[str, str]]:
        """获取所有规则"""
        return self.rules.copy()

    def is_enabled(self) -> bool:
        """
        检查是否启用了路径转换

        Returns:
            如果有规则则返回True，否则返回False
        """
        return len(self.rules) > 0


class UnifiedPathMappingService:
    """统一路径映射服务

    整合 PathMappingService 和 PathMappingConverter，提供统一的路径映射接口。

    设计理念:
    - path_mapping_rules (多行文本格式): 辅助功能，用于自动生成 path_mapping 的 external 路径
    - path_mapping (JSON格式): 主要配置，实际用于路径转换
    - 优先级: path_mapping > path_mapping_rules
    - 向后兼容: 支持仅使用 path_mapping_rules 的场景（但已废弃）

    配置优先级:
    1. path_mapping (JSON格式) - 必须配置
    2. path_mapping_rules (多行文本格式) - 可选，仅用于辅助生成

    使用场景:
    - 等级3删除功能: 必须配置 path_mapping
    - 文件操作服务: 自动检测配置格式
    - 种子备份服务: 统一接口
    """

    def __init__(
        self,
        path_mapping: Optional[str] = None,
        path_mapping_rules: Optional[str] = None,
        require_json_config: bool = False
    ):
        """
        初始化统一路径映射服务

        Args:
            path_mapping: JSON格式的路径映射配置（主要配置）
            path_mapping_rules: 多行文本格式的路径映射规则（辅助配置）
            require_json_config: 是否必须配置JSON格式（如等级3删除功能）

        Raises:
            ValueError: 当 require_json_config=True 且未配置 path_mapping 时
        """
        self.path_mapping_service: Optional[PathMappingService] = None
        self.path_mapping_converter: Optional[PathMappingConverter] = None
        self.config_type: Optional[str] = None  # 'json', 'rules', 或 'both'

        # 验证必需配置
        if require_json_config and not path_mapping:
            raise ValueError(
                "等级3删除功能必须配置 path_mapping（JSON格式）。"
                "请先在下载器设置中配置路径映射。"
            )

        # 优先使用 path_mapping（JSON格式）
        if path_mapping:
            try:
                self.path_mapping_service = PathMappingService(path_mapping)
                self.config_type = 'json'
                logger.info("使用 path_mapping（JSON格式）进行路径映射")
            except Exception as e:
                logger.error(f"加载 path_mapping 失败: {str(e)}")
                if require_json_config:
                    raise ValueError(f"path_mapping 配置无效: {str(e)}") from e

        # 回退到 path_mapping_rules（多行文本格式）
        elif path_mapping_rules:
            try:
                self.path_mapping_converter = PathMappingConverter(path_mapping_rules)
                if self.path_mapping_converter.is_enabled():
                    self.config_type = 'rules'
                    logger.warning(
                        "⚠️ 使用 path_mapping_rules（多行文本格式）进行路径映射。"
                        "建议配置 path_mapping（JSON格式）以获得更好的功能支持。"
                    )
                else:
                    logger.warning("path_mapping_rules 规则为空或无效")
                    self.path_mapping_converter = None
            except Exception as e:
                logger.error(f"加载 path_mapping_rules 失败: {str(e)}")

        # 记录配置状态
        if not self.is_enabled():
            logger.warning("未配置有效的路径映射，路径转换功能不可用")

    def internal_to_external(self, internal_path: str) -> str:
        """
        将内部路径转换为外部路径

        优先使用 PathMappingService，回退到 PathMappingConverter

        Args:
            internal_path: 下载器内部路径

        Returns:
            项目外部路径，未配置映射时返回原路径
        """
        if not internal_path:
            return internal_path

        # 优先使用 PathMappingService
        if self.path_mapping_service:
            return self.path_mapping_service.internal_to_external(internal_path)

        # 回退到 PathMappingConverter
        if self.path_mapping_converter:
            converted = self.path_mapping_converter.convert(internal_path)
            if converted:
                return converted

        # 未配置映射，返回原路径
        logger.debug(f"未配置路径映射，返回原路径: {internal_path}")
        return internal_path

    def external_to_internal(self, external_path: str) -> str:
        """
        将外部路径转换为内部路径

        仅 PathMappingService 支持反向转换

        Args:
            external_path: 项目外部路径

        Returns:
            下载器内部路径，未配置映射时返回原路径
        """
        if not external_path:
            return external_path

        # 仅 PathMappingService 支持反向转换
        if self.path_mapping_service:
            return self.path_mapping_service.external_to_internal(external_path)

        # PathMappingConverter 不支持反向转换
        if self.path_mapping_converter:
            logger.warning("PathMappingConverter 不支持反向转换，返回原路径")

        return external_path

    def is_enabled(self) -> bool:
        """
        检查是否启用了路径映射

        Returns:
            如果配置了 path_mapping 或 path_mapping_rules 则返回True
        """
        return (
            self.path_mapping_service is not None or
            (self.path_mapping_converter is not None and self.path_mapping_converter.is_enabled())
        )

    def get_config_type(self) -> Optional[str]:
        """
        获取当前配置类型

        Returns:
            'json', 'rules', 或 None
        """
        return self.config_type

    def get_mappings(self) -> List[Dict]:
        """
        获取所有映射配置

        Returns:
            映射配置列表，仅 PathMappingService 支持此功能
        """
        if self.path_mapping_service:
            return self.path_mapping_service.get_mappings()
        return []

    def get_rules(self) -> List[Dict[str, str]]:
        """
        获取所有转换规则

        Returns:
            转换规则列表，仅 PathMappingConverter 支持此功能
        """
        if self.path_mapping_converter:
            return self.path_mapping_converter.get_rules()
        return []

    def to_json(self) -> Optional[str]:
        """
        将配置导出为JSON字符串

        Returns:
            JSON格式的配置，仅 PathMappingService 支持此功能
        """
        if self.path_mapping_service:
            return self.path_mapping_service.to_json()
        return None
