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
CURRENT_VERSION = "1.0.5"


# ============================================================
# 版本历史记录（按版本号倒序排列）
# ============================================================
VERSION_HISTORY: Dict[str, Dict[str, Any]] = {
    "1.0.5": {
        "previous_version": "1.0.4",
        "release_date": "2026-08-21",
        "release_url": "https://github.com/StrainThomas/BtDeck/releases/tag/v1.0.5",
        "summary": "孤儿文件管理、查询模板、安全加固与大量问题修复",
        "content": """
## BtDeck v1.0.5 版本更新

### 核心新功能

**1. 孤儿文件管理**
- 新增孤儿文件管理功能，自动找出占用磁盘空间、但不属于任何下载器的文件
- 支持按名称、大小、状态等条件搜索，可为文件添加备注
- 提供置信度标记和忽视名单，帮助判断文件是否可删，避免误删
- 相同文件的重复副本支持一键定位和删除，释放磁盘空间
- 删除操作多重防护：可疑文件自动延后处理、删除前进入隔离区可查看、误删可恢复

**2. 查询模板**
- 常用搜索条件可保存为模板，下次一键套用，无需重复输入
- 简单搜索和高级搜索均支持保存为模板
- 系统内置常用模板；模板管理页支持筛选、编辑、删除

**3. 种子列表增强**
- 新增「Tracker异常」标签，一眼识别汇报出错的种子，并可查看具体错误原因
- 表格列宽可自由拖动调整，传统模式和分组模式均支持，设置自动记住
- 支持同时按多个下载器、多个状态组合筛选种子
- 重复内容分组支持组内按状态筛选，不再整组消失

**4. 高级搜索优化**
- 标签选择器全新设计，选择更直观
- 界面图标全面更新，风格统一

### 安全加固

**5. 账号与登录安全**
- 修复多项安全漏洞，提升系统整体防护能力
- 多个浏览器标签页同时使用时登录状态保持一致，修复偶尔被意外登出的问题
- 修改密码后其他设备自动退出，需重新登录
- 优化首次使用强制修改初始密码的流程，不再出现页面卡住

### 界面优化

**6. 体验细节**
- 下载器管理页面全新设计，操作更清晰
- 种子进度和速度显示更准确
- 通知中心的文件大小等数字显示更易读

### 技术改进

**7. 性能与稳定性**
- 大幅优化多下载器同时同步时的数据写入，界面响应更快
- 下载器长时间离线后自动清理缓存，恢复连接更顺畅
- 大量种子场景下列表加载更流畅
- 建立完善的自动化测试体系，提升版本质量

**8. 安装与部署**
- 新增 Windows / Linux 桌面安装包，支持独立窗口运行
- 修复部分环境下安装后无法启动的问题
- Docker 部署支持自定义镜像源，国内环境拉取更顺畅

### Bug 修复

**9. 问题修复**
- 修复 qBittorrent 下载中/做种中状态显示颠倒的问题
- 修复 qBittorrent 做种数据统计错误
- 修复 Transmission Tracker 信息同步失败导致记录丢失的问题
- 修复回收站清理网络路径文件失败的问题
- 修复新添加的种子状态显示 unknown 的问题
- 修复 Transmission 执行等级删除时超时的问题
- 其余修复详见版本提交记录

### 数据库变更

- 本次升级涉及数据库结构变更，首次启动时会自动完成升级，请耐心等待

---
感谢您使用 BtDeck！如有问题或建议，请通过导航栏的反馈按钮提交。
""",
    },
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
""",
    },
    "1.0.3": {
        "previous_version": "1.0.2",
        "release_date": "2026-04-21",
        "release_url": "https://github.com/StrainThomas/BtDeck/releases/tag/v1.0.3",
        "summary": "基础功能稳定版",
        "content": "基础功能稳定版本发布。",
    },
    # 后续版本在此处添加...
}


assert CURRENT_VERSION in VERSION_HISTORY, (
    f"CURRENT_VERSION '{CURRENT_VERSION}' not found in VERSION_HISTORY. "
    f"Available versions: {sorted(VERSION_HISTORY.keys())}"
)


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
