# -*- coding: utf-8 -*-
"""
版本信息集中管理模块

产品版本的唯一输入是 release/release-config.json（candidate.product_version）；
本文件的 CURRENT_VERSION 必须与之一致，由 scripts/release/generate_build_info.py
--check-versions 与 backend/tests/release/test_version_consistency.py 强制校验。

使用方式：
    from app.version import CURRENT_VERSION, VERSION_HISTORY, get_version_info
"""

from typing import Any, Dict, Optional

# ============================================================
# 当前版本（发版时只需修改这里）
# ============================================================
CURRENT_VERSION = "1.0.6"


# ============================================================
# 版本历史记录（按版本号倒序排列）
# ============================================================
VERSION_HISTORY: Dict[str, Dict[str, Any]] = {
    "1.0.6": {
        "previous_version": "1.0.5",
        "release_date": "2026-09-21",
        "release_url": "https://github.com/strainhzj/BtDeck/releases/tag/v1.0.6",
        "summary": "安卓客户端、移动端全面移动化、桌面中英双语与发布工程加固",
        "content": """
## BtDeck v1.0.6 版本更新

### 核心新功能

**1. 安卓客户端（新增）**
- 全新 BtDeck 安卓 App（BtDeck Companion），提供两种使用模式：
  - 伴侣模式：连接远程 BtDeck 服务器进行管理，支持服务器连接向导、连接健康探测、凭据记忆与会话恢复
  - 本机服务端模式：在手机上直接运行完整的 BtDeck 后端与前端，无需电脑即可随时启动/停止
- 服务器地址证书指纹钉扎校验，防止中间人攻击；局域网明文测试构建单独提供
- 本机服务端启动预热优化，就绪等待从十几秒缩短到约 3~5 秒
- 全程移动端界面：应用内文件选择、返回导航（标题栏返回箭头 + 左上角名称点击）、品牌化 UI

**2. 移动端网页版**
- 手机浏览器访问自动进入全新移动版界面，全部功能页面完成移动化：仪表盘、种子列表与详情、下载器监控、Tracker 关键词、查询模板、回收站、审计日志、孤儿文件、系统设置
- 支持 PWA 安装到主屏、手势操作（标签页左右滑动切换、抽屉手势）、下拉刷新、无限滚动与空态引导
- 高级搜索重构为移动原生交互：摘要卡片 + 底部条件编辑弹层 + 吸底执行
- 移动端操作补强：通知一键已读、辅种数量展示、单种转移、修改保存路径、Tracker 批量操作按下载器触发、添加种子「跳过校验」选项

**3. 桌面 Web 中英双语**
- 桌面界面全面支持中文/英文切换：登录页与顶栏均可切换，自动识别浏览器语言并记住偏好
- 查询模板内置预设、通知事件、表单校验错误（含参数校验细分类型）等随语言本地化
- 后端接口错误改用稳定错误码（reasonCode）+ 固定文案，两种语言下提示一致可读，原始异常信息仅进入日志
- 日期、数字、文件大小等格式随语言本地化

### 性能与稳定性

**4. 大规模场景内存治理**
- 10 万种子同步内存峰值从约 270MB 降至约 36MB；Tracker 重宣告从全量加载约 1.3GB 降至约 5MB
- 安卓本机服务端内存稳态从约 2.2GB 降至 400~700MB；重启后不再强制整库快照
- 定时任务输出上限与结果摘要加固，防止任务输出占用内存

**5. 稳定性修复**
- 定时任务停止治理：超时强杀、中断真取消、下载器级硬熔断
- 修复断速种子状态振荡、批量添加种子偶发数据库锁死、种子列表终态整表刷新循环、移动端无限加载失控等多项缺陷
- 修复西文 Windows 控制台下服务启动崩溃（编码问题）
- 修复 Python 3.11 下异步任务取消竞态导致的挂死

### 安装与部署

**6. 交付制品质量加固**
- 四类制品（Windows 便携版/安装版、DEB、RPM、Docker 镜像）统一版本号与构建溯源，健康接口可查询产品版本与源码提交
- Linux 单一二进制同时兼容 Debian 12 与 Rocky Linux 9；DEB/RPM 升级过程不再中断服务
- 统一 Python 3.11 / Node 22 工具链，公共依赖带哈希锁定，消除不同安装方式间的依赖版本漂移
- 建立发布门禁体系：版本一致性、制品等价性、安装生命周期（首装/覆盖/升级/卸载）、SBOM 安全扫描
- 安装包与安卓应用接入 BtDeck 品牌图标

### 运维与排查

**7. 诊断能力**
- 新增故障诊断导出接口 /health/diagnosis，一键导出运行状态快照辅助排查
- Docker 镜像统一 UTC 时区与构建身份标签，镜像与源码可对应

### 界面与细节

**8. 其他改进**
- 种子详情新增文件/节点（Peers）页签，支持排序与模糊搜索
- Tracker 域名筛选高亮命中行
- 通知列表摘要剥离 Markdown 记号，显示更干净
- 下载器控制室、登录页等界面细节优化
- 移动下载器表单地址栏上移至端口上方，登录页语言切换统一为胶囊样式

### Bug 修复

**9. 问题修复**
- 修复下载器异步种子同步生命周期问题
- 修复仪表盘已暂停统计缺失与状态桶大小写错配
- 修复等级 3 删除时文件缺失导致流程卡住的问题（现跳过文件操作，种子直接入回收站）
- 修复两步验证（2FA）二维码依赖缺失时无法启用的问题（优雅降级为手动录入）
- 修复移动端回收站失败原因展示、通知详情渲染与桌面不一致等问题
- 其余修复详见版本提交记录

### 数据库变更

- 本次升级包含 3 项数据库结构变更（查询模板与设置模板预设键、孤儿扫描自愈迁移），首次启动时会自动完成迁移，请耐心等待

---
感谢您使用 BtDeck！如有问题或建议，请通过导航栏的反馈按钮提交。
""",
    },
    "1.0.5": {
        "previous_version": "1.0.4",
        "release_date": "2026-08-21",
        "release_url": "https://github.com/strainhzj/BtDeck/releases/tag/v1.0.5",
        "summary": "孤儿文件管理、查询模板、安全加固与大量问题修复",
        "content": """
## BtDeck v1.0.5 版本更新

### 核心新功能

**1. 孤儿文件管理**
- 新增孤儿文件管理功能，自动找出占用磁盘空间、但不属于任何下载器的文件
- 支持按名称、大小、状态等条件搜索
- 提供置信度标记和忽视名单，帮助判断文件是否可删，避免误删
- 相同文件的重复副本支持一键定位和删除，释放磁盘空间
- 删除操作多重防护：可疑文件自动延后处理、删除前进入隔离区可查看、误删可恢复

**2. 高级搜索查询模板**
- 常用搜索条件可保存为模板，下次一键套用，无需重复输入
- 简单搜索和高级搜索均支持保存为模板
- 系统内置常用模板；模板管理页支持筛选、编辑、删除

**3. 种子列表增强**
- 新增「Tracker异常」标签，一眼识别汇报出错的种子，并可查看具体错误原因
- 表格列宽可自由拖动调整，传统模式和分组模式均支持，设置自动记住
- 支持同时按多个下载器、多个状态组合筛选种子

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
        "release_url": "https://github.com/strainhzj/BtDeck/releases/tag/v1.0.4",
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
        "release_url": "https://github.com/strainhzj/BtDeck/releases/tag/v1.0.3",
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
