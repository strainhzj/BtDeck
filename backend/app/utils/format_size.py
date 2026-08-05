# -*- coding: utf-8 -*-
"""字节大小格式化工具：自动选择最接近的单位（1024 进制），保留 2 位小数。

供通知文案等需要人类可读大小展示的场景共用，避免在多个 service 内
重复实现格式化逻辑（参考 frontend utils/formatters.ts 的 formatFileSize）。
"""

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_size(size_bytes: int) -> str:
    """将字节数格式化为人类可读大小。

    自动选择使数值落在 [1, 1024) 的单位（如 57286409241 → "53.35 GB"），
    支持 B/KB/MB/GB/TB/PB；0 或负数原样按字节展示。
    """
    if not size_bytes or size_bytes < 0:
        return "0 B"

    size = float(size_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(_UNITS) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {_UNITS[unit_index]}"
