# -*- coding: utf-8 -*-
"""
task_profiles 注册表回归测试

【覆盖目标】
- 6 个重型 task_code 在注册表中，且 heavy_sync=True。
- 未注册 task_code 返回 None（轻量任务放行）。
- is_heavy_task 谓词与 get_profile 一致。
- task_code 必须与 default_scheduled_tasks.py 的注册值严格对齐（防漂移）。
"""

import pytest

from app.tasks.task_profiles import TASK_PROFILES, TaskProfile, get_profile, is_heavy_task

# 与 app/data/default_scheduled_tasks.py 严格对齐的重型 task_code 集合
# 若 default_scheduled_tasks.py 新增/改名重型任务而忘了同步 task_profiles.py，
# 此常量是发现漂移的锚点。
EXPECTED_HEAVY_TASK_CODES = {
    "torrent_info_sync_ac608e4d",
    "tracker_sync_598b784c",
    "TORRENT_TRACKER_STATUS_JUDGE",
    "TRACKER_MESSAGE_LOGGER",
    "downloader_path_scan",
    "tracker_reannounce",
    "orphan_scan_cleanup",
}


class TestTaskProfilesRegistry:
    """TASK_PROFILES 注册表内容契约。"""

    def test_registry_keys_match_expected_heavy_tasks(self):
        """注册表的 key 集合必须等于 EXPECTED_HEAVY_TASK_CODES。

        漂移场景：
        - 新增重型任务忘了登记 → 注册表少 key，断言报红。
        - 改了 task_code 但没更新注册表 → key 不匹配，断言报红。
        """
        assert (
            set(TASK_PROFILES.keys()) == EXPECTED_HEAVY_TASK_CODES
        ), f"TASK_PROFILES 漂移：期望 {EXPECTED_HEAVY_TASK_CODES}，实际 {set(TASK_PROFILES.keys())}"

    @pytest.mark.parametrize("task_code", sorted(EXPECTED_HEAVY_TASK_CODES))
    def test_heavy_profile_flag(self, task_code):
        """每个已注册的重型任务 heavy_sync 必须为 True。"""
        profile = TASK_PROFILES[task_code]
        assert isinstance(profile, TaskProfile)
        assert profile.heavy_sync is True, f"{task_code} heavy_sync 必须为 True"
        assert profile.task_code == task_code
        # queue_limit 必须 ≥ 1，否则同类任务永远无法排队
        assert profile.queue_limit >= 1
        # wait_timeout 必须 > 0
        assert profile.wait_timeout > 0

    def test_tracker_reannounce_has_shorter_timeout(self):
        """高频任务 tracker_reannounce（5min）应有更短 wait_timeout，避免补跑堆积。

        收敛锚点：若有人把它改成默认 30s，此测试报红提醒评估补跑影响。
        """
        profile = TASK_PROFILES["tracker_reannounce"]
        assert (
            profile.wait_timeout <= 15.0
        ), f"tracker_reannounce 高频任务 wait_timeout={profile.wait_timeout} 过大，会加剧补跑"


class TestGetProfile:
    """get_profile 行为。"""

    @pytest.mark.parametrize("task_code", sorted(EXPECTED_HEAVY_TASK_CODES))
    def test_get_profile_returns_heavy(self, task_code):
        """已注册的 task_code 返回 TaskProfile。"""
        profile = get_profile(task_code)
        assert profile is not None
        assert profile.task_code == task_code

    def test_get_profile_returns_none_for_unregistered(self):
        """未注册 task_code 返回 None（轻量任务放行）。"""
        assert get_profile("nonexistent_task_code_xyz") is None

    def test_get_profile_returns_none_for_empty(self):
        """空字符串/None 返回 None。"""
        assert get_profile("") is None
        assert get_profile(None) is None

    def test_is_heavy_task_predicate_consistent(self):
        """is_heavy_task 与 get_profile 结果一致。"""
        for code in EXPECTED_HEAVY_TASK_CODES:
            assert is_heavy_task(code) is True
        assert is_heavy_task("nonexistent") is False
        assert is_heavy_task("") is False
        assert is_heavy_task(None) is False


class TestTaskProfilesAlignWithDefaultTasks:
    """TASK_PROFILES 与 default_scheduled_tasks.py 交叉验证（防单边漂移）。

    漂移场景：
    - default_scheduled_tasks.py 改了某 task_code，task_profiles 没同步 → 测试报红。
    - task_profiles 删了某 profile，但 default_scheduled_tasks.py 还有 → 测试报红。
    - 注意：default_scheduled_tasks.py 没有"是否重型"标记字段，无法自动判定哪些
      是重型，只能验证"TASK_PROFILES 的每个 key 都在 DEFAULT_SCHEDULED_TASKS 中存在"。
    """

    def test_all_profile_codes_exist_in_default_scheduled_tasks(self):
        """TASK_PROFILES 的每个 task_code 必须在 DEFAULT_SCHEDULED_TASKS 中存在。

        防止 task_profiles 单边改名/删任务导致的漂移。
        """
        from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS

        default_codes = {t["task_code"] for t in DEFAULT_SCHEDULED_TASKS}
        profile_codes = set(TASK_PROFILES.keys())

        # 每个 profile 的 task_code 必须在 default 中存在
        missing_in_default = profile_codes - default_codes
        assert not missing_in_default, (
            f"TASK_PROFILES 含有 default_scheduled_tasks.py 中不存在的 task_code: "
            f"{missing_in_default}。"
            f"这通常意味着某重型任务被重命名或删除，但 task_profiles 没同步。"
        )

    def test_profile_codes_subset_of_python_class_tasks(self):
        """所有重型 profile 必须对应 task_type=4（Python 内部类）任务。

        admission 接入点 _run_python_internal_class 只覆盖 task_type=4；
        若某重型任务被错误配置为其它 task_type，admission 不会生效。
        """
        from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS

        TASK_TYPE_PYTHON_INTERNAL = 4

        for code in TASK_PROFILES:
            task = next(t for t in DEFAULT_SCHEDULED_TASKS if t["task_code"] == code)
            assert task["task_type"] == TASK_TYPE_PYTHON_INTERNAL, (
                f"重型任务 {code} 的 task_type={task['task_type']}，"
                f"必须是 {TASK_TYPE_PYTHON_INTERNAL}（Python内部类）才能进入 admission。"
            )
