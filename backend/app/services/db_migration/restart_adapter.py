"""托管重启适配（database-migration-ui W3-8，PLANS §7.2.5；T16）。

评审修正选型：cgroup 探测仅证明"在容器"，INVOCATION_ID 仅证明"systemd 托管"，
都**不证明编排器会重启本进程**（--restart=no / Restart=no / on-failure+正常
退出均反例）。因此自动退出必须同时满足：

1. 已知托管适配器（systemd 服务 / Docker 容器）；
2. 部署**显式 opt-in**（``BTD_MIGRATION_MANAGED_RESTART=1``，由部署清单/
   compose 显式声明编排器重启策略已配置）；
3. 进程角色验证：systemd 形态下 PID1=自身意味误当 init 运行（无编排器
   保证），拒绝退出；**Docker 形态例外**——容器内应用即主进程（PID1）
   是常态，opt-in 已声明 restart 策略，退出即交由容器拉起（T16「已知
   Docker 托管真实重启」；W6-B 发现①修正：此前一刀切拒 PID1 导致
   compose 声明的自动拉起永不生效）。

不满足任一 → 返回 False，调用方仅置 RESTART_PENDING+手动重启提示。
持久提交并完成响应发送后才调度退出；客户端丢响应靠幂等 /status 恢复。
"""

from __future__ import annotations

import os
import signal
import threading
from typing import Any, Dict, Optional

__all__ = ["detect_hosting", "schedule_graceful_exit", "hosting_capability"]

_OPT_IN_ENV = "BTD_MIGRATION_MANAGED_RESTART"


def _in_container() -> bool:
    """cgroup/标记文件探测（仅证明容器环境，不证明重启策略）。"""
    if os.path.exists("/.dockerenv"):
        return True
    for cgroup in ("/proc/self/cgroup", "/proc/self/mountinfo"):
        try:
            with open(cgroup, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except OSError:
            continue
        for marker in ("docker", "kubepods", "containerd"):
            if marker in content:
                return True
    return False


def detect_hosting() -> str:
    """宿主形态：systemd（服务单元）/ docker（容器）/ unknown。"""
    if os.environ.get("INVOCATION_ID") and os.environ.get("SYSTEMD_EXEC_PID"):
        return "systemd"
    if _in_container():
        return "docker"
    return "unknown"


def hosting_capability(*, opt_in: Optional[bool] = None) -> Dict[str, Any]:
    """探测结果 + 自动重启能力判定（status 接口数据源）。"""
    hosting = detect_hosting()
    if opt_in is None:
        opt_in = (os.environ.get(_OPT_IN_ENV) or "").strip().lower() in {"1", "true", "yes"}
    pid1_self = os.getpid() == 1
    # W6-B 发现①：docker+opt-in 允许 PID1 退出（容器主进程即常态，重启交
    # 编排器是有意声明）；systemd/unknown 的 PID1 自检仍拒绝。
    capable = opt_in and (hosting == "docker" or (hosting == "systemd" and not pid1_self))
    return {
        "hosting": hosting,
        "optIn": opt_in,
        "pid1Self": pid1_self,
        "autoRestartCapable": capable,
        "hintCode": None if capable else "MANAGED_RESTART_MANUAL",
        "hint": None if capable else "未知托管或未显式 opt-in（BTD_MIGRATION_MANAGED_RESTART=1）：切换提交后需手动重启",
    }


def schedule_graceful_exit(*, delay_seconds: float = 1.5, reason: str = "") -> bool:
    """延迟 SIGTERM 自身（响应 flush 后退出；不 kill -9、不杀他人）。

    返回 True=已调度。若届时进程角色已变化（PID1）则放弃退出仅记日志。
    """
    capability = hosting_capability()
    if not capability["autoRestartCapable"]:
        return False

    def _exit_later() -> None:
        # 双检：调度窗口内重新评估能力（角色/环境变化则放弃）——与
        # hosting_capability 同一规则（docker+opt-in 允许 PID1，W6-B 发现①）。
        if not hosting_capability()["autoRestartCapable"]:
            print(f"[WARN] 托管退出放弃（能力复核不通过；reason={reason}）")
            return
        print(f"[OK] 托管优雅退出（reason={reason}；hosting={capability['hosting']}）")
        os.kill(os.getpid(), signal.SIGTERM)

    timer = threading.Timer(delay_seconds, _exit_later)
    timer.daemon = True
    timer.start()
    return True
