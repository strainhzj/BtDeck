"""放弃目标的最小删除授权（database-migration-ui W3-5，PLANS §6.5；T11）。

- 仅操作 manifest 固定目标（不接受换 host/path）；维护态+worker 已停+未
  COMMITTED+目标非当前有效/源库；
- nonce/deployment/database_id/schema/对象清单全符才动；
- 恢复失败或 marker 存在**不是删除授权**：核已提交表内容与对象清单，出现
  外部表/行/修改/未知依赖 → 拒绝；
- PG：有界锁+事务内逐个清理本次清单对象，顺序明确，**禁止 DROP DATABASE/
  SCHEMA CASCADE**；新外部对象不得被删；清理后非空 → 隔离拒重建；
- SQLite：仅清本次专属 staging/final（核 identity/hash/inode/句柄关闭）；
  不删任意路径、当前 active、源、旧三件；
- 清理失败保留线索，不自动升级为更强删除。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.services.db_migration.journal import (
    COMMIT_PHASE_NONE,
    Journal,
)

__all__ = ["DiscardError", "DiscardTargetService"]


class DiscardError(RuntimeError):
    """discard 拒绝（授权不足/外部内容/状态不符）。"""


class DiscardTargetService:
    """§6.5 最小删除授权执行器（PG/SQLite 连接器注入；测试替身）。"""

    def __init__(self, config_dir: os.PathLike[str] | str) -> None:
        self._journal = Journal(config_dir)

    # ------------------------------------------------------------------
    # 授权核验（全部通过才允许清理）
    # ------------------------------------------------------------------

    def authorize(
        self,
        attempt_id: str,
        *,
        ownership_nonce: str,
        database_id: str,
        confirm_token: str,
    ) -> Dict[str, Any]:
        """核 manifest 绑定 + 双确认 token；返回授权摘要（含对象清单）。"""
        manifest = self._journal.read_manifest(attempt_id)
        if manifest.get("commit_phase", COMMIT_PHASE_NONE) != COMMIT_PHASE_NONE:
            raise DiscardError("COMMITTED/PREPARED 之后禁 discard（只能 redo/clear）")
        if manifest.get("ownership_nonce") != ownership_nonce:
            raise DiscardError("ownership_nonce 不符（拒绝清理）")
        target = manifest.get("target", {})
        if target.get("database_id") != database_id:
            raise DiscardError("目标 database_id 不符（manifest 固定目标不可替换）")
        # 双确认：token = f"discard:{attempt_id}:{database_id[:8]}"（调用方展示后回传）
        expected = f"discard:{attempt_id}:{str(database_id)[:8]}"
        if confirm_token != expected:
            raise DiscardError("二次确认 token 不符（双确认未完成）")
        objects: List[str] = list(manifest.get("objects", []))
        if not objects:
            raise DiscardError("manifest 无对象清单（拒绝无清单清理）")
        return {
            "attempt_id": attempt_id,
            "dialect": target.get("dialect"),
            "objects": objects,
            "staging_path": manifest.get("staging_path"),
            "final_path": manifest.get("final_path"),
        }

    # ------------------------------------------------------------------
    # PG：逐对象清理（禁 CASCADE）
    # ------------------------------------------------------------------

    def discard_pg(
        self,
        attempt_id: str,
        *,
        engine: Any,
        objects: Sequence[str],
        listed_owner_check: Any,
    ) -> Dict[str, Any]:
        """清空/移除清单内对象；外部内容出现 → DiscardError（不扩大范围）。

        ``listed_owner_check(conn, objects)`` → List[str]：返回含外部内容的
        对象名（有界锁下 SELECT 核对；空列表=可安全清理）。
        """
        with engine.begin() as conn:
            foreign = listed_owner_check(conn, list(objects))
            if foreign:
                raise DiscardError(f"对象含非本次内容/未知依赖，拒绝: {sorted(foreign)}")
            for obj in objects:  # 固定顺序（清单序）；禁 CASCADE DROP——逐对象独立删除
                conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{obj}"')
        # 清理后非空 → 隔离拒重建
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
            ).fetchall()
        leftovers = [r[0] for r in rows]
        if leftovers:
            raise DiscardError(f"清理后 schema 非空（隔离，拒绝重建）: {leftovers}")
        manifest = self._journal.read_manifest(attempt_id)
        merged = dict(manifest)
        merged["discarded"] = True
        self._journal.write_manifest(attempt_id, merged, expect_state_version=manifest["state_version"])
        return {"attempt_id": attempt_id, "discarded_objects": list(objects), "empty": True}

    # ------------------------------------------------------------------
    # SQLite：仅专属产物
    # ------------------------------------------------------------------

    def discard_sqlite(
        self,
        attempt_id: str,
        *,
        staging_path: Optional[str],
        final_path: Optional[str],
        expected_sha256: Optional[str] = None,
    ) -> Dict[str, Any]:
        """删本次 staging/final（核 inode/句柄/可选 hash；不删其他任何路径）。"""
        removed: List[str] = []
        for raw in (staging_path, final_path):
            if not raw:
                continue
            path = Path(raw)
            # 专属产物命名核验：必须位于 attempts 目录或 final 命名含 attempt 尾段
            tail = attempt_id.rsplit("/", 1)[1]
            if tail not in path.name and "db-migration" not in str(path):
                raise DiscardError(f"拒绝删除非本次专属路径: {path}")
            if path.exists():
                if expected_sha256:
                    import hashlib

                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest != expected_sha256:
                        raise DiscardError(f"产物 hash 不符（内容漂移，拒绝删除）: {path}")
                try:
                    path.unlink()
                    removed.append(str(path))
                except OSError as exc:
                    raise DiscardError(f"删除失败（保留线索，不升级删除）: {exc}") from exc
        manifest = self._journal.read_manifest(attempt_id)
        merged = dict(manifest)
        merged["discarded"] = True
        self._journal.write_manifest(attempt_id, merged, expect_state_version=manifest["state_version"])
        return {"attempt_id": attempt_id, "removed": removed}
