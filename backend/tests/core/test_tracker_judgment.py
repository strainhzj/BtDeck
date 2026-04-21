"""
Tracker判断引擎单元测试

测试 TrackerJudgmentEngine 的核心功能：
- 关键词匹配（精确短语、大小写不敏感）
- 批量关键词匹配
- 状态判断（失败优先策略）
- 缓存刷新机制
- 缓存统计信息
"""

import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# 在模块级别 mock 数据库连接，防止 TrackerJudgmentEngine 全局实例化时连接真实数据库
# 注意：tracker_judgment 模块从 app.database 导入 SessionLocal（第28行）
# 模块末尾有 `judgment_engine = TrackerJudgmentEngine()`（第435行）
# 必须在 import 该模块之前 mock 掉 app.database.SessionLocal（原始导入源）
with patch("app.database.SessionLocal"):
    from app.core.tracker_judgment import TrackerJudgmentEngine, TrackerStatus


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def engine():
    """创建不自动加载关键词的引擎实例"""
    return TrackerJudgmentEngine(cache_ttl=3600, auto_load=False)


@pytest.fixture
def engine_with_keywords(engine):
    """手动设置关键词缓存的引擎实例"""
    engine.keyword_cache = {
        "candidate": [],
        "ignored": ["bad gateway", "connection reset"],
        "success": ["success", "ok", "announce successful", "worked"],
        "failed": ["timeout", "refused", "unreachable", "error", "fail"],
    }
    engine.last_cache_update = datetime.now()
    return engine


@pytest.fixture
def engine_with_language_keywords(engine):
    """带语言分组关键词的引擎实例"""
    engine.keyword_cache = {
        "candidate": [],
        "ignored": ["bad gateway"],
        "success": ["success", "ok"],
        "failed": ["timeout", "refused"],
    }
    engine.keyword_cache_by_language = {
        "zh_CN": {
            "candidate": [],
            "ignored": ["连接重置"],
            "success": ["成功", "正常"],
            "failed": ["超时", "拒绝"],
        },
        "en_US": {
            "candidate": [],
            "ignored": ["bad gateway"],
            "success": ["success", "ok"],
            "failed": ["timeout", "refused"],
        },
    }
    engine.last_cache_update = datetime.now()
    return engine


# ============================================================
# Test _match_keyword
# ============================================================


class TestMatchKeyword:
    """单个关键词匹配测试"""

    def test_精确短语匹配(self, engine):
        """消息中包含完整关键词时返回 True"""
        assert engine._match_keyword("success", "Download success") is True

    def test_不包含关键词返回False(self, engine):
        """消息中不包含关键词时返回 False"""
        assert engine._match_keyword("success", "Download failed") is False

    def test_大小写不敏感(self, engine):
        """匹配不区分大小写"""
        assert engine._match_keyword("SUCCESS", "download success") is True
        assert engine._match_keyword("success", "DOWNLOAD SUCCESS") is True
        assert engine._match_keyword("Success", "download SUCCESS") is True

    def test_空消息返回False(self, engine):
        """空消息返回 False"""
        assert engine._match_keyword("success", "") is False

    def test_空关键词返回False(self, engine):
        """空关键词返回 False"""
        assert engine._match_keyword("", "some message") is False

    def test_两者都为空返回False(self, engine):
        """关键词和消息都为空时返回 False"""
        assert engine._match_keyword("", "") is False

    def test_中文关键词匹配(self, engine):
        """支持中文关键词匹配"""
        assert engine._match_keyword("超时", "连接超时") is True

    def test_部分匹配也算成功(self, engine):
        """简单包含匹配，子串也算匹配"""
        assert engine._match_keyword("time", "Connection timed out") is True


# ============================================================
# Test _match_any_keyword
# ============================================================


class TestMatchAnyKeyword:
    """批量关键词匹配测试"""

    def test_多个关键词中第一个匹配(self, engine):
        """第一个关键词匹配即返回 True"""
        assert engine._match_any_keyword(["success", "ok"], "Download success") is True

    def test_多个关键词中第二个匹配(self, engine):
        """第二个关键词匹配也返回 True"""
        assert engine._match_any_keyword(["success", "ok"], "Everything ok") is True

    def test_无匹配返回False(self, engine):
        """没有任何关键词匹配时返回 False"""
        assert engine._match_any_keyword(["success", "ok"], "Unknown status") is False

    def test_空关键词列表返回False(self, engine):
        """空关键词列表返回 False"""
        assert engine._match_any_keyword([], "some message") is False

    def test_空消息返回False(self, engine):
        """空消息返回 False"""
        assert engine._match_any_keyword(["success"], "") is False

    def test_关键词列表和消息都为空返回False(self, engine):
        """关键词列表和消息都为空返回 False"""
        assert engine._match_any_keyword([], "") is False


