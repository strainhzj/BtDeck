# -*- coding: utf-8 -*-
"""审计归档/导出路径安全测试。

安全背景（对抗验证结论）：
- archive_logs 曾把用户提供的 archive_path 直接 open("w")——任意文件覆盖写
  （JSON 是 YAML 子集，可覆盖 config.yaml），且归档即删除主库日志（销毁审计）；
- download-export 曾把 {file_name} 直接拼接——Windows 下 %5C 反斜杠与
  盘符绝对路径（pathlib 锚点替换）可穿越读取任意文件。

修复：归档仅取文件名 + 强制 .json + 固定目录；导出下载白名单 fullmatch。
"""

from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.audit_service import AuditLogService
from app.torrents.audit_models import TorrentAuditLog


@pytest.fixture()
async def audit_db(tmp_path):
    """异步内存库，仅建审计日志表。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[TorrentAuditLog.__table__])
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = maker()
    yield session
    await session.close()
    await engine.dispose()


async def _seed_log(session: AsyncSession) -> None:
    session.add(
        TorrentAuditLog(
            operation_type="ADD_TORRENT",
            operation_result="success",
            operator="tester",
            operation_time=datetime(2026, 1, 1, 0, 0, 0),
        )
    )
    await session.commit()


class TestArchivePathConfinement:
    """archive_logs：用户路径仅取文件名并固定写入归档目录。"""

    @pytest.mark.parametrize(
        "user_path",
        [
            "../../backend/config/config.yaml",
            "..\\..\\backend\\config\\config.yaml",
            "/etc/cron.d/evil",
            "C:/Windows/evil",
            "..",
            ".",
        ],
    )
    async def test_traversal_archive_path_confined(self, audit_db, tmp_path, monkeypatch, user_path):
        monkeypatch.chdir(tmp_path)  # 归档目录是相对路径，隔离到临时目录
        await _seed_log(audit_db)
        service = AuditLogService(db_session=audit_db)
        result = await service.archive_logs(end_time=datetime(2026, 6, 1), archive_path=user_path)

        assert result["success"] is True
        written = Path(result["archive_path"]).resolve()
        archive_root = (tmp_path / "data" / "audit_logs_archive").resolve()
        assert written.is_relative_to(archive_root), f"归档文件必须落在固定目录内: {written}"
        assert written.suffix == ".json"
        assert written.exists()

    async def test_plain_name_preserved_with_json_suffix(self, audit_db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        await _seed_log(audit_db)
        service = AuditLogService(db_session=audit_db)
        result = await service.archive_logs(end_time=datetime(2026, 6, 1), archive_path="my_archive")

        written = Path(result["archive_path"])
        assert written.parent.name == "audit_logs_archive"
        assert written.name == "my_archive.json"

    async def test_auto_generated_when_empty(self, audit_db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        await _seed_log(audit_db)
        service = AuditLogService(db_session=audit_db)
        result = await service.archive_logs(end_time=datetime(2026, 6, 1), archive_path=None)
        assert result["archive_path"] is not None
        assert Path(result["archive_path"]).name.startswith("audit_logs_")


class TestDownloadExportWhitelist:
    """download-export：文件名白名单（仅本端点生成的格式）。"""

    @pytest.mark.parametrize(
        "evil_name",
        [
            "..%5C..%5Cconfig%5Cconfig.yaml",
            "..\\..\\config\\config.yaml",
            "C:\\Windows\\win.ini",
            "C:/Windows/win.ini",
            "../../app.db",
            "audit_logs_evil.xlsx",
            "audit_logs_20260101.csv.bak",
            "audit_logs_20260101_120000.txt",
            "",
        ],
    )
    async def test_non_whitelisted_names_rejected_404(self, evil_name):
        from app.api.endpoints.audit_logs import download_export_file

        with pytest.raises(HTTPException) as exc_info:
            await download_export_file(evil_name, current_user=None)
        assert exc_info.value.status_code == 404

    async def test_whitelisted_name_passes_gate_then_404_on_missing_file(self, tmp_path, monkeypatch):
        """合法格式通过白名单闸门，仅因文件不存在而 404（非路径拒绝）。"""
        from app.api.endpoints import audit_logs as mod

        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "audit_logs_export").mkdir(parents=True)
        with pytest.raises(HTTPException) as exc_info:
            await mod.download_export_file("audit_logs_20260101_120000.csv", current_user=None)
        assert exc_info.value.status_code == 404
        assert "文件不存在" in str(exc_info.value.detail)
