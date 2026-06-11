# BtDeck - BitTorrent Management Platform

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.11+-brightgreen)](https://python.org/)
[![Vue](https://img.shields.io/badge/vue-2.6.12-brightgreen)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-green)](https://fastapi.tiangolo.com/)

统一管理多种 BitTorrent 客户端（qBittorrent、Transmission）的全栈 Web 应用。

## 核心特性

- **多下载器统一管理** - 支持 qBittorrent 和 Transmission
- **实时状态监控** - WebSocket 实时推送下载速度和状态
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
│   └── btdeck.service       # systemd 服务
├── docker-compose.yml        # 全栈 Docker 部署
├── CLAUDE.md                 # 开发指导
└── ROADMAP.md                # 开发路线图
```

## 安装包构建

### Windows

```bash
cd deploy
build-windows.bat
```

生成 `dist/BtDeck-v1.0.9-windows-x64-setup.exe`

### Linux

```bash
cd deploy
chmod +x build-linux.sh
./build-linux.sh
```

生成 `dist/BtDeck-v1.0.9-linux-amd64.deb` 和 `.rpm`

### Docker 镜像

```bash
./build-and-push.sh
```

## 版本历史

| 版本 | 主题 | 状态 |
|------|------|------|
| v1.0.4 | 实时速度监控 + 通知中心 | 已完成 |
| v1.0.9 | 全栈仓库整合 + 一键部署 | 已完成 |
| v1.0.5 | 查询模板系统 | 计划中 |
| v1.0.6 | 孤儿文件管理 | 计划中 |
| v1.1.0 | 自动化运维 | 计划中 |

详见 [ROADMAP.md](./ROADMAP.md) 和 [PLANS/](./PLANS/)。

## 开发文档

- [CLAUDE.md](./CLAUDE.md) - 全栈开发指导
- [backend/CLAUDE.md](./backend/CLAUDE.md) - 后端开发规范
- [frontend/CLAUDE.md](./frontend/CLAUDE.md) - 前端开发规范

## 许可证

[GNU General Public License v3.0](./LICENSE)
