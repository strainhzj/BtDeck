# -*- coding: utf-8 -*-
"""
标签管理API新端点的集成测试

测试新增的跨下载器聚合接口：
- GET /tags/all - 获取所有标签
- GET /tags/categories - 获取所有分类名称
- GET /tags/tags - 获取所有标签名称

使用 FastAPI TestClient 进行完整的HTTP请求测试。
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base
from app.models.torrent_tags import TorrentTag
from app.services.tag_service import TagService


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
            tag_name="电影",
            tag_type="category",
            color="#FF5733",
            dr=0
        ),
        # 已删除的标签
        TorrentTag(
            tag_id="tag-999",
            downloader_id="dl-003",
            tag_name="已删除",
            tag_type="tag",
            color="#CCCCCC",
            dr=1
        ),
    ]

    db_session.add_all(tags)
    db_session.commit()
    return tags


@pytest.fixture
def client(db_session):
    """创建测试客户端，注入真实数据库会话"""
    def override_get_db():
        yield db_session

    from app.api.endpoints.tag_management import get_db
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def mock_auth():
    """模拟JWT认证"""
    with patch("app.api.endpoints.tag_management.verify_token_and_get_user", return_value="admin"):
        yield


# ==================== GET /tags/all 测试 ====================

class TestGetAllTagsEndpoint:
    """测试 GET /tags/all 端点"""

    def test_get_all_tags_success(self, client, mock_auth, sample_tags):
        """成功获取所有标签（去重）"""
        response = client.get(
            "/tags/all",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["code"] == "200"
        assert data["total_count"] == 3  # 电影、剧集、PT（去重）

        # 验证返回数据结构
        assert "data" in data
        assert len(data["data"]) == 3

        # 验证去重（电影只出现一次）
        movie_count = sum(1 for tag in data["data"] if tag["tag_name"] == "电影")
        assert movie_count == 1

    def test_get_all_tags_with_category_filter(self, client, mock_auth, sample_tags):
        """按分类类型筛选"""
        response = client.get(
            "/tags/all?tag_type=category",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["total_count"] == 2  # 电影、剧集

        # 验证所有结果都是category类型
        for tag in data["data"]:
            assert tag["tag_type"] == "category"

    def test_get_all_tags_with_tag_filter(self, client, mock_auth, sample_tags):
        """按标签类型筛选"""
        response = client.get(
            "/tags/all?tag_type=tag",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["total_count"] == 1  # PT

        # 验证所有结果都是tag类型
        for tag in data["data"]:
            assert tag["tag_type"] == "tag"

    def test_get_all_tags_no_auth(self, client, sample_tags):
        """无认证token"""
        with patch("app.api.endpoints.tag_management.verify_token_and_get_user", return_value=None):
            response = client.get("/tags/all")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "error"
        assert data["code"] == "401"

    def test_get_all_tags_invalid_tag_type(self, client, mock_auth, sample_tags):
        """无效的标签类型"""
        response = client.get(
            "/tags/all?tag_type=invalid",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "error"
        assert "无效的标签类型" in data["msg"]


# ==================== GET /tags/categories 测试 ====================

class TestGetCategoriesEndpoint:
    """测试 GET /tags/categories 端点"""

    def test_get_categories_success(self, client, mock_auth, sample_tags):
        """成功获取所有分类名称"""
        response = client.get(
            "/tags/categories",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["code"] == "200"
        assert data["total_count"] == 2  # 电影、剧集（去重）

        # 验证返回的是名称列表
        assert isinstance(data["data"], list)
        assert "电影" in data["data"]
        assert "剧集" in data["data"]
        # 验证去重
        assert data["data"].count("电影") == 1

    def test_get_categories_no_auth(self, client, sample_tags):
        """无认证token"""
        with patch("app.api.endpoints.tag_management.verify_token_and_get_user", return_value=None):
            response = client.get("/tags/categories")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "error"
        assert data["code"] == "401"

    def test_get_categories_empty_result(self, client, mock_auth, db_session):
        """空分类列表"""
        # 清空数据库
        db_session.query(TorrentTag).delete()
        db_session.commit()

        response = client.get(
            "/tags/categories",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["total_count"] == 0
        assert data["data"] == []


# ==================== GET /tags/tags 测试 ====================

class TestGetTagNamesEndpoint:
    """测试 GET /tags/tags 端点"""

    def test_get_tags_success(self, client, mock_auth, sample_tags):
        """成功获取所有标签名称"""
        response = client.get(
            "/tags/tags",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["code"] == "200"
        assert data["total_count"] == 1  # PT

        # 验证返回的是名称列表
        assert isinstance(data["data"], list)
        assert "PT" in data["data"]

    def test_get_tags_no_auth(self, client, sample_tags):
        """无认证token"""
        with patch("app.api.endpoints.tag_management.verify_token_and_get_user", return_value=None):
            response = client.get("/tags/tags")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "error"
        assert data["code"] == "401"

    def test_get_tags_empty_result(self, client, mock_auth, db_session):
        """空标签列表"""
        # 清空数据库
        db_session.query(TorrentTag).delete()
        db_session.commit()

        response = client.get(
            "/tags/tags",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["total_count"] == 0
        assert data["data"] == []


# ==================== 边界条件测试 ====================

class TestEdgeCases:
    """测试边界条件"""

    def test_unicode_tag_names(self, client, mock_auth, db_session):
        """测试Unicode字符处理"""
        unicode_tags = [
            TorrentTag(
                tag_id="tag-001",
                downloader_id="dl-001",
                tag_name="日语タグ",
                tag_type="category",
                color="#FF5733",
                dr=0
            ),
            TorrentTag(
                tag_id="tag-002",
                downloader_id="dl-001",
                tag_name="Emoji😀标签",
                tag_type="tag",
                color="#33FF57",
                dr=0
            ),
        ]

        db_session.add_all(unicode_tags)
        db_session.commit()

        # 测试分类接口
        response = client.get(
            "/tags/categories",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "日语タグ" in data["data"]

        # 测试标签接口
        response = client.get(
            "/tags/tags",
            headers={"x-access-token": "valid_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "Emoji😀标签" in data["data"]

    def test_large_dataset_performance(self, client, mock_auth, db_session):
        """测试大数据集性能"""
        # 创建100个标签
        tags = []
        for i in range(100):
            tags.append(TorrentTag(
                tag_id=f"tag-{i:03d}",
                downloader_id="dl-001",
                tag_name=f"标签{i}",
                tag_type="category" if i % 2 == 0 else "tag",
                color="#FF5733",
                dr=0
            ))

        db_session.add_all(tags)
        db_session.commit()

        # 测试查询性能
        import time
        start_time = time.time()

        response = client.get(
            "/tags/all",
            headers={"x-access-token": "valid_token"}
        )

        elapsed_time = time.time() - start_time

        assert response.status_code == 200
        data = response.json()

        assert data["total_count"] == 100
        # 验证查询时间合理（<1秒）
        assert elapsed_time < 1.0

    def test_concurrent_requests(self, client, mock_auth, sample_tags):
        """测试并发请求"""
        import threading
        results = []

        def make_request():
            response = client.get(
                "/tags/categories",
                headers={"x-access-token": "valid_token"}
            )
            results.append(response.json())

        # 模拟10个并发请求
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 验证所有请求都成功
        assert len(results) == 10
        for result in results:
            assert result["status"] == "success"
            assert result["total_count"] == 2  # 电影、剧集


# ==================== 错误处理测试 ====================

class TestErrorHandling:
    """测试错误处理"""

    def test_database_error_handling(self, client, mock_auth):
        """测试数据库错误处理"""
        # 模拟数据库错误
        with patch("app.services.tag_service.TagService.get_all_tag_names") as mock_service:
            mock_service.side_effect = Exception("数据库连接失败")

            response = client.get(
                "/tags/categories",
                headers={"x-access-token": "valid_token"}
            )

            assert response.status_code == 500
            data = response.json()

            assert data["status"] == "error"
            assert "数据库连接失败" in data["msg"]

    def test_service_error_handling(self, client, mock_auth):
        """测试服务层错误处理"""
        with patch("app.services.tag_service.TagService.get_all_tag_names") as mock_service:
            # 模拟服务层返回失败
            mock_service.return_value = {
                "success": False,
                "message": "服务层错误",
                "data": None
            }

            response = client.get(
                "/tags/categories",
                headers={"x-access-token": "valid_token"}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "error"
            assert "服务层错误" in data["msg"]
