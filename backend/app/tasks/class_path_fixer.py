"""
类路径修复工具 - REQ-003实现
用于修复数据库中无效的Python内部类类路径

功能:
1. 自动检测无效类路径
2. 提供修复建议和选项
3. 支持批量修复操作
4. 生成修复日志和报告
"""

import logging
import sys
import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import get_db
from app.tasks.cron_crud import CronTaskCRUD
from app.tasks.class_path_validator import validate_single_class_path, ClassPathValidationError, class_path_validator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ClassPathFixer:
    """类路径修复器"""

    def __init__(self):
        self.fix_history = []
        self.auto_fix_enabled = True

    def analyze_invalid_class_paths(self) -> Dict[str, Any]:
        """
        分析数据库中的无效类路径

        Returns:
            Dict[str, Any]: 分析结果
        """
        logger.info("开始分析无效类路径...")

        # 获取所有Python内部类任务
        db = next(get_db())
        try:
            result = CronTaskCRUD.get_cron_tasks(db, skip=0, limit=1000, task_type=4)
            if not result.success:
                return {
                    "status": "error",
                    "message": f"获取任务失败: {result.message}"
                }

            all_tasks = result.data.get('list', [])
            analysis_results = []

            for task in all_tasks:
                task_id = task.get('task_id')
                task_name = task.get('task_name')
                task_code = task.get('task_code')
                executor = task.get('executor', '').strip()

                analysis = {
                    "task_id": task_id,
                    "task_name": task_name,
                    "task_code": task_code,
                    "original_executor": executor,
                    "is_class_path": False,
                    "validation_result": None,
                    "fix_suggestions": [],
                    "auto_fix_possible": False,
                    "recommended_fix": None
                }

                # 检查是否是类路径格式
                if executor and '.' in executor and not executor.strip().startswith(('import', 'def', 'print', 'await', 'time', 'async', '#')):
                    analysis["is_class_path"] = True

                    # 验证类路径
                    validation_result = validate_single_class_path(executor)
                    analysis["validation_result"] = validation_result

                    if not validation_result["is_valid"]:
                        # 生成修复建议
                        for error in validation_result["errors"]:
                            fixes = class_path_validator.suggest_fix_for_error(error)
                            analysis["fix_suggestions"].extend(fixes)

                        # 去重修复建议
                        analysis["fix_suggestions"] = list(set(analysis["fix_suggestions"]))

                        # 判断是否可以自动修复
                        analysis["auto_fix_possible"] = self.can_auto_fix(validation_result)

                        if analysis["auto_fix_possible"]:
                            analysis["recommended_fix"] = self.generate_auto_fix(executor, validation_result)

                analysis_results.append(analysis)

            # 统计结果
            total_tasks = len(analysis_results)
            class_path_tasks = sum(1 for a in analysis_results if a["is_class_path"])
            valid_class_paths = sum(1 for a in analysis_results if a["is_class_path"] and a["validation_result"] and a["validation_result"]["is_valid"])
            invalid_class_paths = class_path_tasks - valid_class_paths
            auto_fixable = sum(1 for a in analysis_results if a.get("auto_fix_possible", False))

            return {
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total_python_tasks": total_tasks,
                    "class_path_tasks": class_path_tasks,
                    "valid_class_paths": valid_class_paths,
                    "invalid_class_paths": invalid_class_paths,
                    "auto_fixable": auto_fixable,
                    "fix_rate": f"{(auto_fixable / invalid_class_paths * 100):.1f}%" if invalid_class_paths > 0 else "0%"
                },
                "detailed_analysis": analysis_results
            }

        finally:
            db.close()

    def can_auto_fix(self, validation_result: Dict[str, Any]) -> bool:
        """
        判断是否可以自动修复

        Args:
            validation_result: 验证结果

        Returns:
            bool: 是否可以自动修复
        """
        if not validation_result["errors"]:
            return False

        # 只能修复某些类型的简单错误
        auto_fixable_errors = {
            "INVALID_FORMAT"  # 格式错误通常需要人工干预
        }

        # 检查是否有可以自动修复的错误
        for error in validation_result["errors"]:
            error_type = error.get("error_type")
            if error_type in auto_fixable_errors:
                return True

        return False

    def generate_auto_fix(self, original_path: str, validation_result: Dict[str, Any]) -> Optional[str]:
        """
        生成自动修复建议

        Args:
            original_path: 原始类路径
            validation_result: 验证结果

        Returns:
            Optional[str]: 修复后的类路径
        """
        # 对于格式错误，尝试修复基本问题
        if validation_result["errors"]:
            for error in validation_result["errors"]:
                error_type = error.get("error_type")

                if error_type == "INVALID_FORMAT":
                    # 移除多余空格
                    fixed_path = original_path.strip()

                    # 移除开头和结尾的引号
                    if fixed_path.startswith('"') and fixed_path.endswith('"'):
                        fixed_path = fixed_path[1:-1]
                    elif fixed_path.startswith("'") and fixed_path.endswith("'"):
                        fixed_path = fixed_path[1:-1]

                    # 验证修复后的路径
                    if fixed_path != original_path:
                        validation = validate_single_class_path(fixed_path)
                        if validation["is_valid"]:
                            return fixed_path

        return None

    def apply_auto_fixes(self, analysis_result: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
        """
        应用自动修复

        Args:
            analysis_result: 分析结果
            dry_run: 是否为试运行模式

        Returns:
            Dict[str, Any]: 修复结果
        """
        if not dry_run:
            logger.warning("自动修复功能需要在生产环境中谨慎使用")
            return {"status": "disabled", "message": "自动修复功能已禁用，仅支持试运行模式"}

        fix_results = []
        db = next(get_db())

        try:
            for analysis in analysis_result["detailed_analysis"]:
                if not analysis.get("auto_fix_possible", False):
                    continue

                task_id = analysis["task_id"]
                original_executor = analysis["original_executor"]
                recommended_fix = analysis.get("recommended_fix")

                fix_result = {
                    "task_id": task_id,
                    "task_name": analysis["task_name"],
                    "original_executor": original_executor,
                    "recommended_fix": recommended_fix,
                    "fix_applied": False,
                    "fix_success": False,
                    "error_message": None
                }

                if recommended_fix and recommended_fix != original_executor:
                    if dry_run:
                        fix_result["fix_applied"] = True
                        fix_result["fix_success"] = True
                        fix_result["message"] = "试运行模式 - 修复建议已生成"
                    else:
                        # 实际应用修复（暂时禁用）
                        pass

                fix_results.append(fix_result)

            return {
                "status": "completed",
                "mode": "dry_run" if dry_run else "live",
                "timestamp": datetime.now().isoformat(),
                "fixes_attempted": len(fix_results),
                "fixes_successful": sum(1 for f in fix_results if f.get("fix_success", False)),
                "detailed_results": fix_results
            }

        finally:
            db.close()

    def generate_manual_fix_guide(self, analysis_result: Dict[str, Any]) -> str:
        """
        生成手动修复指南

        Args:
            analysis_result: 分析结果

        Returns:
            str: 修复指南
        """
        guide_lines = []
        guide_lines.append("# Python内部类数据完整性修复指南")
        guide_lines.append(f"生成时间: {datetime.now().isoformat()}")
        guide_lines.append("")

        summary = analysis_result["summary"]
        guide_lines.append("## 修复摘要")
        guide_lines.append(f"- 总Python任务数: {summary['total_python_tasks']}")
        guide_lines.append(f"- 类路径任务数: {summary['class_path_tasks']}")
        guide_lines.append(f"- 有效类路径: {summary['valid_class_paths']}")
        guide_lines.append(f"- 无效类路径: {summary['invalid_class_paths']}")
        guide_lines.append(f"- 可自动修复: {summary['auto_fixable']}")
        guide_lines.append("")

        if summary['invalid_class_paths'] > 0:
            guide_lines.append("## 需要手动修复的任务")

            for analysis in analysis_result["detailed_analysis"]:
                if analysis["is_class_path"] and (not analysis["validation_result"] or not analysis["validation_result"]["is_valid"]):
                    task_id = analysis["task_id"]
                    task_name = analysis["task_name"]
                    original_executor = analysis["original_executor"]

                    guide_lines.append(f"\n### 任务ID: {task_id} - {task_name}")
                    guide_lines.append(f"**原始类路径**: `{original_executor}`")

                    if analysis["validation_result"] and analysis["validation_result"]["errors"]:
                        guide_lines.append("\n**错误详情**:")
                        for error in analysis["validation_result"]["errors"]:
                            guide_lines.append(f"- {error.get('message', '未知错误')}")

                    if analysis["fix_suggestions"]:
                        guide_lines.append("\n**修复建议**:")
                        for suggestion in analysis["fix_suggestions"]:
                            guide_lines.append(f"- {suggestion}")

                    if analysis.get("recommended_fix"):
                        guide_lines.append(f"\n**推荐修复**: `{analysis['recommended_fix']}`")

                    # 生成SQL修复语句模板
                    guide_lines.append("\n**SQL修复模板**:")
                    guide_lines.append(f"```sql")
                    guide_lines.append(f"-- 备份当前任务")
                    guide_lines.append(f"SELECT * FROM cron_task WHERE task_id = {task_id};")
                    guide_lines.append(f"-- 修复类路径（请将 NEW_CLASS_PATH 替换为正确值）")
                    guide_lines.append(f"UPDATE cron_task SET executor = 'NEW_CLASS_PATH', update_time = datetime('now') WHERE task_id = {task_id};")
                    guide_lines.append(f"```")

        guide_lines.append("\n## 修复步骤")
        guide_lines.append("1. 查看上述需要修复的任务列表")
        guide_lines.append("2. 根据错误详情和修复建议确定正确的类路径")
        guide_lines.append("3. 在测试环境中验证修复后的类路径是否有效")
        guide_lines.append("4. 使用提供的SQL模板或通过管理界面修复类路径")
        guide_lines.append("5. 修复后重新运行验证工具确认修复成功")
        guide_lines.append("")
        guide_lines.append("## 注意事项")
        guide_lines.append("- 修复前请务必备份数据库")
        guide_lines.append("- 建议在测试环境中先验证修复方案")
        guide_lines.append("- 修复后需要重启任务调度器以生效")
        guide_lines.append("- 记录所有修复操作以备审计")

        return "\n".join(guide_lines)

    def save_fix_guide(self, analysis_result: Dict[str, Any], output_dir: str = "reports") -> str:
        """
        保存修复指南

        Args:
            analysis_result: 分析结果
            output_dir: 输出目录

        Returns:
            str: 保存的文件路径
        """
        os.makedirs(output_dir, exist_ok=True)

        guide_content = self.generate_manual_fix_guide(analysis_result)
        guide_file = os.path.join(output_dir, f"class_path_fix_guide_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")

        with open(guide_file, 'w', encoding='utf-8') as f:
            f.write(guide_content)

        logger.info(f"修复指南已保存到: {guide_file}")
        return guide_file


def main():
    """主函数"""
    print("=" * 60)
    print("Python内部类数据完整性修复工具")
    print("REQ-003: Python内部类数据完整性修复")
    print("=" * 60)

    fixer = ClassPathFixer()

    # 1. 分析现有问题
    print("\n1. 正在分析数据库中的类路径...")
    analysis = fixer.analyze_invalid_class_paths()

    if analysis["status"] != "completed":
        print(f"分析失败: {analysis.get('message', '未知错误')}")
        return

    # 显示分析结果
    summary = analysis["summary"]
    print(f"\n分析结果摘要:")
    print(f"  总Python任务数: {summary['total_python_tasks']}")
    print(f"  类路径任务数: {summary['class_path_tasks']}")
    print(f"  有效类路径: {summary['valid_class_paths']}")
    print(f"  无效类路径: {summary['invalid_class_paths']}")
    print(f"  可自动修复: {summary['auto_fixable']}")
    print(f"  修复率预估: {summary['fix_rate']}")

    # 2. 生成修复方案
    if summary['invalid_class_paths'] > 0:
        print(f"\n2. 生成修复方案...")

        # 生成手动修复指南
        guide_file = fixer.save_fix_guide(analysis)
        print(f"   修复指南已生成: {guide_file}")

        # 试运行自动修复（如果可能）
        if summary['auto_fixable'] > 0:
            print(f"\n3. 试运行自动修复...")
            auto_fix_result = fixer.apply_auto_fixes(analysis, dry_run=True)

            if auto_fix_result["status"] == "completed":
                print(f"   尝试修复数: {auto_fix_result['fixes_attempted']}")
                print(f"   预计成功数: {auto_fix_result['fixes_successful']}")
    else:
        print(f"\n✅ 所有类路径都已验证通过，无需修复！")

    print("\n" + "=" * 60)
    print("修复工具运行完成")
    print("=" * 60)


if __name__ == "__main__":
    main()