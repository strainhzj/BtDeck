"""应用生命周期的数据库迁移 fail-fast 回归。"""

import pytest
from fastapi import FastAPI

from app.startup.lifecycle import lifespan


@pytest.mark.asyncio
async def test_lifespan_stops_before_initialization_when_migration_fails(monkeypatch):
    events: list[str] = []

    monkeypatch.setattr(
        "app.database.init_config_file",
        lambda: events.append("config"),
    )
    monkeypatch.setattr(
        "app.yamlConfig.yaml.reload",
        lambda: events.append("yaml"),
    )
    monkeypatch.setattr(
        "app.core.migration.migrate_database",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.database.init_db",
        lambda: events.append("seed"),
    )

    with pytest.raises(RuntimeError, match="数据库迁移未完成"):
        async with lifespan(FastAPI()):
            pytest.fail("迁移失败时不得进入已启动状态")

    assert events == ["config", "yaml"]
