# BTDeck 后端项目

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python Version](https://img.shields.io/badge/python-3.11+-brightgreen)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-green)](https://fastapi.tiangolo.com/)

基于 FastAPI + Python 的 BitTorrent 管理器后端服务。

## 📋 项目简介

BTDeck 后端是基于 FastAPI 框架的 BitTorrent 下载管理平台，支持多种下载器（qBittorrent、Transmission）的集中管理和实时监控。

### 核心特性

- 🎯 **多下载器统一管理** - 支持 qBittorrent 和 Transmission
- 📊 **实时状态监控** - WebSocket 实时推送下载器状态
- 🔄 **后台任务调度** - APScheduler 自动化下载管理
- 🔐 **安全认证体系** - JWT + TOTP 二次验证
- 💾 **数据加密** - SM4 国密算法敏感数据加密
- 📡 **REST API** - 完整的 RESTful API 接口
- 📖 **自动文档** - Swagger/OpenAPI 自动生成

### 技术栈

- **框架**: FastAPI 0.115.0
- **Python**: 3.11+
- **ORM**: SQLAlchemy 2.0.15（异步）
- **数据验证**: Pydantic 2.12.4
- **数据库**: SQLite
- **认证**: JWT + OAuth2 + TOTP
- **任务调度**: APScheduler 3.10.0
- **WebSocket**: FastAPI WebSocket
- **加密**: SM4 国密算法
- **数据库迁移**: Alembic 1.13.3

## 🚀 快速开始

### 环境要求

- Python 3.11+
- conda（推荐）或 venv

### 安装依赖

```bash
# 创建 conda 环境
conda create -n btpManager python=3.11
conda activate btpManager

# 安装依赖
pip install -r requirements.txt
```

### 数据库迁移

```bash
# 自动执行迁移（应用启动时自动执行）
alembic upgrade head

# 手动生成迁移脚本
alembic revision --autogenerate -m "描述"

# 查看当前版本
alembic current

# 查看迁移历史
alembic history
```

### 开发环境运行

```bash
# 启动后端服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001
```

访问 http://localhost:5001

### 服务端口

- **API服务**: http://localhost:5001
- **WebSocket**: ws://localhost:5002
- **API文档**: http://localhost:5001/docs

## 📁 项目结构

```
btpManager/
├── app/
│   ├── api/              # API 路由
│   │   └── routers/      # 路由模块
│   ├── common/           # 公共模块
│   │   ├── response.py   # 统一响应格式
│   │   └── exceptions.py # 自定义异常
│   ├── core/             # 核心配置
│   │   ├── config.py     # 配置管理
│   │   └── security.py   # 安全相关
│   ├── models/           # 数据库模型
│   ├── schemas/          # Pydantic 模型
│   ├── services/         # 业务逻辑层
│   ├── utils/            # 工具函数
│   ├── main.py           # 应用入口
│   └── dependencies.py   # 依赖注入
├── alembic/              # 数据库迁移
│   └── versions/         # 迁移脚本
├── tests/                # 测试文件
├── config/               # 配置文件
│   └── app.db           # SQLite 数据库
├── alembic.ini           # Alembic 配置
├── requirements.txt      # 依赖列表
├── pyproject.toml       # 项目配置
└── CLAUDE.md            # 开发指导文档
```

## 🔧 开发配置

### 环境变量

创建 `.env` 文件：

```bash
# 应用配置
APP_NAME=BTDeck
APP_VERSION=1.0.0
DEBUG=True

# 数据库配置
DATABASE_URL=sqlite+aiosqlite:///config/app.db

# JWT 配置
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# WebSocket 配置
WS_PORT=5002
```

### 开发工具

```bash
# 类型检查
mypy app/

# 代码格式化
black app/

# 导入排序
isort app/

# Lint 检查
flake8 app/
```

### 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_api.py

# 生成覆盖率报告
pytest --cov=app tests/

# 查看覆盖率报告
pytest --cov=app --cov-report=html tests/
```

## 📖 开发文档

详细的开发指南请参考 [CLAUDE.md](./CLAUDE.md)

### 核心文档

- **项目认知框架** - 了解项目定位和核心价值
- **开发工作约束** - 代码简洁性原则、交互模式、代码复用
- **后端特定约束** - 数据库迁移管理、下载器连接管理
- **后端架构** - 技术栈、项目结构、API 设计
- **开发工作流** - 启动、迁移、测试流程

### 详细技能文档

完整的后端开发技能文档位于 `.claude/skills/backend-dev-guidelines-python3/` 目录：

- **[项目文档索引](.claude/skills/backend-dev-guidelines-python3/项目文档索引.md)** - 完整的开发指南导航
- **[后端开发技能指南](.claude/skills/backend-dev-guidelines-python3/开发指南/SKILL.md)** - Python3 后端开发完整技能指南
- **[btpManager 项目示例](.claude/skills/backend-dev-guidelines-python3/项目示例/CUSTOM_EXAMPLES.md)** - 项目特定示例和模板

### API 响应格式规范

所有 API 接口必须遵循统一响应格式：

```python
from app.common.response import CommonResponse

return CommonResponse(
    status="success",
    msg="操作成功",
    code="200",
    data={...}
)
```

**响应格式说明**：
```json
{
 "code": "200",      // 状态码字符串
 "msg": "操作成功",   // 接口返回信息
 "data": {},         // 接口返回的数据对象
 "status": "success" // 接口返回状态描述
}
```

**分页响应格式**（强制规范）：

```python
return CommonResponse(
    status="success",
    msg="查询成功",
    code="200",
    data={
        "total": total,
        "page": page,
        "pageSize": page_size,  # 必须使用 pageSize
        "list": items           # 必须使用 list
    }
)
```

## 🎨 核心功能模块

### 认证和安全

- **JWT 认证**: 基于令牌的身份验证
- **TOTP 二次验证**: 双因素认证
- **密码加密**: bcrypt 哈希算法
- **SM4 加密**: 敏感数据国密算法加密
- **输入验证**: Pydantic 模型验证
- **SQL 注入防护**: ORM 参数化查询

### 数据库设计

- **ORM 映射**: SQLAlchemy 异步 ORM
- **软删除**: 支持逻辑删除
- **审计日志**: 自动记录创建和修改时间
- **索引优化**: 合理创建索引
- **关系管理**: 外键和关系定义

### API 设计

- **RESTful 风格**: 遵循 REST 架构风格
- **统一响应格式**: 所有接口使用 CommonResponse
- **自动文档生成**: Swagger/OpenAPI 文档
- **依赖注入**: 使用 FastAPI 依赖注入系统
- **异步处理**: 全异步 API 处理

### 任务调度

- **APScheduler**: 后台任务调度
- **Cron 表达式**: 灵活的任务调度
- **任务持久化**: 数据库存储任务配置
- **失败重试**: 任务失败自动重试机制

### WebSocket 通信

- **实时推送**: 下载器状态实时更新
- **连接管理**: 连接状态跟踪
- **认证机制**: 基于 Cookie 的 JWT 验证
- **多线程**: 每个下载器独立监控线程

## 🔐 安全机制

- JWT Token 认证
- TOTP 二次验证
- SM4 国密算法加密
- 密码 bcrypt 哈希
- SQL 注入防护
- XSS 防护
- CORS 跨域配置

## 🧪 测试策略

- **单元测试**: Pydantic 模型验证
- **集成测试**: 完整 API 调用链路
- **端到端测试**: 前端 → 后端 → 数据库

## 📦 部署

### 生产环境启动

```bash
# 使用启动脚本
./btdeck_startup.sh start

# 或直接使用 uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port 5001 --workers 4
```

### Nginx 反向代理配置

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api {
        proxy_pass http://localhost:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /ws {
        proxy_pass http://localhost:5002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 🤝 协作开发

### Git 工作流

```bash
# 1. 查看当前状态
git status

# 2. 添加修改的文件
git add .

# 3. 提交代码（使用约定式提交格式）
git commit -m "feat: 添加XX接口"

# 4. 推送到远程仓库
git push origin feature-branch
```

### 提交信息格式

```
feat: 新增功能
fix: 修复bug
docs: 文档更新
style: 代码格式调整
refactor: 重构代码
test: 测试相关
chore: 构建/工具链更新
```

### 数据库迁移规范

**⚠️ 重要**: 所有数据库层面的修改必须通过 Alembic 迁移脚本管理

1. **生成迁移脚本**:
   ```bash
   alembic revision --autogenerate -m "描述"
   ```

2. **审查迁移文件**: 确保变更符合预期

3. **执行迁移**:
   ```bash
   alembic upgrade head
   ```

4. **验证版本**:
   ```bash
   alembic heads  # 确保只有 1 个 head
   ```

## 📜 更新日志

### v1.0.1 (2026-03-16)

#### 🐛 Bug 修复

**修复 qBittorrent 下载器做种数据统计错误** (关键修复)
- **问题描述**：qBittorrent 下载器的 `seedingCount` 显示为 0 或错误值，`downloadingCount` 和 `seedingCount` 数据完全相反
- **根本原因**：
  - 状态分类错误：`checkingUP` 状态被错误归类为"下载中"而非"做种中"
  - 状态映射未应用：种子获取时未使用 `TorrentStatusMapper` 进行状态转换
  - 状态映射不一致：状态映射器与状态分类器的定义不匹配
- **修复内容**：
  - `torrent_stats_cache.py`: 将 `checkingUP` 从 `DOWNLOADING_STATES` 移到 `SEEDING_STATES`
  - `torrent_fetcher.py`: 在获取 qBittorrent 种子时应用状态映射
  - `torrent_status_mapper.py`: 修正 `pausedUP` 和 `pausedDL` 的映射策略，保持原始状态

**其他修复**
- 修复修改密码接口参数验证问题
- 修复多下载器并发同步时的数据库锁定问题
- 修复多选筛选和批量更新中的潜在 panic 风险

#### ⚡ 性能优化

- 优化数据库重试间隔策略
- 优化数据库并发性能和状态枚举映射

#### ✨ 新增功能

- 种子列表和重复任务支持下载器/状态多选筛选

#### 📝 技术改进

- 完善种子状态映射和分类逻辑
- 提高下载器状态统计的准确性

---

### v1.0.0 (2026-03-XX)

#### 🎉 首次发布

- 完整的 BitTorrent 管理器后端服务
- 支持 qBittorrent 和 Transmission 下载器
- WebSocket 实时状态推送
- 后台任务调度系统
- JWT + TOTP 二次验证
- SM4 国密算法数据加密

## 📝 开发规范

- 遵循 [CLAUDE.md](./CLAUDE.md) 中的开发指导
- 代码提交前确保通过类型检查和测试
- 优先复用现有模块和工具函数
- 遵循 KISS、DRY、YAGNI 原则
- 数据库变更必须生成迁移脚本

## 🔗 相关项目

- **前端项目**: [btpManager_fronted](../btpManager_fronted/)
- **主项目**: [btpManager_full_stack](../)

## 📄 许可证

本项目采用 **GNU General Public License v3.0** 许可证。

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)

### 核心要点

- ✅ **自由使用** - 可以自由使用、研究、修改软件
- ✅ **自由分享** - 可以自由分发原始版本和修改版本
- ⚠️ **开源义务** - 修改和衍生作品必须同样使用 GPL v3 开源
- ⚠️ **提供源码** - 分发时必须提供完整的源代码
- ❌ **禁止闭源** - 不得将软件闭源后分发

完整许可证文本请参阅 [LICENSE](./LICENSE) 文件。

### GPL v3 与商业使用

GPL v3 允许商业使用，但有以下限制：
- ✅ 可以在内部商业环境中使用
- ✅ 可以提供基于BTDeck的商业服务
- ⚠️ 如果分发修改版本，必须开源修改的代码
- ❌ 不能将BTDeck集成到闭源产品中分发

---

**开发协作**: 后端开发人员应共同维护文档，及时更新架构变更和最佳实践。
**问题反馈**: 遇到文档未覆盖的场景，请记录并更新，确保团队知识积累。
