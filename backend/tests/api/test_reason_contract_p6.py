# -*- coding: utf-8 -*-
"""双语 P6-3 错误契约测试（Tracker 关键词池 / 汇报配置 / 判断测试工具）。

锁定的不变量（对齐 P2/P4/P5 契约批；PLANS/desktop-bilingual.md §3.3）：
- CommonResponse 信封四字段不变；仅 data 新增 reasonCode 字段（B03 兼容冻结）；
- reasonCode 取值属对外契约，本文件逐路径钉死（前端 errors.byCode 依赖）；
- 动态拼接 msg（str(e)/关键词值/池类型/id/合法值清单）只进日志，msg 固定（防泄露 + 可翻译）；
- tracker_reannounce 的 not-found 判定改用 result.error_code 结构化枚举，
  禁止回流「"不存在" in result.message」中文子串匹配（源码级断言钉死）；
- 成功路径（含含计数的汇总 msg）不在契约范围，不做断言（前端自建本地化文案）。
"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import get_current_user, require_authenticated_user
from app.core import reannounce_config_operations as ops
from app.core.database_result import DatabaseResult
from app.database import Base, get_async_db, get_db
from app.torrents.models import TrackerKeywordConfig, TrackerReannounceConfig

URL_KW = "/api/v1/tracker-keywords"
URL_POOL = URL_KW + "/pool"
URL_MOVE = URL_KW + "/move"
URL_BATCH_MOVE = URL_KW + "/batch-move"
URL_PREVIEW = URL_KW + "/pool/prefix-match-preview"
URL_REANNOUNCE = "/api/v1/tracker-reannounce"
URL_MATCH = "/api/v1/tracker-test/match"

ENDPOINT_FILES = [
    "app/api/endpoints/tracker_keywords.py",
    "app/api/endpoints/tracker_keywords_pools.py",
    "app/api/endpoints/tracker_reannounce.py",
    "app/api/endpoints/tracker_test.py",
]

# 本批登记的全部 reasonCode（前端 errors.byCode camelCase 键与之逐一对齐）
EXPECTED_REASON_CODES = {
    "KEYWORD_TOO_LONG",
    "LANGUAGE_CODE_TOO_LONG",
    "CATEGORY_TOO_LONG",
    "DESCRIPTION_TOO_LONG",
    "KEYWORD_ALREADY_EXISTS",
    "KEYWORD_NOT_FOUND",
    "KEYWORD_LIST_REQUIRED",
    "KEYWORD_DUPLICATE_IN_BATCH",
    "KEYWORD_INVALID_POOL_TYPE",
    "KEYWORD_PARAMS_REQUIRED",
    "KEYWORD_IDS_MUST_BE_LIST",
    "KEYWORD_PREFIX_REQUIRED",
    "REANNOUNCE_CONFIG_NOT_FOUND",
    "REANNOUNCE_CONFIG_INVALID",
    "REANNOUNCE_NO_FIELDS_TO_UPDATE",
    "REANNOUNCE_BATCH_FORMAT_INVALID",
    "REANNOUNCE_BATCH_EMPTY",
    "TEST_MATCH_FAILED",
    # 复用既有键（P4 已登记）
    "DB_OPERATION_FAILED",
}


def _reason_code(body: dict) -> str:
    data = body["data"]
    assert isinstance(data, dict), f"data 应为携带 reasonCode 的 dict，实际: {data!r}"
    assert set(data.keys()) == {"reasonCode"}, f"data 仅应含 reasonCode，实际: {data!r}"
    return data["reasonCode"]


@pytest.fixture()
def sync_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[TrackerKeywordConfig.__table__, TrackerReannounceConfig.__table__])
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(sync_engine):
    Session = sessionmaker(bind=sync_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    """内存库 + 认证豁免的 TestClient（同步 SessionLocal 一并指到内存库）。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")

    with patch("app.database.SessionLocal", return_value=db_session):
        yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


