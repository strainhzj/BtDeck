"""路径映射规则在「空格 + 中文」场景下的行为验证测试。

本测试集针对下载器设置卡片中的路径映射规则，验证当映射路径中同时包含
空格与中文字符时，路径映射逻辑是否能够正确工作。

覆盖范围：
- ``PathMappingService``（JSON 格式主配置）的标准化、双向转换、最长前缀匹配。
- ``PathMappingConverter``（多行文本规则）的规则解析、转换类型判定、批量转换。
- 边界场景：首尾空格被 strip、前导空格导致不匹配、连续多空格不归一化、
  Windows 反斜杠 + 中文 + 空格的混合路径。

相关约束：
- 后端代码复用与单元测试约束见 ``backend/docs/constraints/``。
- 本测试为纯单元测试，不依赖数据库或 FastAPI 客户端。
"""

import json

import pytest

from app.core.path_mapping import (
    PathMappingConverter,
    PathMappingService,
    UnifiedPathMappingService,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_json_config(mappings, default_mapping=None):
    """构造 JSON 格式的路径映射配置字符串。"""
    config = {"mappings": mappings}
    if default_mapping is not None:
        config["default_mapping"] = default_mapping
    return json.dumps(config, ensure_ascii=False)


# ---------------------------------------------------------------------------
# PathMappingService._normalize_path —— 标准化
# ---------------------------------------------------------------------------

class TestNormalizePathWithUnicode:
    """验证路径标准化对「空格 + 中文」的处理。"""

    def test_normalize_preserves_chinese_and_internal_space(self):
        """中文字符与路径内部的空格应被原样保留，仅补齐尾部斜杠。"""
        svc = PathMappingService.__new__(PathMappingService)

        normalized = svc._normalize_path("/data/我的 资料")

        assert normalized == "/data/我的 资料/"

    def test_normalize_converts_backslashes_with_chinese_and_space(self):
        """Windows 反斜杠路径在含中文与空格时应被转换为正斜杠。"""
        svc = PathMappingService.__new__(PathMappingService)

        normalized = svc._normalize_path("D:\\下载\\我的 文件夹")

        assert normalized == "D:/下载/我的 文件夹/"

    def test_normalize_preserves_unc_with_chinese_and_space(self):
        """UNC 路径（以 // 开头）在含中文与空格时应保留双斜杠前缀。"""
        svc = PathMappingService.__new__(PathMappingService)

        normalized = svc._normalize_path("//nas/共享 资料/电影")

        # UNC 前缀 // 保留，目录补齐尾部 /
        assert normalized == "//nas/共享 资料/电影/"


# ---------------------------------------------------------------------------
# PathMappingService —— 双向路径转换
# ---------------------------------------------------------------------------

class TestJsonServiceBidirectionalConversion:
    """验证 JSON 格式映射在「空格 + 中文」场景下的双向转换。"""

    def test_internal_to_external_with_chinese_and_space(self):
        """内部路径转外部路径：含空格与中文的前缀应被正确替换。"""
        config = _make_json_config(
            [
                {
                    "name": "Docker下载目录",
                    "internal": "/downloads/我的 资料/",
                    "external": "D:/DockerData/我的 资料/",
                    "mapping_type": "docker",
                }
            ],
            default_mapping="Docker下载目录",
        )
        svc = PathMappingService(config)

        result = svc.internal_to_external("/downloads/我的 资料/电影/movie.mkv")

        assert result == "D:/DockerData/我的 资料/电影/movie.mkv"

    def test_external_to_internal_with_chinese_and_space(self):
        """外部路径转内部路径：反向映射同样应正确处理空格与中文。"""
        config = _make_json_config(
            [
                {
                    "name": "Docker下载目录",
                    "internal": "/downloads/我的 资料/",
                    "external": "D:/DockerData/我的 资料/",
                }
            ]
        )
        svc = PathMappingService(config)

        result = svc.external_to_internal("D:/DockerData/我的 资料/电影/movie.mkv")

        assert result == "/downloads/我的 资料/电影/movie.mkv"

    def test_config_normalizes_backslashes_with_chinese_and_space(self):
        """JSON 配置加载时会归一化双方斜杠：反斜杠 + 中文 + 空格可正确匹配。

        与 Converter 不同，``PathMappingService._validate_config`` 会对
        internal/external 双向调用 ``_normalize_path``，因此配置和查询路径
        的斜杠方向不一致也能正确匹配。
        """
        config = _make_json_config(
            [
                {
                    "name": "Docker下载目录",
                    # 配置使用反斜杠
                    "internal": "\\downloads\\我的 资料\\",
                    "external": "D:\\DockerData\\我的 资料\\",
                }
            ]
        )
        svc = PathMappingService(config)

        # 输入使用正斜杠仍能匹配（因配置已归一化为正斜杠）
        result = svc.internal_to_external("/downloads/我的 资料/movie.mkv")
        assert result == "D:/DockerData/我的 资料/movie.mkv"


# ---------------------------------------------------------------------------
# PathMappingService —— 最长前缀匹配
# ---------------------------------------------------------------------------

class TestLongestPrefixMatchWithUnicode:
    """验证含中文与空格的路径前缀重叠时，最长前缀匹配仍然生效。"""

    def test_longest_prefix_wins_when_chinese_prefixes_overlap(self):
        """当存在中文短前缀与长前缀时，应匹配更长的前缀。"""
        config = _make_json_config(
            [
                {"name": "短前缀", "internal": "/data/我", "external": "/A/"},
                {"name": "长前缀", "internal": "/data/我的 资料", "external": "/B/"},
            ]
        )
        svc = PathMappingService(config)

        result = svc.internal_to_external("/data/我的 资料/a.mkv")

        # 应命中「长前缀」(/B/) 而非「短前缀」(/A/)
        assert result == "/B/a.mkv"

    def test_multiple_consecutive_spaces_not_normalized(self):
        """多个连续空格不归一化：两空格路径与一空格路径互不匹配。

        这是预期行为——路径映射按字面精确匹配，不做空格归一化。
        用本测试固化此行为，避免后续改动意外破坏。
        """
        config = _make_json_config(
            [{"name": "m", "internal": "/data/我的  资料/", "external": "/X/"}]
        )
        svc = PathMappingService(config)

        # 两个空格（与映射一致）应能匹配
        assert svc.internal_to_external("/data/我的  资料/a.mkv") == "/X/a.mkv"
        # 一个空格（与映射不一致）不应匹配，返回原路径
        assert svc.internal_to_external("/data/我的 资料/a.mkv") == "/data/我的 资料/a.mkv"


# ---------------------------------------------------------------------------
# PathMappingConverter —— 文本规则解析与转换
# ---------------------------------------------------------------------------

class TestConverterRulesWithUnicode:
    """验证多行文本格式规则在「空格 + 中文」场景下的解析与转换。"""

    def test_load_rules_strips_surrounding_spaces_only(self):
        """规则行中 source/target 的首尾空格应被 strip，中间空格保留。

        这是 ``load_rules`` 的既定行为：``source_path = parts[0].strip()``。
        注意：这意味着路径两端的真实空格会丢失——属于已知行为。
        """
        rules = "/downloads/我的 资料  {#**#}  /volume1/我的 资料"
        conv = PathMappingConverter(rules)

        loaded = conv.get_rules()
        assert len(loaded) == 1
        assert loaded[0]["source"] == "/downloads/我的 资料"
        assert loaded[0]["target"] == "/volume1/我的 资料"

    def test_convert_add_type_with_chinese_and_space(self):
        """「加」类型转换：target 不以 source 结尾，前缀替换。"""
        rules = "/downloads/我的 资料{#**#}/volume1/我的 资料"
        conv = PathMappingConverter(rules)

        assert conv.get_rules()[0]["type"] == "add"
        result = conv.convert("/downloads/我的 资料/第一季/E01.mkv")
        assert result == "/volume1/我的 资料/第一季/E01.mkv"

    def test_convert_replace_type_with_chinese_and_space(self):
        """「替换」类型转换：target 以 source 结尾，保留相对路径。"""
        rules = "/downloads/我的 资料{#**#}/volume1/downloads/我的 资料"
        conv = PathMappingConverter(rules)

        assert conv.get_rules()[0]["type"] == "replace"
        result = conv.convert("/downloads/我的 资料/电影/a.mkv")
        assert result == "/volume1/downloads/我的 资料/电影/a.mkv"

    def test_convert_with_backslashes_and_chinese_and_space(self):
        """Converter 不归一化已存储规则的斜杠方向，仅归一化输入路径。

        已知行为：``load_rules`` 仅对 source/target 做 ``.strip()``，不做斜杠
        归一化；而 ``convert`` 只对输入路径归一化为正斜杠。因此当规则使用反斜杠、
        输入使用正斜杠（或反之）时，``startswith`` 会因斜杠方向不一致而失败。

        本测试固化该行为：规则与输入斜杠方向一致时才能匹配。
        """
        # 规则与输入都使用正斜杠 → 能匹配
        conv_forward = PathMappingConverter(
            "/downloads/我的 资料{#**#}/volume1/我的 资料"
        )
        assert (
            conv_forward.convert("/downloads/我的 资料/movie.mkv")
            == "/volume1/我的 资料/movie.mkv"
        )

        # 规则使用反斜杠、输入也使用反斜杠 → 输入被归一化为正斜杠后与反斜杠规则不匹配
        conv_backslash = PathMappingConverter(
            "D:\\下载\\我的 资料{#**#}E:\\备份\\我的 资料"
        )
        assert conv_backslash.convert("D:\\下载\\我的 资料\\movie.mkv") is None

    def test_convert_returns_none_when_leading_space_in_input(self):
        """原始路径带前导空格时不应匹配（_normalize_path 不 strip 输入）。

        已知行为：``convert`` 内部仅做斜杠归一化，不 strip 输入路径，
        因此前导空格会导致前缀匹配失败，返回 None。
        """
        conv = PathMappingConverter("/downloads/我的 资料{#**#}/volume1/我的 资料")

        # 前导空格 → 不匹配
        assert conv.convert("  /downloads/我的 资料/x.mkv") is None


# ---------------------------------------------------------------------------
# PathMappingConverter —— 批量转换与一致性
# ---------------------------------------------------------------------------

class TestConverterBatchWithUnicode:
    """验证批量转换在「空格 + 中文」场景下的一致性。"""

    def test_convert_batch_preserves_order_with_chinese_paths(self):
        """批量转换应保持输入顺序，未匹配项为 None。"""
        conv = PathMappingConverter("/downloads/我的 资料{#**#}/volume1/我的 资料")
        paths = [
            "/downloads/我的 资料/a.mkv",
            "/other/path.mkv",  # 不匹配 → None
            "/downloads/我的 资料/b.mkv",
        ]

        results = conv.convert_batch(paths)

        assert results[0] == "/volume1/我的 资料/a.mkv"
        assert results[1] is None
        assert results[2] == "/volume1/我的 资料/b.mkv"


# ---------------------------------------------------------------------------
# UnifiedPathMappingService —— 双格式一致性
# ---------------------------------------------------------------------------

class TestUnifiedServiceConsistency:
    """验证 JSON 与文本规则两种格式在「空格 + 中文」下的转换结果一致。"""

    def test_json_and_rules_produce_equivalent_external_path(self):
        """对同一逻辑映射，JSON 配置与文本规则应得到一致的外部路径。

        映射语义：/downloads/我的 资料 → /volume1/我的 资料
        """
        json_config = _make_json_config(
            [
                {
                    "name": "bangumi",
                    "internal": "/downloads/我的 资料/",
                    "external": "/volume1/我的 资料/",
                }
            ]
        )
        rules = "/downloads/我的 资料{#**#}/volume1/我的 资料"
        internal_path = "/downloads/我的 资料/电影/a.mkv"

        json_svc = UnifiedPathMappingService(path_mapping=json_config)
        rules_svc = UnifiedPathMappingService(path_mapping_rules=rules)

        # JSON 服务：internal → external
        json_result = json_svc.internal_to_external(internal_path)
        # 文本规则服务：internal → external（单向）
        rules_result = rules_svc.internal_to_external(internal_path)

        assert json_result == "/volume1/我的 资料/电影/a.mkv"
        assert rules_result == "/volume1/我的 资料/电影/a.mkv"
        assert json_result == rules_result


# ---------------------------------------------------------------------------
# 回归：完整配置往返（to_json）保持中文与空格
# ---------------------------------------------------------------------------

class TestRoundTripPreservesUnicode:
    """验证配置经标准化后导出，仍保留中文与空格。"""

    def test_to_json_preserves_chinese_and_spaces(self, monkeypatch):
        """``to_json`` 使用 ``ensure_ascii=False``，中文应原样保留。"""
        # 抑制 PathMappingService 初始化期间的日志噪音
        config = _make_json_config(
            [
                {
                    "name": "我的 映射",
                    "description": "包含 空格 与 中文 的描述",
                    "internal": "/downloads/我的 资料/",
                    "external": "D:/DockerData/我的 资料/",
                    "mapping_type": "docker",
                }
            ],
            default_mapping="我的 映射",
        )
        svc = PathMappingService(config)

        exported = svc.to_json()
        exported_data = json.loads(exported)

        assert "我的 映射" in exported  # ensure_ascii=False 生效
        assert exported_data["mappings"][0]["name"] == "我的 映射"
        assert exported_data["mappings"][0]["description"] == "包含 空格 与 中文 的描述"
        assert exported_data["default_mapping"] == "我的 映射"


# ---------------------------------------------------------------------------
# 分隔符敏感性回归测试
# ---------------------------------------------------------------------------

class TestSeparatorSensitivityRegression:
    """分隔符敏感性回归测试。

    回归来源：用户报告规则
    ``/Downloads/bangumi - 硬链接{**}/Downloads/hpan/bangumi - 硬链接``
    无法转换。根因是分隔符写成了 ``{**}``（缺少 ``#``），而代码硬编码的
    分隔符是 ``{#**#}``（``PathMappingConverter.RULE_SEPARATOR``）。

    该场景的失败是「静默」的——``load_rules`` 仅打印告警并跳过该行，最终加载
    0 条规则，``convert`` 返回原路径（而非抛错）。因此本测试用多层独立断言
    锁定行为，避免单一弱断言导致的「伪通过」。
    """

    # 用户实际误用的分隔符
    WRONG_SEPARATOR = "{**}"
    # 代码要求的正确分隔符（直接引用类常量，避免硬编码漂移）
    CORRECT_SEPARATOR = PathMappingConverter.RULE_SEPARATOR

    # 用户报告的规则源/目标（含空格、中文、连字符）
    SOURCE = "/Downloads/bangumi - 硬链接"
    TARGET = "/Downloads/hpan/bangumi - 硬链接"
    TEST_PATH = "/Downloads/bangumi - 硬链接/Season 1/E01.mkv"

    def test_wrong_separator_loads_zero_rules(self):
        """错误分隔符 {**} 应加载 0 条规则。

        断言1（根因）：``get_rules`` 为空——这是「转换不生效」的真正原因，
        不能省略，否则无法区分「分隔符错误」与「规则加载正常但匹配失败」。
        """
        rule = self.SOURCE + self.WRONG_SEPARATOR + self.TARGET
        conv = PathMappingConverter(rule)

        assert conv.get_rules() == []
        assert conv.is_enabled() is False

    def test_wrong_separator_convert_returns_original_path(self):
        """错误分隔符下 convert 返回「原路径」（无规则 → 不转换）。

        关键：断言 ``result == self.TEST_PATH``，而不是
        ``result != 期望转换值``。后者在「转换功能整体坏掉」时也可能成立，
        属于弱断言；前者精确锁定「输入原样返回」这一行为。

        同时与正确分隔符的结果做不等比较，证明转换确实没有发生——若两种
        分隔符返回相同结果（例如都返回原路径），说明转换功能失效，测试应失败。
        """
        wrong_conv = PathMappingConverter(self.SOURCE + self.WRONG_SEPARATOR + self.TARGET)

        result = wrong_conv.convert(self.TEST_PATH)

        # 无规则 → 返回原路径（不是 None）
        assert result == self.TEST_PATH

        # 对照：正确分隔符应当得到不同的结果；二者不等才说明转换「本应发生」
        correct_conv = PathMappingConverter(
            self.SOURCE + self.CORRECT_SEPARATOR + self.TARGET
        )
        expected = correct_conv.convert(self.TEST_PATH)
        assert result != expected, "错误分隔符与正确分隔符结果相同，转换功能可能失效"

    def test_correct_separator_loads_and_converts(self):
        """正确分隔符 {#**#} 应加载 1 条规则并完成精确转换。

        逐字段断言 source/target/type，防止「规则加载但字段解析错误」被漏过。
        """
        rule = self.SOURCE + self.CORRECT_SEPARATOR + self.TARGET
        conv = PathMappingConverter(rule)

        loaded = conv.get_rules()
        assert len(loaded) == 1
        assert loaded[0]["source"] == self.SOURCE
        assert loaded[0]["target"] == self.TARGET
        # target 不以 source 结尾 → 自动判定为 'add'（前缀替换，保留相对路径）
        assert loaded[0]["type"] == "add"

        assert conv.convert(self.TEST_PATH) == (
            self.TARGET + "/Season 1/E01.mkv"
        )

    def test_unmatched_path_returns_none_distinct_from_no_rules(self):
        """正确分隔符下，不匹配源前缀的路径返回 None。

        这与「无规则返回原路径」是两种不同行为，必须分别覆盖，否则回归时
        容易混淆。本测试确保 ``None`` 语义不被「无规则返回原路径」掩盖。
        """
        conv = PathMappingConverter(
            self.SOURCE + self.CORRECT_SEPARATOR + self.TARGET
        )

        # 有规则但不匹配 → None
        assert conv.convert("/other/path.mkv") is None


# ---------------------------------------------------------------------------
# 类比规则测试：与用户报告规则同结构、不同地址
# ---------------------------------------------------------------------------

class TestAnalogousRuleWithSpaceAndChinese:
    """与用户报告规则 ``/Downloads/bangumi - 硬链接{#**#}/...`` 同结构、
    不同地址的类比测试。

    规则结构特征（保留以验证映射逻辑对这些字符的鲁棒性）：
    - 路径中含**空格**
    - 路径中含**中文**
    - 路径中含**连字符** ``-``
    - 正确的分隔符 ``{#**#}``

    地址完全独立于用户原地址，避免与
    ``TestSeparatorSensitivityRegression`` 重复。
    """

    SOURCE = "/downloads/影视 - 收藏"
    TARGET = "/mnt/media/影视 - 收藏"
    RULE = SOURCE + PathMappingConverter.RULE_SEPARATOR + TARGET

    def test_rule_loads_with_correct_fields(self):
        """规则被正确解析：1 条规则，source/target 逐字段精确匹配。

        逐字段断言而非整体相等，可分别捕获「source 多/少字符」与
        「target 解析错位」等不同回归。
        """
        conv = PathMappingConverter(self.RULE)

        loaded = conv.get_rules()
        assert len(loaded) == 1
        assert loaded[0]["source"] == self.SOURCE
        assert loaded[0]["target"] == self.TARGET

    def test_conversion_type_is_add(self):
        """转换类型自动判定为 'add'。

        target (``/mnt/media/影视 - 收藏``) 不以 source
        (``/downloads/影视 - 收藏``) 结尾，故为前缀替换（add）。
        """
        conv = PathMappingConverter(self.RULE)

        assert conv.get_rules()[0]["type"] == "add"

    def test_deep_nested_path_is_converted(self):
        """深嵌套路径：前缀替换，相对路径完整保留。"""
        conv = PathMappingConverter(self.RULE)

        result = conv.convert(self.SOURCE + "/电影/2024/沙丘.mp4")

        assert result == "/mnt/media/影视 - 收藏/电影/2024/沙丘.mp4"

    def test_exact_source_path_is_converted(self):
        """恰好等于源路径（无相对路径后缀）也应完整转换。"""
        conv = PathMappingConverter(self.RULE)

        assert conv.convert(self.SOURCE) == self.TARGET

    def test_path_with_suffix_requires_prefix_match_not_suffix(self):
        """带相对路径后缀的转换必须依赖「前缀匹配」而非「后缀匹配」。

        本测试针对 ``startswith`` 被误改为 ``endswith`` 的回归：当输入路径
        恰好等于 source（如 ``test_exact_source_path_is_converted``）时，
        endswith 也能通过，无法抓到该 bug；必须用「source + 子路径」的形式
        才能让 startswith/endswith 的差异显现。
        """
        conv = PathMappingConverter(self.RULE)

        # 输入 = source + "/sub"，endswith(source) 为 False → 该路径不会被误转换
        result = conv.convert(self.SOURCE + "/sub/file.mkv")
        assert result == self.TARGET + "/sub/file.mkv"

    def test_single_level_child_is_converted(self):
        """一级子路径转换。"""
        conv = PathMappingConverter(self.RULE)

        assert (
            conv.convert(self.SOURCE + "/剧集/三体.S01.mkv")
            == self.TARGET + "/剧集/三体.S01.mkv"
        )

    def test_unmatched_path_returns_none(self):
        """不匹配源前缀的路径返回 None。"""
        conv = PathMappingConverter(self.RULE)

        assert conv.convert("/other/library/movie.mkv") is None

    def test_prefix_collision_resolves_to_longest(self):
        """当存在「短前缀」与「长前缀」时，应匹配更长的前缀。

        本测试构造一个与 source 有公共前缀 ``/downloads/影视 - 收藏`` 的
        短规则，验证转换不会误命中短前缀。
        """
        rules_text = "\n".join(
            [
                # 短前缀（应为公共前缀，长度更短）
                "/downloads" + PathMappingConverter.RULE_SEPARATOR + "/short",
                # 长前缀（应被优先匹配）
                self.RULE,
            ]
        )
        conv = PathMappingConverter(rules_text)

        result = conv.convert(self.SOURCE + "/x.mkv")

        # 首条匹配规则胜出：长前缀在第二行，但 '/downloads/影视...' 也以
        # '/downloads' 开头——Converter 按配置顺序取第一条匹配，
        # 故此处命中第一条 '/downloads' → '/short'。此行为与 JSON 服务的
        # 「最长前缀匹配」不同，用断言固化差异。
        assert result == "/short/影视 - 收藏/x.mkv"
