# -*- coding: utf-8 -*-
"""统一下载器连通性探测（dual-mode-client Phase 1.1）。

历史问题：downloader.py 与 initialization.py 各自直接调用 ping3（ICMP raw
socket）。ICMP 在安卓上无 raw socket 权限、ping3 在无权限桌面/容器里会静默
失败或抛 PermissionError，且 ICMP 可达不等于下载器端口可达。

统一策略（与 PLANS/dual-mode-client.md 第 2/4 节一致）：
1. loopback 主机短路返回固定延迟（保持历史语义，避免本地无谓网络 IO）；
2. 桌面在权限允许时可先 ICMP（可选优化，失败回退 TCP）；
3. 兜底与准绳：按下载器端口的 TCP connect 计时——安卓/无 ICMP 权限环境
   唯一路径，禁止调用系统 ping 子进程。

所有函数不抛出探测异常：成功返回毫秒延迟，失败返回 None。
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import time
from typing import Optional

# loopback 固定延迟（毫秒）：与历史 get_delay/get_delay_async 的
# "127.0.0.1 → delay = 1" 语义保持一致，测试也依赖此短路避免真实网络 IO。
LOOPBACK_DELAY_MS = 1.0

# ping3 超时单位为秒（整数）；TCP connect 计时用 float 秒。
DEFAULT_PROBE_TIMEOUT_SECONDS = 3.0

# 延迟合理范围（毫秒）：超出视为异常值（与 initialization 历史校验一致）。
MAX_REASONABLE_DELAY_MS = 30000.0


def clean_host(host: object) -> str:
    """清理主机地址：去掉协议前缀、路径与空白，仅保留主机名。

    与 initialization._clean_host_url 语义一致，但独立实现以免
    downloader 链路反向依赖 initialization（避免循环导入）。
    """
    if not host or not isinstance(host, str):
        return ""
    value = host.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    if "/" in value:
        value = value.split("/", 1)[0]
    return value.strip()


def is_loopback(host: object) -> bool:
    """判断是否 loopback 主机（精确匹配，替代历史子串包含判断）。

    历史代码用 `"127.0.0.1" in host` 子串匹配，会把
    "127.0.0.1.example.com" 这类主机误判为本地；此处先清洗再精确比较。
    """
    cleaned = clean_host(host).lower()
    # "127.0.0.1:8080" 形式剥掉端口再比较（仅单个冒号的 IPv4:port；
    # "::1" 等 IPv6 字面量冒号数 >=2，走下方精确匹配）
    if cleaned.count(":") == 1:
        head, _, tail = cleaned.rpartition(":")
        if tail.isdigit() and head:
            cleaned = head
    if cleaned in ("localhost", "::1", "[::1]", "0:0:0:0:0:0:0:1"):
        return True
    # 127.0.0.0/8 整段均为 loopback
    return cleaned.startswith("127.") and cleaned[4:].replace(".", "").isdigit()


def is_android_environment() -> bool:
    """检测安卓运行环境（Chaquopy 提供 sys.getandroidapilevel，Termux 有专用环境变量）。

    安卓禁止 ICMP 探测：无 raw socket 权限，也不允许依赖系统 ping 命令。
    """
    if os.getenv("BTDECK_PLATFORM", "").strip().lower() == "android":
        return True
    if hasattr(sys, "getandroidapilevel"):  # Chaquopy / python-for-android
        return True
    return bool(os.getenv("TERMUX_VERSION"))


def icmp_allowed() -> bool:
    """是否允许 ICMP 探测：显式禁用环境变量或安卓环境一律 False。"""
    flag = os.getenv("BTDECK_DISABLE_ICMP", "").strip().lower()
    if flag not in ("", "0", "false", "no"):
        return False
    return not is_android_environment()


def _coerce_port(port: object) -> Optional[int]:
    """端口安全转换：非法/超范围返回 None。"""
    if isinstance(port, bool):  # bool 是 int 子类，先行排除
        return None
    if isinstance(port, int):
        port_int = port
    elif isinstance(port, float) and port.is_integer():
        port_int = int(port)
    elif isinstance(port, str) and port.strip().isdigit():
        port_int = int(port.strip())
    else:
        return None
    if 1 <= port_int <= 65535:
        return port_int
    return None


def icmp_ping_delay(host: object, timeout_s: float = DEFAULT_PROBE_TIMEOUT_SECONDS) -> Optional[float]:
    """可选 ICMP 探测（桌面优化路径）。ping3 缺失、无权限（PermissionError）、
    超时等一切失败均返回 None，由调用方回退 TCP，绝不抛出。
    """
    cleaned = clean_host(host)
    if not cleaned:
        return None
    try:
        import ping3
    except Exception:  # noqa: BLE001 - 缺依赖即视为不可用
        return None
    try:
        result = ping3.ping(cleaned, max(1, int(timeout_s)), "ms", "0.0.0.0", seq=2)
    except Exception:  # noqa: BLE001 - PermissionError / raw socket 不可用等
        return None
    if result is None or result is False:  # noqa: E712 - ping3 以 False 表示失败
        return None
    try:
        return float(result)
    except (TypeError, ValueError):
        return None


def tcp_connect_delay(host: object, port: object, timeout_s: float = DEFAULT_PROBE_TIMEOUT_SECONDS) -> Optional[float]:
    """按下载器端口的 TCP connect 计时（毫秒）。

    成功返回连接耗时；拒绝、超时、DNS 失败、非法端口均返回 None。
    仅支持 IPv4（与既有 check_port_connectivity 的 AF_INET 一致）。
    """
    cleaned = clean_host(host)
    port_int = _coerce_port(port)
    if not cleaned or port_int is None:
        return None

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout_s)
        start = time.perf_counter()
        sock.connect((cleaned, port_int))
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        # 保底正值：perf_counter 精度内可能得到 0.0，下游把 0 视为未连接
        return max(elapsed_ms, 0.01)
    except Exception:  # noqa: BLE001 - refused/timeout/DNS 等失败统一为 None
        return None
    finally:
        try:
            sock.close()
        except Exception:  # noqa: BLE001 - 关闭失败无需处理
            pass


def probe_delay_sync(
    host: object,
    port: object,
    timeout_s: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    allow_icmp: Optional[bool] = None,
) -> Optional[float]:
    """同步统一探测入口：loopback 短路 → ICMP（可选）→ TCP connect 计时。

    Args:
        host: 下载器主机（可含协议前缀，会被清洗）
        port: 下载器端口（字符串/整数均可）
        timeout_s: 单次探测超时（秒）
        allow_icmp: 显式控制是否先试 ICMP；None 时按环境自动判定

    Returns:
        毫秒延迟；不可达/失败返回 None。loopback 返回 LOOPBACK_DELAY_MS。
    """
    if is_loopback(host):
        return LOOPBACK_DELAY_MS

    if allow_icmp is None:
        allow_icmp = icmp_allowed()
    if allow_icmp:
        icmp = icmp_ping_delay(host, timeout_s)
        if icmp is not None:
            return icmp
    return tcp_connect_delay(host, port, timeout_s)


async def probe_delay(
    host: object,
    port: object,
    timeout_s: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    allow_icmp: Optional[bool] = None,
) -> Optional[float]:
    """异步统一探测入口（线程池包装，避免阻塞事件循环）。"""
    return await asyncio.to_thread(probe_delay_sync, host, port, timeout_s, allow_icmp)
