"""构建身份读取（release-artifact-equivalence-gate G1）。

读取嵌入制品的 ``build-info.json``（由 scripts/release/generate_build_info.py 生成，
schema 见 release/schemas/build-info.schema.json），供健康接口暴露同一 Git SHA、
产品版本、Alembic head 与前端 manifest 指纹。

查找顺序（先命中先生效）：
  1. 环境变量 ``BTDECK_BUILD_INFO`` 指定的路径（测试/运维覆写）
  2. PyInstaller ``sys._MEIPASS``（EXE/单文件制品）
  3. 仓库布局 ``<repo>/release/build-info.json``（源码运行 + 生成器默认输出位）
  4. ``/app/build-info.json``（Docker backend 镜像）

fail-closed 语义：命中文件但内容缺失/畸形 → 抛 :class:`BuildInfoError`（由调用方
决定 503），绝不把不完整身份当正常数据返回；完全未命中 → dev 源码模式
（``source_mode=True``、git_sha 为 None），不伪造身份。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.version import CURRENT_VERSION

BUILD_INFO_FILENAME = "build-info.json"

_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ALEMBIC_HEAD_PATTERN = re.compile(r"^[0-9a-f]{12}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_ARTIFACT_KINDS = frozenset(
    {
        "windows-exe",
        "windows-setup",
        "linux-binary",
        "linux-deb",
        "linux-rpm",
        "docker-backend",
        "docker-frontend",
    }
)

_REQUIRED_FIELDS = (
    "product_version",
    "git_sha",
    "git_tag",
    "artifact_kind",
    "alembic_head",
    "frontend_manifest_sha256",
    "dirty",
)

_cache: Optional[Dict[str, Any]] = None


class BuildInfoError(RuntimeError):
    """build-info 命中但非法（缺失字段/格式错/JSON 损坏）。"""


def _candidate_paths() -> Tuple[Path, ...]:
    candidates: list = []
    override = os.environ.get("BTDECK_BUILD_INFO")
    if override:
        candidates.append(Path(override))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / BUILD_INFO_FILENAME)
    # backend/app/core/build_info.py → parents: core, app, backend, 仓库根
    candidates.append(Path(__file__).resolve().parents[3] / "release" / BUILD_INFO_FILENAME)
    candidates.append(Path("/app") / BUILD_INFO_FILENAME)
    return tuple(candidates)


def _validate(payload: Any, origin: Path) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise BuildInfoError(f"build-info 不是 JSON 对象：{origin}")
    missing = [field for field in _REQUIRED_FIELDS if field not in payload]
    if missing:
        raise BuildInfoError(f"build-info 缺少字段 {missing}：{origin}")
    if not isinstance(payload["git_sha"], str) or not _GIT_SHA_PATTERN.fullmatch(payload["git_sha"]):
        raise BuildInfoError(f"build-info git_sha 非完整 40 位：{origin}")
    if not isinstance(payload["alembic_head"], str) or not _ALEMBIC_HEAD_PATTERN.fullmatch(payload["alembic_head"]):
        raise BuildInfoError(f"build-info alembic_head 非 12 位 revision：{origin}")
    if not isinstance(payload["frontend_manifest_sha256"], str) or not _SHA256_PATTERN.fullmatch(
        payload["frontend_manifest_sha256"]
    ):
        raise BuildInfoError(f"build-info frontend_manifest_sha256 非法：{origin}")
    if payload["artifact_kind"] not in _ARTIFACT_KINDS:
        raise BuildInfoError(f"build-info artifact_kind 未知：{payload['artifact_kind']!r}")
    if payload["dirty"] is True:
        # 脏构建不允许出现在可运行制品身份中（G1）
        raise BuildInfoError(f"build-info dirty=true 不允许出现在制品中：{origin}")
    return payload


def locate_build_info() -> Optional[Tuple[Path, Dict[str, Any]]]:
    """返回 (命中路径, 校验后的内容)；未命中返回 None；命中但非法抛 BuildInfoError。"""
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BuildInfoError(f"build-info 无法读取/解析：{path}（{exc}）") from exc
        return path, _validate(payload, path)
    return None


def _dev_fallback() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "product_version": CURRENT_VERSION,
        "git_sha": None,
        "git_tag": None,
        "source_date_epoch": None,
        "build_id": None,
        "artifact_kind": None,
        "target_os": None,
        "target_arch": None,
        "python_version": None,
        "node_version": None,
        "alembic_head": None,
        "frontend_manifest_sha256": None,
        "source_manifest_sha256": None,
        "dependency_manifest_sha256": None,
        "dirty": None,
        "source_mode": True,
    }


def get_build_info() -> Dict[str, Any]:
    """返回构建身份 dict（缓存）。dev 源码模式不伪造任何身份字段。"""
    global _cache
    if _cache is not None:
        return _cache
    found = locate_build_info()
    if found is None:
        _cache = _dev_fallback()
    else:
        origin, payload = found
        info = dict(payload)
        info["source_mode"] = False
        info["origin"] = str(origin)
        _cache = info
    return _cache


def reset_cache() -> None:
    """测试/运维用途：清除缓存，下次 get_build_info 重新探测。"""
    global _cache
    _cache = None


def build_identity_block() -> Dict[str, Any]:
    """健康接口用的身份块：ok / dev / invalid 三态。invalid 不携带细节（不泄露路径）。"""
    try:
        info = get_build_info()
    except BuildInfoError:
        return {"status": "invalid"}
    if info.get("source_mode"):
        return {
            "status": "dev",
            "productVersion": info["product_version"],
        }
    return {
        "status": "ok",
        "productVersion": info["product_version"],
        "gitSha": info["git_sha"],
        "gitTag": info["git_tag"],
        "artifactKind": info["artifact_kind"],
        "alembicHead": info["alembic_head"],
        "frontendManifestSha256": info["frontend_manifest_sha256"],
    }
