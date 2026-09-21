# -*- coding: utf-8 -*-
"""双语 P6-4b 错误契约测试（审计日志 + 孤儿文件域：audit_logs / orphan_files 全端点）。

锁定的不变量（对齐 P2/P4/P5/P6-3/P6-4a 契约批）：
- CommonResponse 信封四字段不变；仅 data 新增 reasonCode 字段（B03 兼容冻结）；
- reasonCode 取值属对外契约，本文件逐路径钉死（前端 errors.byCode AUDIT_LOG_* / ORPHAN_* 依赖）；
- 动态拼接 msg（str(e)/scan_id/文件名/合法值清单）只进日志，msg 固定（防泄露 + 可翻译）；
- 归档业务失败（service message）与 hardlink 副本删除 rejected 双形态保持 200/原 msg 透传，
  reasonCode 以 data 追加（E14 同款语义）；
- download-export 是唯一 HTTPException 端点（404/500 真状态码），动态诊断不进 detail。
"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.api import api_router
from app.auth.dependencies import get_current_user, require_authenticated_user
from app.database import get_async_db

AUDIT_URL = "/api/v1/audit-logs"
ORPHAN_URL = "/api/v1/orphan-files"

AUDIT_FILE = "app/api/endpoints/audit_logs.py"
ORPHAN_FILE = "app/api/endpoints/orphan_files.py"

EXPECTED_AUDIT_CODES = {
    "AUDIT_LOG_PARAM_INVALID",
    "AUDIT_LOG_QUERY_FAILED",
    "AUDIT_LOG_STATS_FAILED",
    "AUDIT_LOG_ARCHIVE_FAILED",
    "AUDIT_LOG_EXPORT_EMPTY",
    "AUDIT_LOG_EXPORT_FAILED",
    "AUDIT_LOG_OPERATION_TYPES_FAILED",
}

EXPECTED_ORPHAN_CODES = {
    "ORPHAN_LATEST_FAILED",
    "ORPHAN_SCAN_NOT_FOUND",
    "ORPHAN_SCAN_STATUS_FAILED",
    "ORPHAN_GUARDRAIL_REVIEW_INCOMPLETE",
    "ORPHAN_GUARDRAIL_REVIEW_FAILED",
    "ORPHAN_LIST_FAILED",
    "ORPHAN_FOLDER_CHILDREN_FAILED",
    "ORPHAN_HARDLINK_QUERY_FAILED",
    "ORPHAN_HARDLINK_DELETE_REJECTED",
    "ORPHAN_HARDLINK_DELETE_FAILED",
    "ORPHAN_SCAN_SUBMIT_FAILED",
    "ORPHAN_CLEANUP_PREVIEW_FAILED",
    "ORPHAN_CLEANUP_SUBMIT_FAILED",
    "ORPHAN_IGNORE_FAILED",
    "ORPHAN_PREFIX_PREVIEW_FAILED",
    "ORPHAN_QUARANTINE_LIST_FAILED",
    "ORPHAN_QUARANTINE_RESTORE_FAILED",
    "ORPHAN_PURGE_SUBMIT_FAILED",
    "ORPHAN_PURGE_JOB_NOT_FOUND",
    "ORPHAN_PURGE_JOB_QUERY_FAILED",
    "ORPHAN_CLEANUP_JOB_NOT_FOUND",
    "ORPHAN_CLEANUP_JOB_QUERY_FAILED",
}


def _reason_code(body: dict) -> str:
    data = body["data"]
    assert isinstance(data, dict), f"data 应为携带 reasonCode 的 dict，实际: {data!r}"
    assert "reasonCode" in data, f"data 应含 reasonCode，实际: {data!r}"
    return data["reasonCode"]


@pytest.fixture()
def client():
    """认证豁免的 TestClient（服务层按用例 patch，无需真实库）。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    user = SimpleNamespace(username="tester")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_authenticated_user] = lambda: user

    async def override_get_async_db():
        yield MagicMock()

    app.dependency_overrides[get_async_db] = override_get_async_db

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ====================================================================
# 一、audit-logs 失败路径
# ====================================================================


