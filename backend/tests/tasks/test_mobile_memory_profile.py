# -*- coding: utf-8 -*-
"""移动端内存 profile 测试（2026-09-05 Tier-1）。

覆盖：
- 分配器归还钩子 release_free_heap_memory 的平台分支与降级语义；
- android-server 形态门控：GitHub 版本检查任务不注册（WAL 门控经
  is_android_server 单测 + 代码审覆盖，lifespan 内联门控不做重量级装配测试）。
"""

from unittest.mock import MagicMock, patch

from app.core import platform_capabilities
from app.services import sync_observability as obs
from app.tasks.cron_executor import CronTaskExecutor


# ==================== is_android_server 判定 ====================


class TestIsAndroidServer:
    def test_env_set_android_server(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "android-server")
        assert platform_capabilities.is_android_server() is True

    def test_env_unset_defaults_desktop(self, monkeypatch):
        monkeypatch.delenv("BTDECK_PLATFORM", raising=False)
        assert platform_capabilities.is_android_server() is False

    def test_invalid_value_falls_back_desktop(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "not-a-platform")
        assert platform_capabilities.is_android_server() is False

    def test_desktop_companion_mode_not_android(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "desktop")
        assert platform_capabilities.is_android_server() is False


# ==================== 分配器归还钩子 ====================


def _fake_libc(with_malloc_trim=True, with_mallopt=True):
    lib = MagicMock()
    if with_malloc_trim:
        lib.malloc_trim = MagicMock(return_value=1)
    else:
        del lib.malloc_trim
    if with_mallopt:
        lib.mallopt = MagicMock(return_value=1)
    else:
        del lib.mallopt
    return lib


class TestReleaseFreeHeapMemory:
    def test_non_linux_platform_returns_false(self, monkeypatch):
        monkeypatch.setattr(obs.sys, "platform", "win32")
        assert obs.release_free_heap_memory() is False

    def test_glibc_malloc_trim_preferred(self, monkeypatch):
        """glibc 路径：malloc_trim(0) 被调用且返回 True。"""
        monkeypatch.setattr(obs.sys, "platform", "linux")
        lib = _fake_libc(with_mallopt=False)
        with patch("ctypes.CDLL", return_value=lib):
            assert obs.release_free_heap_memory() is True
        lib.malloc_trim.assert_called_once()

    def test_bionic_falls_back_to_mallopt_purge(self, monkeypatch):
        """bionic 路径（无 malloc_trim）：mallopt(M_PURGE=101, 0) 被调用。"""
        monkeypatch.setattr(obs.sys, "platform", "linux")
        lib = _fake_libc(with_malloc_trim=False)
        with patch("ctypes.CDLL", return_value=lib):
            assert obs.release_free_heap_memory() is True
        lib.mallopt.assert_called_once()
        args = lib.mallopt.call_args.args
        assert int(args[0].value) == 101, f"M_PURGE 常量应为 101，实际 {args[0]}"
        assert int(args[1].value) == 0

    def test_trim_failing_returns_false(self, monkeypatch):
        """malloc_trim 返回 0（未归还任何页）→ False，不抛异常。"""
        monkeypatch.setattr(obs.sys, "platform", "linux")
        lib = _fake_libc(with_mallopt=False)
        lib.malloc_trim = MagicMock(return_value=0)
        with patch("ctypes.CDLL", return_value=lib):
            assert obs.release_free_heap_memory() is False

    def test_cdll_failure_returns_false(self, monkeypatch):
        monkeypatch.setattr(obs.sys, "platform", "linux")
        with patch("ctypes.CDLL", side_effect=OSError("no libc")):
            assert obs.release_free_heap_memory() is False

    def test_no_allocators_returns_false(self, monkeypatch):
        monkeypatch.setattr(obs.sys, "platform", "linux")
        lib = _fake_libc(with_malloc_trim=False, with_mallopt=False)
        with patch("ctypes.CDLL", return_value=lib):
            assert obs.release_free_heap_memory() is False


# ==================== android-server 门控：GitHub 版本检查 ====================


class TestVersionCheckGating:
    async def test_android_server_skips_version_check_job(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "android-server")
        executor = CronTaskExecutor()
        executor._ensure_version_check_job()
        assert executor.scheduler.get_job("github_version_check") is None

    async def test_desktop_registers_version_check_job(self, monkeypatch):
        monkeypatch.delenv("BTDECK_PLATFORM", raising=False)
        executor = CronTaskExecutor()
        executor._ensure_version_check_job()
        try:
            assert executor.scheduler.get_job("github_version_check") is not None
        finally:
            executor.scheduler.remove_job("github_version_check")

    def test_trim_toggle_gate_in_sampler(self):
        """SYNC_PROCESS_MEMORY_TRIM_ENABLED 默认开（回滚开关存在性）。"""
        from app.core.config import settings

        assert settings.SYNC_PROCESS_MEMORY_TRIM_ENABLED is True
