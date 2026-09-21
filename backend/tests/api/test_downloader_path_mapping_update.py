"""下载器更新接口的路径映射字段契约回归测试。"""

from unittest.mock import MagicMock

import pytest

from app.api.endpoints.downloader import update
from app.api.schemas.path_mapping import PathMappingConfig, PathMappingItem
from app.downloader.request import UpdateDownloader


class JsonRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


@pytest.mark.asyncio
async def test_toggle_enabled_only_keeps_other_fields():
    """列表启停开关只传 enabled 时其余字段必须保持原值（回归 2026-09-07）。

    列表行是 camelCase 且不含 isSearch 之外的 SSL 字段，曾因 is_search/is_ssl
    必填直接 422；修复后缺省字段走 case when :x is not null 保持原值。
    """
    db = MagicMock()
    current_result = MagicMock()
    current_result.fetchone.return_value = ("admin", "encrypted-password")
    db.execute.side_effect = [current_result, MagicMock()]

    raw_request = JsonRequest({"enabled": "0"})
    request_data = UpdateDownloader(enabled=False)

    response = await update(
        downloader_request=request_data,
        downloader_id="dl-1",
        _user=None,
        req=raw_request,
        db=db,
    )

    assert response.code == "200"
    update_sql = str(db.execute.call_args_list[1].args[0])
    update_params = db.execute.call_args_list[1].args[1]
    # 未提供的字段以 None 传入，SQL 侧保持原值
    assert update_params["is_search"] is None
    assert update_params["is_ssl"] is None
    assert update_params["enabled"] is False
    assert update_params["nickname"] is None
    assert update_params["host"] is None
    assert "path_mapping" not in update_sql
    # enabled 仍按 case when 部分更新语义写库
    assert "enabled= case when :enabled is not null then :enabled else enabled end" in update_sql


@pytest.mark.asyncio
async def test_missing_path_mapping_keeps_existing_mapping_while_updating_rules():
    """未传 path_mapping 时只更新规则，不能把既有结构化映射清空。"""
    db = MagicMock()
    current_result = MagicMock()
    current_result.fetchone.return_value = ("admin", "encrypted-password")
    db.execute.side_effect = [current_result, MagicMock()]

    request_data = UpdateDownloader(
        nickname="tr",
        host="192.168.5.51",
        username="admin",
        password=None,
        old_password=None,
        is_search=True,
        enabled=True,
        downloader_type=1,
        port=19591,
        is_ssl=False,
        path_mapping_rules="/Downloads/bangumi{#**#}/Downloads/bangumi",
    )
    raw_request = JsonRequest(
        {
            "nickname": "tr",
            "host": "192.168.5.51",
            "port": 19591,
            "username": "admin",
            "is_ssl": "0",
            "is_search": "1",
            "downloader_type": 1,
            "enabled": "1",
            "path_mapping_rules": "/Downloads/bangumi{#**#}/Downloads/bangumi",
        }
    )

    response = await update(
        downloader_request=request_data,
        downloader_id="dl-1",
        _user=None,
        req=raw_request,
        db=db,
    )

    assert response.code == "200"
    update_sql = str(db.execute.call_args_list[1].args[0])
    update_params = db.execute.call_args_list[1].args[1]
    assert "path_mapping =" not in update_sql
    assert "path_mapping_rules = :path_mapping_rules" in update_sql
    assert update_params["path_mapping_rules"] == "/Downloads/bangumi{#**#}/Downloads/bangumi"


@pytest.mark.asyncio
async def test_explicit_path_mapping_is_written_alongside_rules():
    db = MagicMock()
    current_result = MagicMock()
    current_result.fetchone.return_value = ("admin", "encrypted-password")
    db.execute.side_effect = [current_result, MagicMock()]

    path_mapping = PathMappingConfig(
        mappings=[
            PathMappingItem(
                name="bangumi",
                internal="/Downloads/bangumi/",
                external="/srv/bangumi/",
                mapping_type="local",
            )
        ],
        default_mapping="bangumi",
    )
    request_data = UpdateDownloader(
        nickname="tr",
        host="192.168.5.51",
        username="admin",
        password=None,
        old_password=None,
        is_search=True,
        enabled=True,
        downloader_type=1,
        port=19591,
        is_ssl=False,
        path_mapping=path_mapping,
        path_mapping_rules="/Downloads/bangumi{#**#}/Downloads/bangumi",
    )
    raw_request = JsonRequest(
        {
            "nickname": "tr",
            "host": "192.168.5.51",
            "port": 19591,
            "username": "admin",
            "is_ssl": "0",
            "is_search": "1",
            "downloader_type": 1,
            "enabled": "1",
            "path_mapping": {
                "mappings": [
                    {
                        "name": "bangumi",
                        "internal": "/Downloads/bangumi/",
                        "external": "/srv/bangumi/",
                        "mapping_type": "local",
                    }
                ],
                "default_mapping": "bangumi",
            },
            "path_mapping_rules": "/Downloads/bangumi{#**#}/Downloads/bangumi",
        }
    )

    response = await update(
        downloader_request=request_data,
        downloader_id="dl-1",
        _user=None,
        req=raw_request,
        db=db,
    )

    assert response.code == "200"
    update_sql = str(db.execute.call_args_list[1].args[0])
    update_params = db.execute.call_args_list[1].args[1]
    assert "path_mapping = :path_mapping" in update_sql
    assert "path_mapping_rules = :path_mapping_rules" in update_sql
    assert '"external": "/srv/bangumi/"' in update_params["path_mapping"]
