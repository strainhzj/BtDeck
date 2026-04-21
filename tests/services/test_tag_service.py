# -*- coding: utf-8 -*-
"""
TagService 的单元测试

测试标签管理服务的同步方法，包括：
- create_tag / get_tag_list / update_tag / delete_tag
- assign_tags_to_torrent / remove_tags_from_torrent
- _to_dict / _to_response 私有转换方法

所有 Repository 层依赖通过 mock 隔离。
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.services.tag_service import TagService
from app.models.torrent_tags import TorrentTag, TorrentTagRelation
from app.core.database_result import DatabaseResult


# ==================== 辅助工具 ====================

class _FakeTag:
    """轻量级标签对象，用于替代 SQLAlchemy 模型实例，避免 ORM 初始化依赖"""
    def __init__(
        self,
        tag_id="tag-001",
        downloader_id="dl-001",
        tag_name="测试标签",
        tag_type="tag",
        color="#FF5733",
        created_at=None,
        updated_at=None,
    ):
        self.tag_id = tag_id
        self.downloader_id = downloader_id
        self.tag_name = tag_name
        self.tag_type = tag_type
        self.color = color
        self.created_at = created_at or datetime(2026, 1, 1, 12, 0, 0)
        self.updated_at = updated_at or datetime(2026, 1, 1, 12, 0, 0)
        self.dr = 0


class _FakeRelation:
    """轻量级关联对象，替代 TorrentTagRelation"""
    def __init__(
        self,
        relation_id="rel-001",
        downloader_id="dl-001",
        torrent_hash="abc123",
        tag_id="tag-001",
        assigned_at=None,
    ):
        self.relation_id = relation_id
        self.downloader_id = downloader_id
        self.torrent_hash = torrent_hash
        self.tag_id = tag_id
        self.assigned_at = assigned_at or datetime(2026, 1, 1, 12, 0, 0)
        self.dr = 0


def make_tag(**kwargs):
    """创建测试用标签对象"""
    return _FakeTag(**kwargs)


def make_relation(**kwargs):
    """创建测试用关联对象"""
    return _FakeRelation(**kwargs)


# ==================== Fixtures ====================

@pytest.fixture
def mock_repo():
    """创建 mock Repository"""
    return MagicMock()


@pytest.fixture
def tag_service(mock_repo):
    """
    创建 TagService 实例，注入 mock 的同步 Session。
    通过 patch 把 Repository 替换为 mock，避免真实 DB 操作。
    """
    mock_db = MagicMock()
    with patch("app.services.tag_service.TorrentTagRepository", return_value=mock_repo):
        svc = TagService(db=mock_db)
    return svc


# ==================== _to_dict 测试 ====================

class TestToDict:
    """_to_dict 转换方法测试"""

    def test_normal_tag(self, tag_service):
        """正常标签对象应转为包含所有字段的字典"""
        tag = make_tag()
        result = tag_service._to_dict(tag)

        assert result["tag_id"] == "tag-001"
        assert result["downloader_id"] == "dl-001"
        assert result["tag_name"] == "测试标签"
        assert result["tag_type"] == "tag"
        assert result["color"] == "#FF5733"
        assert result["created_at"] == "2026-01-01T12:00:00"
        assert result["updated_at"] == "2026-01-01T12:00:00"

    def test_none_returns_none(self, tag_service):
        """传入 None 应返回 None"""
        assert tag_service._to_dict(None) is None

    def test_missing_datetime_fields(self, tag_service):
        """created_at / updated_at 为 None 时字典中对应值应为 None"""
        tag = make_tag()
        tag.created_at = None
        tag.updated_at = None
        result = tag_service._to_dict(tag)

        assert result["created_at"] is None
        assert result["updated_at"] is None


# ==================== _to_relation_dict 测试 ====================

class TestToRelationDict:
    """_to_relation_dict 转换方法测试"""

    def test_normal_relation(self, tag_service):
        """正常关联对象应转为完整字典"""
        rel = make_relation()
        result = tag_service._to_relation_dict(rel)

        assert result["relation_id"] == "rel-001"
        assert result["downloader_id"] == "dl-001"
        assert result["torrent_hash"] == "abc123"
        assert result["tag_id"] == "tag-001"
        assert result["assigned_at"] == "2026-01-01T12:00:00"

    def test_none_returns_none(self, tag_service):
        """传入 None 应返回 None"""
        assert tag_service._to_relation_dict(None) is None


# ==================== _to_response 测试 ====================

class TestToResponse:
    """_to_response 统一响应格式转换测试"""

    def test_success_with_tag_object(self, tag_service):
        """成功的 DatabaseResult（包含有 tag_id 属性的对象）应转为成功响应"""
        tag = make_tag()
        db_result = DatabaseResult.success_result(data=tag, message="创建成功")

        resp = tag_service._to_response(db_result, success_msg="OK")
        assert resp["success"] is True
        assert resp["message"] == "创建成功"
        # _to_response 内部调用 _to_dict，结果应包含 tag_id
        assert resp["data"]["tag_id"] == "tag-001"

    def test_failure_result(self, tag_service):
        """失败的 DatabaseResult 应转为失败响应"""
        db_result = DatabaseResult.failure_result("出错了", error_code=MagicMock(value="DB_ERROR"))

        resp = tag_service._to_response(db_result, error_prefix="标签操作")
        assert resp["success"] is False
        assert resp["data"] is None
        # 失败时 message 优先使用 db_result.message
        assert "出错了" in resp["message"]

    def test_success_with_dict_data(self, tag_service):
        """成功的 DatabaseResult（data 为 dict，无 tag_id 属性）应原样保留 data"""
        db_result = DatabaseResult.success_result(data={"total_count": 2}, message="完成")

        resp = tag_service._to_response(db_result)
        assert resp["success"] is True
        assert resp["data"] == {"total_count": 2}


# ==================== create_tag 测试 ====================

class TestCreateTag:
    """create_tag 方法测试"""

    def test_valid_tag(self, tag_service, mock_repo):
        """有效参数 → 调用 repository.create 并返回成功"""
        tag = make_tag()
        mock_repo.create.return_value = DatabaseResult.success_result(data=tag, message="创建成功")

        result = tag_service.create_tag("dl-001", "电影", "tag", "#FF0000")
        assert result["success"] is True
        mock_repo.create.assert_called_once()

    def test_empty_name(self, tag_service, mock_repo):
        """空标签名 → 直接返回失败，不调用 repository"""
        result = tag_service.create_tag("dl-001", "", "tag")
        assert result["success"] is False
        assert "不能为空" in result["message"]
        mock_repo.create.assert_not_called()

    def test_whitespace_name(self, tag_service, mock_repo):
        """仅空格的标签名 → 返回失败"""
        result = tag_service.create_tag("dl-001", "   ", "tag")
        assert result["success"] is False
        assert "不能为空" in result["message"]

    def test_invalid_type(self, tag_service, mock_repo):
        """无效标签类型 → 返回失败"""
        result = tag_service.create_tag("dl-001", "测试", "invalid_type")
        assert result["success"] is False
        assert "无效的标签类型" in result["message"]
        mock_repo.create.assert_not_called()

    def test_color_without_hash(self, tag_service, mock_repo):
        """颜色不以 # 开头 → 返回失败"""
        result = tag_service.create_tag("dl-001", "测试", "tag", color="FF0000")
        assert result["success"] is False
        assert "#" in result["message"]

    def test_color_with_hash(self, tag_service, mock_repo):
        """颜色以 # 开头 → 通过验证"""
        tag = make_tag(color="#00FF00")
        mock_repo.create.return_value = DatabaseResult.success_result(data=tag)

        result = tag_service.create_tag("dl-001", "测试", "tag", color="#00FF00")
        assert result["success"] is True

    def test_no_color(self, tag_service, mock_repo):
        """不传颜色 → 正常创建"""
        tag = make_tag(color=None)
        mock_repo.create.return_value = DatabaseResult.success_result(data=tag)

        result = tag_service.create_tag("dl-001", "测试", "tag")
        assert result["success"] is True

    def test_name_with_special_chars(self, tag_service, mock_repo):
        """标签名含特殊字符 → 名称应保留原样（仅做 strip）"""
        tag = make_tag(tag_name="电影/电视剧")
        mock_repo.create.return_value = DatabaseResult.success_result(data=tag)

        result = tag_service.create_tag("dl-001", "电影/电视剧", "category")
        assert result["success"] is True

    def test_category_type(self, tag_service, mock_repo):
        """tag_type=category → 成功"""
        tag = make_tag(tag_type="category")
        mock_repo.create.return_value = DatabaseResult.success_result(data=tag)

        result = tag_service.create_tag("dl-001", "分类", "category")
        assert result["success"] is True


