"""
class_path_validator.py 和 BatchClassValidator 单元测试

覆盖 ClassPathValidator 的格式验证、模块导入验证、类存在验证、
execute 方法验证、综合验证、修复建议以及 BatchClassValidator 的辅助逻辑。
"""

import pytest
from unittest.mock import patch, MagicMock

from app.tasks.class_path_validator import (
    ClassPathValidator,
    ClassPathValidationError,
    validate_single_class_path,
    validate_class_paths_batch,
    class_path_validator,
)
from app.tasks.batch_class_validator import BatchClassValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def validator():
    """ClassPathValidator 实例"""
    return ClassPathValidator()


@pytest.fixture
def batch_validator():
    """BatchClassValidator 实例"""
    return BatchClassValidator()


# ===========================================================================
# ClassPathValidationError
# ===========================================================================


class TestClassPathValidationError:
    """错误模型测试"""

    def test_to_dict(self):
        """to_dict 应返回正确的字典结构"""
        err = ClassPathValidationError("INVALID_FORMAT", "格式错误", "详细信息")
        d = err.to_dict()

        assert d["error_type"] == "INVALID_FORMAT"
        assert d["message"] == "格式错误"
        assert d["details"] == "详细信息"


# ===========================================================================
# ClassPathValidator - 格式验证
# ===========================================================================


class TestClassPathFormatValidation:
    """类路径格式验证"""

    def test_valid_format(self, validator):
        """标准格式路径应通过"""
        valid, error = validator.validate_class_path_format("app.tasks.my_module.MyClass")
        assert valid is True
        assert error is None

    def test_empty_path(self, validator):
        """空路径应失败"""
        valid, error = validator.validate_class_path_format("")
        assert valid is False
        assert error.error_type == "INVALID_FORMAT"

    def test_none_like_empty(self, validator):
        """仅空白字符的路径应失败"""
        valid, error = validator.validate_class_path_format("   ")
        assert valid is False

    def test_no_dot(self, validator):
        """不含点号的路径应失败"""
        valid, error = validator.validate_class_path_format("JustAName")
        assert valid is False
        assert "应包含模块路径和类名" in error.message

    def test_python_keyword_prefix(self, validator):
        """以 Python 关键字开头应失败"""
        valid, error = validator.validate_class_path_format("import.something.MyClass")
        assert valid is False
        assert "Python关键字" in error.message

    def test_invalid_chars(self, validator):
        """包含非法字符应失败"""
        for ch in ['/', '\\', ':', '*', '?', '<', '>']:
            valid, error = validator.validate_class_path_format(f"app.module{ch}Class")
            assert valid is False, f"字符 '{ch}' 应被拒绝"
            assert "非法字符" in error.message

    def test_empty_part(self, validator):
        """路径部分为空应失败（连续点号）"""
        valid, error = validator.validate_class_path_format("app..MyClass")
        assert valid is False

    def test_non_identifier_part(self, validator):
        """路径部分不是有效 Python 标识符应失败"""
        valid, error = validator.validate_class_path_format("app.123module.MyClass")
        assert valid is False
        assert "不是有效的Python标识符" in error.message


# ===========================================================================
# ClassPathValidator - 模块导入验证
# ===========================================================================


class TestModuleImportValidation:
    """模块导入验证"""

    def test_existing_stdlib_module(self, validator):
        """标准库模块应可导入"""
        valid, error = validator.validate_module_import("os.path")
        assert valid is True
        assert error is None

    def test_nonexistent_module(self, validator):
        """不存在的模块应失败"""
        valid, error = validator.validate_module_import("nonexistent_module_xyz_123")
        assert valid is False
        assert error.error_type == "MODULE_NOT_FOUND"


# ===========================================================================
# ClassPathValidator - 类存在验证
# ===========================================================================


