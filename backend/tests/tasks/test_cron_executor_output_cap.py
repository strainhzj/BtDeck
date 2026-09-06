# -*- coding: utf-8 -*-
"""cron_executor 脚本输出上限与结果渲染摘要化测试（OOM 加固 2026-09-05 批次 4）。

覆盖：
- R5 `_communicate_with_output_cap`：单流字节上限、超限标记与原始总长、
  UTF-8 多字节截断安全、双流并发 drain（假进程 + 手喂 StreamReader）、
  <=0 回落不限语义；
- R5 `_run_script_process`：成功/失败/截断标记进入 log_detail；
- R6 `_summarize_result_for_log`：大结果（10 万元素）不放大——有界输出，
  list/dict 只记长度 + 前 3 项概览；
- R6 集成：`_run_python_internal_class` 的 log_detail 尾巴为摘要且
  phase 行保留（复用 fake module 注入模式，见 test_cron_executor_admission）。

均为净新增覆盖：改造前这两个路径没有任何直接测试。
"""

import asyncio
import sys
import time
import types
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.tasks import cron_executor as ce


# ==================== 假进程构造 ====================


def _make_fake_process(stdout_chunks, stderr_chunks):
    """构造带手喂 StreamReader 的假子进程（平台无关，不真实 spawn）。"""

    def _stream(chunks):
        reader = asyncio.StreamReader()
        for chunk in chunks:
            reader.feed_data(chunk)
        reader.feed_eof()
        return reader

    process = MagicMock()
    process.stdout = _stream(stdout_chunks)
    process.stderr = _stream(stderr_chunks)
    process.wait = AsyncMock(returnvalue=0)
    process.returncode = 0
    return process


