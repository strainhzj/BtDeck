# deploy — 多部署模式

> BtDeck 支持 4 种部署模式：Docker Compose（推荐）、PyInstaller 单机包（Windows/Linux）、Inno Setup（Windows 安装包）、fpm（Linux 包）。⚠ 不同模式的入口与 SPA fallback 不同。
> 定位方式：`Grep -i <功能词> docs/roadmap/deploy/README.md`，命中行即含模式/文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 模式/文件 | 一句话职责 |
|--------|-----------|-----------|
| Docker Compose docker | `docker-compose.yml` + `btdeck_startup.sh` | 服务器部署（推荐）；backend 仅 EXPOSE 5001 不暴露端口，nginx 反代 5001；SPA fallback = nginx |
| Docker 镜像源参数化 docker-mirror | `backend/Dockerfile` / `frontend/Dockerfile(.prod)`（v1.0.6.28） | build-arg 注入 `APT_MIRROR`/`PIP_INDEX_URL`/`NPM_REGISTRY`，默认空串=官方源（向后兼容） |
| 一键脚本 start | `deploy/start.sh` / `build-images.sh` / `build-and-export-images.bat` | 宿主机 `docker compose up -d --build`；构建导出镜像 tar；bat 含 3 profile 镜像源重试链 |
| PyInstaller 单机 pyinstaller | `deploy/btdeck.spec` / `btdeck-windows.spec` | PyInstaller 打包配置（Linux / Windows）；SPA fallback = `factory.py:_mount_frontend_static` |
| 构建脚本 build | `deploy/build-windows.bat` / `deploy/build-linux.sh` | Windows 一键构建（PyInstaller + Inno Setup）；Linux 一键构建（PyInstaller + fpm） |
| Inno Setup 安装包 innosetup | `deploy/btdeck.iss` + `ChineseSimplified.isl` | Windows 安装包脚本 + 中文语言包 |
| fpm Linux 包 fpm | `deploy/build-linux.sh` | Linux deb/rpm 打包 |
| 系统服务 nssm | `deploy/btdeck.service` / `deploy/nssm.exe` | systemd 服务单元（Linux）/ Windows 服务包装器 |
| 启动脚本 start.bat | `deploy/start.bat` / `deploy/start.sh` | 启动脚本 |
| 打包依赖 requirements | `deploy/requirements-linux-package.txt` / `requirements-windows-package.txt` | Linux / Windows 打包专用依赖 |
| 打包辅助 analyze-package | `deploy/analyze-package-size.py` / `verify-package.py` | 打包体积分析 / 产物校验 |
| TLS 参考配置 nginx-tls | `deploy/nginx-tls.conf.example` | HTTPS 反代参考配置（安全修复 W14）：HTTP 301 → HTTPS、HSTS、证书挂载说明，保留 `/api/` 内网代理 |
| 构建产物 artifact | 仓库根 `dist/`（`btdeck.exe`、`btdeck-linux`、`BtDeck-v1.0.9-*.deb/.rpm`、`config`） / `build/btdeck-windows/` | Windows/Linux 可执行与安装包 / PyInstaller 中间产物（均已 .gitignore，不入库） |

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
| `backend` | `btdeck-backend:latest`（构建上下文 `./backend`） | 仅 `EXPOSE 5001`（容器内） | `./data/backend/{data,logs,config,backup}` → `/app/{data,logs,config,backup}` | healthcheck `curl -f http://localhost:5001/health/ready`（严格 readiness） |
| `frontend` | `btdeck-frontend:latest`（Dockerfile `Dockerfile.prod`） | `${BTDECK_PORT:-8080}:80` | `frontend_cache` / `frontend_logs` 命名卷 | `depends_on: backend (condition: service_healthy)` |

- 网络：`btdeck_network`（bridge）
- 卷：`frontend_cache`、`frontend_logs`（local）
- **backend 不暴露端口**：入口统一从 frontend nginx 反代访问

### backend 启动

- `backend/Dockerfile` L114 `CMD ["/app/btdeck_startup.sh"]`
- `backend/btdeck_startup.sh` 真正执行（L102）：
  ```
  exec uvicorn app.main:app --host 0.0.0.0 --port 5001 --workers $WORKERS --loop asyncio --log-level info
  ```
- `APP_MODULE="app.main:app"`（L15）；`PORT=5001`（L16）；`WORKERS` 默认 1（L18）
- 启动前 fail-fast（L71-82）：SQLite 后端 + `WORKERS != 1` 直接拒绝启动（多 worker 共享 SQLite 文件库会损坏数据），日志提示改回单 worker
- 脚本只做环境准备（日志目录、PYTHONPATH、SQLite worker 校验）；配置初始化、数据库迁移、seed 全部交由 FastAPI lifespan 负责

