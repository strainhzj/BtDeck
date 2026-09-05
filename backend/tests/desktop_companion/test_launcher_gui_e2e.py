# -*- coding: utf-8 -*-
"""桌面伴侣 GUI E2E（opt-in：BTDECK_GUI_E2E=1 且 Windows 桌面会话可用时运行）。

task .8 桌面验收面的设备级实证：真实 pywebview/WebView2 窗口内完成
表单保存凭据、远程窗口自动登录、关闭回管理页、改密重登、失败登录静默、
切换 profile 凭据不越界。CI/无桌面环境自动 skip（不视为失败）。

运行：BTDECK_GUI_E2E=1 pytest backend/tests/desktop_companion/test_launcher_gui_e2e.py -v
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DRIVER = Path(__file__).resolve().parent / "gui_e2e_driver.py"

pytestmark = [
    pytest.mark.skipif(os.environ.get("BTDECK_GUI_E2E") != "1", reason="BTDECK_GUI_E2E 未开启（opt-in GUI 桌面验收）"),
    pytest.mark.skipif(sys.platform != "win32", reason="桌面 GUI 验收仅 Windows（WebView2）"),
]


def test_desktop_companion_gui_credentials_flow(tmp_path: Path) -> None:
    result_path = tmp_path / "gui-result.json"
    process = subprocess.run(
        [
            sys.executable,
            str(DRIVER),
            "--work-dir",
            str(tmp_path / "work"),
            "--result",
            str(result_path),
        ],
        cwd=str(DRIVER.parents[2]),
        timeout=420,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result_path.exists(), f"驱动未产出结果文件\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    steps = {step["name"]: step for step in payload["steps"]}
    assert steps, "驱动未记录任何步骤"
    failed = [name for name, step in steps.items() if not step["ok"]]
    assert not failed, f"GUI E2E 失败步骤: {failed}；明细: {json.dumps(payload['steps'], ensure_ascii=False)}"
    assert process.returncode == 0, f"驱动退出码 {process.returncode}\nstdout:\n{process.stdout}"


def test_driver_requires_real_desktop_session() -> None:
    """无桌面会话（SESSIONNAME 含 services/RDP 会话线程）时驱动会失败——登记为已知边界，不算通过。"""
    # 说明性用例：CI 上整个文件已被 opt-in 门控 skip；本用例仅锚定驱动文件存在，
    # 防止 gui_e2e_driver.py 被误删导致验收面静默消失。
    assert DRIVER.exists()
