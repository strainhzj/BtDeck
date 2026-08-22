from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.downloader_adapters.transmission import TransmissionDeleteAdapter
from app.services.torrent_deletion_service import DeleteOption, SafetyCheckLevel


@pytest.mark.asyncio
async def test_delete_uses_hash_without_fetching_all_torrents():
    client = MagicMock()
    client.get_torrents.side_effect = AssertionError("delete path must not fetch all torrents")

    adapter = TransmissionDeleteAdapter(client=client)
    adapter.get_torrent_info = AsyncMock(return_value={"state": "paused", "progress": 0.5, "ratio": 2.0, "size": 1024})

    result = await adapter.delete_torrents(
        torrent_hashes=["hash-1"],
        delete_option=DeleteOption.DELETE_ONLY_TORRENT,
        safety_check_level=SafetyCheckLevel.ENHANCED,
    )

    assert result["success_hashes"] == ["hash-1"]
    client.get_torrents.assert_not_called()
    client.remove_torrent.assert_called_once_with(ids="hash-1", delete_data=False)
    adapter.get_torrent_info.assert_awaited_once_with("hash-1")
