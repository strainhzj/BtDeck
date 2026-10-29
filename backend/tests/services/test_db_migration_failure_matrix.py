# -*- coding: utf-8 -*-
"""activation 提交协议故障注入矩阵（database-migration-ui W5-2，PLANS §11 T04/T17 补全）。

对提交链路逐故障点注入（发布失败/ACK 失败/崩溃窗口），断言：
- 本地持久决定（COMMITTED）先于一切副作用——发布/ACK 失败不回退决定；
- 任一故障点后旧状态完好，重试幂等收敛；
- 目标 ACK 先于本地 ACTIVATED_ACK（目标失败则本地不前进）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

import app.services.db_migration.activation as activation_module
from app.services.db_migration.activation import SWITCH_MODE_B, ActivationError, ActivationService
from app.services.db_migration.journal import Journal

from tests.services.test_db_migration_activation import ATTEMPT, DB_ID, _prepared_attempt


def _service(tmp_path: Path, ack: Any = None, exits: Any = None) -> ActivationService:
    return ActivationService(
        str(tmp_path),
        yaml_path=str(tmp_path / "config.yaml"),
        target_ack_writer=ack,
        restart_scheduler=exits or (lambda info: True),
    )


def _prepare(svc: ActivationService) -> None:
    svc.prepare_switch(
        ATTEMPT,
        mode=SWITCH_MODE_B,
        candidate_active={"dialect": "postgresql", "expected_database_id": DB_ID},
        identity={"generation": "g1"},
    )


class TestPublishFailureInjection:
    def test_publish_failure_keeps_committed_and_retry_publishes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _prepared_attempt(tmp_path)
        svc = _service(tmp_path)
        _prepare(svc)
        journal = Journal(str(tmp_path))
        # 注入：COMMITTED 已持久后发布炸（磁盘满/权限类；发布函数在调用点局部导入，须打 config_store 属性）

        def _failing_atomic(path: Any, tree: Dict[str, Any]) -> None:
            raise OSError("injected: disk full")

        from app.services.db_migration import config_store as cs

        monkeypatch.setattr(cs, "write_yaml_atomic", _failing_atomic, raising=False)
        # commit：决定已持久 + 发布失败应整体抛错，但 phase 不回退
        with pytest.raises((ActivationError, OSError)):
            svc.commit_switch(ATTEMPT)
        manifest = journal.read_manifest(ATTEMPT)
        assert manifest["commit_phase"] == "COMMITTED"
        assert not manifest.get("config_published")
        # 重试（故障消失）→ 幂等发布成功
        monkeypatch.setattr(
            cs,
            "write_yaml_atomic",
            lambda path, tree: Path(path).write_text("database: ok", encoding="utf-8"),
            raising=False,
        )
        result = svc.commit_switch(ATTEMPT)
        assert result["configPublished"] is True
        assert journal.read_manifest(ATTEMPT)["config_published"] is True
        assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == "database: ok"

    def test_redo_republishes_unpublished_committed(self, tmp_path: Path) -> None:
        _prepared_attempt(tmp_path)
        svc = _service(tmp_path)
        _prepare(svc)
        journal = Journal(str(tmp_path))
        # 模拟崩溃窗口：COMMITTED 持久但发布未发生
        svc.commit_switch(ATTEMPT)
        manifest = journal.read_manifest(ATTEMPT)
        merged = dict(manifest)
        merged.pop("config_published", None)
        merged["state_version"] = manifest["state_version"] + 1
        journal.write_manifest(ATTEMPT, merged)
        # 新进程 redo：补发布并报告待目标 ACK
        redo = svc.redo_pending_activation()
        assert redo is not None and redo["awaitingTargetAck"] is True
        assert journal.read_manifest(ATTEMPT)["config_published"] is True
        assert (tmp_path / "config.yaml").exists()


class TestTargetAckFailureInjection:
    def test_target_ack_failure_keeps_committed_and_restart_pending(self, tmp_path: Path) -> None:
        _prepared_attempt(tmp_path)
        ack_calls: List[tuple] = []

        def _flaky(aid: str, gen: str) -> None:
            ack_calls.append((aid, gen))
            if len(ack_calls) == 1:
                raise RuntimeError("injected: target unreachable")

        svc = _service(tmp_path, ack=_flaky)
        _prepare(svc)
        svc.commit_switch(ATTEMPT)
        journal = Journal(str(tmp_path))
        assert (journal.read_control() or {})["restart_pending"] is True
        # 目标 ACK 失败 → 本地不前进、RESTART_PENDING 不清
        with pytest.raises(RuntimeError, match="target unreachable"):
            svc.complete_activation(ATTEMPT)
        assert journal.read_manifest(ATTEMPT)["commit_phase"] == "COMMITTED"
        assert (journal.read_control() or {})["restart_pending"] is True
        # 目标恢复（第二次成功）→ 本地 ACK + 清 pending（目标先本地后）
        done = svc.complete_activation(ATTEMPT)
        assert done["commitPhase"] == "ACTIVATED_ACK"
        assert len(ack_calls) == 2
        assert (journal.read_control() or {})["restart_pending"] is False

    def test_redo_reports_activated_pending(self, tmp_path: Path) -> None:
        _prepared_attempt(tmp_path)
        svc = _service(tmp_path, ack=lambda aid, gen: None)
        _prepare(svc)
        svc.commit_switch(ATTEMPT)
        svc.complete_activation(ATTEMPT)
        redo = svc.redo_pending_activation()
        assert redo is not None and redo["awaitingTargetAck"] is False


class TestPrepareFailureInjection:
    def test_candidate_write_failure_leaves_phase_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _prepared_attempt(tmp_path)
        journal = Journal(str(tmp_path))
        monkeypatch.setattr(
            activation_module,
            "write_candidate_config",
            lambda *a, **k: (_ for _ in ()).throw(OSError("injected")),
            raising=False,
        )
        svc = _service(tmp_path)
        with pytest.raises(OSError, match="injected"):
            svc.prepare_switch(ATTEMPT, mode=SWITCH_MODE_B, candidate_active={}, identity={})
        assert journal.read_manifest(ATTEMPT)["commit_phase"] == "NONE"
        # 故障消失后重试收敛
        monkeypatch.undo()
        result = svc.prepare_switch(
            ATTEMPT,
            mode=SWITCH_MODE_B,
            candidate_active={"dialect": "postgresql"},
            identity={"generation": "g2"},
        )
        assert result.commit_phase == "PREPARED"
