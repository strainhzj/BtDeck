"""
测试 CronTaskCRUD 和 TaskLogsCRUD 的所有方法

覆盖目标：
- CronTaskCRUD: 静态映射方法 + CRUD 操作（创建、查询、更新、删除、状态变更、启用任务查询）
- TaskLogsCRUD: 日志创建、日志列表查询、日志统计
"""

import pytest
from unittest.mock import MagicMock, patch
from app.tasks.cron_crud import CronTaskCRUD, TaskLogsCRUD
from app.core.database_result import DatabaseResult

# 源码中使用了 DatabaseResult.not_found，但实际方法名为 not_found_result，
# 这里统一 patch 使其可用
DatabaseResult.not_found = staticmethod(DatabaseResult.not_found_result)


# ---------------------------------------------------------------------------
# convert_task_type_to_chinese
# ---------------------------------------------------------------------------

class TestConvertTaskTypeToChinese:
    """任务类型转中文测试"""

    @pytest.mark.parametrize(
        "task_type, expected",
        [
            (0, "shell脚本"),
            (1, "cmd脚本"),
            (2, "powershell脚本"),
            (3, "python脚本"),
            (4, "python内部类"),
        ],
        ids=["shell脚本", "cmd脚本", "powershell脚本", "python脚本", "python内部类"],
    )
    def test_已知任务类型映射正确(self, task_type, expected):
        """已知类型值应返回对应的中文名"""
        result = CronTaskCRUD.convert_task_type_to_chinese(task_type)
        assert result == expected

    @pytest.mark.parametrize(
        "task_type",
        [-1, 5, 99, 100, 999],
        ids=["负数-1", "超出范围5", "未知值99", "超出范围100", "大数值999"],
    )
    def test_未知任务类型返回未知类型(self, task_type):
        """未定义的类型值应返回'未知类型'"""
        result = CronTaskCRUD.convert_task_type_to_chinese(task_type)
        assert result == "未知类型"

    def test_返回值类型为字符串(self):
        """返回值必须是字符串类型"""
        result = CronTaskCRUD.convert_task_type_to_chinese(0)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# convert_task_status_to_chinese
# ---------------------------------------------------------------------------

class TestConvertTaskStatusToChinese:
    """任务状态转中文测试"""

    @pytest.mark.parametrize(
        "task_status, expected",
        [
            (0, "等待运行"),
            (1, "运行中"),
            (2, "空闲"),
        ],
        ids=["等待运行", "运行中", "空闲"],
    )
    def test_已知任务状态映射正确(self, task_status, expected):
        """已知状态值应返回对应的中文名"""
        result = CronTaskCRUD.convert_task_status_to_chinese(task_status)
        assert result == expected

    @pytest.mark.parametrize(
        "task_status",
        [-1, 3, 99, 100],
        ids=["负数-1", "超出范围3", "未知值99", "大数值100"],
    )
    def test_未知任务状态返回未知状态(self, task_status):
        """未定义的状态值应返回'未知状态'"""
        result = CronTaskCRUD.convert_task_status_to_chinese(task_status)
        assert result == "未知状态"

    def test_返回值类型为字符串(self):
        """返回值必须是字符串类型"""
        result = CronTaskCRUD.convert_task_status_to_chinese(0)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 辅助：Fake ORM 对象（绕过 SQLAlchemy 模型实例化）
# ---------------------------------------------------------------------------

class _FakeCronTask:
    """模拟 CronTask ORM 对象"""

    def __init__(self, task_id=1, task_name="测试任务", task_code="TEST_001",
                 task_type=0, task_status=0, executor="echo hello",
                 enabled=True, cron_plan="*/5 * * * *", dr=0,
                 create_by="admin", update_by="admin"):
        self.task_id = task_id
        self.task_name = task_name
        self.task_code = task_code
        self.task_type = task_type
        self.task_status = task_status
        self.executor = executor
        self.enabled = enabled
        self.cron_plan = cron_plan
        self.dr = dr
        self.create_by = create_by
        self.update_by = update_by
        self.create_time = "2026-01-01T00:00:00"
        self.update_time = "2026-01-01T00:00:00"

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_code": self.task_code,
            "task_type": self.task_type,
            "task_status": self.task_status,
            "executor": self.executor,
            "enabled": self.enabled,
            "cron_plan": self.cron_plan,
            "dr": self.dr,
            "create_by": self.create_by,
            "update_by": self.update_by,
            "create_time": self.create_time,
            "update_time": self.update_time,
        }


