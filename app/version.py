# -*- coding: utf-8 -*-
"""
版本信息集中管理模块

所有版本相关信息在此处维护，发新版本时只需修改此文件。

使用方式：
    from app.version import CURRENT_VERSION, VERSION_HISTORY, get_version_info
"""

from typing import Any, Dict, Optional


# ============================================================
# 当前版本（发版时只需修改这里）
# ============================================================
CURRENT_VERSION = "1.0.4"


# ============================================================
# 版本历史记录（按版本号倒序排列）
# ============================================================
VERSION_HISTORY: Dict[str, Dict[str, Any]] = {
    "1.0.4": {
        "previous_version": "1.0.3",
        "release_date": "2026-06-05",
        "release_url": "https://github.com/StrainThomas/BtDeck/releases/tag/v1.0.4",
        "summary": "通知中心、实时速度监控、活动种子筛选",
        "content": """
## BtDeck v1.0.4 版本更新

### 核心新功能

**1. 通知中心**
- 新增完整的通知管理系统，支持版本更新和系统消息
- 通知列表支持分页查询、按类型筛选（全部/未读/更新/系统）
- 支持标记已读/未读、全部已读、删除通知等操作
- 点击通知条目弹出详情弹窗，支持 Markdown 内容渲染
- 自动检查 GitHub Release 版本更新并推送通知
- 60秒轮询未读通知数量，实时更新角标

**2. 实时速度监控**
- 种子列表新增独立的下载速度和上传速度列
- 下载速度显示 ▼ 图标，上传速度显示 ▲ 图标
- 活跃种子（有速度的种子）自动排序到列表顶部
- 新增专用 API 接口获取活跃种子状态

**3. 活动种子筛选**
- 新增"仅显示活动种子"复选框筛选功能
- 快速筛选出正在下载/上传的种子
- 与现有搜索条件组合使用

**4. 手动刷新功能**
- 种子列表新增手动刷新按钮
- 支持加载状态显示，避免重复点击

### 界面优化

**5. 导航栏优化**
- 导航栏顶部 UI 布局优化
- 新增用户反馈按钮，方便用户提交问题

**6. 种子列表改进**
- 修复种子列表页面样式失效问题
- 优化进度条实时更新逻辑
- 改进种子状态图标显示

### 技术改进

**7. 性能优化**
- qBittorrent 速度接口使用 status_filter 参数减少数据传输
- 修复种子速度监控的线程池泄漏问题
- 优化定时器清理机制，避免内存泄漏

**8. 开发基础设施**
- 新增 Harness 开发基础设施，规范开发流程
- 添加开发约束文档，确保代码质量
- 完善 TypeScript 类型定义

**9. Bug 修复**
- 修复下载队列状态图标显示为问号的问题
- 修复生产环境 API 路径配置问题
- 修复类型安全和定时器清理问题
- 修正活跃种子速度接口单位注释

### API 变更

**新增接口：**
- `GET /api/v1/torrents/active-torrents` - 获取活跃种子列表
- `GET /api/v1/notifications` - 获取通知列表
- `GET /api/v1/notifications/unread-count` - 获取未读通知数量
- `PUT /api/v1/notifications/mark-read` - 标记通知已读
- `PUT /api/v1/notifications/mark-unread` - 标记通知未读
- `PUT /api/v1/notifications/read-all` - 全部标记已读
- `DELETE /api/v1/notifications/{id}` - 删除通知

**数据库变更：**
- 新增 `notification` 表，用于存储系统通知

---
感谢您使用 BtDeck！如有问题或建议，请通过导航栏的反馈按钮提交。
"""
    },
    "1.0.3": {
        "previous_version": "1.0.2",
        "release_date": "2026-04-21",
        "release_url": "https://github.com/StrainThomas/BtDeck/releases/tag/v1.0.3",
        "summary": "基础功能稳定版",
        "content": "基础功能稳定版本发布。"
    },
    # 后续版本在此处添加...
}


def get_version_info(version: Optional[str] = None) -> Dict[str, Any]:
    """
    获取指定版本的信息

    Args:
        version: 版本号，默认为当前版本

    Returns:
        版本信息字典，包含 previous_version, release_date, content 等
    """
    target_version = version or CURRENT_VERSION
    return VERSION_HISTORY.get(target_version, {})


def get_current_version() -> str:
    """获取当前版本号"""
    return CURRENT_VERSION


def get_previous_version() -> str:
    """获取上一个版本号"""
    current_info = VERSION_HISTORY.get(CURRENT_VERSION, {})
    return current_info.get("previous_version", "0.0.0")


def get_version_content(version: Optional[str] = None) -> str:
    """
    获取版本更新内容（Markdown 格式）

    Args:
        version: 版本号，默认为当前版本

    Returns:
        Markdown 格式的更新内容
    """
    version_info = get_version_info(version)
    return version_info.get("content", "")


def get_all_versions() -> list:
    """获取所有版本号列表（倒序）"""
    return sorted(VERSION_HISTORY.keys(), reverse=True)
