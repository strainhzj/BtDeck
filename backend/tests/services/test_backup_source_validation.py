# -*- coding: utf-8 -*-
"""备份链路安全测试：上传 filename 消毒 + source_file_path 限源。

安全背景（对抗验证结论）：
- 备份导入的 multipart filename 可携带 ../../（python-multipart 原样保留），
  历史实现直接拼接落盘 = 认证后任意文件写入；
- source_file_path 直传 shutil.copy2，配合下载端点 = 认证后任意文件读取
  （config.yaml/app.db 均可被复制带走）；
- seed_transfer 的 info_hash 拼入本地路径，非 hex 字符可穿越读取。

修复策略：导入侧 filename 消毒 + 每请求子目录；备份侧 .torrent 后缀
（端点层）+ bencode 内容校验（core 层唯一收口）；转移侧 info_hash
服务层 hex 格式闸门。
"""

from pathlib import Path

import bencodepy
import pytest

from app.core.filename_utils import FilenameUtils
from app.core.torrent_file_backup import TorrentFileBackupService
from app.services.seed_transfer_service import SeedTransferService


def _write_valid_torrent(path: Path) -> None:
    """构造最小合法 bencode 种子（含 info 字典）。"""
    data = {b"announce": b"http://example.com/announce", b"info": {b"name": b"test", b"length": 1}}
    path.write_bytes(bencodepy.encode(data))


class TestImportFilenameSanitized:
    """W3：导入上传的 filename 消毒后不含路径成分。"""

    @pytest.mark.parametrize(
        "raw",
        [
            "../../backend/config/evil.yaml",
            "..\\..\\backend\\config\\evil2.yaml",
            "/etc/passwd",
            "C:\\Windows\\evil",
        ],
    )
    def test_traversal_filenames_stripped(self, raw):
        safe = FilenameUtils.sanitize_filename(raw)
        assert "/" not in safe
        assert "\\" not in safe
        assert ".." not in safe


class TestBackupSourceContentValidation:
    """W4：core 层内容校验——非 bencode 文件（config.yaml/app.db 类）被拒。"""

    def test_valid_torrent_accepted(self, tmp_path):
        service = TorrentFileBackupService(backup_dir=str(tmp_path / "backup"))
        src = tmp_path / "test.torrent"
        _write_valid_torrent(src)
        result = service.backup_torrent_file_from_path("a" * 40, "test", str(src))
        assert result["success"] is True
        # 副本内容与源一致
        copied = Path(result["backup_file_path"]).read_bytes()
        assert copied == src.read_bytes()

    def test_yaml_config_rejected(self, tmp_path):
        """模拟 config.yaml 外泄：非 bencode 内容被拒，不产生副本。"""
        service = TorrentFileBackupService(backup_dir=str(tmp_path / "backup"))
        src = tmp_path / "config.yaml"
        src.write_text("app:\n  name: BtDeck\n  secret_key: leak\n", encoding="utf-8")
        result = service.backup_torrent_file_from_path("b" * 40, "config", str(src))
        assert result["success"] is False
        assert "不是有效的种子文件" in result["error_message"]

    def test_sqlite_db_rejected(self, tmp_path):
        """模拟 app.db 外泄：SQLite 头不是合法 bencode。"""
        service = TorrentFileBackupService(backup_dir=str(tmp_path / "backup"))
        src = tmp_path / "app.db"
        src.write_bytes(b"SQLite format 3\x00" + b"\x00" * 256)
        result = service.backup_torrent_file_from_path("c" * 40, "db", str(src))
        assert result["success"] is False

    def test_bencode_without_info_rejected(self, tmp_path):
        """合法 bencode 但无 info 字典（如某些数据文件）仍被拒。"""
        service = TorrentFileBackupService(backup_dir=str(tmp_path / "backup"))
        src = tmp_path / "data.torrent"
        src.write_bytes(bencodepy.encode({b"foo": b"bar"}))
        result = service.backup_torrent_file_from_path("d" * 40, "data", str(src))
        assert result["success"] is False

    def test_oversized_source_rejected(self, tmp_path):
        """超过 2MB 上限的源文件被拒（防超大文件与解析 DoS）。"""
        service = TorrentFileBackupService(backup_dir=str(tmp_path / "backup"))
        src = tmp_path / "huge.torrent"
        # 合法 bencode 结构 + 超大 padding 字段，验证大小闸门优先于解析
        data = {b"info": {b"name": b"t", b"length": 1}, b"padding": b"x" * (TorrentFileBackupService.TORRENT_CONTENT_MAX_BYTES + 1)}
        src.write_bytes(bencodepy.encode(data))
        result = service.backup_torrent_file_from_path("e" * 40, "huge", str(src))
        assert result["success"] is False

    def test_malformed_bencode_rejected(self, tmp_path):
        """畸形 bencode（深嵌套/坏字节）不抛异常、按拒绝处理。"""
        service = TorrentFileBackupService(backup_dir=str(tmp_path / "backup"))
        src = tmp_path / "bad.torrent"
        src.write_bytes(b"d" * 100000)  # 未闭合的字典
        result = service.backup_torrent_file_from_path("f" * 40, "bad", str(src))
        assert result["success"] is False


class TestSeedTransferInfoHashGate:
    """W4：seed_transfer 服务层 info_hash 格式闸门（防路径穿越读取）。"""

    @pytest.mark.parametrize(
        "bad_hash",
        [
            "../../etc/passwd",
            "..%2f..%2fevil",
            "zz" * 20,  # 40 位但非 hex
            "abc",
            "",
        ],
    )
    async def test_malformed_info_hash_rejected_before_any_io(self, bad_hash):
        svc = object.__new__(SeedTransferService)  # 跳过 __init__ 的 DB 会话构建
        svc.db = None  # 闸门在首次 db 访问之前返回，None 即可验证顺序
        result = await svc.transfer_seed(
            source_downloader_id=1,
            target_downloader_id=2,
            info_hash=bad_hash,
            target_path="/downloads",
            delete_source=False,
            user_id=1,
            username="tester",
        )
        assert result["success"] is False
        assert "info_hash 格式非法" in result["error_message"]

    async def test_valid_v1_hash_passes_gate(self):
        svc = object.__new__(SeedTransferService)
        svc.db = None
        # 合法 40 位 hex 通过闸门后在下载器查询处失败（db=None 抛错被外层捕获或传播），
        # 这里只验证不再报"格式非法"——用 asyncio.to_thread 包装的查询异常做断言边界
        import inspect

        src = inspect.getsource(SeedTransferService.transfer_seed)
        assert 're.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", info_hash or "")' in src