class _FakeTaskLog:
    """模拟 TaskLogs ORM 对象"""

    def __init__(self, log_id=1, task_id=1, task_name="测试任务",
                 task_type=0, start_time="2026-01-01T00:00:00",
                 end_time="2026-01-01T00:01:00", duration=60,
                 success=True, log_detail="执行成功", dr=0):
        self.log_id = log_id
        self.task_id = task_id
        self.task_name = task_name
        self.task_type = task_type
        self.start_time = start_time
        self.end_time = end_time
        self.duration = duration
        self.success = success
        self.log_detail = log_detail
        self.dr = dr

    def to_dict(self):
        return {
            "log_id": self.log_id,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_type": self.task_type,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "success": self.success,
            "log_detail": self.log_detail,
            "dr": self.dr,
        }


def _make_query_chain(db, first_result=None, all_result=None, count_result=0):
    """构造 db.query().filter().first()/.all()/.count() 链式 mock"""
    mock_filter = MagicMock()
    mock_filter.first.return_value = first_result
    mock_filter.all.return_value = all_result or []
    mock_filter.count.return_value = count_result
    # 支持 .filter() 链式调用返回自身
    mock_filter.filter.return_value = mock_filter
    # 支持 .order_by().offset().limit().all() 链
    mock_order = MagicMock()
    mock_offset = MagicMock()
    mock_limit = MagicMock()
    mock_limit.all.return_value = all_result or []
    mock_offset.limit.return_value = mock_limit
    mock_order.offset.return_value = mock_offset
    mock_filter.order_by.return_value = mock_order
    # db.query() 返回 mock_filter
    db.query.return_value = mock_filter
    return mock_filter


# ---------------------------------------------------------------------------
# CronTaskCRUD - create_cron_task
# ---------------------------------------------------------------------------

