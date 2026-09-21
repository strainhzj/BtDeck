"""W2 内容级包验证器回归（release-artifact-equivalence-gate task .4 / G5）。

直接构造归档条目 dict 驱动 verify-package 的纯函数，覆盖计划 §7-G5 要求的
五类变异：旧 index、缺契约 JSON、身份/依赖漂移、混入 app.db、SHA 篡改。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Dict

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VERIFY_PATH = _REPO_ROOT / "deploy" / "verify-package.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("btdeck_verify_package", _VERIFY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verifier():
    return _load_verifier()


def _canonical_sha(verifier, payload: object) -> str:
    return verifier.canonical_json_sha256(payload)


def _build_entries(verifier) -> tuple:
    """构造合法归档条目；返回 (entries, frontend_manifest)。"""
    index_html = b"<!doctype html><html>btdeck w2 fixture</html>"
    app_js = b"// app fixture chunk"
    files = [
        {"path": "index.html", "size_bytes": len(index_html), "sha256": hashlib.sha256(index_html).hexdigest()},
        {"path": "assets/app.js", "size_bytes": len(app_js), "sha256": hashlib.sha256(app_js).hexdigest()},
    ]
    manifest = {"schema_version": 1, "file_count": len(files), "files": files}
    manifest_sha = _canonical_sha(verifier, manifest)
    build_info = {
        "schema_version": 1,
        "product_version": "1.0.6",
        "git_sha": "29c6f6f68ab35e25f8cf7237ee187de359c77714",
        "git_tag": "v1.0.6",
        "source_date_epoch": 1770000000,
        "build_id": None,
        "artifact_kind": "linux-deb",
        "target_os": "linux",
        "target_arch": "amd64",
        "python_version": "3.11.9",
        "node_version": "22.23.2",
        "alembic_head": "c1d2e3f4a5b6",
        "frontend_manifest_sha256": manifest_sha,
        "source_manifest_sha256": "b" * 64,
        "dependency_manifest_sha256": None,
        "dirty": False,
    }
    entries: Dict[str, bytes] = {
        "build-info.json": json.dumps(build_info).encode(),
        "source-manifest.json": b"{}",
        "frontend-asset-manifest.json": json.dumps(manifest).encode(),
        "frontend_dist/index.html": index_html,
        "frontend_dist/assets/app.js": app_js,
        "app/contracts/advanced_search_contract.json": b"{}",
        "config/production_complete_schema.sql": b"-- schema",
        "alembic/versions/aaaa11112222_add_fixture.py": b"revision: str = 'aaaa11112222'",
    }
    return entries, build_info, manifest


class TestPositive:
    def test_valid_archive_passes(self, verifier):
        entries, info, _ = _build_entries(verifier)
        result = verifier.verify_entries(entries)
        assert result["git_sha"] == info["git_sha"]


class TestWindowsBackslashCanonicalization:
    """Windows 归档条目名反斜杠规范化（W3 Windows 首跑实测拦截）。

    PyInstaller 在 Windows 用 os.path.join 组装 datas 目标路径，目录型条目
    进入 CArchive 时是反斜杠形式（本地 PyInstaller 6.19 实证：
    'app\\contracts\\contract.json'）；collect_archive_entries 必须规范化
    为 POSIX 名，否则必需条目/前端哈希校验在 Windows 制品上全部误报缺失。
    """

    def test_canonical_entry_name(self, verifier):
        assert verifier.canonical_entry_name("app\\contracts\\x.json") == "app/contracts/x.json"
        assert verifier.canonical_entry_name("frontend_dist\\index.html") == "frontend_dist/index.html"
        # POSIX 名与二进制条目不受影响
        assert verifier.canonical_entry_name("build-info.json") == "build-info.json"

    def test_backslash_archive_passes_after_canonicalization(self, verifier):
        """反斜杠键名条目经规范化后应与 POSIX 形态等价通过全部校验。"""
        entries, _, _ = _build_entries(verifier)
        backslashed = {name.replace("/", "\\") if "/" in name else name: data for name, data in entries.items()}
        # 前置：确认真构造出了反斜杠键（防御测试自身失效）
        assert any("\\" in name for name in backslashed)
        canonical = {verifier.canonical_entry_name(name): data for name, data in backslashed.items()}
        result = verifier.verify_entries(canonical)
        assert result["artifact_kind"] == "linux-deb"


class TestFiveMutations:
    """计划 §7-G5：五类变异必须稳定报红。"""

    def _entries(self, verifier):
        return _build_entries(verifier)

    def test_m1_stale_index_detected(self, verifier):
        """变异1：旧 index —— index.html 内容被替换为旧产物。"""
        entries, _, _ = self._entries(verifier)
        entries["frontend_dist/index.html"] = b"<!doctype html><html>OLD STALE BUILD</html>"
        with pytest.raises(verifier.VerificationFailure, match="哈希不符|缺少"):
            verifier.verify_entries(entries)

    def test_m2_missing_contract_json_detected(self, verifier):
        """变异2：缺契约 JSON —— app.contracts 运行时数据被移除。"""
        entries, _, _ = self._entries(verifier)
        del entries["app/contracts/advanced_search_contract.json"]
        with pytest.raises(verifier.VerificationFailure, match="缺少必需条目"):
            verifier.verify_entries(entries)

    def test_m3_identity_drift_detected(self, verifier):
        """变异3：身份漂移 —— build-info 的 git_sha/alembic_head/artifact_kind 篡改。

        版本号漂移（1.0.6→1.0.7）属跨制品比对范围，由 verify_release_bundle
        的 compare_identities 覆盖（test_verify_bundle.py）。
        """
        entries, info, _ = self._entries(verifier)
        drifted = dict(info, alembic_head="c1d2e3f4")
        entries["build-info.json"] = json.dumps(drifted).encode()
        with pytest.raises(verifier.VerificationFailure, match="alembic_head"):
            verifier.verify_entries(entries)
        # git_sha 短化同样拦截
        entries, info, _ = self._entries(verifier)
        drifted = dict(info, git_sha="29c6f6f")
        entries["build-info.json"] = json.dumps(drifted).encode()
        with pytest.raises(verifier.VerificationFailure, match="git_sha"):
            verifier.verify_entries(entries)

    def test_m4_app_db_smuggled_detected(self, verifier):
        """变异4：混入 app.db —— 数据库/密钥残留进入制品。"""
        entries, _, _ = self._entries(verifier)
        entries["config/app.db"] = b"SQLite format 3..."
        entries["config/config.yaml"] = b"secret_key: leak"
        with pytest.raises(verifier.VerificationFailure, match="禁入"):
            verifier.verify_entries(entries)

    def test_m5_manifest_sha_tampered_detected(self, verifier):
        """变异5：SHA 篡改 —— build-info 的前端 manifest 指纹被改。"""
        entries, info, _ = self._entries(verifier)
        tampered = dict(info, frontend_manifest_sha256="f" * 64)
        entries["build-info.json"] = json.dumps(tampered).encode()
        with pytest.raises(verifier.VerificationFailure, match="不一致"):
            verifier.verify_entries(entries)

    def test_dirty_artifact_detected(self, verifier):
        entries, info, _ = self._entries(verifier)
        dirty = dict(info, dirty=True)
        entries["build-info.json"] = json.dumps(dirty).encode()
        with pytest.raises(verifier.VerificationFailure, match="dirty"):
            verifier.verify_entries(entries)

    def test_removed_frontend_file_detected(self, verifier):
        """前端文件被删除（manifest 有、归档无）。"""
        entries, _, _ = self._entries(verifier)
        del entries["frontend_dist/assets/app.js"]
        with pytest.raises(verifier.VerificationFailure, match="缺少前端文件"):
            verifier.verify_entries(entries)