def _seed_keyword(db, keyword="success-", keyword_type="success", keyword_id="kw-1"):
    row = TrackerKeywordConfig(
        keyword_id=keyword_id,
        keyword=keyword,
        keyword_type=keyword_type,
        language=None,
        priority=100,
        enabled=True,
        category=None,
        description=None,
        create_by="tester",
        update_by="tester",
        dr=0,
    )
    db.add(row)
    db.commit()
    return row


# ====================================================================
# 一、关键词 CRUD（tracker_keywords.py）
# ====================================================================


class TestKeywordCrudContract:
    def test_length_guard_helper_reason_codes(self):
        """端点内长度检查属纵深防御（pydantic max_length 已先行拦截，API 层不可达），
        直接单测 helper 的 reasonCode 产物。"""
        from app.api.endpoints.tracker_keywords import _keyword_error

        cases = {
            "KEYWORD_TOO_LONG": "关键词长度超过限制(最大200字符)",
            "LANGUAGE_CODE_TOO_LONG": "语言代码长度超过限制(最大10字符)",
            "CATEGORY_TOO_LONG": "分类长度超过限制(最大50字符)",
            "DESCRIPTION_TOO_LONG": "描述长度超过限制(最大200字符)",
        }
        for reason, msg in cases.items():
            body = _keyword_error(reason, msg).model_dump()
            assert body["code"] == "400"
            assert body["data"] == {"reasonCode": reason}
            assert body["msg"] == msg

    def test_already_exists_fixed_msg_without_pool_name(self, client, db_session):
        _seed_keyword(db_session, keyword="dup-kw")
        resp = client.post(URL_KW, json={"keyword": "dup-kw", "keyword_type": "failed"})
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "KEYWORD_ALREADY_EXISTS"
        # 动态池类型/关键词值不得回流 msg（诊断只进日志）
        assert "success" not in body["msg"]
        assert "dup-kw" not in body["msg"]
        assert body["msg"] == "该关键词已存在于对应池中"

    def test_not_found_404_with_reason_code(self, client):
        resp = client.delete(URL_KW + "/missing-id")
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "KEYWORD_NOT_FOUND"

    def test_batch_empty_list_reason_code(self, client):
        resp = client.post(URL_KW + "/batch", json={"keywords": []})
        body = resp.json()
        assert _reason_code(body) == "KEYWORD_LIST_REQUIRED"

    def test_batch_duplicate_reason_code(self, client):
        payload = {
            "keywords": [{"keyword": "a", "keyword_type": "success"}, {"keyword": "a", "keyword_type": "failed"}]
        }
        resp = client.post(URL_KW + "/batch", json=payload)
        body = resp.json()
        assert _reason_code(body) == "KEYWORD_DUPLICATE_IN_BATCH"

    def test_db_failure_fixed_msg_with_reason_code(self, client):
        with patch("app.api.endpoints.tracker_keywords.uuid.uuid4", side_effect=RuntimeError("boom-secret")):
            resp = client.post(URL_KW, json={"keyword": "new-kw", "keyword_type": "success"})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "DB_OPERATION_FAILED"
        # 动态 str(e) 不得进 msg
        assert "boom-secret" not in body["msg"]
        assert body["msg"] == "数据库操作失败"


# ====================================================================
# 二、关键词池（tracker_keywords_pools.py）
# ====================================================================


