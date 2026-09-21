# BtDeck - BitTorrent Management Platform

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.11+-brightgreen)](https://python.org/)
[![Vue](https://img.shields.io/badge/vue-2.6.12-brightgreen)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-green)](https://fastapi.tiangolo.com/)

统一管理多种 BitTorrent 客户端（qBittorrent、Transmission）的全栈 Web 应用。

## 核心特性

- **多下载器统一管理** - 支持 qBittorrent 和 Transmission
- **实时状态监控** - WebSocket 实时推送下载速度和状态
- **高级搜索与查询模板** - 常用搜索条件保存为模板一键套用，系统内置常用模板
- **孤儿文件管理** - 自动识别不属于任何下载器的磁盘占用文件，置信度标记 + 忽视名单 + 隔离区，误删可恢复
- **Tracker 异常识别** - 种子列表「Tracker异常」标签，一眼识别汇报出错的种子并可查看错误原因
- **安全认证体系** - JWT + TOTP 二次验证
- **通知中心** - 版本更新通知、系统消息
- **数据加密** - SM4 国密算法敏感数据加密
- **一键部署** - Docker / Windows 安装包 / Linux 包

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ / FastAPI / SQLAlchemy / SQLite |
| 前端 | Vue 2.6.12 / TypeScript / Element UI / Vuex |
| 部署 | Docker Compose / PyInstaller / Inno Setup / fpm |

## 快速开始

### Docker 部署（推荐）

```bash
git clone https://github.com/strainhzj/BtDeck.git
cd BtDeck
docker compose up -d --build
```

访问 http://localhost:8080

> **首次登录**：默认账号 `admin` / `admin`，系统会强制要求修改密码。
> **安全加固**（公网/跨网络部署必做）：复制 `.env.example` 为 `.env`，按注释设置
> `DEV=false` + `SECRET_KEY` + `ALLOWED_HOSTS` 三件套（缺一容器拒绝启动），
> 并启用 TLS——参考 `deploy/nginx-tls.conf.example`（默认纯 HTTP 部署下
> 登录口令与 token 明文传输，可被网络嗅探）。

### 开发环境

```bash
# 后端
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001

# 前端
cd frontend
npm install
npm run serve
```

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:8080 |
| API | http://localhost:5001 |
| API 文档 | http://localhost:5001/docs |
| WebSocket | ws://localhost:5002 |

## 代码路线图

本项目在 `docs/roadmap/` 下维护一份**渐进式披露的多文件代码路线图**，用于快速定位模块职责、调用关系与架构约定（不修改源码，纯只读索引）。

- **入口**：[docs/roadmap/README.md](./docs/roadmap/README.md) ⇄ [CLAUDE.md](./CLAUDE.md) / [AGENTS.md](./AGENTS.md)
- **三层结构**：① 模块路由（根 README）→ ② 分支文件清单（各分支 README）→ ③ 源文件方法签名详情（单文件 .md）
- **跨切专题**（调用链 / 约定 / 风险 / 测试覆盖）：[docs/roadmap/perspectives/](./docs/roadmap/perspectives/)
- **覆盖范围**：backend（api/services/core/models/tasks 等 8 分支）+ frontend（entry/api/views/store 等 6 分支）+ deploy + tests
- **第三层样例**：[torrent_crud.py 路线图](./docs/roadmap/backend/api/endpoints/torrent_crud.md)（其余源文件待后续按"模式 B"增量补齐）

## 项目结构

```
BtDeck/
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── api/             # API 路由
│   │   ├── models/          # 数据库模型
│   │   ├── schemas/         # Pydantic 模型
│   │   ├── services/        # 业务逻辑
│   │   └── main.py          # 应用入口
│   ├── alembic/             # 数据库迁移
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # Vue.js 前端
│   ├── src/
│   │   ├── api/             # API 接口
│   │   ├── components/      # 组件
│   │   ├── router/          # 路由
│   │   ├── store/           # Vuex 状态管理
│   │   └── views/           # 页面
│   ├── Dockerfile.prod
│   └── package.json
├── deploy/                   # 部署与打包
│   ├── btdeck.spec          # PyInstaller 配置
│   ├── btdeck.iss           # Inno Setup (Windows)
│   ├── build-linux.sh       # Linux 构建脚本
│   ├── build-windows.bat    # Windows 构建脚本
│   ├── build-android.bat    # Android APK 构建脚本
│   └── btdeck.service       # systemd 服务
├── build-packages.bat        # Windows EXE + Android APK 统一入口
├── docker-compose.yml        # 全栈 Docker 部署
├── CLAUDE.md                 # 开发指导
├── AGENTS.md                 # 全栈工作流路由
└── docs/
    └── roadmap/              # 代码路线图（三层渐进式披露）
```

## 安装包构建

### Windows EXE / 安装包

```bat
deploy\build-windows.bat
```

始终生成 `dist\btdeck.exe` 便携版；安装 Inno Setup 且 `ISCC` 可用时，额外生成
`dist\BtDeck-v1.0.6-windows-x64-setup.exe`。

### Android APK

```bat
deploy\build-android.bat
```

默认运行 JVM 单测并生成两个 debug APK 到 `android\dist\`：严格版
`btdeck-companion-0.2.5-strict-debug.apk` 与局域网明文测试版
`btdeck-companion-0.2.5-lan-cleartext-debug.apk`。只构建单个变体可使用
`deploy\build-android.bat --strict-only` 或 `--lan-only`。

### EXE + APK 统一构建

```bat
build-packages.bat
```

也可使用 `build-packages.bat --windows`、`--android`、
`--android-strict-only` 或 `--android-lan-only` 选择目标。

### Linux

```bash
cd deploy
chmod +x build-linux.sh
./build-linux.sh
```

生成 `dist/BtDeck-v1.0.6-linux-amd64.deb` 和 `.rpm`

### Docker 镜像

```bash
./build-images.sh
```

仅构建本地镜像（`btdeck-backend:latest` / `btdeck-frontend:latest`，版本号从 `feature_list.json` 自动读取），不推送至镜像仓库。完成后执行 `docker compose up -d` 启动。

## 版本历史

| 版本 | 主题 | 发布日期 | 状态 |
|------|------|----------|------|
| v1.0.4 | 实时速度监控 + 通知中心 + 活动种子筛选 | 2026-06-05 | 已发布 |
| v1.0.5 | 孤儿文件管理 + 查询模板 + 安全加固 + 大量问题修复 | 2026-08-21 | 已发布 |
| v1.0.6 | 安卓客户端 + 移动端全面移动化 + 桌面中英双语 + 发布工程加固 | 2026-09-21 | 已发布 |
| v1.1.0 | 自动化运维 | - | 计划中 |

> 产品发布号以 [`release/release-config.json`](./release/release-config.json) 为唯一输入（`backend/app/version.py` 等六处由发布门禁强制一致）。`feature_list.json` 与 `PLANS/` 中的 v1.0.x 为内部里程碑编号，与发布号相互独立（v1.0.5 发布打包了里程碑 v1.0.5 查询模板、v1.0.6 孤儿文件管理、v1.0.9 一键部署及 2026-06~08 全部修复；v1.0.6 发布打包了里程碑 v1.0.6 双模式客户端、desktop-bilingual-20260918 桌面双语及 2026-08~09 全部修复）。

### v1.0.6 更新亮点（2026-09-21）

- **安卓客户端（新增）** - 全新 BtDeck 安卓 App：既可作为「伴侣模式」连接并管理远程 BtDeck 服务器（服务器连接向导、健康探测、凭据记忆与会话恢复、证书指纹钉扎校验防中间人），也可切换为「本机服务端模式」在手机上直接运行完整后端与前端，无需电脑即可随时启停（启动预热优化后约 3~5 秒可用）；全程移动端界面，支持应用内文件选择、返回导航与品牌化 UI
- **移动端网页版** - 手机浏览器访问自动进入全新移动版：仪表盘、种子列表与详情、下载器监控、Tracker 关键词、查询模板、回收站、审计日志、孤儿文件、系统设置等页面全部移动化；支持 PWA 安装、手势操作（标签页滑动切换、抽屉手势）、下拉刷新、无限滚动与空态引导；高级搜索重构为移动原生交互（摘要卡片 + 底部条件编辑弹层）
- **桌面中英双语** - 桌面 Web 全量支持中文/英文切换（登录页与顶栏入口，自动识别浏览器语言并记住偏好）；查询模板内置预设、通知事件、表单校验错误等随语言本地化；后端接口错误改用稳定错误码（reasonCode）+ 固定文案，两种语言下提示一致可读，原始异常只进日志
- **性能与稳定性** - 大规模种子场景内存治理：10 万种子同步内存峰值从约 270MB 降至 36MB，Tracker 重宣告从全量加载降至 5MB；安卓本机服务端内存稳态从 2.2GB 降至 400~700MB；定时任务超时强杀、真取消与下载器级熔断；修复断速种子状态振荡、批量添加偶发数据库锁死、种子列表终态刷新循环、移动端无限加载失控、西文 Windows 服务启动崩溃等多项缺陷
- **安装包与部署** - 四类制品（Windows EXE/安装版、DEB、RPM、Docker 镜像）统一版本号与构建溯源，健康接口可查产品版本与源码提交；Linux 单二进制同时兼容 Debian 12 与 Rocky Linux 9，DEB/RPM 升级不再中断服务；统一 Python 3.11 / Node 22 工具链与带哈希依赖锁定；建立发布门禁体系（版本一致性、制品等价性、安装生命周期、SBOM 安全扫描）
- **运维与排查** - 新增故障诊断导出（`/health/diagnosis`）一键导出状态快照；Docker 镜像统一 UTC 时区与构建身份标签；安装包接入 BtDeck 品牌图标
- **种子管理增强** - 种子详情新增文件/节点页签（排序与模糊搜索）；Tracker 域名筛选命中标记；移动端支持辅种数量展示、单种转移、修改保存路径、Tracker 批量操作按下载器触发、添加种子「跳过校验」选项与通知一键已读

> 完整更新日志以 [`backend/app/version.py`](./backend/app/version.py) 为准，另见 [GitHub Release v1.0.6](https://github.com/strainhzj/BtDeck/releases/tag/v1.0.6)。本次升级包含 3 项数据库结构变更（查询模板/设置模板预设键、孤儿扫描自愈迁移），首次启动时会自动完成迁移。

### v1.0.5 更新亮点（2026-08-21）

- **孤儿文件管理** - 自动找出占用磁盘空间但不属于任何下载器的文件；支持按名称、大小、状态搜索；置信度标记与忽视名单辅助判断是否可删；重复副本一键定位删除；可疑文件自动延后处理，删除前进入隔离区可查看，误删可恢复
- **查询模板** - 简单搜索和高级搜索的常用条件均可保存为模板一键套用；系统内置常用模板，模板管理页支持筛选、编辑、删除
- **种子列表增强** - 新增「Tracker异常」标签并可查看具体错误原因；表格列宽自由拖动（传统/分组模式均支持）且自动记住；支持同时按多个下载器、多个状态组合筛选
- **安全加固** - 修复多项账号与登录安全漏洞；多标签页同时使用时登录状态保持一致；修改密码后其他设备自动退出
- **性能与稳定性** - 优化多下载器同时同步时的数据写入；下载器长时间离线后自动清理缓存；大量种子场景下列表加载更流畅；建立完善的自动化测试体系
- **安装与部署** - 新增 Windows / Linux 桌面安装包，支持独立窗口运行；修复部分环境安装后无法启动的问题；Docker 部署支持自定义镜像源
- **Bug 修复** - qBittorrent 下载/做种状态显示颠倒、做种数据统计错误、Transmission Tracker 信息同步丢失、回收站网络路径文件清理失败、新种子状态显示 unknown 等

> 完整更新日志以 [`backend/app/version.py`](./backend/app/version.py) 为准，另见 [GitHub Release v1.0.5](https://github.com/strainhzj/BtDeck/releases/tag/v1.0.5)。本次升级涉及数据库结构变更，首次启动时会自动完成迁移。

详见 [PLANS/](./PLANS/)。

## 开发文档

- [CLAUDE.md](./CLAUDE.md) - 全栈开发指导
- [backend/CLAUDE.md](./backend/CLAUDE.md) - 后端开发规范
- [frontend/CLAUDE.md](./frontend/CLAUDE.md) - 前端开发规范

## 许可证

[GNU General Public License v3.0](./LICENSE)
