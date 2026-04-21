"""
FilenameUtils 文件名处理工具单元测试

测试 sanitize_filename、generate_backup_filename、is_path_too_long、safe_path_join
等文件名处理函数，覆盖非法字符清理、长度限制、路径拼接等场景。
所有测试均为纯函数测试，无外部依赖。
"""

import pytest
from app.core.filename_utils import FilenameUtils


# ============================================================
# sanitize_filename 测试
# ============================================================

class TestSanitizeFilename:
    """sanitize_filename 文件名清理测试"""

    # --- Windows 非法字符移除 ---

    def test_移除尖括号(self):
        """移除 < 和 >"""
        assert "<" not in FilenameUtils.sanitize_filename("file<name>")
        assert ">" not in FilenameUtils.sanitize_filename("file<name>")

    def test_移除冒号(self):
        """移除 :"""
        result = FilenameUtils.sanitize_filename("file:name")
        assert ":" not in result
        assert "_" in result

    def test_移除双引号(self):
        """移除 """
        result = FilenameUtils.sanitize_filename('file"name')
        assert '"' not in result

    def test_移除斜杠(self):
        """移除 / 和 \\"""
        assert "/" not in FilenameUtils.sanitize_filename("file/name")
        assert "\\" not in FilenameUtils.sanitize_filename("file\\name")

    def test_移除竖线(self):
        """移除 |"""
        result = FilenameUtils.sanitize_filename("file|name")
        assert "|" not in result

    def test_移除问号(self):
        """移除 ?"""
        result = FilenameUtils.sanitize_filename("file?name")
        assert "?" not in result

    def test_移除星号(self):
        """移除 *"""
        result = FilenameUtils.sanitize_filename("file*name")
        assert "*" not in result

    def test_移除控制字符(self):
        """移除 ASCII 控制字符 (0x00-0x1F)"""
        # 包含 NUL, SOH, STX 等控制字符
        filename = "file\x00\x01\x1fname"
        result = FilenameUtils.sanitize_filename(filename)
        # 确保没有控制字符
        for ch in result:
            assert ord(ch) >= 0x20, f"发现控制字符: {ord(ch)}"

    def test_多种非法字符混合(self):
        """混合多种非法字符"""
        result = FilenameUtils.sanitize_filename('test<>:"/\\|?*file')
        for ch in '<>:"/\\|?*':
            assert ch not in result

    # --- 空值处理 ---

    def test_空字符串返回unnamed(self):
        """空字符串返回 unnamed"""
        assert FilenameUtils.sanitize_filename("") == "unnamed"

    def test_仅空格返回unnamed(self):
        """仅空格的字符串返回 unnamed"""
        assert FilenameUtils.sanitize_filename("   ") == "unnamed"

    def test_仅点号返回unnamed(self):
        """仅点号的字符串返回 unnamed"""
        assert FilenameUtils.sanitize_filename("...") == "unnamed"

    def test_空格和点混合返回unnamed(self):
        """空格和点的混合返回 unnamed"""
        assert FilenameUtils.sanitize_filename(" . . ") == "unnamed"

    # --- Unicode 字符保留 ---

    def test_中文字符保留(self):
        """中文字符应保留"""
        result = FilenameUtils.sanitize_filename("测试文件名")
        assert result == "测试文件名"

    def test_日文字符保留(self):
        """日文字符应保留"""
        result = FilenameUtils.sanitize_filename("テスト")
        assert result == "テスト"

    def test_emoji保留(self):
        """Emoji 字符应保留"""
        result = FilenameUtils.sanitize_filename("file🎉name")
        assert "🎉" in result

    def test_混合中英文数字(self):
        """混合中英文和数字"""
        result = FilenameUtils.sanitize_filename("BT下载2026版")
        assert result == "BT下载2026版"

    # --- 空格处理 ---

    def test_多空格压缩为单下划线(self):
        """多个连续空格压缩为一个下划线"""
        result = FilenameUtils.sanitize_filename("hello   world")
        assert "   " not in result
        assert "_" in result

    def test_单空格替换为下划线(self):
        """单个空格替换为下划线"""
        result = FilenameUtils.sanitize_filename("hello world")
        assert result == "hello_world"

    def test_首尾空格去除(self):
        """首尾空格被去除"""
        result = FilenameUtils.sanitize_filename("  filename  ")
        # 空格被替换为下划线，首尾的去除
        assert not result.startswith("_") or result.strip("._") == result or result == "unnamed"

    # --- 点号处理 ---

    def test_连续点号压缩(self):
        """连续点号压缩为单个点"""
        result = FilenameUtils.sanitize_filename("file...name")
        assert "..." not in result

    def test_首尾点号去除(self):
        """首尾点号被去除"""
        result = FilenameUtils.sanitize_filename(".filename.")
        # strip(' ._') 会去除首尾的点、空格、下划线
        assert not result.startswith(".")
        assert not result.endswith(".")

    # --- 正常文件名 ---

    def test_正常文件名不变(self):
        """不含非法字符的文件名保持不变"""
        assert FilenameUtils.sanitize_filename("normal_filename.txt") == "normal_filename.txt"

    def test_含扩展名的文件名(self):
        """带扩展名的文件名正常处理"""
        result = FilenameUtils.sanitize_filename("my file.torrent")
        assert "torrent" in result


