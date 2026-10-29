"""维护本地审计测试（database-migration-ui W2-6，PLANS §5.3/§11 T22）。

- 关键事件先持久化（append+fsync）；磁盘满/容量上限 → 拒绝关键动作（不丢日志）；
- 非关键事件超容聚合哨兵；
- 键名脱敏（password/totp/token/确认口令嵌套结构）；
- event_id 去重回放（崩溃重复 append 安全）；token/密码不落盘。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.db_migration.local_audit import (
    AUDIT_FILENAME,
    LocalAuditUnavailable,
    MaintenanceLocalAudit,
)


class TestWriteAndReplay:
    def test_event_persisted_and_replayed(self, tmp_path):
        audit = MaintenanceLocalAudit(tmp_path)
        event = audit.audit_event("control", operator="admin", action="freeze", detail={"x": 1})
        assert (tmp_path / "db-migration" / AUDIT_FILENAME).exists()
        rows = audit.replay_events()
        assert len(rows) == 1
        assert rows[0]["event_id"] == event["event_id"]
        assert rows[0]["action"] == "freeze"

    def test_replay_dedupes_by_event_id(self, tmp_path):
        audit = MaintenanceLocalAudit(tmp_path)
        audit.audit_event("control", action="a")
        # 模拟崩溃窗口重复 append（同一行写两次）
        path = tmp_path / "db-migration" / AUDIT_FILENAME
        line = path.read_text(encoding="utf-8").splitlines()[0]
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        assert len(audit.replay_events()) == 1

    def test_replay_skips_half_line(self, tmp_path):
        audit = MaintenanceLocalAudit(tmp_path)
        audit.audit_event("control", action="a")
        path = tmp_path / "db-migration" / AUDIT_FILENAME
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"event_id": "half')  # 崩溃半行
        assert len(audit.replay_events()) == 1

    def test_no_file_replays_empty(self, tmp_path):
        assert MaintenanceLocalAudit(tmp_path).replay_events() == []


class TestRedaction:
    def test_forbidden_keys_redacted_nested(self, tmp_path):
        audit = MaintenanceLocalAudit(tmp_path)
        audit.audit_event(
            "auth",
            action="maintenance-auth",
            detail={
                "username": "admin",
                "password": "should-not-appear",
                "nested": {"totp": "123456", "api_key": "abc", "ok": 1},
                "confirmCleanup": "yes",
            },
        )
        raw = (tmp_path / "db-migration" / AUDIT_FILENAME).read_text(encoding="utf-8")
        assert "should-not-appear" not in raw
        assert "123456" not in raw
        assert "abc" not in raw
        row = json.loads(raw.strip())
        assert row["detail"]["password"] == "<redacted>"
        assert row["detail"]["nested"]["totp"] == "<redacted>"
        assert row["detail"]["nested"]["ok"] == 1


class TestFailClosed:
    def test_disk_full_refuses_critical(self, tmp_path, monkeypatch):
        audit = MaintenanceLocalAudit(tmp_path)
        import app.services.db_migration.local_audit as la

        def _boom(*args, **kwargs):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr("builtins.open", _boom)
        with pytest.raises(LocalAuditUnavailable):
            audit.audit_event("control", action="dangerous")

    def test_capacity_refuses_critical(self, tmp_path):
        audit = MaintenanceLocalAudit(tmp_path, max_events=2)
        audit.audit_event("control", action="a")
        audit.audit_event("control", action="b")
        with pytest.raises(LocalAuditUnavailable, match="容量上限"):
            audit.audit_event("control", action="c")

    def test_noncritical_dropped_then_sentinel(self, tmp_path):
        audit = MaintenanceLocalAudit(tmp_path, max_events=2)
        audit.audit_event("control", action="a")
        audit.audit_event("obs", action="b", critical=False)
        # 容量满：非关键聚合丢弃，不留静默无痕
        audit.audit_event("obs", action="c", critical=False)  # dropped
        rows = audit.replay_events()
        kinds = [r.get("kind") for r in rows]
        assert "audit_dropped_aggregate" in kinds