class TestCommunicateWithOutputCap:
    async def test_stdout_capped_with_marker_and_total(self):
        chunks = [b"x" * 65536, b"y" * 65536, b"z" * 100]
        process = _make_fake_process(chunks, [b"err"])
        stdout_text, stderr_text = await ce._communicate_with_output_cap(process, 1000)

        assert stdout_text.startswith("x" * 1000)
        assert "[TRUNCATED]" in stdout_text
        assert "131172" in stdout_text  # 原始总长 65536*2+100
        assert "1000" in stdout_text
        assert stderr_text == "err"  # 未超限的流不加标记

    async def test_utf8_multibyte_truncation_is_safe(self):
        # 每个汉字 3 字节；上限切在多字节序列中间时 errors=ignore 丢弃残缺序列
        process = _make_fake_process(["你好世界".encode("utf-8") * 100], [])
        stdout_text, _ = await ce._communicate_with_output_cap(process, 100)
        assert stdout_text.startswith("你好世")  # 99 字节 → 3 个完整字符 + 残缺被丢
        assert "[TRUNCATED]" in stdout_text

    async def test_under_cap_no_marker(self):
        process = _make_fake_process([b"hello"], [b"warning: x"])
        stdout_text, stderr_text = await ce._communicate_with_output_cap(process, 1000)
        assert stdout_text == "hello"
        assert stderr_text == "warning: x"
        assert "[TRUNCATED]" not in stdout_text
        assert "[TRUNCATED]" not in stderr_text

    async def test_both_streams_drained(self):
        """双流都被读完（防只读一流导致另一流管道写满死锁——假件层面验证 drain 到 EOF）。"""
        big = [b"a" * 65536] * 5
        process = _make_fake_process(big, [b"e" * 65536] * 5)
        stdout_text, stderr_text = await ce._communicate_with_output_cap(process, 500)
        assert len(stdout_text.split("\n")[0]) == 500
        assert "[TRUNCATED]" in stdout_text and "[TRUNCATED]" in stderr_text
        assert process.wait.await_count == 1

    async def test_zero_or_negative_cap_means_unlimited(self):
        process = _make_fake_process([b"a" * 100000], [b""])
        stdout_text, _ = await ce._communicate_with_output_cap(process, 0)
        assert len(stdout_text) == 100000
        assert "[TRUNCATED]" not in stdout_text

    async def test_outer_cancel_cleans_readers_and_kills_child(self, monkeypatch):
        """取消路径（2026-09-06 泄漏修复回归）：外层在 await 读取任务时被取消 →
        两个读取任务被取消回收、进程树被终止且收尸，无遗留 _read_capped 协程。

        旧实现依次 await 且无 finally：等待 stdout 时被取消会孤儿化 stderr 任务，
        process.wait() 被跳过、子进程不终止——管道不关则协程永久挂在 read() 上。
        """
        hang_event = asyncio.Event()

        class _HangingStream:
            async def read(self, n: int = -1) -> bytes:
                await hang_event.wait()  # 模拟管道一直不关闭
                return b""

        process = MagicMock()
        process.stdout = _HangingStream()
        process.stderr = _HangingStream()
        process.returncode = None

        async def _wait_sets_returncode():
            process.returncode = -9  # 模拟真实语义：wait() 收尸后才设置退出码

        process.kill = MagicMock()
        process.wait = AsyncMock(side_effect=_wait_sets_returncode)

        tree_kill_calls: list = []
        monkeypatch.setattr(ce, "_kill_process_tree", lambda proc: tree_kill_calls.append(proc))

        async def _run():
            return await ce._communicate_with_output_cap(process, 1024)

        outer = asyncio.create_task(_run())
        await asyncio.sleep(0)  # 让两个读取任务先挂到 read() 上
        outer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await outer

        # 让被取消的读取任务完成收尾后再检查遗留
        for _ in range(3):
            await asyncio.sleep(0)
        lingering = [
            task
            for task in asyncio.all_tasks()
            if not task.done() and task.get_coro().cr_code.co_name == "_read_capped"
        ]
        assert lingering == [], f"取消后仍遗留读取协程: {lingering}"
        assert tree_kill_calls == [process], "取消路径应整树终止进程"
        assert process.wait.await_count == 1, "树杀后应收尸（await wait）"

    async def test_first_reader_error_cleans_second_reader_and_child(self, monkeypatch):
        """异常路径（2026-09-06 同族加固）：stdout 读取抛异常 → stderr 读取任务
        同样被取消回收，进程树被终止——旧实现第二个任务同样会孤儿化。"""

        class _BrokenStream:
            async def read(self, n: int = -1) -> bytes:
                raise RuntimeError("stream broken")

        hang_event = asyncio.Event()

        class _HangingStream:
            async def read(self, n: int = -1) -> bytes:
                await hang_event.wait()
                return b""

        process = MagicMock()
        process.stdout = _BrokenStream()
        process.stderr = _HangingStream()
        process.returncode = None

        async def _wait_sets_returncode():
            process.returncode = -9

        process.kill = MagicMock()
        process.wait = AsyncMock(side_effect=_wait_sets_returncode)

        tree_kill_calls: list = []
        monkeypatch.setattr(ce, "_kill_process_tree", lambda proc: tree_kill_calls.append(proc))

        with pytest.raises(RuntimeError, match="stream broken"):
            await ce._communicate_with_output_cap(process, 1024)

        for _ in range(3):
            await asyncio.sleep(0)
        lingering = [
            task
            for task in asyncio.all_tasks()
            if not task.done() and task.get_coro().cr_code.co_name == "_read_capped"
        ]
        assert lingering == [], f"首个读取任务异常后仍遗留读取协程: {lingering}"
        assert tree_kill_calls == [process], "异常路径应整树终止进程"
        assert process.wait.await_count == 1


class TestRunScriptProcess:
    async def test_success_detail_contains_output(self):
        executor = ce.CronTaskExecutor()
        process = _make_fake_process([b"ok-output"], [b""])
        with patch.object(ce.asyncio, "create_subprocess_shell", new=AsyncMock(return_value=process)):
            result = await executor._run_shell_script("echo hi")
        assert result["success"] is True
        assert "Shell脚本执行成功" in result["log_detail"]
        assert "ok-output" in result["log_detail"]

    async def test_failure_detail_contains_capped_stderr(self):
        executor = ce.CronTaskExecutor()
        process = _make_fake_process([b""], [b"E" * 200000])
        process.returncode = 3
        with patch.object(ce.asyncio, "create_subprocess_shell", new=AsyncMock(return_value=process)):
            result = await executor._run_cmd_script("bad-command")
        assert result["success"] is False
        assert "CMD脚本执行失败" in result["log_detail"]
        assert "[TRUNCATED]" in result["log_detail"]

    async def test_cap_respects_settings_override(self, monkeypatch):
        monkeypatch.setattr(settings, "CRON_SCRIPT_OUTPUT_MAX_BYTES", 10)
        executor = ce.CronTaskExecutor()
        process = _make_fake_process([b"A" * 5000], [b""])
        with patch.object(ce.asyncio, "create_subprocess_shell", new=AsyncMock(return_value=process)):
            result = await executor._run_shell_script("x")
        assert result["success"] is True
        assert "A" * 10 in result["log_detail"]
        assert "A" * 11 not in result["log_detail"].split("[TRUNCATED]")[0]