# ==================== get_tag_list 测试 ====================

class TestGetTagList:
    """get_tag_list 方法测试"""

    def test_no_filter(self, tag_service, mock_repo):
        """无过滤条件 → 返回该下载器全部标签"""
        mock_repo.find_by_downloader.return_value = [make_tag(tag_id="t1"), make_tag(tag_id="t2")]

        result = tag_service.get_tag_list("dl-001")
        assert result["success"] is True
        assert result["total_count"] == 2
        mock_repo.find_by_downloader.assert_called_once_with(
            downloader_id="dl-001", include_deleted=False, tag_type=None
        )

    def test_filter_by_tag_type(self, tag_service, mock_repo):
        """按 tag_type 过滤 → 传递正确参数"""
        mock_repo.find_by_downloader.return_value = [make_tag(tag_type="category")]

        result = tag_service.get_tag_list("dl-001", tag_type="category")
        assert result["success"] is True
        mock_repo.find_by_downloader.assert_called_once_with(
            downloader_id="dl-001", include_deleted=False, tag_type="category"
        )

    def test_filter_by_downloader_id(self, tag_service, mock_repo):
        """指定不同的 downloader_id → 查询参数正确"""
        mock_repo.find_by_downloader.return_value = []

        result = tag_service.get_tag_list("dl-other")
        assert result["success"] is True
        assert result["total_count"] == 0
        mock_repo.find_by_downloader.assert_called_once_with(
            downloader_id="dl-other", include_deleted=False, tag_type=None
        )

    def test_invalid_tag_type(self, tag_service, mock_repo):
        """无效 tag_type → 直接返回失败，不查询数据库"""
        result = tag_service.get_tag_list("dl-001", tag_type="bad_type")
        assert result["success"] is False
        assert "无效的标签类型" in result["message"]
        mock_repo.find_by_downloader.assert_not_called()

    def test_empty_result(self, tag_service, mock_repo):
        """无匹配结果 → 返回空列表"""
        mock_repo.find_by_downloader.return_value = []

        result = tag_service.get_tag_list("dl-001")
        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0

    def test_exception_handling(self, tag_service, mock_repo):
        """Repository 抛异常 → 返回失败响应"""
        mock_repo.find_by_downloader.side_effect = Exception("DB错误")

        result = tag_service.get_tag_list("dl-001")
        assert result["success"] is False
        assert "DB错误" in result["message"]