class TestAuditLogsContract:
    def test_query_bad_time_param_400(self, client):
        resp = client.post(AUDIT_URL + "/query", json={"start_time": "not-a-date"})
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "AUDIT_LOG_PARAM_INVALID"
        # ISO 解析诊断不进 msg
        assert "not-a-date" not in body["msg"]

    def test_query_service_failure_500_fixed_msg(self, client):
        service = MagicMock()
        service.query_logs = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.audit_logs.get_audit_service", AsyncMock(return_value=service)):
            resp = client.post(AUDIT_URL + "/query", json={})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "AUDIT_LOG_QUERY_FAILED"
        assert "boom-secret" not in body["msg"]
        assert body["msg"] == "查询审计日志失败，请稍后重试"

    def test_statistics_bad_time_param_400(self, client):
        resp = client.get(AUDIT_URL + "/statistics", params={"start_time": "bad"})
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "AUDIT_LOG_PARAM_INVALID"

    def test_statistics_service_failure_500(self, client):
        service = MagicMock()
        service.get_statistics = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.audit_logs.get_audit_service", AsyncMock(return_value=service)):
            resp = client.get(AUDIT_URL + "/statistics")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "AUDIT_LOG_STATS_FAILED"
        assert "boom-secret" not in body["msg"]

    def test_archive_service_failure_500(self, client):
        service = MagicMock()
        service.archive_logs = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.audit_logs.get_audit_service", AsyncMock(return_value=service)):
            resp = client.post(AUDIT_URL + "/archive", json={"end_time": "2026-01-01T00:00:00"})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "AUDIT_LOG_ARCHIVE_FAILED"
        assert "boom-secret" not in body["msg"]

    def test_archive_business_failure_msg_passthrough_with_reason_code(self, client):
        """归档业务失败：服务层 message 原文透传（B03），reasonCode 追加进 data。"""
        service = MagicMock()
        service.archive_logs = AsyncMock(
            return_value={"success": False, "archived_count": 0, "archive_path": None, "message": "归档目录不可写"}
        )
        with patch("app.api.endpoints.audit_logs.get_audit_service", AsyncMock(return_value=service)):
            resp = client.post(AUDIT_URL + "/archive", json={"end_time": "2026-01-01T00:00:00"})
        body = resp.json()
        assert body["code"] == "500"
        assert body["msg"] == "归档目录不可写"
        assert body["data"]["reasonCode"] == "AUDIT_LOG_ARCHIVE_FAILED"

    def test_export_empty_400(self, client):
        service = MagicMock()
        service.query_logs = AsyncMock(return_value={"list": [], "total": 0})
        with patch("app.api.endpoints.audit_logs.get_audit_service", AsyncMock(return_value=service)):
            resp = client.post(AUDIT_URL + "/export", json={})
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "AUDIT_LOG_EXPORT_EMPTY"
        assert body["msg"] == "没有符合条件的数据可导出"

    def test_export_write_failure_500(self, client):
        service = MagicMock()
        service.query_logs = AsyncMock(return_value={"list": [{"log_id": 1}], "total": 1})
        service.export_logs_to_csv = AsyncMock(return_value=False)
        with patch("app.api.endpoints.audit_logs.get_audit_service", AsyncMock(return_value=service)):
            resp = client.post(AUDIT_URL + "/export", json={})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "AUDIT_LOG_EXPORT_FAILED"

    def test_operation_types_failure_500(self, client):
        class _BrokenEnum:
            def __iter__(self):
                raise RuntimeError("boom-secret")

        with patch("app.api.endpoints.audit_logs.AuditOperationType", _BrokenEnum()):
            resp = client.get(AUDIT_URL + "/operation-types")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "AUDIT_LOG_OPERATION_TYPES_FAILED"
        assert "boom-secret" not in body["msg"]

    def test_download_export_404_is_http_exception(self, client):
        """download-export 保持真 HTTPException（404），detail 固定无动态诊断。"""
        resp = client.get(AUDIT_URL + "/download-export/no_such_file.csv")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "文件不存在"


# ====================================================================
# 二、orphan-files 失败路径
# ====================================================================


