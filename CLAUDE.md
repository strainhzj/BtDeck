# CLAUDE.md - BTDeck后端项目

为Claude Code提供后端开发指导，专注于FastAPI + Python技术栈和最佳实践。

## 1. 项目认知框架

### 项目定位与价值
**BTDeck**是一个全栈Web应用，为用户提供多种BitTorrent客户端(qBittorrent、Transmission)的统一管理界面。

**核心用户价值**：
- 统一管理多个下载器，避免切换不同客户端
- 提供Web界面，支持远程管理和移动设备访问
- 后台任务调度，实现自动化下载管理
- 实时状态监控，及时获取下载进度和问题预警

**关键业务目标**：
- 支持1000+并发下载任务管理
- API响应时间<200ms，界面操作流畅
- 多用户安全访问，支持权限控制
- 7x24小时稳定运行，自动故障恢复

### 技术挑战与解决方案
| 挑战 | 解决方案 |
|------|----------|
| 多协议适配 | 统一下载器接口，支持qBittorrent API和Transmission RPC |
| 实时状态同步 | WebSocket推送 + 后台定时任务双重保障 |
| 高并发处理 | FastAPI异步框架 + SQLAlchemy连接池 |
| 数据安全 | JWT认证 + TOTP二次验证 + 敏感数据SM4加密 |

## 2. 开发工作约束

### 2.1 代码简洁性原则

✅ **追求代码简洁、模块化、可复用，避免过度复杂**

**核心原则**：代码应该足够简洁、模块化，可以直接复用，无须关心内部过程，并非越多越好。

**实现标准**：
1. **简洁性优先**：用最少的代码实现功能，避免不必要的复杂性
2. **模块化设计**：每个模块只做一件事，职责单一明确
3. **封装内部实现**：使用者只需知道"做什么"，无需了解"怎么做"
4. **可复用性第一**：通用功能提取为公共模块，避免重复代码
5. **拒绝过度工程**：不预支未来需求，不添加当前不需要的功能

**判断标准**：
- ✅ 代码行数减少 = 更好（在不损失可读性的前提下）
- ✅ 一个函数能完成 = 绝不拆成两个
- ✅ 现有组件能满足 = 绝不创建新组件
- ❌ 为了"可能将来需要"而添加功能 = 错误
- ❌ 代码"看起来很专业"但实际没用 = 错误

**遵循原则**：KISS（保持简单）、DRY（不重复）、YAGNI（不做不需要的事）

### 2.2 交互模式（必读）

🔴 **开始任务前，必须先提出实现假设并获得确认**

- **步骤 1**：分析需求，提出你的实现假设
 - 使用的框架和类库
 - 架构设计方案
 - 涉及的关键文件和模块
- **步骤 2**：检查假设之间的矛盾关系
 - 技术栈兼容性
 - 架构设计一致性
 - 与现有代码的冲突
- **步骤 3**：等待用户确认后再开始编码
 - 不要假设用户会接受你的方案
 - 重大变更必须获得明确批准

**示例**：

```
❌ 错误：直接开始编码
✅ 正确："我计划创建新的 API router 来管理下载器，
      会修改 app/api/routers/downloader.py，这样设计符合吗？"
```

### 2.3 代码复用优先

✅ **优先复用现有代码和类，仅在必要时创建新的**

- **检查清单**：
 1. 搜索项目中是否已有相似功能
 2. 检查是否可以扩展现有模块/函数
 3. 评估复用 vs 新增的成本
- **创建新代码的条件**：
 - 现有代码无法满足需求
 - 扩展现有代码会导致复杂度显著增加
 - 新代码有明确的复用价值

### 2.4 问题澄清机制

❓ **遇到不清楚的细节时，主动提问获取补充信息**

- **必须提问的场景**：
 - 需求描述模糊或存在歧义
 - 多种实现方案，需要用户决策
 - 涉及架构变更或影响现有功能
 - 不确定业务逻辑或数据流向
- **提问方式**：
 - 描述当前理解
 - 列出可选方案及优劣
 - 推荐方案并说明理由
 - 等待用户决策

### 2.5 API响应格式规范

**所有后端开发者必须严格遵守以下API响应格式规范！**

#### 标准API响应格式（强制）