### frontend 构建 + nginx

- 构建：`frontend/Dockerfile.prod` L50 `RUN npm run build` → 产物 `dist`
- 拷贝：L70 `COPY --from=builder /app/dist /usr/share/nginx/html`
- 启动：L95 `CMD ["nginx", "-g", "daemon off;"]`
- `frontend/nginx.conf` 关键：
  - L53 `listen 80;`；L60 `root /usr/share/nginx/html;`
  - L71 `service-worker.js` 精确 no-store；L81 只有 `/assets/` 内容哈希资源缓存 1y immutable
  - L93 `location = /api/v1/auth/login`（登录接口 body 上限 1M，安全修复 W13）
  - L105 `location /api/ { proxy_pass http://btdeck-backend:5001; }`
  - L129 `location / { try_files $uri $uri/ /index.html; }`（SPA history fallback + no-store）
  - L138 `location /health`（容器健康检查端点）

> 部署会整体替换包含哈希文件的不可变前端镜像。已打开的旧 SPA 可能在客户端路由跳转时请求旧 chunk；`router.onError` 会携带一次性 query 重新加载当前 no-store 入口，60 秒门禁防止服务器真实缺文件时循环刷新。

### 一键脚本

- `deploy/start.sh`：宿主机一键 `docker compose up -d --build`（L47），**不是应用启动入口**
- `build-images.sh`（根目录）：构建并导出镜像 tar
- `build-and-export-images.bat`（根目录，Windows）：构建 + 导出 + 可选 SSH 部署到远端（含镜像源 profile 重试链，见下节）

### Dockerfile 镜像源参数化（v1.0.6.28，commit `48bbcf7`）

三个 Dockerfile（`backend/Dockerfile`、`frontend/Dockerfile`、`frontend/Dockerfile.prod`）把原本硬编码的 `mirrors.aliyun.com` 改为 **build-arg 注入**，默认空串 = 走官方源（向后兼容）：

| build-arg | 作用 | 注入方式 |
|-----------|------|---------|
| `APT_MIRROR` | apt 源（替换 `deb.debian.org` + `security.debian.org`，Bookworm deb822 格式） | builder + runtime 两阶段都需重新 `ARG APT_MIRROR=`（ARG 不跨 `FROM` 继承） |
| `PIP_INDEX_URL` / `PIP_TRUSTED_HOST` | pip 源 | `ENV PIP_INDEX_URL=${PIP_INDEX_URL}` 让本阶段所有 pip 命令自动读取 |
| `NPM_REGISTRY` | npm registry | `ENV NPM_CONFIG_REGISTRY=${NPM_REGISTRY}` 让所有 npm 命令自动读取 |

**关键设计**：
- `APT_MIRROR` 为空时跳过 `sed`（`if [ -n "$APT_MIRROR" ]`），与改造前"硬编码阿里云"不同 —— 默认现在是官方源，需镜像源才显式注入
- `build-and-export-images.bat` 内置 3 个 profile（官方 / 阿里云 / 华为云）的重试链：profile 2（阿里云）失败自动切 profile 3（华为云），最后回退 profile 1（官方）
- 注：tencent apt 镜像被排除（强制 HTTPS，builder 阶段无 ca-certificates 会证书校验失败）；阿里云/华为云走 HTTP 可在裸 builder 阶段工作

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

### 产物（仓库根 `dist/` 与 `build/`，均已 .gitignore 不入库）

| 文件/目录 | 用途 |
|-----------|------|
| `dist/btdeck.exe` | Windows 可执行 |
| `dist/btdeck-linux` | Linux 可执行 |
| `dist/BtDeck-v1.0.9-linux-amd64.deb` / `.rpm` | fpm 打包的 Linux deb/rpm 安装包 |
| `dist/config` | 打包配套配置 |
| `build/btdeck-windows/` | PyInstaller 中间产物（Analysis/EXE/PYZ/PKG .toc 等） |

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
- **WebSocket 已移除**：`websocket_main.py` 与 5002 端口转发已删除（前端用 5 秒轮询，无实时推送服务）。
- **构建产物不入库（已整改）**：历史曾误提交 `deploy/dist/btdeck.exe`、`deploy/build/`、根目录镜像 tar；现产物仅落在本机仓库根 `dist/` 与 `build/`，`dist/`、`build/`、`btdeck-*.tar` 均已加入 `.gitignore`（`git ls-files` 实测 0 条跟踪记录）。

## 第三层详情

- 本分支为部署配置，通常不需要第三层方法签名详情；如需要，可对 `btdeck_startup.sh`、`btdeck.iss`、`nginx.conf` 做专项分析。