# ==================== update_tag 测试 ====================

class TestUpdateTag:
    """update_tag 方法测试"""

    def test_valid_update(self, tag_service, mock_repo):
        """正常更新 → 返回成功"""
        existing = make_tag()
        updated = make_tag(tag_name="新名称")
        mock_repo.find_by_id.return_value = existing
        mock_repo.update.return_value = DatabaseResult.success_result(data=updated, message="更新成功")

        result = tag_service.update_tag("tag-001", tag_name="新名称")
        assert result["success"] is True
        mock_repo.update.assert_called_once()

    def test_tag_not_found(self, tag_service, mock_repo):
        """标签不存在 → 返回失败"""
        mock_repo.find_by_id.return_value = None

        result = tag_service.update_tag("nonexistent")
        assert result["success"] is False
        assert "不存在" in result["message"]
        mock_repo.update.assert_not_called()

    def test_invalid_tag_type(self, tag_service, mock_repo):
        """更新为无效 tag_type → 返回失败"""
        mock_repo.find_by_id.return_value = make_tag()

        result = tag_service.update_tag("tag-001", tag_type="invalid")
        assert result["success"] is False
        assert "无效的标签类型" in result["message"]
        mock_repo.update.assert_not_called()

    def test_update_color(self, tag_service, mock_repo):
        """更新颜色 → 成功"""
        mock_repo.find_by_id.return_value = make_tag()
        updated = make_tag(color="#000000")
        mock_repo.update.return_value = DatabaseResult.success_result(data=updated)

        result = tag_service.update_tag("tag-001", color="#000000")
        assert result["success"] is True