**所有API接口必须遵循以下统一响应格式**：

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
 "msg": "操作成功",   // 接口返回信息，用于前端显示给用户
 "data": {},         // 接口返回的数据对象
 "status": "success" // 接口返回状态描述
}
```

#### 分页响应格式（强制 - 严禁修改字段名）

**⚠️ 所有返回列表数据的API必须使用以下格式，字段名绝对不能修改！**

```python
from app.common.response import CommonResponse

# ✅ 正确的后端分页响应
return CommonResponse(
    status="success",
    msg="查询成功",
    code="200",
    data={
        "total": total,
        "page": page,
        "pageSize": page_size,  # ✅ 必须使用pageSize
        "list": items           # ✅ 必须使用list
    }
)
```

**分页字段定义（强制要求）**：
- **total**: 总记录数（`int`类型）
- **page**: 当前页码（`int`类型，从1开始）
- **pageSize**: 每页记录数（`int`类型）
  - ❌ **严禁使用** `page_size`、`page_size`等其他变体
  - ❌ **严禁使用** `limit`、`size`、`per_page`等其他命名
  - ✅ **必须使用** `pageSize`（驼峰命名）
- **list**: 数据列表数组（`list`类型）
  - ❌ **严禁使用** `items`、`data`、`results`等其他命名
  - ❌ **严禁使用** `rows`、`records`等其他变体
  - ✅ **必须使用** `list`（小写）

### 2.6 Git操作规范

🔧 **后端项目独立管理，Git操作必须在项目根目录执行**

**Git操作流程**：

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

**提交信息格式**（Conventional Commits）：
```
feat: 新增功能
fix: 修复bug
docs: 文档更新
style: 代码格式调整
refactor: 重构代码
test: 测试相关
chore: 构建/工具链更新
```

**⚠️ 注意事项**：
- ✅ 提交前确保代码通过类型检查
- ✅ 提交前确保所有测试通过
- ✅ 提交信息清晰描述变更内容

## 3. 后端特定约束

### 3.1 数据库迁移管理（强制）

**🔴 核心原则**：所有数据库层面的修改必须通过 Alembic 迁移脚本管理，应用程序启动时必须自动执行数据库迁移。

#### 严格禁止

- ❌ 直接在数据库中修改表结构（使用 DDL 语句）
- ❌ 仅修改 SQLAlchemy 模型代码而不生成迁移文件
- ❌ 手动创建或删除数据库表、索引、约束

#### 必须执行

- ✅ 任何 Schema 变更（新增/修改表、字段、索引）**必须**生成对应的 Alembic revision
- ✅ 使用 `alembic revision --autogenerate -m "描述"` 生成迁移脚本
- ✅ 审查自动生成的迁移文件，确保变更符合预期
- ✅ 提交前执行 `alembic heads`，确保只有 **1 个 head**（避免 Multiple Heads）

#### 应用启动流程要求

后端应用启动脚本（`app/main.py`）必须包含自动迁移执行逻辑，确保数据库结构始终是最新状态。

**启动顺序**：
```
1. 初始化配置文件
2. 执行数据库迁移（alembic upgrade head）
3. 初始化数据库连接
4. 启动 API 服务
```

### 3.2 下载器客户端连接管理（强制）

**🔴 核心原则**：所有涉及下载器操作的接口，必须使用 `app.state.store` 缓存中的客户端连接，严禁重复创建连接。

#### 使用规范

1. **从缓存获取下载器**
  ```python
  cached_downloaders = app.state.store.get_snapshot_sync()
  downloader_vo = next(
      (d for d in cached_downloaders if d.downloader_id == downloader_id),
      None
  )
  ```

2. **验证连接有效性**
  ```python
  if not downloader_vo or downloader_vo.fail_time > 0:
      return error_response("下载器不可用")

  client = downloader_vo.client
  ```

3. **使用缓存的客户端**
  ```python
  if downloader_vo.downloader_type == 0:  # qBittorrent
      client.torrents_pause(torrent_hashes=hashes)
  elif downloader_vo.downloader_type == 1:  # Transmission
      client.stop_torrent(hashes)
  ```

**严格禁止**：
- ❌ 在业务接口中创建新的客户端连接（`qbClient(...)` 或 `trClient(...)`）
- ❌ 手动释放缓存连接（`client.logout()`）

**适用范围**：所有下载器操作接口（pause/resume/recheck 等）

### 3.3 跨环境数据库一致性保障（强制）

**🔴 核心原则**：确保所有开发环境和生产环境的数据库结构始终保持一致，避免因迁移版本不同步导致的功能异常。

#### 严格禁止

- ❌ 启动应用前不检查数据库版本
- ❌ 在不同环境间切换时直接启动应用
- ❌ 迁移失败时强制启动应用
- ❌ 手动修改数据库结构而不生成迁移脚本

#### 必须执行

- ✅ **每次启动前检查版本**：`alembic current` 与 `alembic heads` 对比
- ✅ **版本不一致时立即升级**：`alembic upgrade head`
- ✅ **git pull后自动检查**：配置 `.git/hooks/post-merge` 自动验证
- ✅ **部署前强制验证**：CI/CD流程中加入版本一致性检查
- ✅ **定期备份正常数据库**：保留已知可用的数据库副本

#### 快速诊断与修复

```bash
# 检查版本一致性
alembic current   # 应输出: 9aea25308aff (head)
alembic heads     # 确认最新版本