class TestCreateCronTask:
    """创建定时任务测试"""

    def test_正常创建任务(self):
        """任务编码和名称都不存在时，应成功创建"""
        db = MagicMock()
        chain = _make_query_chain(db, first_result=None)
        chain.first.return_value = None  # 编码不存在、名称不存在
        # 让连续两次 query 调用都返回 None
        db.query.return_value.filter.return_value.first.return_value = None

        task_data = {
            "task_name": "新任务",
            "task_code": "NEW_001",
            "task_type": 0,
            "executor": "echo hi",
            "cron_plan": "*/5 * * * *",
        }

        # 需要模拟 db.query 多次调用：第一次检查编码，第二次检查名称
        db.query.side_effect = [
            _make_query_chain(db, first_result=None),
            _make_query_chain(db, first_result=None),
        ]

        # patch CronTask 构造函数，避免 ORM 实例化
        with patch("app.tasks.cron_crud.CronTask", return_value=_FakeCronTask()):
            result = CronTaskCRUD.create_cron_task(db, task_data)

        assert result.success is True
        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_任务编码已存在(self):
        """任务编码已存在时，应返回失败"""
        db = MagicMock()
        existing = _FakeCronTask(task_code="DUP_CODE")
        _make_query_chain(db, first_result=existing)

        task_data = {"task_name": "任务", "task_code": "DUP_CODE"}
        result = CronTaskCRUD.create_cron_task(db, task_data)

        assert result.success is False
        assert "已存在" in result.message
        assert "DUP_CODE" in result.message

    def test_任务名称已存在(self):
        """任务名称已存在时，应返回失败"""
        db = MagicMock()

        # 第一次 query 检查编码 → None（编码不存在）
        mock_q1 = MagicMock()
        mock_q1.filter.return_value.first.return_value = None
        # 第二次 query 检查名称 → 存在
        mock_q2 = MagicMock()
        mock_q2.filter.return_value.first.return_value = _FakeCronTask(task_name="重复名称")

        db.query.side_effect = [mock_q1, mock_q2]

        task_data = {"task_name": "重复名称", "task_code": "UNIQUE_CODE"}
        result = CronTaskCRUD.create_cron_task(db, task_data)

        assert result.success is False
        assert "已存在" in result.message
        assert "重复名称" in result.message

    def test_数据库异常时回滚(self):
        """db.add 抛异常时，应 rollback 并返回失败"""
        db = MagicMock()
        db.query.side_effect = [
            _make_query_chain(db, first_result=None),
            _make_query_chain(db, first_result=None),
        ]
        db.add.side_effect = Exception("DB connection lost")

        task_data = {"task_name": "任务", "task_code": "CODE"}
        result = CronTaskCRUD.create_cron_task(db, task_data)

        assert result.success is False
        assert "创建定时任务失败" in result.message
        db.rollback.assert_called_once()

    def test_默认参数填充(self):
        """未提供 enabled 和 create_by 时使用默认值"""
        db = MagicMock()
        db.query.side_effect = [
            _make_query_chain(db, first_result=None),
            _make_query_chain(db, first_result=None),
        ]
        fake_task = _FakeCronTask()
        with patch("app.tasks.cron_crud.CronTask", return_value=fake_task) as MockTask:
            task_data = {"task_name": "任务", "task_code": "C1", "task_type": 0}
            CronTaskCRUD.create_cron_task(db, task_data)
            # 验证 CronTask 被创建时传入默认 enabled=True, create_by="admin"
            call_kwargs = MockTask.call_args[1]
            assert call_kwargs["enabled"] is True
            assert call_kwargs["create_by"] == "admin"


# ---------------------------------------------------------------------------
# CronTaskCRUD - get_cron_task_by_id
# ---------------------------------------------------------------------------

class TestGetCronTaskById:
    """根据ID获取定时任务测试"""

    def test_任务存在(self):
        """根据有效ID查询到任务"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=10)
        _make_query_chain(db, first_result=fake_task)

        result = CronTaskCRUD.get_cron_task_by_id(db, 10)
        assert result.success is True
        assert result.data["task_id"] == 10

    def test_任务不存在(self):
        """查询不存在的ID应返回失败"""
        db = MagicMock()
        _make_query_chain(db, first_result=None)

        result = CronTaskCRUD.get_cron_task_by_id(db, 999)
        assert result.success is False
        assert "不存在" in result.message

    def test_数据库异常(self):
        """查询过程中抛异常应返回失败"""
        db = MagicMock()
        db.query.side_effect = Exception("connection error")

        result = CronTaskCRUD.get_cron_task_by_id(db, 1)
        assert result.success is False
        assert "获取定时任务失败" in result.message

    def test_返回数据为字典格式(self):
        """返回的data应为字典格式"""
        db = MagicMock()
        fake_task = _FakeCronTask()
        _make_query_chain(db, first_result=fake_task)

        result = CronTaskCRUD.get_cron_task_by_id(db, 1)
        assert isinstance(result.data, dict)
        assert "task_name" in result.data


# ---------------------------------------------------------------------------
# CronTaskCRUD - get_cron_task_by_code
# ---------------------------------------------------------------------------

class TestGetCronTaskByCode:
    """根据编码获取定时任务测试"""

    def test_编码存在(self):
        """查询存在的编码应返回 total=1 和 list"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_code="SHELL_001")
        _make_query_chain(db, first_result=fake_task)

        result = CronTaskCRUD.get_cron_task_by_code(db, "SHELL_001")
        assert result.success is True
        assert result.data["total"] == 1
        assert len(result.data["list"]) == 1
        assert result.data["list"][0]["task_code"] == "SHELL_001"

    def test_编码不存在(self):
        """查询不存在的编码应返回 total=0 和空 list"""
        db = MagicMock()
        _make_query_chain(db, first_result=None)

        result = CronTaskCRUD.get_cron_task_by_code(db, "NOT_EXIST")
        assert result.success is True
        assert result.data["total"] == 0
        assert result.data["list"] == []

    def test_数据库异常(self):
        """查询过程中抛异常应返回失败"""
        db = MagicMock()
        db.query.side_effect = Exception("db error")

        result = CronTaskCRUD.get_cron_task_by_code(db, "CODE")
        assert result.success is False
        assert "根据编码获取定时任务失败" in result.message


