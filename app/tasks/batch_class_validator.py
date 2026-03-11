"""
批量类路径验证脚本 - REQ-003实现
用于验证和修复数据库中的Python内部类任务数据完整性
"""

import logging
import sys
import os
from typing import Dict, List, Any
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import get_db
from app.tasks.cron_crud import CronTaskCRUD
from app.tasks.class_path_validator import validate_single_class_path, validate_class_paths_batch

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BatchClassValidator:
    """批量类路径验证器"""

    def __init__(self):
        self.validation_results = []
        self.fix_suggestions = []

    def scan_database_for_python_internal_classes(self) -> List[Dict[str, Any]]:
        """
        扫描数据库中所有Python内部类任务

        Returns:
            List[Dict[str, Any]]: Python内部类任务列表
        """
        try:
            db = next(get_db())
            result = CronTaskCRUD.get_cron_tasks(db, skip=0, limit=1000, task_type=4)  # 只获取Python内部类任务

            if not result.success:
                logger.error(f"获取任务列表失败: {result.message}")
                return []

            all_tasks = result.data.get('list', [])
            python_internal_tasks = [
                task for task in all_tasks
                if task.get('task_type') == 4  # Python内部类类型
            ]

            logger.info(f"找到 {len(python_internal_tasks)} 个Python内部类任务")
            return python_internal_tasks

        except Exception as e:
            logger.error(f"扫描数据库时发生错误: {str(e)}")
            return []
        finally:
            if 'db' in locals():
                db.close()

    def extract_class_paths_from_tasks(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """
        从任务列表中提取类路径

        Args:
            tasks: 任务列表

        Returns:
            List[str]: 类路径列表
        """
        class_paths = []
        for task in tasks:
            executor = task.get('executor', '').strip()
            if executor:
                # 检查是否可能是类路径格式
                if '.' in executor and not executor.strip().startswith(('import', 'def', 'print', 'await', 'time', 'async', '#')):
                    class_paths.append(executor)

        logger.info(f"从任务中提取到 {len(class_paths)} 个可能的类路径")
        return class_paths

    def validate_all_class_paths(self) -> Dict[str, Any]:
        """
        验证数据库中所有Python内部类的类路径

        Returns:
            Dict[str, Any]: 验证报告
        """
        logger.info("开始批量验证类路径...")

        # 1. 扫描数据库
        python_tasks = self.scan_database_for_python_internal_classes()
        if not python_tasks:
            return {
                "status": "no_tasks_found",
                "message": "数据库中没有找到Python内部类任务",
                "timestamp": datetime.now().isoformat()
            }

        # 2. 提取类路径
        class_paths = self.extract_class_paths_from_tasks(python_tasks)
        if not class_paths:
            return {
                "status": "no_class_paths_found",
                "message": "没有找到有效的类路径格式",
                "timestamp": datetime.now().isoformat()
            }

        # 3. 批量验证
        logger.info(f"开始验证 {len(class_paths)} 个类路径...")
        validation_report = validate_class_paths_batch(class_paths)

        # 4. 生成详细报告
        detailed_report = self.generate_detailed_report(python_tasks, validation_report)

        return detailed_report

    def generate_detailed_report(self, tasks: List[Dict[str, Any]], validation_report: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成详细的验证报告

        Args:
            tasks: 原始任务数据
            validation_report: 验证结果报告

        Returns:
            Dict[str, Any]: 详细报告
        """
        detailed_results = []

        # 将验证结果与任务数据关联
        class_path_to_task = {}
        for task in tasks:
            executor = task.get('executor', '').strip()
            if executor and '.' in executor:
                class_path_to_task[executor] = task

        for validation_result in validation_report['detailed_results']:
            class_path = validation_result['class_path']
            task = class_path_to_task.get(class_path)

            detailed_result = {
                "task_id": task.get('task_id') if task else None,
                "task_name": task.get('task_name') if task else None,
                "task_code": task.get('task_code') if task else None,
                "class_path": class_path,
                "is_valid": validation_result['is_valid'],
                "errors": validation_result['errors'],
                "module_path": validation_result.get('module_path'),
                "class_name": validation_result.get('class_name'),
                "suggested_fixes": []
            }

            # 为每个错误生成修复建议
            for error in validation_result['errors']:
                # 使用验证器的建议生成功能
                from app.tasks.class_path_validator import class_path_validator
                fixes = class_path_validator.suggest_fix_for_error(error)
                detailed_result["suggested_fixes"].extend(fixes)

            # 去重修复建议
            detailed_result["suggested_fixes"] = list(set(detailed_result["suggested_fixes"]))

            detailed_results.append(detailed_result)

        return {
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "summary": validation_report['summary'],
            "error_statistics": validation_report['error_statistics'],
            "repair_suggestions": validation_report['repair_suggestions'],
            "detailed_results": detailed_results,
            "total_python_tasks_scanned": len(tasks),
            "total_class_paths_validated": len(validation_report['detailed_results'])
        }

    def generate_repair_script(self, validation_report: Dict[str, Any]) -> str:
        """
        生成修复脚本

        Args:
            validation_report: 验证报告

        Returns:
            str: 修复SQL脚本
        """
        repair_sql_lines = []
        repair_sql_lines.append("-- Python内部类数据完整性修复脚本")
        repair_sql_lines.append(f"-- 生成时间: {datetime.now().isoformat()}")
        repair_sql_lines.append("")
        repair_sql_lines.append("-- 注意: 执行前请备份数据库!")
        repair_sql_lines.append("")

        for result in validation_report['detailed_results']:
            if not result['is_valid'] and result['task_id']:
                task_id = result['task_id']
                task_name = result['task_name']
                class_path = result['class_path']

                repair_sql_lines.append(f"-- 任务ID: {task_id}, 名称: {task_name}")
                repair_sql_lines.append(f"-- 类路径: {class_path}")
                repair_sql_lines.append("-- 错误详情:")

                for error in result['errors']:
                    error_msg = error.get('message', '')
                    repair_sql_lines.append(f"--   - {error_msg}")

                repair_sql_lines.append("-- 建议修复:")
                for fix in result['suggested_fixes']:
                    repair_sql_lines.append(f"--   * {fix}")

                # 生成禁用任务的SQL（临时措施）
                repair_sql_lines.append(f"-- 临时禁用问题任务（建议手动修复后重新启用）:")
                repair_sql_lines.append(f"UPDATE cron_task SET enabled = 0 WHERE task_id = {task_id};")
                repair_sql_lines.append("")

        return "\n".join(repair_sql_lines)

    def save_reports_to_files(self, report: Dict[str, Any], output_dir: str = "reports"):
        """
        保存报告到文件

        Args:
            report: 验证报告
            output_dir: 输出目录
        """
        import json

        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)

        # 保存详细报告（JSON格式）
        report_file = os.path.join(output_dir, f"class_path_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"详细报告已保存到: {report_file}")

        # 保存修复脚本
        repair_script = self.generate_repair_script(report)
        script_file = os.path.join(output_dir, f"class_path_repair_script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql")
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(repair_script)

        logger.info(f"修复脚本已保存到: {script_file}")

        return report_file, script_file


def main():
    """主函数"""
    validator = BatchClassValidator()

    print("=" * 60)
    print("Python内部类数据完整性验证工具")
    print("REQ-003: Python内部类数据完整性修复")
    print("=" * 60)

    # 执行验证
    report = validator.validate_all_class_paths()

    # 显示结果摘要
    print(f"\n验证状态: {report['status']}")
    print(f"验证时间: {report['timestamp']}")

    if report['status'] == 'completed':
        summary = report['summary']
        print(f"\n验证结果摘要:")
        print(f"  总任务数: {report['total_python_tasks_scanned']}")
        print(f"  验证类路径数: {report['total_class_paths_validated']}")
        print(f"  有效类路径: {summary['valid_count']}")
        print(f"  无效类路径: {summary['invalid_count']}")
        print(f"  成功率: {summary['success_rate']}")

        if report['error_statistics']:
            print(f"\n错误统计:")
            for error_type, count in report['error_statistics'].items():
                print(f"  {error_type}: {count}")

        # 保存报告文件
        try:
            report_file, script_file = validator.save_reports_to_files(report)
            print(f"\n报告文件已生成:")
            print(f"  详细报告: {report_file}")
            print(f"  修复脚本: {script_file}")
        except Exception as e:
            print(f"保存报告文件时出错: {str(e)}")
    else:
        print(f"\n消息: {report['message']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()