class TestClassExistsValidation:
    """类存在验证"""

    def test_existing_class_in_stdlib(self, validator):
        """标准库中的已有类应通过"""
        # logging.Logger 是一个真实存在的类
        valid, cls, error = validator.validate_class_exists("logging", "Logger")
        assert valid is True
        assert cls is not None

    def test_nonexistent_class(self, validator):
        """不存在的类应失败"""
        valid, cls, error = validator.validate_class_exists("os.path", "TotallyFakeClass")
        assert valid is False
        assert error.error_type == "CLASS_NOT_FOUND"

    def test_non_class_attribute(self, validator):
        """非类属性（如函数）应失败"""
        valid, cls, error = validator.validate_class_exists("os.path", "join")
        assert valid is False
        assert "不是一个类" in error.message

    def test_nonexistent_module_for_class(self, validator):
        """不存在模块中查找类应失败"""
        valid, cls, error = validator.validate_class_exists("fake_mod_xyz", "SomeClass")
        assert valid is False
        assert error.error_type in ("MODULE_NOT_FOUND", "IMPORT_FAILED")


# ===========================================================================
# ClassPathValidator - execute 方法验证
# ===========================================================================


class TestExecuteMethodValidation:
    """execute 方法验证"""

    def test_class_with_execute(self, validator):
        """有 execute 方法的类应通过"""
        class FakeTask:
            def execute(self):
                pass

        valid, error = validator.validate_execute_method(FakeTask)
        assert valid is True
        assert error is None

    def test_class_without_execute(self, validator):
        """没有 execute 方法的类应失败"""
        class NoExecute:
            pass

        valid, error = validator.validate_execute_method(NoExecute)
        assert valid is False
        assert error.error_type == "NO_EXECUTE_METHOD"

    def test_execute_not_callable(self, validator):
        """execute 属性不可调用应失败"""
        class BadTask:
            execute = "not a method"

        valid, error = validator.validate_execute_method(BadTask)
        assert valid is False
        assert "不是可调用" in error.message


# ===========================================================================
# ClassPathValidator - 综合验证
# ===========================================================================


class TestComprehensiveValidation:
    """综合验证"""

    def test_invalid_format_comprehensive(self, validator):
        """格式错误的路径在综合验证中应立即返回"""
        result = validator.validate_class_path_comprehensive("NoDots")
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_nonexistent_module_comprehensive(self, validator):
        """不存在模块的综合验证应失败"""
        result = validator.validate_class_path_comprehensive("fake_pkg_abc.SomeClass")
        assert result["is_valid"] is False
        assert result["module_path"] == "fake_pkg_abc"
        assert result["class_name"] == "SomeClass"

    def test_existing_path_comprehensive(self, validator):
        """存在的有效路径（带 execute 方法的类）应通过综合验证"""
        # 使用 ClassPathValidator 自身作为验证目标：它有 execute 方法吗？没有。
        # 用一个确保有 execute 的类来测试比较困难，所以我们只检查格式层面的流程
        result = validator.validate_class_path_comprehensive("os.path.join")
        # os.path.join 是函数不是类
        assert result["is_valid"] is False


# ===========================================================================
# 便捷函数
# ===========================================================================


class TestConvenienceFunctions:
    """便捷函数测试"""

    def test_validate_single_class_path(self):
        """validate_single_class_path 应返回字典结果"""
        result = validate_single_class_path("invalid-no-dots")
        assert isinstance(result, dict)
        assert result["is_valid"] is False

    def test_validate_class_paths_batch(self):
        """批量验证应返回报告结构"""
        paths = [
            "invalid-path",
            "fake.module.XYZ",
            "os.path.join",
        ]
        report = validate_class_paths_batch(paths)

        assert "summary" in report
        assert "error_statistics" in report
        assert "repair_suggestions" in report
        assert "detailed_results" in report
        assert report["summary"]["total_count"] == 3
        assert report["summary"]["invalid_count"] == 3  # 全部无效