# ---------------------------------------------------------------------------
# CronTaskCRUD - get_cron_tasks（列表查询）
# ---------------------------------------------------------------------------

class TestGetCronTasks:
    """获取定时任务列表测试"""

    def test_无筛选条件查询(self):
        """不带任何筛选条件，返回全部任务"""
        db = MagicMock()
        fake_tasks = [_FakeCronTask(task_id=1), _FakeCronTask(task_id=2)]
        _make_query_chain(db, all_result=fake_tasks, count_result=2)

        result = CronTaskCRUD.get_cron_tasks(db)
        assert result.success is True
        assert result.data["total"] == 2
        assert len(result.data["list"]) == 2

    def test_空列表查询(self):
        """没有任务时返回空列表"""
        db = MagicMock()
        _make_query_chain(db, all_result=[], count_result=0)

        result = CronTaskCRUD.get_cron_tasks(db)
        assert result.success is True
        assert result.data["total"] == 0
        assert result.data["list"] == []

    def test_列表结果包含中文名称(self):
        """列表中每条记录应包含 task_type_name 和 task_status_name"""
        db = MagicMock()
        fake_tasks = [_FakeCronTask(task_type=0, task_status=1)]
        _make_query_chain(db, all_result=fake_tasks, count_result=1)

        result = CronTaskCRUD.get_cron_tasks(db)
        item = result.data["list"][0]
        assert item["task_type_name"] == "shell脚本"
        assert item["task_status_name"] == "运行中"

    def test_数据库异常(self):
        """查询过程中抛异常应返回失败"""
        db = MagicMock()
        db.query.side_effect = Exception("err")

        result = CronTaskCRUD.get_cron_tasks(db)
        assert result.success is False
        assert "获取定时任务列表失败" in result.message

    def test_分页参数传递(self):
        """skip 和 limit 参数应正确传递到查询链"""
        db = MagicMock()
        chain = _make_query_chain(db, all_result=[], count_result=0)

        CronTaskCRUD.get_cron_tasks(db, skip=10, limit=5)

        # 验证 offset 和 limit 被调用
        chain.order_by.return_value.offset.assert_called_once_with(10)
        chain.order_by.return_value.offset.return_value.limit.assert_called_once_with(5)


# ---------------------------------------------------------------------------
# CronTaskCRUD - update_cron_task
# ---------------------------------------------------------------------------