class TestKeywordPoolContract:
    def test_invalid_pool_type_fixed_msg(self, client):
        resp = client.get(URL_POOL, params={"pool_type": "bad-type"})
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "KEYWORD_INVALID_POOL_TYPE"
        # 合法值清单不得回流 msg
        assert "candidate" not in body["msg"]

    def test_move_missing_params_reason_code(self, client):
        resp = client.post(URL_MOVE, json={})
        body = resp.json()
        assert _reason_code(body) == "KEYWORD_PARAMS_REQUIRED"

    def test_batch_move_ids_not_list_reason_code(self, client):
        resp = client.post(URL_BATCH_MOVE, json={"keyword_ids": "not-a-list", "target_pool": "success"})
        body = resp.json()
        assert _reason_code(body) == "KEYWORD_IDS_MUST_BE_LIST"

    def test_move_missing_keyword_404(self, client):
        resp = client.post(URL_MOVE, json={"keyword_id": "missing", "target_pool": "success"})
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "KEYWORD_NOT_FOUND"

    def test_batch_move_no_valid_keywords_404(self, client):
        resp = client.post(URL_BATCH_MOVE, json={"keyword_ids": ["missing"], "target_pool": "success"})
        body = resp.json()
        assert _reason_code(body) == "KEYWORD_NOT_FOUND"

    def test_prefix_required_reason_code(self, client):
        resp = client.post(URL_PREVIEW, json={"pool_type": "success", "prefix": "  "})
        body = resp.json()
        assert _reason_code(body) == "KEYWORD_PREFIX_REQUIRED"

    def test_preview_success_shape_stable(self, client, db_session):
        """成功路径 data 形状不回归（B03）：count/sample_keywords/keyword_ids。"""
        row = _seed_keyword(db_session, keyword="success-abc", keyword_id="kw-p1")
        resp = client.post(URL_PREVIEW, json={"pool_type": "success", "prefix": "success"})
        body = resp.json()
        assert body["code"] == "200"
        assert body["data"]["count"] == 1
        assert body["data"]["keyword_ids"] == [row.keyword_id]
        assert body["data"]["sample_keywords"] == ["success-abc"]

    def test_search_all_success_shape_stable(self, client, db_session):
        """search-all 成功路径 data 形状（list/total/page/pageSize）不回归。"""
        _seed_keyword(db_session, keyword="success-xyz", keyword_id="kw-s1")
        resp = client.get(URL_POOL + "/search-all", params={"keyword": "xyz"})
        body = resp.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 1
        assert body["data"]["list"][0]["pool_type"] == "success"


# ====================================================================
# 三、汇报配置（tracker_reannounce.py）
# ====================================================================


class TestReannounceContract:
    def test_update_not_found_structural_404(self, client):
        """not-found 判定走 error_code 结构化枚举（原「不存在」中文子串匹配禁回流）。"""
        resp = client.put(URL_REANNOUNCE + "/configs/missing-id", json={"interval_minutes": 60})
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "REANNOUNCE_CONFIG_NOT_FOUND"

    def test_create_validation_reason_code(self, client):
        resp = client.post(URL_REANNOUNCE + "/configs", json={"domain_pattern": ""})
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "REANNOUNCE_CONFIG_INVALID"
        # ops 层动态诊断（如「domain_pattern 不能为空」）不得透传 msg
        assert "domain_pattern" not in body["msg"]

    def test_no_fields_reason_code(self, client):
        resp = client.put(URL_REANNOUNCE + "/configs/some-id", json={})
        body = resp.json()
        assert _reason_code(body) == "REANNOUNCE_NO_FIELDS_TO_UPDATE"

    def test_batch_format_invalid_reason_code(self, client):
        resp = client.put(URL_REANNOUNCE + "/configs/batch", json={"bad": 1})
        body = resp.json()
        assert _reason_code(body) == "REANNOUNCE_BATCH_FORMAT_INVALID"

    def test_batch_empty_reason_code(self, client):
        resp = client.put(URL_REANNOUNCE + "/configs/batch", json={"items": []})
        body = resp.json()
        assert _reason_code(body) == "REANNOUNCE_BATCH_EMPTY"

    def test_list_db_failure_fixed_msg_with_reason_code(self, client):
        with patch.object(
            ops, "get_configs", return_value=DatabaseResult.database_error_result(message="查询失败: boom-secret")
        ):
            resp = client.get(URL_REANNOUNCE + "/configs")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "DB_OPERATION_FAILED"
        assert "boom-secret" not in body["msg"]

    def test_batch_partial_success_shape_stable(self, client, db_session):
        """批量部分成功路径 data 形状不回归（success_count/failed_count/results）。"""
        from datetime import datetime

        row = TrackerReannounceConfig(
            domain_pattern="%.tracker.com",
            domain_display_name="demo",
            interval_minutes=30,
            enabled=True,
            create_time=datetime.now(),
            update_time=datetime.now(),
            dr=0,
        )
        db_session.add(row)
        db_session.commit()

        resp = client.put(
            URL_REANNOUNCE + "/configs/batch",
            json={"items": [{"config_id": row.id_, "interval_minutes": 45}]},
        )
        body = resp.json()
        assert body["code"] == "200"
        assert body["data"]["success_count"] == 1
        assert body["data"]["failed_count"] == 0
        assert isinstance(body["data"]["results"], list)