# ============================================================
# Test judge_status
# ============================================================


class TestJudgeStatus:
    """状态判断测试（失败优先策略）"""

    def test_包含失败关键词返回工作失败(self, engine_with_keywords):
        """消息包含失败关键词时返回 '工作失败'"""
        result = engine_with_keywords.judge_status("工作中", "Connection timeout")
        assert result == TrackerStatus.FAILED

    def test_包含成功关键词返回工作中(self, engine_with_keywords):
        """消息包含成功关键词（无失败）时返回 '工作中'"""
        result = engine_with_keywords.judge_status("未联系", "Download success")
        assert result == TrackerStatus.WORKING

    def test_无匹配返回原始状态(self, engine_with_keywords):
        """无关键词匹配时返回原始状态"""
        result = engine_with_keywords.judge_status("未联系", "Unknown status message")
        assert result == "未联系"

    def test_空消息返回原始状态(self, engine_with_keywords):
        """空消息直接返回原始状态"""
        result = engine_with_keywords.judge_status("工作中", "")
        assert result == "工作中"

    def test_失败优先于成功(self, engine_with_keywords):
        """消息同时包含失败和成功关键词时，失败优先"""
        # "timeout" 在 failed 中, "success" 在 success 中
        result = engine_with_keywords.judge_status(
            "工作中", "timeout but success in message"
        )
        assert result == TrackerStatus.FAILED

    def test_忽略池也算失败(self, engine_with_keywords):
        """ignored 池中的关键词也触发 '工作失败'"""
        result = engine_with_keywords.judge_status("工作中", "bad gateway detected")
        assert result == TrackerStatus.FAILED

    def test_指定语言池匹配(self, engine_with_language_keywords):
        """指定 language 时使用对应语言池的关键词"""
        result = engine_with_language_keywords.judge_status(
            "工作中", "连接超时", language="zh_CN"
        )
        assert result == TrackerStatus.FAILED

    def test_指定语言池匹配成功关键词(self, engine_with_language_keywords):
        """指定语言时匹配成功关键词"""
        result = engine_with_language_keywords.judge_status(
            "未联系", "announce 成功", language="zh_CN"
        )
        assert result == TrackerStatus.WORKING

    def test_指定语言池不存在时使用通用池(self, engine_with_language_keywords):
        """指定的语言不存在时回退到通用池"""
        result = engine_with_language_keywords.judge_status(
            "未联系", "Download success", language="fr_FR"
        )
        assert result == TrackerStatus.WORKING

    def test_不指定语言使用通用池(self, engine_with_language_keywords):
        """不指定 language 时使用通用池"""
        result = engine_with_language_keywords.judge_status("未联系", "success")
        assert result == TrackerStatus.WORKING

    def test_缓存未加载时自动触发加载(self, engine):
        """缓存未加载时调用 judge_status 会触发 _ensure_cache_loaded"""
        with patch.object(engine, "load_keywords", return_value=True) as mock_load:
            engine.judge_status("工作中", "some message")
            # load_keywords 会被调用：_ensure_cache_loaded 调用一次，
            # 如果缓存未刷新成功，judge_status 内部还可能再次调用
            assert mock_load.call_count >= 1


# ============================================================
# Test _should_refresh_cache
# ============================================================


class TestShouldRefreshCache:
    """缓存刷新判断测试"""

    def test_无缓存时间返回True(self, engine):
        """last_cache_update 为 None 时需要刷新"""
        engine.last_cache_update = None
        assert engine._should_refresh_cache() is True

    def test_缓存未过期返回False(self, engine):
        """缓存未过期时不需要刷新"""
        engine.last_cache_update = datetime.now()
        engine.cache_ttl = 3600
        assert engine._should_refresh_cache() is False

    def test_缓存已过期返回True(self, engine):
        """缓存已过期时需要刷新"""
        engine.last_cache_update = datetime.now() - timedelta(seconds=7200)
        engine.cache_ttl = 3600
        assert engine._should_refresh_cache() is True


# ============================================================
# Test get_cache_stats
# ============================================================


