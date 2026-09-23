# 快速开始

本文带你用 Docker 启动一套可访问的 BtDeck。首次部署建议先在局域网完成验证，再配置域名和 TLS。

## 前置条件

- 已安装 Docker Engine 和 Docker Compose v2。
- 主机可以访问下载器的 Web API；BtDeck 容器与下载器之间的网络路径必须互通。
- 生产环境准备一个强随机 `SECRET_KEY`，并确定允许访问的域名或地址。

## Docker 启动

在项目根目录执行：

```bash
git clone https://github.com/strainhzj/BtDeck.git
cd BtDeck
cp .env.example .env
docker compose up -d --build
```

默认通过 `http://localhost:8080` 访问前端。宿主机端口可以在 `.env` 中用 `BTDECK_PORT` 修改。

首次启动会准备配置目录并执行数据库迁移。登录后请立即修改初始化密码，并为每个下载器执行连接测试。Wiki 不保存任何初始密码、密钥或真实地址。

检查容器状态：

```bash
docker compose ps
docker compose logs -f backend
```

后端就绪检查在容器内为 `http://localhost:5001/health/ready`；前端容器的健康检查为 `/health`。如果后端尚未就绪，前端服务会等待其健康检查通过后再启动。

## 本地开发

本地开发需要 Python 3.12+、Node.js 22.23.2（22.x）和 npm。后端与前端分别启动：

```bash
# 后端
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001
```

另开终端：

```bash
cd frontend
npm ci
npm run serve
```

开发环境的默认地址为：

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://localhost:8080` |
| API | `http://localhost:5001` |
| API 文档 | `http://localhost:5001/docs` |
| WebSocket | `ws://localhost:5002` |

应用启动时会自动执行迁移。SQLite 场景只运行一个后端 worker；不要通过增加 worker 数量来扩展服务。

## 第一次验证

1. 打开前端并完成登录与改密。
2. 在“下载器”页面添加 qBittorrent 或 Transmission，填写可从后端访问的地址、端口和凭据。
3. 执行连接测试并等待首次同步完成。
4. 在仪表盘确认下载器在线、种子数量和速度可见。
5. 再配置查询模板、通知和移动访问等高级能力。

如果第 2 步失败，先确认下载器的 Web API 已启用、容器能解析其地址，并查看后端日志中的结构化错误码。

