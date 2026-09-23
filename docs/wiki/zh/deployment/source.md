# 源码部署

源码部署适合开发、调试和贡献代码。生产环境优先使用 Docker 或经过发布门禁验证的安装包。

## 工具链

| 组件 | 版本基线 |
| --- | --- |
| Python | 3.12+ |
| Node.js | 22.23.2（22.x） |
| npm | 10.9.8 |
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 前端 | Vue 2.6 + TypeScript + Element UI |

依赖安装应使用仓库中的锁定文件和 `package-lock.json`。不要把虚拟环境、`node_modules` 或本地数据库加入提交。

## 启动后端

```bash
cd backend
python -m venv .venv
# 激活 .venv 后执行
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001
```

后端启动时会执行迁移和初始数据准备。数据库路径由配置决定，开发时请为不同实验使用独立数据库，避免把临时 schema 带入常用环境。

## 启动前端

```bash
cd frontend
npm ci
npm run serve
```

需要验证生产构建时执行：

```bash
npm run typecheck
npm run lint
npm run build
```

前端开发服务器通常在 `http://localhost:8080`，API 文档在 `http://localhost:5001/docs`。如前端无法请求 API，先检查 API 基地址配置和后端是否已通过 `/health/ready`。

## 测试与环境验证

项目根目录提供轻量验证入口：

```bash
./init.sh --ci
```

后端测试在 `backend/` 下运行 `pytest`；前端测试使用 `npm run test:unit`。修改 Wiki 内容不要求运行全栈测试，但修改部署示例或启动命令后应至少重新验证对应命令。

## 开发边界

- 后端和前端的 API 信封、错误码和分页字段是稳定契约。
- 下载器连接必须复用应用缓存；不要为每个请求创建新客户端。
- 前端仍以 Vue 2 Options API/class-component 代码为主，不要把 Vue 3 组合式写法当作当前基线。
- 数据库结构只通过 Alembic 迁移管理。