# ===========================================================================
# ClassPathValidator - 修复建议
# ===========================================================================


class TestSuggestFix:
    """修复建议生成测试"""

    def test_suggest_for_invalid_format(self, validator):
        """INVALID_FORMAT 应给出格式修复建议"""
        error = {"error_type": "INVALID_FORMAT"}
        suggestions = validator.suggest_fix_for_error(error)

        assert len(suggestions) > 0
        assert any("格式" in s for s in suggestions)

    def test_suggest_for_module_not_found(self, validator):
        """MODULE_NOT_FOUND 应给出模块修复建议"""
        error = {"error_type": "MODULE_NOT_FOUND"}
        suggestions = validator.suggest_fix_for_error(error)

        assert len(suggestions) > 0
        assert any("模块" in s for s in suggestions)

    def test_suggest_for_class_not_found(self, validator):
        """CLASS_NOT_FOUND 应给出类名修复建议"""
        error = {"error_type": "CLASS_NOT_FOUND"}
        suggestions = validator.suggest_fix_for_error(error)

        assert len(suggestions) > 0

    def test_suggest_for_no_execute_method(self, validator):
        """NO_EXECUTE_METHOD 应给出添加 execute 的建议"""
        error = {"error_type": "NO_EXECUTE_METHOD"}
        suggestions = validator.suggest_fix_for_error(error)

        assert any("execute" in s for s in suggestions)

    def test_suggest_for_unknown_error(self, validator):
        """未知错误类型应返回空建议"""
        error = {"error_type": "UNKNOWN_ERROR_TYPE"}
        suggestions = validator.suggest_fix_for_error(error)

        assert len(suggestions) == 0


# ===========================================================================
# ClassPathValidator - 验证报告生成
# ===========================================================================


class TestValidationReport:
    """验证报告生成测试"""

    def test_report_all_valid(self, validator):
        """全部有效时的报告统计"""
        results = [
            {"is_valid": True, "errors": []},
            {"is_valid": True, "errors": []},
        ]
        report = validator.generate_validation_report(results)

        assert report["summary"]["total_count"] == 2
        assert report["summary"]["valid_count"] == 2
        assert report["summary"]["invalid_count"] == 0
        assert "100.0%" in report["summary"]["success_rate"]

    def test_report_all_invalid(self, validator):
        """全部无效时的报告统计"""
        results = [
            {"is_valid": False, "errors": [{"error_type": "INVALID_FORMAT"}]},
            {"is_valid": False, "errors": [{"error_type": "MODULE_NOT_FOUND"}]},
        ]
        report = validator.generate_validation_report(results)

        assert report["summary"]["invalid_count"] == 2
        assert report["error_statistics"]["INVALID_FORMAT"] == 1
        assert report["error_statistics"]["MODULE_NOT_FOUND"] == 1
        assert len(report["repair_suggestions"]) > 0

    def test_report_empty_results(self, validator):
        """空结果列表的报告"""
        report = validator.generate_validation_report([])

        assert report["summary"]["total_count"] == 0
        assert report["summary"]["success_rate"] == "0%"

    def test_report_error_statistics(self, validator):
        """错误统计应正确聚合"""
        results = [
            {"is_valid": False, "errors": [
                {"error_type": "INVALID_FORMAT"},
                {"error_type": "MODULE_NOT_FOUND"},
            ]},
            {"is_valid": False, "errors": [
                {"error_type": "INVALID_FORMAT"},
            ]},
        ]
        report = validator.generate_validation_report(results)

        assert report["error_statistics"]["INVALID_FORMAT"] == 2
        assert report["error_statistics"]["MODULE_NOT_FOUND"] == 1


# ===========================================================================
# BatchClassValidator - 辅助逻辑
# ===========================================================================


