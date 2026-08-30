# -*- coding: utf-8 -*-
"""主机能力矩阵（dual-mode-client Phase 4：API/UI 一致降级的单一真相源）。

能力级别是 Phase 1.7 冻结的产品决策基线（docs/android/host-capability-matrix.md）；
本模块按注入的主机形态（BTDECK_PLATFORM）生成 capability 集合，经
GET /api/v1/platform/capabilities 下发，前端设置页/任务列表/创建表单三处
消费同一来源——不以 UA 猜测客户端形态（计划第 5 节红线）。

形态判定：
- ``desktop``        桌面 exe / NAS / 服务器（默认，fail-safe）
- ``android-server`` Android 本机服务端（壳工程 btdeck_server 注入）

约束：新增后台能力必须先在矩阵文档登记级别（本模块 CAPABILITY_DEFINITIONS
键集有单测锁定，未登记即红）。
"""

import os
from typing import Any, Dict

PLATFORM_DESKTOP = "desktop"
PLATFORM_ANDROID_SERVER = "android-server"
VALID_PLATFORMS = frozenset({PLATFORM_DESKTOP, PLATFORM_ANDROID_SERVER})

LEVEL_SUPPORTED = "supported"
LEVEL_DEGRADED = "degraded"
LEVEL_UNSUPPORTED = "unsupported"

_ENV_KEY = "BTDECK_PLATFORM"

# 矩阵冻结基线（docs/android/host-capability-matrix.md 第 2 节）。
# note 仅在非 supported 时下发展示文案；desktop 的 custom_scripts 默认关
# 由独立安全开关 BTDECK_ALLOW_CUSTOM_SCRIPTS 控制（级别仍为 supported）。
CAPABILITY_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "downloader_management": {
        "label": "下载器管理/增删改/连接测试",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_SUPPORTED,
    },
    "torrent_crud": {
        "label": "种子管理/同步/删除/回收站",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_SUPPORTED,
    },
    "tracker_management": {
        "label": "Tracker 管理/关键词/重宣告",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_SUPPORTED,
    },
    "advanced_search": {
        "label": "高级搜索/查询模板",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_SUPPORTED,
    },
    "audit_export": {
        "label": "审计日志 CSV/Excel 导出",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_SUPPORTED,
    },
    "custom_scripts": {
        "label": "自定义脚本任务（Shell/CMD/PowerShell/Python）",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_UNSUPPORTED,
        "note_android-server": "Android 服务端形态不提供脚本执行；内置任务类型不受影响",
    },
    "shell_capabilities": {
        "label": "宿主 shell 依赖能力（bash/PowerShell/cmd）",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_UNSUPPORTED,
        "note_android-server": "Android 无宿主 shell 契约；后端已无 shell 调用（ping 子进程已移除）",
    },
    "host_filesystem": {
        "label": "宿主文件系统任意路径（路径维护/孤儿清理根）",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_DEGRADED,
        "note_android-server": "仅应用私有目录与 SAF 授权目录；扫描根来自种子 save_path",
    },
    "saf_file_access": {
        "label": "文件选择（下载/上传 .torrent）",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_DEGRADED,
        "note_android-server": "仅 SAF 授权 URI 可访问（桌面为原生文件对话框）",
    },
    "torrent_file_transfer": {
        "label": "种子文件下载/上传",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_DEGRADED,
        "note_android-server": "仅授权目录内可用",
    },
    "system_notifications": {
        "label": "系统通知",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_DEGRADED,
        "note_android-server": "前台服务通知 + 站内通知；系统推送不在范围",
    },
    "scheduled_tasks": {
        "label": "定时任务调度",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_DEGRADED,
        "note_android-server": "系统省电（Doze）下不保证准点，任务列表展示“可能延迟”",
    },
    "local_server": {
        "label": "本地服务端（Web UI）",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_SUPPORTED,
    },
    "always_on_service": {
        "label": "常驻 7×24 服务端",
        PLATFORM_DESKTOP: LEVEL_SUPPORTED,
        PLATFORM_ANDROID_SERVER: LEVEL_UNSUPPORTED,
        "note_android-server": "Android 服务端定位为临时/轻量服务（产品边界）",
    },
}


def resolve_platform() -> str:
    """解析主机形态：BTDECK_PLATFORM ∈ {desktop, android-server}。

    未设置/非法值一律回落 desktop（fail-safe：能力只多不少的方向不存在——
    desktop 恰是能力全集，回落不会误伤降级展示，只会在漏注入时少降级）。
    """
    raw = (os.environ.get(_ENV_KEY) or "").strip().lower()
    return raw if raw in VALID_PLATFORMS else PLATFORM_DESKTOP


def get_capability_matrix(platform: str) -> Dict[str, Dict[str, str]]:
    """指定形态的完整能力矩阵：key → {label, level, note?}。"""
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"未知主机形态: {platform}")
    matrix: Dict[str, Dict[str, str]] = {}
    for key, definition in CAPABILITY_DEFINITIONS.items():
        level = definition[platform]
        entry: Dict[str, str] = {
            "label": definition["label"],
            "level": level,
        }
        note = definition.get(f"note_{platform}")
        if level != LEVEL_SUPPORTED and note:
            entry["note"] = note
        matrix[key] = entry
    return matrix


def capability_level(key: str, platform: str | None = None) -> str:
    """单项能力级别查询（cron 拦截等服务端内部判定用）。"""
    target = platform if platform is not None else resolve_platform()
    definition = CAPABILITY_DEFINITIONS.get(key)
    if definition is None:
        raise KeyError(f"未登记的能力: {key}（先更新 docs/android/host-capability-matrix.md）")
    return definition[target]


def capability_payload() -> Dict[str, Any]:
    """API 载荷：形态 + 矩阵 + 降级统计（CommonResponse.data 形状）。"""
    platform = resolve_platform()
    matrix = get_capability_matrix(platform)
    levels = [entry["level"] for entry in matrix.values()]
    return {
        "platform": platform,
        "capabilities": matrix,
        "degradedCount": levels.count(LEVEL_DEGRADED),
        "unsupportedCount": levels.count(LEVEL_UNSUPPORTED),
    }