class TestSummarizeResultForLog:
    def test_scalars_kept_with_repr_truncation(self):
        summary = ce._summarize_result_for_log({"status": "success", "count": 5})
        assert "'success'" in summary and "5" in summary
        long_value = "v" * 5000
        summary = ce._summarize_result_for_log({"detail": long_value})
        assert len(summary) < 300
        assert "截断" in summary

    def test_list_records_length_and_head_only(self):
        big_list = list(range(100000))
        summary = ce._summarize_result_for_log({"items": big_list})
        assert "len=100000" in summary
        assert "head=" in summary
        assert len(summary) < 300

    def test_dict_records_length_and_head_only(self):
        big_dict = {f"k{i}": i for i in range(50000)}
        summary = ce._summarize_result_for_log({"map": big_dict})
        assert "len=50000" in summary
        assert len(summary) < 300

    def test_nested_containers_bounded(self):
        huge_nested = {"rows": [{"path": f"/data/f-{i}", "size": i} for i in range(100000)]}
        summary = ce._summarize_result_for_log(huge_nested)
        assert len(summary) < 500

    def test_set_container_supported(self):
        summary = ce._summarize_result_for_log({"tags": {"a", "b", "c", "d"}})
        assert "len=4" in summary

    def test_non_dict_input_bounded(self):
        assert len(ce._summarize_result_for_log("x" * 10000)) < 300
        assert "len=" in ce._summarize_result_for_log([1, 2, 3])

    def test_allocations_bounded_for_million_element_list(self):
        """分配上限回归（2026-09-06）：旧实现 list(value) 完整复制容器——百万元素
        列表输出仅数十字符却额外分配 ~8MB；且顶层 dict 无项数上限。新实现全程
        islice + 边渲染边 break，峰值分配 < 256KiB。"""
        import tracemalloc

        big = list(range(1000000))
        wide = {f"k{i}": i for i in range(100000)}
        tracemalloc.start()
        try:
            list_summary = ce._summarize_result_for_log({"items": big})
            wide_summary = ce._summarize_result_for_log(wide)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert "len=1000000" in list_summary
        assert "截断" in wide_summary and len(wide_summary) < 1200
        assert peak < 256 * 1024, f"摘要期间峰值分配 {peak / 1024:.1f} KiB，超出 256KiB 预算"

    def test_unknown_object_renders_type_name_known_types_keep_repr(self):
        """未知自定义对象不调用 __repr__（可能无界，降级 <类型名>）；
        datetime 等已知有界类型保留 repr 可读性。"""

        class _HugeRepr:
            def __repr__(self) -> str:
                raise AssertionError("未知对象的 __repr__ 不应被调用（可能无界）")

        summary = ce._summarize_result_for_log({"obj": _HugeRepr(), "ts": datetime(2026, 9, 6, 12, 0, 0)})
        assert "<_HugeRepr>" in summary
        assert "2026" in summary, "datetime 属已知有界类型，应保留 repr"

    def test_deep_nesting_and_self_reference_depth_capped(self):
        deep: dict = {}
        node = deep
        for _ in range(50):
            node["child"] = {}
            node = node["child"]
        node["leaf"] = 1
        self_ref: list = [1]
        self_ref.append(self_ref)
        summary = ce._summarize_result_for_log({"tree": deep, "loop": self_ref})
        assert len(summary) < 400, f"深嵌套/自引用应被深度上限截断: {len(summary)}"

    def test_bytes_sliced_before_repr(self):
        summary = ce._summarize_result_for_log({"blob": b"B" * 100000})
        assert len(summary) < 300 and "截断" in summary


def _inject_fake_task_class(monkeypatch, module_name, class_name, execute_result):
    """把返回固定结果的假任务类注入 app.tasks.* 命名空间（复用 admission 测试模式）。"""

    class _FakeTask:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, **kwargs):
            return execute_result

    fake_module = types.ModuleType(module_name)
    setattr(fake_module, class_name, _FakeTask)
    monkeypatch.setitem(sys.modules, module_name, fake_module)


