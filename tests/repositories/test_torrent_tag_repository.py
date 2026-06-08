# -*- coding: utf-8 -*-
"""
TorrentTagRepository 的单元测试

测试标签仓储的同步方法，重点关注：
- find_all_tags: 查询所有标签（跨下载器聚合）
- find_all_tag_names_by_type: 查询指定类型的标签名称（去重）

所有数据库操作通过内存数据库隔离测试。
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.torrent_tag_repository import TorrentTagRepository
from app.models.torrent_tags import TorrentTag
from app.database import Base


# ==================== 测试夹具 ====================

@pytest.fixture
def in_memory_db():
    """创建内存数据库"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(in_memory_db):
    """创建数据库会话"""
    Session = sessionmaker(bind=in_memory_db)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def repository(db_session):
    """创建Repository实例"""
    return TorrentTagRepository(db_session)


@pytest.fixture
def sample_tags(db_session):
    """创建测试数据：多个下载器的标签"""
    tags = [
        # 下载器1的分类
        TorrentTag(
            tag_id="tag-001",
            downloader_id="dl-001",
            tag_name="电影",
            tag_type="category",
            color="#FF5733",
            dr=0
        ),
        TorrentTag(
            tag_id="tag-002",
            downloader_id="dl-001",
            tag_name="剧集",
            tag_type="category",
            color="#33FF57",
            dr=0
        ),
        # 下载器1的标签
        TorrentTag(
            tag_id="tag-003",
            downloader_id="dl-001",
            tag_name="PT",
            tag_type="tag",
            color="#3357FF",
            dr=0
        ),
        # 下载器2的分类（包含重复）
        TorrentTag(
            tag_id="tag-004",
            downloader_id="dl-002",
            tag_name="电影",  # 重复
            tag_type="category",
            color="#FF5733",
            dr=0
        ),
        TorrentTag(
            tag_id="tag-005",
            downloader_id="dl-002",
            tag_name="音乐",
            tag_type="category",
            color="#F3FF33",
            dr=0
        ),
        # 下载器2的标签（包含重复）
        TorrentTag(
            tag_id="tag-006",
            downloader_id="dl-002",
            tag_name="PT",  # 重复
            tag_type="tag",
            color="#3357FF",
            dr=0
        ),
        # 已删除的标签
        TorrentTag(
            tag_id="tag-007",
            downloader_id="dl-003",
            tag_name="已删除",
            tag_type="tag",
            color="#CCCCCC",
            dr=1  # 已删除
        ),
    ]

    db_session.add_all(tags)
    db_session.commit()
    return tags


# ==================== find_all_tags 测试 ====================

class TestFindAllTags:
    """测试 find_all_tags 方法"""

    def test_find_all_tags_success(self, repository, sample_tags):
        """测试成功获取所有标签"""
        result = repository.find_all_tags()

        # 验证返回所有未删除的标签（不包括已删除的）
        assert len(result) == 6  # 7个总数 - 1个已删除

        # 验证包含重复标签
        tag_names = [tag.tag_name for tag in result]
        assert tag_names.count("电影") == 2  # 两个下载器都有
        assert tag_names.count("PT") == 2
        assert "剧集" in tag_names
        assert "音乐" in tag_names

    def test_find_all_tags_with_category_filter(self, repository, sample_tags):
        """测试按类型筛选为分类"""
        result = repository.find_all_tags(tag_type="category")

        # 验证只返回分类类型
        assert len(result) == 4  # 电影(2) + 剧集(1) + 音乐(1)
        for tag in result:
            assert tag.tag_type == "category"

        tag_names = [tag.tag_name for tag in result]
        assert "电影" in tag_names
        assert "剧集" in tag_names
        assert "音乐" in tag_names
        assert "PT" not in tag_names  # 不是分类

    def test_find_all_tags_with_tag_filter(self, repository, sample_tags):
        """测试按类型筛选为标签"""
        result = repository.find_all_tags(tag_type="tag")

        # 验证只返回标签类型
        assert len(result) == 2  # PT(2)
        for tag in result:
            assert tag.tag_type == "tag"

        tag_names = [tag.tag_name for tag in result]
        assert "PT" in tag_names
        assert "电影" not in tag_names  # 不是标签

    def test_find_all_tags_include_deleted(self, repository, sample_tags):
        """测试包含已删除标签"""
        result = repository.find_all_tags(include_deleted=True)

        # 验证包含所有标签（包括已删除的）
        assert len(result) == 7  # 所有标签

        tag_names = [tag.tag_name for tag in result]
        assert "已删除" in tag_names

    def test_find_all_tags_ordering(self, repository, sample_tags):
        """测试按标签名称排序"""
        result = repository.find_all_tags()

        tag_names = [tag.tag_name for tag in result]
        # 验证按字母顺序排列
        assert tag_names == sorted(tag_names)

    def test_find_all_tags_empty_database(self, repository):
        """测试空数据库"""
        result = repository.find_all_tags()

        assert result == []

    def test_find_all_tags_database_error(self, repository):
        """测试数据库错误处理"""
        # 模拟数据库错误
        repository.db.query = MagicMock(side_effect=SQLAlchemyError("数据库连接失败"))

        result = repository.find_all_tags()

        # 验证返回空列表而不是抛出异常
        assert result == []