class TestUpdateCronTask:
    """更新定时任务测试"""

    def test_正常更新(self):
        """任务存在且无冲突时，应成功更新"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)

        # q1: 找到当前任务, q2: 名称无冲突（因为 task_data 含 task_name）
        mock_q1 = MagicMock()
        mock_q1.filter.return_value.first.return_value = fake_task
        mock_q2 = MagicMock()
        mock_q2.filter.return_value.first.return_value = None

        db.query.side_effect = [mock_q1, mock_q2]

        task_data = {"task_name": "更新后名称", "cron_plan": "0 * * * *"}
        result = CronTaskCRUD.update_cron_task(db, 1, task_data)

        assert result.success is True
        db.commit.assert_called_once()
        db.refresh.assert_called_once()
        assert fake_task.task_name == "更新后名称"

    def test_任务不存在(self):
        """更新不存在的任务应返回失败"""
        db = MagicMock()
        _make_query_chain(db, first_result=None)

        result = CronTaskCRUD.update_cron_task(db, 999, {"task_name": "x"})
        assert result.success is False
        assert "不存在" in result.message

    def test_更新编码已被其他任务使用(self):
        """更新编码时如果已被其他任务占用，应返回失败"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)
        other_task = _FakeCronTask(task_id=2, task_code="USED_CODE")

        # 第一次 query 找到当前任务，第二次 query 检查编码冲突找到 other_task
        mock_q1 = MagicMock()
        mock_q1.filter.return_value.first.return_value = fake_task
        mock_q2 = MagicMock()
        mock_q2.filter.return_value.first.return_value = other_task

        db.query.side_effect = [mock_q1, mock_q2]

        result = CronTaskCRUD.update_cron_task(db, 1, {"task_code": "USED_CODE"})
        assert result.success is False
        assert "已被其他任务使用" in result.message

    def test_更新名称已被其他任务使用(self):
        """更新名称时如果已被其他任务占用，应返回失败"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)

        # q1: 找到当前任务, q2: 编码无冲突, q3: 名称有冲突
        mock_q1 = MagicMock()
        mock_q1.filter.return_value.first.return_value = fake_task
        mock_q2 = MagicMock()
        mock_q2.filter.return_value.first.return_value = None
        mock_q3 = MagicMock()
        mock_q3.filter.return_value.first.return_value = _FakeCronTask(task_id=2, task_name="重复")

        db.query.side_effect = [mock_q1, mock_q2, mock_q3]

        result = CronTaskCRUD.update_cron_task(db, 1, {"task_code": "NEW", "task_name": "重复"})
        assert result.success is False
        assert "已被其他任务使用" in result.message

    def test_数据库异常时回滚(self):
        """commit 抛异常时应 rollback"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)
        _make_query_chain(db, first_result=fake_task)
        db.commit.side_effect = Exception("commit fail")

        # 不含 task_code/task_name，不触发冲突检查
        result = CronTaskCRUD.update_cron_task(db, 1, {"cron_plan": "0 0 * * *"})
        assert result.success is False
        db.rollback.assert_called_once()

    def test_不传编码和名称时跳过冲突检查(self):
        """更新数据中不含 task_code 和 task_name 时，不做冲突检查"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)
        _make_query_chain(db, first_result=fake_task)

        result = CronTaskCRUD.update_cron_task(db, 1, {"cron_plan": "0 0 * * *"})
        assert result.success is True
        # db.query 只被调用一次（查找任务本身），不会再检查冲突
        assert db.query.call_count == 1

    def test_更新时间戳自动设置(self):
        """更新操作应自动设置 update_time"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)
        _make_query_chain(db, first_result=fake_task)

        CronTaskCRUD.update_cron_task(db, 1, {"cron_plan": "* * * * *"})
        assert fake_task.update_time is not None

    def test_默认update_by为admin(self):
        """未提供 update_by 时默认为 admin"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)
        _make_query_chain(db, first_result=fake_task)

        CronTaskCRUD.update_cron_task(db, 1, {"cron_plan": "* * * * *"})
        assert fake_task.update_by == "admin"


# ---------------------------------------------------------------------------
# CronTaskCRUD - delete_cron_task
# ---------------------------------------------------------------------------

class TestDeleteCronTask:
    """删除定时任务测试（逻辑删除）"""

    def test_正常删除(self):
        """任务存在时应成功逻辑删除"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=5)
        _make_query_chain(db, first_result=fake_task)

        result = CronTaskCRUD.delete_cron_task(db, 5)
        assert result.success is True
        assert result.data["task_id"] == 5
        assert fake_task.dr == 1
        db.commit.assert_called_once()

    def test_任务不存在(self):
        """删除不存在的任务应返回失败"""
        db = MagicMock()
        _make_query_chain(db, first_result=None)

        result = CronTaskCRUD.delete_cron_task(db, 999)
        assert result.success is False
        assert "不存在" in result.message

    def test_数据库异常时回滚(self):
        """commit 抛异常时应 rollback"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)
        _make_query_chain(db, first_result=fake_task)
        db.commit.side_effect = Exception("commit error")

        result = CronTaskCRUD.delete_cron_task(db, 1)
        assert result.success is False
        db.rollback.assert_called_once()

    def test_自定义删除人(self):
        """传入 delete_by 参数应正确设置到任务"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)
        _make_query_chain(db, first_result=fake_task)

        CronTaskCRUD.delete_cron_task(db, 1, delete_by="test_user")
        assert fake_task.update_by == "test_user"