class TestNormalizeResultRenderIntegration:
    async def test_huge_result_dict_does_not_blow_log_detail(self, monkeypatch):
        """10 万元素结果 dict：log_detail 保持 ≤2000 且含摘要标记。"""
        huge = {
            "status": "success",
            "items": [{"id": i} for i in range(100000)],
            "execution_log": ["阶段1: 提交", "阶段2: 完成"],
        }
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_render_huge", "Task", huge)
        executor = ce.CronTaskExecutor()
        task = {
            "task_id": 1,
            "task_name": "大结果任务",
            "task_code": None,
            "task_type": 4,
            "executor": "app.tasks.fake_module_render_huge.Task",
        }
        result = await executor._run_python_internal_class(task)

        assert result["success"] is True
        assert len(result["log_detail"]) <= 2000
        assert "len=100000" in result["log_detail"]
        # phase 行保留（execution_log 渲染契约，test_cron_executor_admission 锚点）
        assert "阶段1: 提交" in result["log_detail"]
        # 消费契约键不受摘要化影响
        assert result["outcome"] == "success"


class TestNormalizeResultBounding:
    """normalize_internal_result 的非 dict 结果与 phase 行有界（2026-09-06）：
    旧实现非 dict 走 str(result) 且不经过任何截断；phase 行 join 无行数上限，
    10 万行会先 join 出巨型字符串才被 [:2000] 截断。"""

    @staticmethod
    def _task(executor_path: str) -> dict:
        return {
            "task_id": 1,
            "task_name": "有界渲染任务",
            "task_code": None,
            "task_type": 4,
            "executor": executor_path,
        }

    async def test_non_dict_huge_list_result_bounded(self, monkeypatch):
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_nd_list", "Task", list(range(100000)))
        executor = ce.CronTaskExecutor()
        result = await executor._run_python_internal_class(self._task("app.tasks.fake_module_nd_list.Task"))
        assert result["success"] is True
        assert len(result["log_detail"]) <= 2000
        assert "len=100000" in result["log_detail"]

    async def test_non_dict_str_result_keeps_plain_text(self, monkeypatch):
        """str 结果直接切片保留原文风格，不被 repr 化（"done" 不变 "'done'"）。"""
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_nd_str", "Task", "done")
        executor = ce.CronTaskExecutor()
        result = await executor._run_python_internal_class(self._task("app.tasks.fake_module_nd_str.Task"))
        assert "结果: done" in result["log_detail"]

    async def test_phase_lines_capped_to_100_with_marker(self, monkeypatch):
        payload = {"status": "success", "execution_log": [f"line-{i}" for i in range(5000)]}
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_nd_phases", "Task", payload)
        executor = ce.CronTaskExecutor()
        result = await executor._run_python_internal_class(self._task("app.tasks.fake_module_nd_phases.Task"))
        assert len(result["log_detail"]) <= 2000
        assert "line-0" in result["log_detail"], "前 100 行应保留"
        assert "（共 5000 行，略）" in result["log_detail"], "超出 100 行应有省略标记"

    def test_huge_key_and_huge_numbers_bounded_allocation(self):
        """二轮分配上限回归（2026-09-06）：超长 str 键（800 万字符）与超大
        int/Decimal 不再先建完整字符串再截断——旧实现 8M 键额外分配 ~38MiB，
        百万位 Decimal 先做完整 repr。键与值统一按剩余预算预截断/降级。"""
        import tracemalloc

        payload = {
            "K" * 8_000_000: 1,
            "huge_int": 10**1_000_000,
            "huge_decimal": Decimal("9" * 1_000_000),
        }
        tracemalloc.start()
        try:
            summary = ce._summarize_result_for_log(payload)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert len(summary) < 1200, f"输出应受预算约束: {len(summary)}"
        assert "截断" in summary
        assert peak < 256 * 1024, f"摘要期间峰值分配 {peak / 1024:.1f} KiB，超出 256KiB 预算"

    def test_small_int_and_decimal_keep_repr(self):
        """正常量级的 int/Decimal 保留 repr 可读性（位数预检只在超预算时降级）。"""
        summary = ce._summarize_result_for_log({"count": 5, "ratio": Decimal("1.5")})
        assert "5" in summary
        assert "1.5" in summary


