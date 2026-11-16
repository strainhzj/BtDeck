# -*- coding: utf-8 -*-
"""历史迁移记录一次性对账（只读报告；复核修复批 W3 / R4 深水区）。

W1（2026-11-15）修复之前的历史 attempt 存在两类**不可证明/不可比**记录：

1. 目标 ACK 真实性不可证明：旧默认 ACK writer 连接"导入期缓存库"，UPDATE
   不核身份不核行数，零行也当成功（冷启动实测：候选从未连接而本地推进
   ACTIVATED_ACK）。manifest 缺 ``candidate_active``（W4 前提交形态）或缺
   ``identity`` 段的历史记录无法用严格 writer 时代证据回溯证明。
2. verify 覆盖不可比：``digest_version`` 非 ``btdeck-canonical-v1``（或缺
   失）时 counts/digests 与现行算法不可比；且旧 verifier 对有主键表跳过全
   列内容摘要——即便 digest_version 相同，2026-11-15 前完成的 verify 结论
   也弱于现行口径。

本工具**只读**扫描 journal（绝不改任何状态/配置/库），逐 attempt 分类并给
出处置建议；供升级到修复版后的一次性人工对账使用。退出码：0=扫描完成；
2=journal 损坏（fail-closed，禁止默认化——与 bootstrap 语义一致）。

用法::

    python -m app.services.db_migration.legacy_audit \
        [--config-dir DIR] [--yaml PATH] [--json OUT_PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.database_bootstrap import (
    ManagedConfigError,
    ManagedStateError,
    list_attempt_ids,
    read_manifest,
    resolve_effective_database_config,
)
from app.core.database_protocol import DIGEST_VERSION_CANONICAL_V1
from app.services.db_migration.journal import (
    COMMIT_PHASE_ACTIVATED_ACK,
    COMMIT_PHASE_COMMITTED,
    MANIFEST_SCHEMA_VERSION,
)

__all__ = ["scan_legacy_attempts", "format_report", "main"]

#: 严格 ACK writer（显式候选目标 + 事务核验 + 恰好一行）落地日期。此前的
#: ACK 记录一律按"真实性不可证明"保守上报（journal 无 ACK 行数证据可回溯）。
STRICT_ACK_SINCE = "2026-11-15"


def _flag_definitions() -> Dict[str, str]:
    return {
        "schema-version-mismatch": "manifest schema_version 缺失或非 "
        f"{MANIFEST_SCHEMA_VERSION}——记录形态早于/晚于现行协议，字段语义不可靠",
        "digest-version-mismatch": "digest_version 缺失或非 "
        f"{DIGEST_VERSION_CANONICAL_V1}——历史 verify 结果与现行摘要算法不可比",
        "identity-missing": "manifest 缺 identity 段——来源库身份未记录，" "无法对账来源指纹（老形态记录）",
        "legacy-ack-unprovable": f"提交/ACK 产生于严格 ACK writer（{STRICT_ACK_SINCE}）"
        "之前（manifest 缺 candidate_active）——目标 ACK 真实性不可证明（旧实现"
        "连导入期缓存库、零行也当成功）",
        "pre-strict-ack-window": f"commit_phase={COMMIT_PHASE_ACTIVATED_ACK} 且 updated_at 早于 "
        f"{STRICT_ACK_SINCE}——即使形态完整，其 ACK/verify 也弱于现行口径（旧 verifier "
        "跳过有主键表全列摘要）",
    }


_RECOMMENDATIONS: Dict[str, str] = {
    "schema-version-mismatch": "人工核读 manifest 原文；确认该 attempt 是否仍有未竟事实",
    "digest-version-mismatch": "不可据此声称数据一致；对存活目标重跑 verify_counts_and_digests 或重跑迁移",
    "identity-missing": "无来源指纹可比对；若该 attempt 对应现役库，建议重跑迁移以重建证据链",
    "legacy-ack-unprovable": "核对目标库 receipt（status/activation_generation/identity）与数据量；"
    "存疑则重跑迁移（严格 writer 会重出全部证据）",
    "pre-strict-ack-window": "建议对现役目标执行一次全量复核（重跑迁移或人工 counts/digests 抽验）",
}


def scan_legacy_attempts(
    config_dir: str,
    *,
    yaml_path: Optional[str] = None,
) -> Dict[str, Any]:
    """只读扫描 journal 全部 attempt 并分类；journal 损坏抛 ManagedStateError。"""
    attempts: List[Dict[str, Any]] = []
    active_receipt: Optional[str] = None
    active_note: Optional[str] = None
    if yaml_path is not None:
        try:
            effective = resolve_effective_database_config(yaml_path)
            active_receipt = effective.receipt_attempt_id
        except ManagedConfigError as exc:
            active_note = f"active 配置解析失败（不影响扫描）: {exc}"

    for attempt_id in list_attempt_ids(config_dir):
        manifest = read_manifest(config_dir, attempt_id)
        flags: List[str] = []
        phase = manifest.get("commit_phase")
        if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            flags.append("schema-version-mismatch")
        digest_version = manifest.get("digest_version")
        if not digest_version or digest_version != DIGEST_VERSION_CANONICAL_V1:
            flags.append("digest-version-mismatch")
        identity = manifest.get("identity")
        if not isinstance(identity, dict) or not identity:
            flags.append("identity-missing")
        if phase in (COMMIT_PHASE_COMMITTED, COMMIT_PHASE_ACTIVATED_ACK) and not manifest.get("candidate_active"):
            flags.append("legacy-ack-unprovable")
        elif phase == COMMIT_PHASE_ACTIVATED_ACK and str(manifest.get("updated_at") or "")[:10] < STRICT_ACK_SINCE:
            flags.append("pre-strict-ack-window")
        recommendations = sorted({_RECOMMENDATIONS[f] for f in flags})
        attempts.append(
            {
                "attempt_id": attempt_id,
                "direction": manifest.get("direction"),
                "operation_kind": manifest.get("operation_kind"),
                "commit_phase": phase,
                "created_at": manifest.get("created_at"),
                "updated_at": manifest.get("updated_at"),
                "tool_version": manifest.get("tool_version"),
                "digest_version": digest_version,
                "has_candidate_active": bool(manifest.get("candidate_active")),
                "has_identity": isinstance(identity, dict) and bool(identity),
                "active_linked": active_receipt is not None and attempt_id == active_receipt,
                "flags": flags,
                "recommendation": recommendations,
            }
        )
    attempts.sort(
        key=lambda item: (not item["active_linked"], str(item["updated_at"])),
    )
    flagged = sum(1 for item in attempts if item["flags"])
    return {
        "config_dir": str(config_dir),
        "strict_ack_since": STRICT_ACK_SINCE,
        "active_receipt_attempt": active_receipt,
        "active_note": active_note,
        "attempts": attempts,
        "summary": {"total": len(attempts), "flagged": flagged, "clean": len(attempts) - flagged},
    }


def format_report(report: Dict[str, Any]) -> str:
    """人读报告（stdout 面；无密码/无敏感字段——manifest 本就不含密码）。"""
    lines: List[str] = [
        "=== 历史迁移记录一次性对账（只读） ===",
        f"config_dir: {report['config_dir']}",
        f"严格 ACK 口径自: {report['strict_ack_since']}",
        f"现役 active 绑定: {report.get('active_receipt_attempt') or '（无）'}",
    ]
    if report.get("active_note"):
        lines.append(f"注: {report['active_note']}")
    lines.append(f"共 {report['summary']['total']} 条 attempt，需关注 {report['summary']['flagged']} 条")
    definitions = _flag_definitions()
    for item in report["attempts"]:
        mark = "现役" if item["active_linked"] else "    "
        head = f"{mark} [{item['commit_phase']}] {item['attempt_id']} ({item['direction']}, {item['updated_at']})"
        lines.append(head)
        if not item["flags"]:
            lines.append("      ✓ 形态完整，无需处置")
            continue
        for flag in item["flags"]:
            lines.append(f"      ⚑ {flag}: {definitions.get(flag, '')}")
        seen: set = set()
        for rec in item["recommendation"]:
            if rec not in seen:
                lines.append(f"      → 建议: {rec}")
                seen.add(rec)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="历史迁移记录一次性对账（只读）")
    parser.add_argument("--config-dir", default=None, help="CONFIG_DIR（缺省取 settings.CONFIG_DIR/env）")
    parser.add_argument("--yaml", default=None, help="config.yaml 路径（用于现役绑定判定；缺省 settings.YAML_PATH）")
    parser.add_argument("--json", dest="json_path", default=None, help="另存 JSON 报告到指定路径")
    args = parser.parse_args(argv)

    config_dir = args.config_dir
    yaml_path = args.yaml
    if config_dir is None or yaml_path is None:
        try:
            from app.core.config import settings

            config_dir = config_dir or str(settings.CONFIG_DIR)
            yaml_path = yaml_path or str(settings.YAML_PATH)
        except Exception as exc:  # noqa: BLE001 - CLI 无 config 依赖时显式指路
            print(f"[ERROR] 未提供 --config-dir/--yaml 且 settings 不可用: {exc}", file=sys.stderr)
            return 2
    try:
        report = scan_legacy_attempts(config_dir, yaml_path=yaml_path)
    except ManagedStateError as exc:
        print(f"[ERROR] journal 损坏（fail-closed，拒绝默认化）: {exc}", file=sys.stderr)
        return 2
    print(format_report(report))
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] JSON 报告已写入 {args.json_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - python -m 入口
    raise SystemExit(main())