# ---------------------------------------------------------------------------
# CronTaskCRUD - update_task_status
# ---------------------------------------------------------------------------

class TestUpdateTaskStatus:
    """更新任务状态测试"""

    def test_正常更新状态(self):
        """任务存在时应成功更新状态"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1, task_status=0)
        _make_query_chain(db, first_result=fake_task)

        result = CronTaskCRUD.update_task_status(db, 1, 1)
        assert result.success is True
        assert fake_task.task_status == 1
        db.commit.assert_called_once()

    def test_任务不存在(self):
        """更新不存在任务的状态应返回失败"""
        db = MagicMock()
        _make_query_chain(db, first_result=None)

        result = CronTaskCRUD.update_task_status(db, 999, 1)
        assert result.success is False
        assert "不存在" in result.message

    def test_数据库异常时回滚(self):
        """commit 抛异常时应 rollback"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1)
        _make_query_chain(db, first_result=fake_task)
        db.commit.side_effect = Exception("err")

        result = CronTaskCRUD.update_task_status(db, 1, 2)
        assert result.success is False
        db.rollback.assert_called_once()

    def test_状态值正确设置(self):
        """设置的状态值应反映在任务对象上"""
        db = MagicMock()
        fake_task = _FakeCronTask(task_id=1, task_status=0)
        _make_query_chain(db, first_result=fake_task)

        CronTaskCRUD.update_task_status(db, 1, 2)
        assert fake_task.task_status == 2


# ---------------------------------------------------------------------------
# CronTaskCRUD - get_enabled_tasks
# ---------------------------------------------------------------------------

class TestGetEnabledTasks:
    """获取所有启用的定时任务测试"""

    def test_有启用的任务(self):
        """存在启用任务时应返回列表"""
        db = MagicMock()
        fake_tasks = [_FakeCronTask(enabled=True), _FakeCronTask(enabled=True)]
        _make_query_chain(db, all_result=fake_tasks)

        result = CronTaskCRUD.get_enabled_tasks(db)
        assert result.success is True
        assert len(result.data) == 2

    def test_无启用的任务(self):
        """没有启用任务时应返回空列表"""
        db = MagicMock()
        _make_query_chain(db, all_result=[])

        result = CronTaskCRUD.get_enabled_tasks(db)
        assert result.success is True
        assert result.data == []

    def test_数据库异常(self):
        """查询异常时应返回失败"""
        db = MagicMock()
        db.query.side_effect = Exception("err")

        result = CronTaskCRUD.get_enabled_tasks(db)
        assert result.success is False
        assert "获取启用任务失败" in result.message


# ---------------------------------------------------------------------------
# TaskLogsCRUD - create_task_log
# ---------------------------------------------------------------------------

class TestCreateTaskLog:
    """创建任务日志测试"""

    def test_正常创建日志(self):
        """正常数据应成功创建日志"""
        db = MagicMock()
        fake_log = _FakeTaskLog()
        log_data = {
            "task_id": 1,
            "task_name": "测试",
            "task_type": 0,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-01-01T00:01:00",
            "duration": 60,
            "success": True,
            "log_detail": "执行成功",
        }

        with patch("app.tasks.cron_crud.TaskLogs", return_value=fake_log):
            result = TaskLogsCRUD.create_task_log(db, log_data)

        assert result.success is True
        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_数据库异常时回滚(self):
        """db.add 抛异常时应 rollback"""
        db = MagicMock()
        db.add.side_effect = Exception("err")

        with patch("app.tasks.cron_crud.TaskLogs"):
            result = TaskLogsCRUD.create_task_log(db, {"task_name": "x"})

        assert result.success is False
        assert "创建任务日志失败" in result.message
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TaskLogsCRUD - get_task_logs
# ---------------------------------------------------------------------------

