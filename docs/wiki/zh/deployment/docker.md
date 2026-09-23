# Docker 部署

BtDeck 的 Docker Compose 部署包含一个 FastAPI 后端和一个 Nginx 前端。Compose 默认使用 v1.0.6 镜像标签，同时保留本地源码构建配置。

## 启动与更新

```bash
cp .env.example .env
docker compose up -d --build
```

使用已发布镜像时可以先拉取再启动：

```bash
docker compose pull
docker compose up -d
```

升级前先阅读对应版本的发布说明，并备份 `data/backend/config`。应用启动时会自动运行 Alembic 迁移；迁移失败时后端不会以不完整的数据库继续运行。

## 数据持久化

Compose 将后端数据映射到项目目录：

| 主机目录 | 容器目录 | 用途 |
| --- | --- | --- |
| `data/backend/data` | `/app/data` | 种子及业务数据 |
| `data/backend/logs` | `/app/logs` | 后端日志 |
| `data/backend/config` | `/app/config` | SQLite 数据库、配置和迁移状态 |
| `data/backend/backup` | `/app/backup` | 备份文件 |

这些目录包含敏感业务数据，应限制主机权限，不要提交到 Git 或公开下载。

## 生产安全配置

公网或跨网络部署必须在 `.env` 中设置：

```dotenv
DEV=false
SECRET_KEY=替换为强随机值
ALLOWED_HOSTS=https://your-domain.example
DEBUG=false
```

`DEV=false`、`SECRET_KEY` 和 `ALLOWED_HOSTS` 缺一时，后端会拒绝启动。请使用反向代理和 TLS，参考仓库中的 `deploy/nginx-tls.conf.example`。默认纯 HTTP 会让登录凭据和 token 在网络上明文传输。

## 端口与网络

- 前端对外暴露 `${BTDECK_PORT:-8080}`，容器内为 80。
- 后端在 Compose 网络内监听 5001；默认不直接映射到宿主机。
- WebSocket 由后端提供，开发环境使用 5002；生产访问路径由前端 Nginx 配置转发。
- 后端使用 SQLite 和进程内调度器，保持单 worker。多 worker 会造成数据库锁、资源准入和定时任务重复执行问题。

## 维护命令

```bash
docker compose ps
docker compose logs --tail=200 backend
docker compose restart backend
docker compose down
```

`docker compose down` 不会删除绑定的数据目录；不要使用带卷删除选项的命令，除非已经确认备份可恢复且确实要清除数据。