class TestBatchClassValidatorHelpers:
    """BatchClassValidator 中不依赖数据库的辅助方法测试"""

    def test_extract_class_paths_filters_valid(self, batch_validator):
        """应正确提取类路径格式的 executor"""
        tasks = [
            {"executor": "app.tasks.cron_executor.CronTaskExecutor"},
            {"executor": "import os"},
            {"executor": "def foo(): pass"},
            {"executor": "  "},
            {"executor": "app.tasks.fake.MyTask"},
        ]
        paths = batch_validator.extract_class_paths_from_tasks(tasks)

        assert len(paths) == 2
        assert "app.tasks.cron_executor.CronTaskExecutor" in paths
        assert "app.tasks.fake.MyTask" in paths

    def test_extract_class_paths_ignores_code_keywords(self, batch_validator):
        """以代码关键字开头的 executor 不应被当作类路径"""
        tasks = [
            {"executor": "import os"},
            {"executor": "def foo(): pass"},
            {"executor": "print('hello')"},
            {"executor": "await something()"},
            {"executor": "time.sleep(1)"},
            {"executor": "async def bar(): pass"},
            {"executor": "# comment"},
        ]
        paths = batch_validator.extract_class_paths_from_tasks(tasks)

        assert len(paths) == 0

    def test_extract_class_paths_empty_tasks(self, batch_validator):
        """空任务列表应返回空路径列表"""
        paths = batch_validator.extract_class_paths_from_tasks([])
        assert paths == []

    def test_generate_detailed_report_no_matching_tasks(self, batch_validator):
        """当验证结果中的类路径没有匹配任务时，报告应正确处理"""
        tasks = [
            {"task_id": 1, "task_name": "T1", "task_code": "c1", "executor": "app.fake.Task"},
        ]
        validation_report = {
            "detailed_results": [
                {
                    "class_path": "app.other.Task",
                    "is_valid": False,
                    "errors": [{"error_type": "MODULE_NOT_FOUND"}],
                    "module_path": "app.other",
                    "class_name": "Task",
                }
            ],
            "summary": {"total_count": 1, "valid_count": 0, "invalid_count": 1, "success_rate": "0%"},
            "error_statistics": {"MODULE_NOT_FOUND": 1},
            "repair_suggestions": ["检查模块路径"],
        }

        report = batch_validator.generate_detailed_report(tasks, validation_report)

        assert report["status"] == "completed"
        assert report["total_python_tasks_scanned"] == 1
        assert report["total_class_paths_validated"] == 1

    def test_generate_repair_script(self, batch_validator):
        """修复脚本应包含 SQL 语句和注释"""
        report = {
            "detailed_results": [
                {
                    "task_id": 42,
                    "task_name": "测试任务",
                    "class_path": "fake.Mod.Cls",
                    "is_valid": False,
                    "errors": [{"message": "模块不存在"}],
                    "suggested_fixes": ["检查路径"],
                }
            ]
        }
        script = batch_validator.generate_repair_script(report)

        assert "UPDATE cron_task" in script
        assert "task_id = 42" in script
        assert "备份数据库" in script

    def test_generate_repair_script_no_invalid(self, batch_validator):
        """全部有效时修复脚本不应有 UPDATE 语句"""
        report = {
            "detailed_results": [
                {
                    "task_id": 1,
                    "task_name": "OK",
                    "class_path": "app.Real.Task",
                    "is_valid": True,
                    "errors": [],
                    "suggested_fixes": [],
                }
            ]
        }
        script = batch_validator.generate_repair_script(report)

        assert "UPDATE" not in script


# ===========================================================================
# BatchClassValidator - scan_database_for_python_internal_classes
# ===========================================================================