class TestGetCacheStats:
    """缓存统计信息测试"""

    def test_返回正确结构(self, engine_with_keywords):
        """统计信息包含所有必需字段"""
        stats = engine_with_keywords.get_cache_stats()
        assert "success_count" in stats
        assert "failed_count" in stats
        assert "ignored_count" in stats
        assert "candidate_count" in stats
        assert "language_count" in stats
        assert "last_cache_update" in stats
        assert "cache_ttl_seconds" in stats
        assert "is_cache_expired" in stats

    def test_关键词数量正确(self, engine_with_keywords):
        """统计数量与设置的关键词数量一致"""
        stats = engine_with_keywords.get_cache_stats()
        assert stats["success_count"] == 4
        assert stats["failed_count"] == 5
        assert stats["ignored_count"] == 2
        assert stats["candidate_count"] == 0

    def test_缓存未加载时统计为零(self, engine):
        """未加载关键词时数量都为 0"""
        stats = engine.get_cache_stats()
        assert stats["success_count"] == 0
        assert stats["failed_count"] == 0
        assert stats["last_cache_update"] is None

    def test_带语言分组统计(self, engine_with_language_keywords):
        """语言分组数量正确"""
        stats = engine_with_language_keywords.get_cache_stats()
        assert stats["language_count"] == 2


# ============================================================
# Test load_keywords
# ============================================================


class TestLoadKeywords:
    """数据库加载关键词测试"""

    @patch("app.database.SessionLocal")
    def test_成功加载关键词(self, mock_session_local):
        """从数据库成功加载关键词后缓存正确填充"""
        # 构造 mock 数据库返回
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        keyword_success = MagicMock()
        keyword_success.keyword_type = "success"
        keyword_success.keyword = "success"
        keyword_success.language = None

        keyword_failed = MagicMock()
        keyword_failed.keyword_type = "failed"
        keyword_failed.keyword = "timeout"
        keyword_failed.language = "zh_CN"

        mock_db.query.return_value.filter.return_value.all.return_value = [
            keyword_success,
            keyword_failed,
        ]

        engine = TrackerJudgmentEngine(cache_ttl=3600, auto_load=False)
        result = engine.load_keywords()

        assert result is True
        assert "success" in engine.keyword_cache["success"]
        assert "timeout" in engine.keyword_cache["failed"]
        assert "timeout" in engine.keyword_cache_by_language["zh_CN"]["failed"]
        assert engine.last_cache_update is not None
        mock_db.close.assert_called_once()

    @patch("app.database.SessionLocal")
    def test_数据库异常返回False(self, mock_session_local):
        """数据库查询异常时返回 False"""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.side_effect = Exception("DB connection error")

        engine = TrackerJudgmentEngine(cache_ttl=3600, auto_load=False)
        result = engine.load_keywords()
        assert result is False

    @patch("app.database.SessionLocal")
    def test_空数据库结果(self, mock_session_local):
        """数据库无记录时缓存为空但加载成功"""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = []

        engine = TrackerJudgmentEngine(cache_ttl=3600, auto_load=False)
        result = engine.load_keywords()

        assert result is True
        assert engine.keyword_cache["success"] == []
        assert engine.keyword_cache["failed"] == []


# ============================================================
# Test 手动缓存操作
# ============================================================


class TestManualCache:
    """手动设置缓存后 judge_status 行为测试"""

    def test_手动设置缓存后判断成功(self, engine):
        """手动设置关键词缓存后可以直接使用"""
        engine.keyword_cache = {
            "candidate": [],
            "ignored": [],
            "success": ["worked"],
            "failed": ["unreachable"],
        }
        engine.last_cache_update = datetime.now()

        result = engine.judge_status("未联系", "It worked perfectly")
        assert result == TrackerStatus.WORKING

    def test_手动设置缓存后判断失败(self, engine):
        """手动设置关键词缓存后判定失败"""
        engine.keyword_cache = {
            "candidate": [],
            "ignored": [],
            "success": ["worked"],
            "failed": ["unreachable"],
        }
        engine.last_cache_update = datetime.now()

        result = engine.judge_status("工作中", "Host unreachable")
        assert result == TrackerStatus.FAILED

    def test_refresh_cache调用load_keywords(self, engine):
        """refresh_cache 委托给 load_keywords"""
        with patch.object(engine, "load_keywords", return_value=True) as mock_load:
            result = engine.refresh_cache()
            assert result is True
            mock_load.assert_called_once()