class TestOrphanFilesContract:
    def test_latest_failure_500(self, client):
        service = MagicMock()
        service.get_latest_scan_result = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.get(ORPHAN_URL + "/latest")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_LATEST_FAILED"
        assert "boom-secret" not in body["msg"]

    def test_scan_status_not_found_404(self, client):
        service = MagicMock()
        service.get_scan = AsyncMock(return_value=None)
        with patch("app.api.endpoints.orphan_files.OrphanScanJobService", MagicMock(return_value=service)):
            resp = client.get(ORPHAN_URL + "/scans/scan-x")
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "ORPHAN_SCAN_NOT_FOUND"

    def test_scan_status_failure_500_no_scan_id_leak(self, client):
        service = MagicMock()
        service.get_scan = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanScanJobService", MagicMock(return_value=service)):
            resp = client.get(ORPHAN_URL + "/scans/scan-secret-id")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_SCAN_STATUS_FAILED"
        assert "scan-secret-id" not in body["msg"]
        assert "boom-secret" not in body["msg"]

    def test_guardrail_review_incomplete_400(self, client):
        resp = client.post(
            ORPHAN_URL + "/scans/scan-x/guardrail-review",
            json={"confirmed_path_mapping": False, "confirmed_orphan_samples": True, "note": "x" * 8},
        )
        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "ORPHAN_GUARDRAIL_REVIEW_INCOMPLETE"
        assert body["msg"] == "必须同时完成路径映射核查和孤儿样本核查"

    def test_guardrail_review_service_failure_500(self, client):
        service = MagicMock()
        service.review_guardrail = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanScanJobService", MagicMock(return_value=service)):
            resp = client.post(
                ORPHAN_URL + "/scans/scan-x/guardrail-review",
                json={"confirmed_path_mapping": True, "confirmed_orphan_samples": True, "note": "x" * 8},
            )
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_GUARDRAIL_REVIEW_FAILED"
        assert "boom-secret" not in body["msg"]

    def test_list_failure_500(self, client):
        service = MagicMock()
        service.get_orphan_list = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.get(ORPHAN_URL + "/list")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_LIST_FAILED"

    def test_folder_children_failure_500(self, client):
        service = MagicMock()
        service.get_orphan_folder_children = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.get(ORPHAN_URL + "/folders/children", params={"folder_path": "/data"})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_FOLDER_CHILDREN_FAILED"

    def test_hardlink_query_failure_500(self, client):
        service = MagicMock()
        service.get_hardlink_copy_locations = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.post(ORPHAN_URL + "/hardlink-copies", json={"orphan_ids": [1]})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_HARDLINK_QUERY_FAILED"

    def test_hardlink_delete_rejected_keeps_200_with_reason_code(self, client):
        """rejected 双形态：200 包裹 + 原 msg/载荷保留，reasonCode 追加进 data（E14 同款）。"""
        service = MagicMock()
        service.delete_hardlink_copies = AsyncMock(
            return_value={
                "orphan_id": 7,
                "copy_count": None,
                "success_count": 0,
                "failed_count": 1,
                "failed_list": [{"copy_path": "/lib/a.bin", "reason": "另一个孤儿文件维护操作正在运行"}],
                "rejected": True,
                "error": "另一个孤儿文件维护操作正在运行",
            }
        )
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.post(
                ORPHAN_URL + "/hardlink-copies/delete", json={"orphan_id": 7, "copy_paths": ["/lib/a.bin"]}
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["code"] == "200"
        assert body["data"]["reasonCode"] == "ORPHAN_HARDLINK_DELETE_REJECTED"
        assert body["data"]["rejected"] is True

    def test_hardlink_delete_failure_500(self, client):
        service = MagicMock()
        service.delete_hardlink_copies = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.post(
                ORPHAN_URL + "/hardlink-copies/delete", json={"orphan_id": 7, "copy_paths": ["/lib/a.bin"]}
            )
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_HARDLINK_DELETE_FAILED"

    def test_scan_submit_failure_500(self, client):
        service = MagicMock()
        service.submit_scan = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanScanJobService", MagicMock(return_value=service)):
            resp = client.post(ORPHAN_URL + "/scan")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_SCAN_SUBMIT_FAILED"

    def test_cleanup_preview_failure_500(self, client):
        service = MagicMock()
        service.resolve_orphan_selection = AsyncMock(return_value=[1, 2])
        service.cleanup_preview = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.post(ORPHAN_URL + "/cleanup-preview", json={"scan_id": "s1", "orphan_ids": [1]})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_CLEANUP_PREVIEW_FAILED"

    def test_cleanup_submit_failure_500(self, client):
        service = MagicMock()
        service.resolve_orphan_selection = AsyncMock(return_value=[1])
        purge_service = MagicMock()
        purge_service.submit_cleanup_job = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with (
            patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)),
            patch("app.api.endpoints.orphan_files.OrphanPurgeJobService", MagicMock(return_value=purge_service)),
        ):
            resp = client.post(ORPHAN_URL + "/cleanup", json={"scan_id": "s1", "orphan_ids": [1]})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_CLEANUP_SUBMIT_FAILED"

    def test_ignore_failure_500(self, client):
        service = MagicMock()
        service.resolve_orphan_selection = AsyncMock(return_value=[1])
        service.set_ignored = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.post(ORPHAN_URL + "/ignore", json={"orphan_ids": [1], "ignored": True})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_IGNORE_FAILED"

    def test_prefix_preview_failure_500(self, client):
        service = MagicMock()
        service.prefix_match_preview = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.post(
                ORPHAN_URL + "/prefix-match-preview",
                json={"path_prefix": "/data/leak/", "scan_id": "s1"},
            )
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_PREFIX_PREVIEW_FAILED"

    def test_quarantine_list_failure_500(self, client):
        service = MagicMock()
        service.get_quarantine_list = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.get(ORPHAN_URL + "/quarantine")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_QUARANTINE_LIST_FAILED"

    def test_quarantine_restore_failure_500(self, client):
        service = MagicMock()
        service.restore_quarantined = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanFileService", MagicMock(return_value=service)):
            resp = client.post(ORPHAN_URL + "/restore", json={"canonical_paths": ["/data/a.bin"]})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_QUARANTINE_RESTORE_FAILED"

    def test_purge_submit_failure_500(self, client):
        purge_service = MagicMock()
        purge_service.submit_purge_job = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanPurgeJobService", MagicMock(return_value=purge_service)):
            resp = client.post(ORPHAN_URL + "/purge", json={"canonical_paths": ["/data/a.bin"]})
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_PURGE_SUBMIT_FAILED"

    def test_purge_job_not_found_404(self, client):
        purge_service = MagicMock()
        purge_service.get_job = AsyncMock(return_value=None)
        with patch("app.api.endpoints.orphan_files.OrphanPurgeJobService", MagicMock(return_value=purge_service)):
            resp = client.get(ORPHAN_URL + "/purge-jobs/task-x")
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "ORPHAN_PURGE_JOB_NOT_FOUND"

    def test_cleanup_job_not_found_when_operation_type_mismatch(self, client):
        purge_service = MagicMock()
        purge_service.get_job = AsyncMock(
            return_value=SimpleNamespace(operation_type="purge", to_dict=lambda: {"task_id": "t"})
        )
        with patch("app.api.endpoints.orphan_files.OrphanPurgeJobService", MagicMock(return_value=purge_service)):
            resp = client.get(ORPHAN_URL + "/cleanup-jobs/task-x")
        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "ORPHAN_CLEANUP_JOB_NOT_FOUND"

    def test_purge_job_query_failure_500(self, client):
        purge_service = MagicMock()
        purge_service.get_job = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanPurgeJobService", MagicMock(return_value=purge_service)):
            resp = client.get(ORPHAN_URL + "/purge-jobs/task-x")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_PURGE_JOB_QUERY_FAILED"

    def test_cleanup_job_query_failure_500(self, client):
        purge_service = MagicMock()
        purge_service.get_job = AsyncMock(side_effect=RuntimeError("boom-secret"))
        with patch("app.api.endpoints.orphan_files.OrphanPurgeJobService", MagicMock(return_value=purge_service)):
            resp = client.get(ORPHAN_URL + "/cleanup-jobs/task-x")
        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "ORPHAN_CLEANUP_JOB_QUERY_FAILED"