# ====================================================================
# 四、判断测试工具（tracker_test.py）
# ====================================================================


class TestMatchContract:
    def test_match_failure_fixed_msg_with_reason_code(self, client):
        with patch(
            "app.api.endpoints.tracker_test.TrackerJudgmentEngine.judge_status",
            side_effect=RuntimeError("boom-secret"),
        ):
            resp = client.post(URL_MATCH, json={"msg": "download successful"})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "TEST_MATCH_FAILED"
        assert "boom-secret" not in body["msg"]

    def test_match_success_shape_stable(self, client, db_session):
        """成功路径 data 形状（驼峰字段）不回归。"""
        resp = client.post(URL_MATCH, json={"msg": "nothing matches here"})
        body = resp.json()
        assert body["code"] == "200"
        assert body["data"]["matchType"] == "none"
        assert "matchedKeywords" in body["data"]
        assert "finalStatus" in body["data"]


# ====================================================================
# 五、源码级契约：动态拼接禁回流 + reasonCode 清单无遗漏
# ====================================================================


class TestSourceContract:
    def test_no_dynamic_exception_detail_in_msg(self):
        """4 端点文件禁止 msg/detail 携带动态 str(e)（诊断只进日志）。"""
        root = Path(__file__).resolve().parents[2]
        for rel in ENDPOINT_FILES:
            text = (root / rel).read_text(encoding="utf-8")
            assert 'detail=f"' not in text, f'{rel} 存在 detail=f" 动态拼接'
            # msg=f 仅允许成功路径计数汇总；失败分支动态 msg 一律禁止
            for match in re.finditer(r'msg=f"[^"]*\{str\(e\)\}', text):
                raise AssertionError(f"{rel} 存在动态 str(e) 进 msg: {match.group(0)}")

    def test_no_chinese_substring_status_matching_in_reannounce(self):
        """tracker_reannounce 禁止回流「"不存在" in result.message」中文子串判定。"""
        root = Path(__file__).resolve().parents[2]
        text = (root / "app/api/endpoints/tracker_reannounce.py").read_text(encoding="utf-8")
        assert "in result.message" not in text, "not-found 判定必须走 result.error_code 结构化枚举"

    def test_reason_code_inventory_complete(self):
        """端点源码中出现的 reasonCode 全部在本批登记清单内（防拼写漂移）。"""
        root = Path(__file__).resolve().parents[2]
        used = set()
        for rel in ENDPOINT_FILES:
            text = (root / rel).read_text(encoding="utf-8")
            used.update(re.findall(r'"reasonCode":\s*"([A-Z_]+)"', text))
            used.update(re.findall(r'_keyword_error\(\n?\s*"([A-Z_]+)"', text))
            used.update(re.findall(r'_reannounce_error\(\n?\s*"([A-Z_]+)"', text))
        # _ops_failure_reason 的映射产物单独收集
        reann = (root / "app/api/endpoints/tracker_reannounce.py").read_text(encoding="utf-8")
        used.update(re.findall(r'return "([A-Z_]+)", "', reann))
        unexpected = used - EXPECTED_REASON_CODES
        assert not unexpected, f"存在未登记的 reasonCode: {sorted(unexpected)}"