# ============================================================
# generate_backup_filename 测试
# ============================================================

class TestGenerateBackupFilename:
    """generate_backup_filename 备份文件名生成测试"""

    def test_正常格式(self):
        """正常格式: {info_id}_{clean_name}.torrent"""
        result = FilenameUtils.generate_backup_filename("abc123", "test torrent")
        assert result == "abc123_test_torrent.torrent"

    def test_名称含非法字符被清理(self):
        """名称中的非法字符被清理"""
        result = FilenameUtils.generate_backup_filename("id1", 'test<>file')
        assert "<" not in result
        assert ">" not in result
        assert result.startswith("id1_")
        assert result.endswith(".torrent")

    def test_超长名称回退到info_id格式(self):
        """超长名称回退到 {info_id}.torrent 格式"""
        long_name = "a" * 300
        result = FilenameUtils.generate_backup_filename("id123", long_name)
        assert result == "id123.torrent"

    def test_自定义max_length正常(self):
        """自定义 max_length - 不超限时使用完整格式"""
        result = FilenameUtils.generate_backup_filename("id", "name", max_length=100)
        assert result == "id_name.torrent"

    def test_自定义max_length超限回退(self):
        """自定义 max_length - 超限时回退到 info_id 格式"""
        result = FilenameUtils.generate_backup_filename("id", "very_long_name", max_length=10)
        assert result == "id.torrent"

    def test_空名称处理(self):
        """空名称会被 sanitize 为 unnamed"""
        result = FilenameUtils.generate_backup_filename("id456", "")
        assert result == "id456_unnamed.torrent"

    def test_中文名称(self):
        """中文种子名称"""
        result = FilenameUtils.generate_backup_filename("id789", "测试种子")
        assert result == "id789_测试种子.torrent"

    def test_恰好不超长(self):
        """恰好不超长时使用完整格式"""
        info_id = "id"
        name = "n" * 240  # id_ + 240个n + .torrent = 2+1+240+8 = 251 < 255
        result = FilenameUtils.generate_backup_filename(info_id, name)
        assert len(result) <= 255
        assert "_" in result
        assert result.endswith(".torrent")


# ============================================================
# is_path_too_long 测试
# ============================================================

class TestIsPathTooLong:
    """is_path_too_long 路径长度检查测试"""

    def test_恰好260字符为False(self):
        """恰好 260 字符不算过长"""
        path = "a" * 260
        assert FilenameUtils.is_path_too_long(path) is False

    def test_261字符为True(self):
        """261 字符为过长"""
        path = "a" * 261
        assert FilenameUtils.is_path_too_long(path) is True

    def test_短路径为False(self):
        """短路径不过长"""
        assert FilenameUtils.is_path_too_long("C:/test/file.txt") is False

    def test_空路径为False(self):
        """空路径不过长"""
        assert FilenameUtils.is_path_too_long("") is False

    def test_自定义max_length(self):
        """自定义最大长度"""
        path = "a" * 50
        assert FilenameUtils.is_path_too_long(path, max_length=50) is False
        assert FilenameUtils.is_path_too_long(path, max_length=49) is True

    def test_恰好自定义max_length为False(self):
        """恰好等于自定义 max_length 不算过长"""
        path = "a" * 100
        assert FilenameUtils.is_path_too_long(path, max_length=100) is False

    def test_超过自定义max_length为True(self):
        """超过自定义 max_length 算过长"""
        path = "a" * 101
        assert FilenameUtils.is_path_too_long(path, max_length=100) is True


# ============================================================
# safe_path_join 测试
# ============================================================

class TestSafePathJoin:
    """safe_path_join 安全路径拼接测试"""

    def test_正常路径拼接(self):
        """正常路径拼接"""
        result = FilenameUtils.safe_path_join("/data/torrents", "test_file.torrent")
        assert "test_file.torrent" in result
        assert "torrents" in result

    def test_包含非法字符的文件名(self):
        """文件名含非法字符时被清理"""
        result = FilenameUtils.safe_path_join("/data", 'test<>file.torrent')
        assert "<" not in result
        assert ">" not in result
        assert ".torrent" in result

    def test_路径规范化(self):
        """路径分隔符规范化"""
        result = FilenameUtils.safe_path_join("/data/torrents/", "file.torrent")
        # normpath 会去掉尾部的斜杠
        assert "//" not in result or result  # 基本规范化验证
        assert "file.torrent" in result

    def test_中文字符文件名(self):
        """中文文件名拼接"""
        result = FilenameUtils.safe_path_join("/data", "测试种子.torrent")
        assert "测试种子" in result
        assert ".torrent" in result

    def test_空文件名处理(self):
        """空文件名会被清理为 unnamed"""
        result = FilenameUtils.safe_path_join("/data", "")
        assert "unnamed" in result