class TestKillProcessTree:
    """_kill_process_tree 平台分支与回退（2026-09-06 二轮：shell 包装的脚本
    进程是孙进程，只杀 shell 会留下持管道的孤儿）。"""

    def test_windows_uses_taskkill_tree(self, monkeypatch):
        calls = []

        def fake_run(args, **kwargs):
            calls.append(list(args))
            return types.SimpleNamespace(returncode=0)

        monkeypatch.setattr(ce.subprocess, "run", fake_run)
        monkeypatch.setattr(ce.sys, "platform", "win32")
        process = MagicMock()
        process.pid = 4321
        ce._kill_process_tree(process)
        assert calls, "应调用 taskkill"
        assert calls[0] == ["taskkill", "/F", "/T", "/PID", "4321"], "应整树终止"
        process.kill.assert_not_called()  # 树杀成功不回退单进程 kill

    def test_posix_uses_process_group_kill(self, monkeypatch):
        import signal

        killed = []
        monkeypatch.setattr(ce.sys, "platform", "linux")
        # Windows 的 signal 模块无 SIGKILL 常量（生产代码该分支只在真 POSIX 触达）
        monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
        monkeypatch.setattr(ce.os, "getpgid", lambda pid: pid, raising=False)
        monkeypatch.setattr(ce.os, "killpg", lambda pgid, sig: killed.append((pgid, sig)), raising=False)
        process = MagicMock()
        process.pid = 777
        ce._kill_process_tree(process)
        assert killed == [(777, 9)], "应按进程组整组 SIGKILL"

    def test_fallback_to_single_kill_on_failure(self, monkeypatch):
        monkeypatch.setattr(ce.sys, "platform", "linux")

        def _gone(pid):
            raise ProcessLookupError(pid)

        monkeypatch.setattr(ce.os, "getpgid", _gone, raising=False)
        process = MagicMock()
        process.pid = 1
        ce._kill_process_tree(process)
        process.kill.assert_called_once()  # 进程组杀失败回退单进程 kill


class TestPythonScriptSpawnPath:
    """Python 脚本 exec 直启与 frozen 回落（2026-09-06 二轮）。"""

    async def test_python_script_execs_interpreter_directly(self, monkeypatch):
        captured = {}

        async def fake_exec(*argv, **kwargs):
            captured["argv"] = argv
            return _make_fake_process([b"ok"], [b""])

        monkeypatch.setattr(ce.asyncio, "create_subprocess_exec", fake_exec)
        executor = ce.CronTaskExecutor()
        result = await executor._run_python_script("print(1)")
        assert result["success"] is True
        assert captured["argv"][0] == sys.executable, "应直启当前解释器"
        assert captured["argv"][1] == "-c"
        assert "Shell" not in result["log_detail"]

    async def test_frozen_env_falls_back_to_shell(self, monkeypatch):
        captured = {}

        async def fake_shell(command, **kwargs):
            captured["command"] = command
            return _make_fake_process([b"ok"], [b""])

        monkeypatch.setattr(ce, "is_frozen", lambda: True)
        monkeypatch.setattr(ce.asyncio, "create_subprocess_shell", fake_shell)
        executor = ce.CronTaskExecutor()
        result = await executor._run_python_script("print(1)")
        assert result["success"] is True
        assert "python -c" in captured["command"], "frozen 环境保持旧 shell 行为"


class TestCancelKillsProcessTreeReal:
    """真实 spawn 链回归（2026-09-06 二轮）：覆盖 create_subprocess_shell 启动
    链——假进程测试证明不了孙进程存活/管道持有问题（外部审查 Windows 实测：
    旧实现取消后 shell 已退、孙进程存活，中断等 3.95s 到脚本自行结束）。"""

    async def test_cancel_terminates_sleeping_grandchild_promptly(self):
        command = f'"{sys.executable}" -c "import time; time.sleep(120)"'
        executor = ce.CronTaskExecutor()
        start = time.monotonic()
        task = asyncio.create_task(executor._run_shell_script(command))
        await asyncio.sleep(1.5)  # 等 shell 与孙进程启动并占住管道
        task.cancel()
        outcome = await asyncio.gather(task, return_exceptions=True)
        elapsed = time.monotonic() - start
        assert isinstance(outcome[0], asyncio.CancelledError), "取消应传播（任务按中断收尾）"
        assert elapsed < 30, f"取消清理应树杀立即返回，实际耗时 {elapsed:.1f}s（疑似孙进程未被终止）"
