# deploy — 多部署模式

> BtDeck 支持 4 种部署模式：Docker Compose（推荐）、PyInstaller 单机包（Windows/Linux）、Inno Setup（Windows 安装包）、fpm（Linux 包）。⚠ 不同模式的入口与 SPA fallback 不同。

## 部署模式总览

| 模式 | 入口 | 适用场景 | SPA fallback |
|------|------|---------|-------------|
| **Docker Compose** | `docker-compose.yml` + `btdeck_startup.sh` | 服务器部署（推荐） | nginx（`frontend/nginx.conf`） |
| **PyInstaller 单机** | `deploy/btdeck.spec` / `btdeck-windows.spec` | 单机免安装 | `factory.py:_mount_frontend_static` |
| **Inno Setup** | `deploy/btdeck.iss` + `ChineseSimplified.isl` | Windows 安装包 | PyInstaller 同 |
| **fpm Linux 包** | `deploy/build-linux.sh` | Linux deb/rpm | PyInstaller 同 |

> ⚠ **双 SPA fallback**：Docker 用 nginx，PyInstaller 单机用后端 `factory.py` 挂载静态文件。详见 [../perspectives/risks.md](../perspectives/risks.md)。

---

## Docker Compose 模式

### docker-compose.yml（根目录）

两个服务 + 自定义网络 + 命名卷：

| 服务 | 镜像 | 端口 | 挂载 | 依赖 |
|------|------|------|------|------|
| `backend` | `btdeck-backend:latest`（构建上下文 `./backend`） | 仅 `EXPOSE 5001`（容器内） | `./data/backend/{data,logs,config,backup}` → `/app/{data,logs,config,backup}` | healthcheck `curl -f http://localhost:5001/docs` |
| `frontend` | `btdeck-frontend:latest`（Dockerfile `Dockerfile.prod`） | `${BTDECK_PORT:-8080}:80` | `frontend_cache` / `frontend_logs` 命名卷 | `depends_on: backend (condition: service_healthy)` |

- 网络：`btdeck_network`（bridge）
- 卷：`frontend_cache`、`frontend_logs`（local）
- **backend 不暴露端口**：入口统一从 frontend nginx 反代访问

### backend 启动

- `backend/Dockerfile` L95 `CMD ["/app/btdeck_startup.sh"]`
- `backend/btdeck_startup.sh` 真正执行（L62-67）：
  ```
  exec uvicorn app.main:app --host 0.0.0.0 --port 5001 --workers $WORKERS --loop asyncio --log-level info
  ```
- `APP_MODULE="app.main:app"`（L9）；`PORT=5001`（L10）；`WORKERS` 默认 1（L12）
- 脚本只做环境准备（日志目录、PYTHONPATH）；配置初始化、数据库迁移、seed 全部交由 FastAPI lifespan 负责

### frontend 构建 + nginx

- 构建：`frontend/Dockerfile.prod` L39 `RUN npm run build` → 产物 `dist`
- 拷贝：L59 `COPY --from=builder /app/dist /usr/share/nginx/html`
- 启动：L84 `CMD ["nginx", "-g", "daemon off;"]`
- `frontend/nginx.conf` 关键：
  - L53 `listen 80;`；L60 `root /usr/share/nginx/html;`
  - L70-74 静态资源缓存 1y
  - L78 `location /api/ { proxy_pass http://btdeck-backend:5001; }`
  - L106 `location /ws/ { proxy_pass http://btdeck-backend:5002/; }`（WebSocket 走 5002）
  - L123 `location / { try_files $uri $uri/ /index.html; }`（SPA history fallback）
  - L133 `location /health`（容器健康检查端点）

### 一键脚本

- `deploy/start.sh`：宿主机一键 `docker compose up -d --build`（L47），**不是应用启动入口**
- `build-images.sh`（根目录）：构建并导出镜像 tar
- `build-and-export-images.bat`（根目录，Windows）

---

## PyInstaller 单机模式

### spec 文件

| 文件 | 平台 | 用途 |
|------|------|------|
| `deploy/btdeck.spec` | Linux | PyInstaller 打包配置 |
| `deploy/btdeck-windows.spec` | Windows | PyInstaller 打包配置（含 Windows 特殊处理） |

### 构建脚本

| 文件 | 用途 |
|------|------|
| `deploy/build-windows.bat` | Windows 一键构建（PyInstaller + Inno Setup） |
| `deploy/build-linux.sh` | Linux 一键构建（PyInstaller + fpm） |

### 产物

| 文件/目录 | 用途 |
|-----------|------|
| `deploy/dist/btdeck.exe` | Windows 可执行 |
| `deploy/build/btdeck/` | PyInstaller 中间产物（Analysis/EXE/PYZ/PKG .toc 等） |

### Windows 服务支持

| 文件 | 用途 |
|------|------|
| `deploy/btdeck.service` | systemd 服务单元（Linux） |
| `deploy/nssm.exe` | Windows 服务包装器（Non-Sucking Service Manager） |
| `deploy/start.bat` / `deploy/start.sh` | 启动脚本 |

### 依赖

| 文件 | 用途 |
|------|------|
| `deploy/requirements-linux-package.txt` | Linux 打包专用依赖 |
| `deploy/requirements-windows-package.txt` | Windows 打包专用依赖 |

### 辅助

| 文件 | 用途 |
|------|------|
| `deploy/ChineseSimplified.isl` | Inno Setup 中文语言包 |
| `deploy/btdeck.iss` | Inno Setup 安装脚本 |
| `deploy/analyze-package-size.py` | 打包体积分析 |
| `deploy/verify-package.py` | 打包产物校验 |

---

## 关键观察

- **双入口分叉**：Docker 走 `btdeck_startup.sh` + nginx；单机走 PyInstaller + `factory.py:_mount_frontend_static`。两种模式下"如何提供前端静态文件"完全不同。
- **WebSocket 独立端口**：Docker 模式下 HTTP 走 5001，WebSocket 走 5002（`websocket_main.py` 独立入口）。
- **构建产物已入库**：`deploy/dist/btdeck.exe`、`deploy/build/` 已提交到仓库（可能是误提交，体积较大）。

## 第三层详情

- 本分支为部署配置，通常不需要第三层方法签名详情；如需要，可对 `btdeck_startup.sh`、`btdeck.iss`、`nginx.conf` 做专项分析。