# ====================================================================
# 三、源码级契约：动态拼接禁回流 + reasonCode 清单完整
# ====================================================================


class TestSourceContract:
    def test_audit_no_dynamic_exception_in_msg(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / AUDIT_FILE).read_text(encoding="utf-8")
        for match in re.finditer(r'msg=f"[^"]*\{str\(e\)\}', text):
            raise AssertionError(f"audit_logs 存在动态 str(e) 进 msg: {match.group(0)}")
        # download-export 的 HTTPException detail 同样不得携带动态诊断
        assert 'detail=f"' not in text

    def test_orphan_no_dynamic_exception_in_msg(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / ORPHAN_FILE).read_text(encoding="utf-8")
        for match in re.finditer(r'msg=f"[^"]*\{e\}', text):
            raise AssertionError(f"orphan_files 存在动态 str(e) 进 msg: {match.group(0)}")

    def test_audit_reason_code_inventory_complete(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / AUDIT_FILE).read_text(encoding="utf-8")
        used = set(re.findall(r'_audit_error\(\s*\n?\s*"([A-Z_]+)"', text))
        used |= set(re.findall(r'"reasonCode": "([A-Z_]+)"', text))
        assert used, "应至少登记一个 reasonCode"
        unexpected = used - EXPECTED_AUDIT_CODES
        assert not unexpected, f"存在未登记的 audit reasonCode: {sorted(unexpected)}"
        missing = EXPECTED_AUDIT_CODES - used
        assert not missing, f"清单中未在源码使用的 audit reasonCode: {sorted(missing)}"

    def test_orphan_reason_code_inventory_complete(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / ORPHAN_FILE).read_text(encoding="utf-8")
        used = set(re.findall(r'_orphan_error\(\s*\n?\s*"([A-Z_]+)"', text))
        used |= set(re.findall(r'"reasonCode": "([A-Z_]+)"', text))
        assert used, "应至少登记一个 reasonCode"
        unexpected = used - EXPECTED_ORPHAN_CODES
        assert not unexpected, f"存在未登记的 orphan reasonCode: {sorted(unexpected)}"
        missing = EXPECTED_ORPHAN_CODES - used
        assert not missing, f"清单中未在源码使用的 orphan reasonCode: {sorted(missing)}"