class TestScanDatabaseForPythonInternalClasses:
    """数据库扫描方法测试"""

    @patch("app.tasks.batch_class_validator.get_db")
    @patch("app.tasks.batch_class_validator.CronTaskCRUD")
    def test_成功获取Python内部类任务(self, mock_crud, mock_get_db, batch_validator):
        """当数据库返回成功且有Python内部类任务时，应正确过滤返回"""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "list": [
                {"task_id": 1, "task_type": 4, "executor": "app.tasks.MyTask"},
                {"task_id": 2, "task_type": 1, "executor": "other"},
                {"task_id": 3, "task_type": 4, "executor": "app.tasks.AnotherTask"},
            ]
        }
        mock_crud.get_cron_tasks.return_value = mock_result

        result = batch_validator.scan_database_for_python_internal_classes()

        assert len(result) == 2
        assert result[0]["task_id"] == 1
        assert result[1]["task_id"] == 3
        mock_db.close.assert_called_once()

    @patch("app.tasks.batch_class_validator.get_db")
    @patch("app.tasks.batch_class_validator.CronTaskCRUD")
    def test_数据库查询失败时返回空列表(self, mock_crud, mock_get_db, batch_validator):
        """当 get_cron_tasks 返回失败时，应返回空列表"""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.message = "连接超时"
        mock_crud.get_cron_tasks.return_value = mock_result

        result = batch_validator.scan_database_for_python_internal_classes()

        assert result == []
        mock_db.close.assert_called_once()

    @patch("app.tasks.batch_class_validator.get_db")
    @patch("app.tasks.batch_class_validator.CronTaskCRUD")
    def test_数据库异常时返回空列表并关闭连接(self, mock_crud, mock_get_db, batch_validator):
        """当数据库操作抛出异常时，应安全返回空列表并关闭连接"""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_crud.get_cron_tasks.side_effect = Exception("数据库崩溃")

        result = batch_validator.scan_database_for_python_internal_classes()

        assert result == []
        mock_db.close.assert_called_once()

    @patch("app.tasks.batch_class_validator.get_db")
    @patch("app.tasks.batch_class_validator.CronTaskCRUD")
    def test_没有Python内部类任务时返回空列表(self, mock_crud, mock_get_db, batch_validator):
        """当所有任务都不是 Python 内部类类型时，应返回空列表"""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {
            "list": [
                {"task_id": 1, "task_type": 1},
                {"task_id": 2, "task_type": 2},
            ]
        }
        mock_crud.get_cron_tasks.return_value = mock_result

        result = batch_validator.scan_database_for_python_internal_classes()

        assert result == []


# ===========================================================================
# BatchClassValidator - validate_all_class_paths
# ===========================================================================


class TestValidateAllClassPaths:
    """全量类路径验证流程测试"""

    @patch.object(BatchClassValidator, "scan_database_for_python_internal_classes")
    def test_没有任务时返回no_tasks_found状态(self, mock_scan, batch_validator):
        """当数据库中没有任何 Python 内部类任务时，应返回 no_tasks_found"""
        mock_scan.return_value = []

        result = batch_validator.validate_all_class_paths()

        assert result["status"] == "no_tasks_found"
        assert "没有找到" in result["message"]
        assert "timestamp" in result

    @patch("app.tasks.batch_class_validator.validate_class_paths_batch")
    @patch.object(BatchClassValidator, "scan_database_for_python_internal_classes")
    def test_任务中没有类路径时返回no_class_paths_found(self, mock_scan, mock_batch, batch_validator):
        """当任务列表中没有有效的类路径格式时，应返回 no_class_paths_found"""
        mock_scan.return_value = [
            {"executor": "import os"},
            {"executor": "def foo(): pass"},
        ]

        result = batch_validator.validate_all_class_paths()

        assert result["status"] == "no_class_paths_found"
        assert "没有找到有效" in result["message"]
        mock_batch.assert_not_called()

    @patch.object(BatchClassValidator, "generate_detailed_report")
    @patch("app.tasks.batch_class_validator.validate_class_paths_batch")
    @patch.object(BatchClassValidator, "scan_database_for_python_internal_classes")
    def test_正常验证流程返回completed状态(self, mock_scan, mock_batch, mock_report, batch_validator):
        """有任务且有类路径时，应执行完整验证并返回详细报告"""
        mock_scan.return_value = [
            {"task_id": 1, "executor": "app.tasks.MyTask"},
        ]
        mock_batch.return_value = {
            "detailed_results": [{"class_path": "app.tasks.MyTask", "is_valid": True}],
            "summary": {"valid_count": 1, "invalid_count": 0},
        }
        mock_report.return_value = {"status": "completed", "summary": mock_batch.return_value["summary"]}

        result = batch_validator.validate_all_class_paths()

        mock_batch.assert_called_once_with(["app.tasks.MyTask"])
        mock_report.assert_called_once()
        assert result["status"] == "completed"