# ==================== find_all_tag_names_by_type 测试 ====================

class TestFindAllTagNamesByType:
    """测试 find_all_tag_names_by_type 方法"""

    def test_find_all_category_names(self, repository, sample_tags):
        """测试获取所有分类名称"""
        result = repository.find_all_tag_names_by_type(tag_type="category")

        # 验证返回去重后的分类名称
        assert len(result) == 3  # 电影、剧集、音乐（去重）
        assert "电影" in result
        assert "剧集" in result
        assert "音乐" in result
        # 验证去重
        assert result.count("电影") == 1

    def test_find_all_tag_names(self, repository, sample_tags):
        """测试获取所有标签名称"""
        result = repository.find_all_tag_names_by_type(tag_type="tag")

        # 验证返回去重后的标签名称
        assert len(result) == 1  # PT（去重）
        assert "PT" in result
        # 验证去重
        assert result.count("PT") == 1

    def test_find_all_tag_names_ordering(self, repository, sample_tags):
        """测试按名称排序"""
        result = repository.find_all_tag_names_by_type(tag_type="category")

        # 验证按字母顺序排列
        assert result == sorted(result)

    def test_find_all_tag_names_exclude_deleted(self, repository, sample_tags):
        """测试排除已删除标签"""
        result = repository.find_all_tag_names_by_type(tag_type="tag")

        # 验证不包含已删除的标签
        assert "已删除" not in result

    def test_find_all_tag_names_include_deleted(self, repository, sample_tags):
        """测试包含已删除标签"""
        result = repository.find_all_tag_names_by_type(tag_type="tag", include_deleted=True)

        # 验证包含已删除的标签
        assert "已删除" in result
        assert "PT" in result

    def test_find_all_tag_names_empty_database(self, repository):
        """测试空数据库"""
        result = repository.find_all_tag_names_by_type(tag_type="category")

        assert result == []

    def test_find_all_tag_names_invalid_type(self, repository):
        """测试无效的标签类型"""
        # 传入不存在的类型应该返回空列表
        result = repository.find_all_tag_names_by_type(tag_type="invalid")

        assert result == []

    def test_find_all_tag_names_database_error(self, repository):
        """测试数据库错误处理"""
        # 模拟数据库错误
        repository.db.query = MagicMock(side_effect=SQLAlchemyError("数据库查询失败"))

        result = repository.find_all_tag_names_by_type(tag_type="category")

        # 验证返回空列表而不是抛出异常
        assert result == []


# ==================== 边界条件测试 ====================

class TestEdgeCases:
    """测试边界条件"""

    def test_find_all_tags_with_soft_deleted_only(self, repository, db_session):
        """测试只有已删除标签的情况"""
        # 创建只有已删除标签的数据库
        deleted_tag = TorrentTag(
            tag_id="tag-deleted",
            downloader_id="dl-001",
            tag_name="已删除",
            tag_type="tag",
            color="#CCCCCC",
            dr=1
        )
        db_session.add(deleted_tag)
        db_session.commit()

        result = repository.find_all_tags()

        # 默认情况下应该返回空列表
        assert result == []

    def test_find_all_tag_names_unicode(self, repository, db_session):
        """测试Unicode字符处理"""
        unicode_tags = [
            TorrentTag(
                tag_id="tag-001",
                downloader_id="dl-001",
                tag_name="日语标签",
                tag_type="category",
                color="#FF5733",
                dr=0
            ),
            TorrentTag(
                tag_id="tag-002",
                downloader_id="dl-001",
                tag_name="标签测试",
                tag_type="category",
                color="#33FF57",
                dr=0
            ),
            TorrentTag(
                tag_id="tag-003",
                downloader_id="dl-001",
                tag_name="Emoji😀标签",
                tag_type="category",
                color="#3357FF",
                dr=0
            ),
        ]

        db_session.add_all(unicode_tags)
        db_session.commit()

        result = repository.find_all_tag_names_by_type(tag_type="category")

        # 验证Unicode字符正确处理
        assert len(result) == 3
        assert "日语标签" in result
        assert "标签测试" in result
        assert "Emoji😀标签" in result