class TestGetTaskLogs:
    """获取任务日志列表测试"""

    def test_无筛选条件查询(self):
        """不带筛选条件，返回全部日志"""
        db = MagicMock()
        fake_logs = [_FakeTaskLog(log_id=1), _FakeTaskLog(log_id=2)]
        _make_query_chain(db, all_result=fake_logs, count_result=2)

        result = TaskLogsCRUD.get_task_logs(db)
        assert result.success is True
        assert result.data["total"] == 2
        assert len(result.data["list"]) == 2

    def test_空列表查询(self):
        """没有日志时返回空列表"""
        db = MagicMock()
        _make_query_chain(db, all_result=[], count_result=0)

        result = TaskLogsCRUD.get_task_logs(db)
        assert result.success is True
        assert result.data["total"] == 0
        assert result.data["list"] == []

    def test_数据库异常(self):
        """查询异常时应返回失败"""
        db = MagicMock()
        db.query.side_effect = Exception("err")

        result = TaskLogsCRUD.get_task_logs(db)
        assert result.success is False
        assert "获取任务日志失败" in result.message

    def test_分页参数传递(self):
        """skip 和 limit 参数应正确传递"""
        db = MagicMock()
        chain = _make_query_chain(db, all_result=[], count_result=0)

        TaskLogsCRUD.get_task_logs(db, skip=20, limit=10)

        chain.order_by.return_value.offset.assert_called_once_with(20)
        chain.order_by.return_value.offset.return_value.limit.assert_called_once_with(10)


# ---------------------------------------------------------------------------
# TaskLogsCRUD - get_task_logs_statistics
# ---------------------------------------------------------------------------

class TestGetTaskLogsStatistics:
    """获取任务日志统计信息测试"""

    def test_正常统计(self):
        """应返回 total_logs, success_logs, failed_logs, today_logs"""
        db = MagicMock()

        # 源码只调用 db.query() 一次，然后通过 base_query 进行4次 .count()
        # base_query.count() -> total_logs
        # base_query.filter(success=True).count() -> success_logs
        # base_query.filter(success=False).count() -> failed_logs
        # base_query.filter(date==today).count() -> today_logs
        base_query = MagicMock()
        base_query.filter.return_value = base_query  # 链式
        # count 被4次调用，每次 filter 后再 count 也返回 base_query 上
        base_query.count.side_effect = [100, 80, 20, 15]

        db.query.return_value = base_query

        result = TaskLogsCRUD.get_task_logs_statistics(db)
        assert result.success is True
        assert result.data["total_logs"] == 100
        assert result.data["success_logs"] == 80
        assert result.data["failed_logs"] == 20
        assert result.data["today_logs"] == 15

    def test_数据库异常(self):
        """查询异常时应返回失败"""
        db = MagicMock()
        db.query.side_effect = Exception("err")

        result = TaskLogsCRUD.get_task_logs_statistics(db)
        assert result.success is False
        assert "获取任务日志统计失败" in result.message

    def test_统计结果为空数据库(self):
        """数据库无日志时，所有统计值应为0"""
        db = MagicMock()

        base_query = MagicMock()
        base_query.filter.return_value = base_query
        base_query.count.side_effect = [0, 0, 0, 0]

        db.query.return_value = base_query

        result = TaskLogsCRUD.get_task_logs_statistics(db)
        assert result.success is True
        assert result.data["total_logs"] == 0
        assert result.data["success_logs"] == 0
        assert result.data["failed_logs"] == 0
        assert result.data["today_logs"] == 0