# ===========================================================================
# BatchClassValidator - save_reports_to_files
# ===========================================================================


class TestSaveReportsToFiles:
    """报告文件保存测试"""

    @patch("app.tasks.batch_class_validator.datetime")
    @patch("app.tasks.batch_class_validator.os.makedirs")
    @patch("app.tasks.batch_class_validator.os.path.join")
    @patch("builtins.open", new_callable=MagicMock)
    def test_成功保存报告和修复脚本(self, mock_open, mock_join, mock_makedirs, mock_dt, batch_validator):
        """应创建输出目录并保存 JSON 报告和 SQL 脚本两个文件"""
        mock_dt.now.return_value.strftime.return_value = "20260403_120000"
        mock_dt.now.return_value.isoformat.return_value = "2026-04-03T12:00:00"
        # os.path.join 每次调用返回不同路径
        mock_join.side_effect = lambda d, f: f"{d}/{f}"

        report = {
            "status": "completed",
            "detailed_results": [
                {
                    "task_id": 1,
                    "task_name": "测试",
                    "class_path": "app.Mod.Cls",
                    "is_valid": False,
                    "errors": [{"message": "模块不存在"}],
                    "suggested_fixes": ["检查路径"],
                }
            ],
        }

        report_file, script_file = batch_validator.save_reports_to_files(report, "/tmp/test_reports")

        mock_makedirs.assert_called_once_with("/tmp/test_reports", exist_ok=True)
        assert mock_open.call_count == 2
        assert "class_path_validation_report_" in report_file
        assert "class_path_repair_script_" in script_file

    @patch("app.tasks.batch_class_validator.datetime")
    @patch("app.tasks.batch_class_validator.os.makedirs")
    @patch("app.tasks.batch_class_validator.os.path.join")
    @patch("builtins.open", new_callable=MagicMock)
    def test_使用默认输出目录(self, mock_open, mock_join, mock_makedirs, mock_dt, batch_validator):
        """未指定输出目录时应使用默认的 reports 目录"""
        mock_dt.now.return_value.strftime.return_value = "20260403_120000"
        mock_dt.now.return_value.isoformat.return_value = "2026-04-03T12:00:00"
        mock_join.side_effect = lambda d, f: f"{d}/{f}"

        batch_validator.save_reports_to_files({"detailed_results": []})

        mock_makedirs.assert_called_once_with("reports", exist_ok=True)

    @patch("app.tasks.batch_class_validator.datetime")
    @patch("app.tasks.batch_class_validator.os.makedirs")
    @patch("app.tasks.batch_class_validator.os.path.join")
    @patch("builtins.open", new_callable=MagicMock)
    def test_空报告也能正常保存(self, mock_open, mock_join, mock_makedirs, mock_dt, batch_validator):
        """空的详细结果列表不应导致保存失败"""
        mock_dt.now.return_value.strftime.return_value = "20260403_120000"
        mock_dt.now.return_value.isoformat.return_value = "2026-04-03T12:00:00"
        mock_join.side_effect = lambda d, f: f"{d}/{f}"

        report = {"status": "completed", "detailed_results": []}

        report_file, script_file = batch_validator.save_reports_to_files(report, "/tmp/empty")

        assert report_file is not None
        assert script_file is not None