# 版本不一致时立即升级
alembic upgrade head

# 验证表结构完整性
sqlite3 config/app.db ".tables" | wc -l  # 应为 27 个表
```

**备份恢复方案**（迁移失败时）：

```bash
cd config
mv app.db app.db.failed_$(date +%Y%m%d_%H%M%S)
cp app_backup_YYYYMMDD.db app.db
```

## 4. 后端架构与最佳实践

### 4.1 技术栈

- **Python**: 3.11+
- **框架**: FastAPI 0.115.0
- **ORM**: SQLAlchemy 2.0.15（异步）
- **数据验证**: Pydantic 2.12.4
- **数据库**: SQLite
- **认证**: JWT + OAuth2 + TOTP
- **任务调度**: APScheduler 3.10.0
- **WebSocket**: FastAPI WebSocket支持
- **加密**: SM4国密算法

### 4.2 项目结构

```
btpManager/
├── app/
│   ├── api/              # API路由
│   │   └── routers/      # 路由模块
│   ├── common/           # 公共模块
│   │   ├── response.py   # 统一响应格式
│   │   └── exceptions.py # 自定义异常
│   ├── core/             # 核心配置
│   │   ├── config.py     # 配置管理
│   │   └── security.py   # 安全相关
│   ├── models/           # 数据库模型
│   ├── schemas/          # Pydantic模型
│   ├── services/         # 业务逻辑层
│   ├── utils/            # 工具函数
│   ├── main.py           # 应用入口
│   └── dependencies.py   # 依赖注入
├── alembic/              # 数据库迁移
│   └── versions/         # 迁移脚本
├── tests/                # 测试文件
├── config/               # 配置文件
│   └── app.db           # SQLite数据库
├── alembic.ini           # Alembic配置
├── requirements.txt      # 依赖列表
└── pyproject.toml       # 项目配置
```

### 4.3 API设计模式

- **RESTful风格**: 遵循REST架构风格
- **统一响应格式**: 所有接口使用CommonResponse
- **自动文档生成**: Swagger/OpenAPI文档
- **依赖注入**: 使用FastAPI依赖注入系统
- **异步处理**: 全异步API处理

### 4.4 认证和安全

- **JWT认证**: 基于令牌的身份验证
- **TOTP二次验证**: 双因素认证
- **密码加密**: bcrypt哈希算法
- **SM4加密**: 敏感数据国密算法加密
- **输入验证**: Pydantic模型验证
- **SQL注入防护**: ORM参数化查询

### 4.5 数据库设计

- **ORM映射**: SQLAlchemy异步ORM
- **软删除**: 支持逻辑删除
- **审计日志**: 自动记录创建和修改时间
- **索引优化**: 合理创建索引
- **关系管理**: 外键和关系定义

### 4.6 任务调度

- **APScheduler**: 后台任务调度
- **Cron表达式**: 灵活的任务调度
- **任务持久化**: 数据库存储任务配置
- **失败重试**: 任务失败自动重试机制

### 4.7 WebSocket通信

- **实时推送**: 下载器状态实时更新
- **连接管理**: 连接状态跟踪
- **认证机制**: 基于Cookie的JWT验证
- **多线程**: 每个下载器独立监控线程

## 5. 开发工作流

### 5.1 本地开发启动

```bash
# 1. 激活conda环境
conda activate btpManager