# ==================== delete_tag 测试 ====================

class TestDeleteTag:
    """delete_tag 方法测试"""

    def test_existing_tag(self, tag_service, mock_repo):
        """存在的标签 → 软删除成功"""
        tag_info = {"tag_id": "tag-001", "tag_name": "测试"}
        mock_repo.soft_delete.return_value = DatabaseResult.success_result(
            data=tag_info, message="删除成功"
        )

        result = tag_service.delete_tag("tag-001")
        assert result["success"] is True
        assert result["data"] == tag_info

    def test_nonexistent_tag(self, tag_service, mock_repo):
        """不存在的标签 → 返回失败"""
        mock_repo.soft_delete.return_value = DatabaseResult.not_found_result("标签不存在")

        result = tag_service.delete_tag("nonexistent")
        assert result["success"] is False
        assert result["error_code"] is not None

    def test_exception_handling(self, tag_service, mock_repo):
        """Repository 抛异常 → 返回失败"""
        mock_repo.soft_delete.side_effect = Exception("DB错误")

        result = tag_service.delete_tag("tag-001")
        assert result["success"] is False
        assert "DB错误" in result["message"]


# ==================== assign_tags_to_torrent 测试 ====================

class TestAssignTagsToTorrent:
    """assign_tags_to_torrent 方法测试"""

    def test_valid_assignment(self, tag_service, mock_repo):
        """有效标签 → 成功分配"""
        tag1 = make_tag(tag_id="t1", downloader_id="dl-001")
        tag2 = make_tag(tag_id="t2", downloader_id="dl-001")
        mock_repo.find_by_id.side_effect = [tag1, tag2]
        mock_repo.batch_assign_tags.return_value = DatabaseResult.success_result(
            data={"total_count": 2, "success_count": 2, "failed_count": 0},
            message="分配成功"
        )

        result = tag_service.assign_tags_to_torrent("hash1", ["t1", "t2"])
        assert result["success"] is True
        assert result["success_count"] == 2

    def test_tag_not_found(self, tag_service, mock_repo):
        """部分标签不存在 → 返回失败并列出不存在的标签"""
        tag1 = make_tag(tag_id="t1")
        mock_repo.find_by_id.side_effect = [tag1, None]

        result = tag_service.assign_tags_to_torrent("hash1", ["t1", "nonexistent"])
        assert result["success"] is False
        assert "nonexistent" in result["message"]

    def test_empty_tag_list(self, tag_service, mock_repo):
        """空标签列表 → find_by_id 不被调用"""
        mock_repo.batch_assign_tags.return_value = DatabaseResult.success_result(
            data={"total_count": 0, "success_count": 0, "failed_count": 0}
        )

        result = tag_service.assign_tags_to_torrent("hash1", [])
        mock_repo.find_by_id.assert_not_called()


# ==================== remove_tags_from_torrent 测试 ====================

class TestRemoveTagsFromTorrent:
    """remove_tags_from_torrent 方法测试"""

    def test_successful_removal(self, tag_service, mock_repo):
        """成功移除所有标签"""
        mock_repo.remove_tag_from_torrent.return_value = DatabaseResult.success_result(
            data=True, message="移除成功"
        )

        result = tag_service.remove_tags_from_torrent("hash1", ["t1", "t2"])
        assert result["success"] is True
        assert result["data"]["removed_count"] == 2
        assert result["data"]["failed_count"] == 0

    def test_partial_failure(self, tag_service, mock_repo):
        """部分移除失败 → success=False，统计正确"""
        success_result = DatabaseResult.success_result(data=True)
        fail_result = DatabaseResult.not_found_result("关联不存在")

        mock_repo.remove_tag_from_torrent.side_effect = [success_result, fail_result]

        result = tag_service.remove_tags_from_torrent("hash1", ["t1", "t2"])
        assert result["success"] is False
        assert result["data"]["removed_count"] == 1
        assert result["data"]["failed_count"] == 1
        assert len(result["data"]["failed_tags"]) == 1

    def test_empty_list(self, tag_service, mock_repo):
        """空标签列表 → 全部为 0"""
        result = tag_service.remove_tags_from_torrent("hash1", [])
        assert result["success"] is True
        assert result["data"]["removed_count"] == 0
        assert result["data"]["failed_count"] == 0

    def test_exception_handling(self, tag_service, mock_repo):
        """Repository 抛异常 → 返回失败"""
        mock_repo.remove_tag_from_torrent.side_effect = Exception("DB错误")

        result = tag_service.remove_tags_from_torrent("hash1", ["t1"])
        assert result["success"] is False
        assert "DB错误" in result["message"]


