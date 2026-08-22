"""UnifiedPathMappingService 的「JSON 全空 external 回退 rules」行为验证。

背景(生产事故 2026-08-09):
某 Transmission 下载器的 ``path_mapping``（JSON）存了 221 条「系统自动发现」
映射，但 ``external`` 字段全部为空字符串。原 ``__init__`` 逻辑为「JSON 非空
就用 JSON，且与 rules 互斥」，导致正确的 ``path_mapping_rules`` 被完全屏蔽。
孤儿扫描的 ``resolve_external_path`` 过滤空 external 后 sources 为空 → 全部
返回 None → 整下载器降级 → 12 万文件被误判为孤儿。

本测试集锁定修复行为：
- JSON 全空 external 时回退到 path_mapping_rules。
- JSON 有效时仍加载 converter，使 get_rules() 不再返回空。
- resolve_external_path 端到端验证（模拟生产配置）。

相关约束：纯单元测试，不依赖数据库或 FastAPI 客户端。
"""

import json

from app.core.path_mapping import UnifiedPathMappingService


def _json_with_empty_external() -> str:
    """模拟生产事故：JSON 含多条映射，但 external 全为空字符串。"""
    return json.dumps(
        {
            "mappings": [
                {
                    "name": "tr-自动发现-路径001",
                    "internal": "/Downloads/bangumi/弱势角色友崎君/",
                    "external": "",
                    "mapping_type": "local",
                },
                {
                    "name": "tr-自动发现-路径002",
                    "internal": "/Downloads/bangumi/来自新世界/",
                    "external": "",
                    "mapping_type": "local",
                },
            ]
        },
        ensure_ascii=False,
    )


def _valid_rules() -> str:
    """模拟生产事故中正确的 path_mapping_rules（被 JSON 屏蔽的那份）。"""
    return "/Downloads/bangumi{#**#}/Downloads/hpan/bangumi\n" "/Downloads/ipan{#**#}/Downloads/ipan\n"


# ---------------------------------------------------------------------------
# 1. JSON 全空 external 回退 rules
# ---------------------------------------------------------------------------


def test_json_all_empty_external_falls_back_to_rules():
    """JSON 全空 external + rules 有效 → internal_to_external 走 rules。"""
    svc = UnifiedPathMappingService(
        path_mapping=_json_with_empty_external(),
        path_mapping_rules=_valid_rules(),
    )
    # rules 生效：/Downloads/bangumi → /Downloads/hpan/bangumi
    # 注意 PathMappingConverter 不补尾斜杠（与 PathMappingService 的 _normalize_path 不同）
    assert svc.internal_to_external("/Downloads/bangumi/某番剧") == "/Downloads/hpan/bangumi/某番剧"


def test_json_all_empty_external_config_type_is_rules():
    """JSON 全空 external 时 config_type 应为 'rules'（以 rules 为主）。"""
    svc = UnifiedPathMappingService(
        path_mapping=_json_with_empty_external(),
        path_mapping_rules=_valid_rules(),
    )
    assert svc.config_type == "rules"


def test_json_all_empty_external_no_rules_returns_original():
    """JSON 全空 external 且无 rules → 回退目标缺失，返回原路径（不抛异常）。"""
    svc = UnifiedPathMappingService(
        path_mapping=_json_with_empty_external(),
        path_mapping_rules=None,
    )
    # 无任何有效映射：返回原路径（_normalize_path 补尾斜杠）
    assert svc.internal_to_external("/Downloads/bangumi/某番剧") == "/Downloads/bangumi/某番剧/"


# ---------------------------------------------------------------------------
# 2. JSON 有效时不回退，但仍持有 converter
# ---------------------------------------------------------------------------


def _valid_json() -> str:
    """JSON 含至少一条有效映射（internal+external 都非空）。"""
    return json.dumps(
        {
            "mappings": [
                {
                    "name": "手动配置",
                    "internal": "/Downloads/bangumi/",
                    "external": "/Downloads/hpan/bangumi/",
                    "mapping_type": "local",
                }
            ]
        },
        ensure_ascii=False,
    )


def test_valid_json_does_not_fall_back_to_rules():
    """JSON 有效 → 用 JSON 转换，不被 rules 覆盖。"""
    # JSON 映射到 hpan，rules 映射到 ipan，二者不同以区分
    rules = "/Downloads/bangumi{#**#}/Downloads/ipan/bangumi\n"
    svc = UnifiedPathMappingService(path_mapping=_valid_json(), path_mapping_rules=rules)
    # JSON 优先：返回 hpan（JSON 的 external），而非 ipan（rules）
    assert svc.internal_to_external("/Downloads/bangumi/某番剧") == "/Downloads/hpan/bangumi/某番剧/"


def test_valid_json_still_exposes_rules_via_get_rules():
    """JSON 有效 + rules 存在 → get_rules() 返回 rules（不再是空）。

    这是孤儿扫描 resolve_external_path 的 rules 来源修复点：
    原 JSON 模式下 converter 为 None，get_rules() 恒返回 []。
    """
    svc = UnifiedPathMappingService(path_mapping=_valid_json(), path_mapping_rules=_valid_rules())
    rules = svc.get_rules()
    assert rules, "JSON 有效时 get_rules() 应返回 rules 列表，不应为空"
    assert svc.config_type == "both"


def test_valid_json_without_rules_get_rules_empty():
    """JSON 有效但无 rules → get_rules() 返回空（converter 未构造或无规则）。"""
    svc = UnifiedPathMappingService(path_mapping=_valid_json(), path_mapping_rules=None)
    assert svc.get_rules() == []


# ---------------------------------------------------------------------------
# 3. JSON 格式错误回退 rules（既有行为保护）
# ---------------------------------------------------------------------------


def test_invalid_json_falls_back_to_rules():
    """JSON 格式错误 → 回退 rules（不因 require_json_config=False 而崩溃）。"""
    svc = UnifiedPathMappingService(
        path_mapping="{not valid json",
        path_mapping_rules=_valid_rules(),
    )
    assert svc.internal_to_external("/Downloads/bangumi/某番剧") == "/Downloads/hpan/bangumi/某番剧"


# ---------------------------------------------------------------------------
# 4. resolve_external_path 端到端（模拟生产事故配置）
# ---------------------------------------------------------------------------


def test_resolve_external_path_with_production_like_config():
    """模拟生产事故：JSON 全空 external + rules 正确 → resolve 不再返回 None。

    用一个轻量 stub 复现 BtDownloaders.path_mapping_service 的契约
    （该 property 每次 new 一个 UnifiedPathMappingService）。
    """

    class _StubConfig:
        """复现 BtDownloaders 的 path_mapping_service 契约。"""

        def __init__(self, json_cfg: str, rules: str) -> None:
            self._json = json_cfg
            self._rules = rules

        @property
        def path_mapping_service(self):
            return UnifiedPathMappingService(path_mapping=self._json, path_mapping_rules=self._rules)

    from app.services.orphan_manifest import resolve_external_path

    config = _StubConfig(_json_with_empty_external(), _valid_rules())
    # 修复前：返回 None；修复后：返回正确的 external
    result = resolve_external_path("/Downloads/bangumi/弱势角色友崎君", config)
    assert result == "/Downloads/hpan/bangumi/弱势角色友崎君", f"修复后应返回正确 external，实际: {result!r}"