# 2. 启动后端服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001
```

### 5.2 数据库迁移

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 查看当前版本
alembic current

# 查看迁移历史
alembic history
```

### 5.3 代码检查

```bash
# 类型检查
mypy app/

# 代码格式化
black app/

# 导入排序
isort app/

# Lint检查
flake8 app/
```

### 5.4 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_api.py

# 生成覆盖率报告
pytest --cov=app tests/
```

### 5.5 服务端口

- **API服务**: http://localhost:5001
- **WebSocket**: ws://localhost:5002
- **API文档**: http://localhost:5001/docs

## 6. 防御性编程与最佳实践

### 6.1 防御性编程原则

- **永不信任外部输入**: 包括数据库、用户输入
- **提供默认值**: 当数据不符合预期时，使用安全的降级策略
- **日志记录**: 在开发环境输出验证失败的警告

### 6.2 提高代码复用意识

- 实现功能前，优先检查是否存在已实现相同功能的方法
- 通用功能提取为公共模块或工具函数
- 避免在不同模块重复实现相同逻辑

### 6.3 前后端类型定义一致性

- 使用Pydantic模型定义API请求和响应
- 与前端TypeScript接口保持同步
- 考虑使用OpenAPI/Swagger自动生成前端类型
- 避免手动维护两套类型定义

### 6.4 数据库迁移后必须同步更新API验证规则

- Schema变更 → Pydantic模型 → API文档
- 遗漏任何一层都会导致前后端不一致

### 6.5 完整的测试覆盖

- **单元测试**: Pydantic模型验证
- **集成测试**: 完整API调用链路
- **端到端测试**: 前端 → 后端 → 数据库

## 7. 开发调试技巧

### 7.1 日志调试

```python
import logging

logger = logging.getLogger(__name__)
logger.info("信息日志")
logger.error("错误日志")
logger.debug("调试日志")
```

### 7.2 数据库调试

```bash
# 查看数据库表结构
sqlite3 config/app.db ".schema"

# 查询数据
sqlite3 config/app.db "SELECT * FROM users;"
```

### 7.3 API调试

- 访问 http://localhost:5001/docs 查看API文档
- 使用Swagger UI测试接口
- 查看请求和响应详情

### 7.4 常用开发命令

```bash
# 查看依赖
pip list

# 安装新依赖
pip install package_name

# 导出依赖
pip freeze > requirements.txt

# 查看Python版本
python --version
```

## 8. 详细开发文档

本项目有完整的后端开发技能文档体系，位于 `.claude/skills/backend-dev-guidelines-python3/` 目录。

### 核心文档

- **[项目文档索引](.claude/skills/backend-dev-guidelines-python3/项目文档索引.md)** - 完整的开发指南导航
- **[后端开发技能指南](.claude/skills/backend-dev-guidelines-python3/开发指南/SKILL.md)** - Python3后端开发完整技能指南
- **[btpManager项目示例](.claude/skills/backend-dev-guidelines-python3/项目示例/CUSTOM_EXAMPLES.md)** - 项目特定示例和模板

### 主要模块

1. **数据库模块**: 模型设计、数据操作、迁移管理
2. **认证安全模块**: JWT、TOTP、SM4加密
3. **接口层**: REST API设计、请求响应处理
4. **中间件模块**: 认证、日志、错误处理
5. **错误处理模块**: 异常管理、错误响应
6. **测试框架**: 单元测试、集成测试

## 9. 版本更新与维护

### 9.1 依赖更新

```bash
# 检查过时的依赖
pip list --outdated

# 更新依赖
pip install --upgrade package_name
```

### 9.2 文档维护

- 遇到文档未覆盖的场景，请记录并更新
- 确保团队知识积累和传承
- 重大架构变更需及时更新此文档

---

**开发协作**: 后端开发人员应共同维护此文档，及时更新架构变更和最佳实践。
**问题反馈**: 遇到文档未覆盖的场景，请记录并更新，确保团队知识积累。