# ==================== get_torrent_tags 测试 ====================

class TestGetTorrentTags:
    """get_torrent_tags 方法测试"""

    def test_with_tags(self, tag_service, mock_repo):
        """种子有标签 → 返回标签列表"""
        rel = make_relation(tag_id="t1")
        tag = make_tag(tag_id="t1", tag_name="电影")
        mock_repo.find_relations_by_torrent_hash.return_value = [rel]
        mock_repo.find_by_id.return_value = tag

        result = tag_service.get_torrent_tags("hash1")
        assert result["success"] is True
        assert result["total_count"] == 1
        assert result["data"][0]["tag_name"] == "电影"

    def test_no_tags(self, tag_service, mock_repo):
        """种子无标签 → 返回空列表"""
        mock_repo.find_relations_by_torrent_hash.return_value = []

        result = tag_service.get_torrent_tags("hash1")
        assert result["success"] is True
        assert result["data"] == []

    def test_deleted_tag_skipped(self, tag_service, mock_repo):
        """关联的标签已被删除（find_by_id 返回 None）→ 跳过"""
        rel = make_relation(tag_id="deleted-tag")
        mock_repo.find_relations_by_torrent_hash.return_value = [rel]
        mock_repo.find_by_id.return_value = None

        result = tag_service.get_torrent_tags("hash1")
        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0


# ==================== batch_assign_tags 测试 ====================

class TestBatchAssignTags:
    """batch_assign_tags 方法测试"""

    def test_valid_assignments(self, tag_service, mock_repo):
        """有效批量分配 → 成功"""
        tag = make_tag(tag_id="t1", downloader_id="dl-001")
        mock_repo.find_by_id.return_value = tag
        mock_repo.batch_assign_tags.return_value = DatabaseResult.success_result(
            data={"total_count": 2, "success_count": 2, "failed_count": 0}
        )

        assignments = [
            {"torrent_hash": "h1", "tag_ids": ["t1"]},
            {"torrent_hash": "h2", "tag_ids": ["t1"]},
        ]
        result = tag_service.batch_assign_tags(assignments)
        assert result["success"] is True
        assert result["total_assignments"] == 2

    def test_empty_assignments(self, tag_service, mock_repo):
        """空分配列表 → batch_assign_tags 收到空列表"""
        mock_repo.batch_assign_tags.return_value = DatabaseResult.success_result(
            data={"total_count": 0, "success_count": 0, "failed_count": 0}
        )

        result = tag_service.batch_assign_tags([])
        assert result["success"] is True
        assert result["total_assignments"] == 0

    def test_first_tag_not_found(self, tag_service, mock_repo):
        """第一个标签不存在 → 跳过该 assignment"""
        mock_repo.find_by_id.return_value = None
        mock_repo.batch_assign_tags.return_value = DatabaseResult.success_result(
            data={"total_count": 0, "success_count": 0, "failed_count": 0}
        )

        result = tag_service.batch_assign_tags([{"torrent_hash": "h1", "tag_ids": ["bad"]}])
        assert result["success"] is True

    def test_missing_torrent_hash_skipped(self, tag_service, mock_repo):
        """缺少 torrent_hash 的条目被跳过"""
        mock_repo.batch_assign_tags.return_value = DatabaseResult.success_result(
            data={"total_count": 0, "success_count": 0, "failed_count": 0}
        )

        result = tag_service.batch_assign_tags([{"tag_ids": ["t1"]}])
        assert result["success"] is True
        mock_repo.find_by_id.assert_not_called()
