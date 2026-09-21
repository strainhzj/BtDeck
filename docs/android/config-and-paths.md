# 配置、可写路径与网络暴露语义（Phase 1.2）

> 对应计划: `PLANS/dual-mode-client.md` 第 2 节"配置与可写路径"、"监听与 CORS"
> 两行与第 4 节条目 2。
> 本文是 Android 壳工程（Phase 3）与桌面启动器共享的**注入契约**。

## 1. 环境变量注入契约（单一事实来源）

所有可写根目录由**原生层/启动器显式注入环境变量**，后端不猜测运行环境：

| 环境变量 | 消费点 | 语义 |
|---|---|---|
| `CONFIG_DIR` | `Settings.CONFIG_PATH` 及派生路径 | 配置根：`config.yaml`、`app.db`（默认）、`temp/`、`logs/`、`cookies/` |
| `DATABASE_PATH` | `Settings.DATABASE_PATH`、`alembic/env.py` | 显式数据库文件路径；优先级高于 `CONFIG_DIR/app.db` 推导 |
| `TORRENTS_DIR` | `Settings.TORRENTS_PATH` | `.torrent` 备份/种子文件根目录 |
| `SECRET_KEY` | `Settings.SECRET_KEY` | JWT 签名密钥（生产必须显式） |
| `ALLOWED_HOSTS` | `Settings.ALLOWED_HOSTS` | **CORS 来源白名单**（JSON 数组格式，`List[str]` 校验器要求） |
| `HOST` | `Settings.HOST`（uvicorn bind） | **绑定地址**，见第 3 节 |

优先级语义（已在 `app/core/config.py` 实现并测试锁定）：

```text
CONFIG_PATH    = CONFIG_DIR 环境变量 → frozen(exe 同级 config/) → docker(/config) → 仓库 config/
DATABASE_PATH  = DATABASE_PATH 环境变量 → CONFIG_PATH/app.db
TORRENTS_PATH  = TORRENTS_DIR 环境变量 → frozen(exe 同级 torrents/) → docker(/torrents) → 仓库 torrents/
```

**Android 注入值**（Phase 3）：三者均指向 app-private 可写目录
（`context.getFilesDir()` 派生）。这些目录只用于 BtDeck 自身配置、数据库、日志和
用户主动选择的种子文件；Android 主服务端不把它们当作下载器主机目录，
不创建/扫描 `.btdeck_quarantine`，也不执行路径映射、孤儿清理或下载器种子备份。
历史路径配置仍保留在数据库中，切换到桌面/NAS 主服务端后再生效。

**禁止**：新增任何"检测到 Android 就改路径"的静态分支；路径解析只认环境变量
与上述回落序。

## 2. 可写根目录清单（打包/备份/迁移验收基线）

| 根 | 创建者 | 内容 | 进系统备份？ |
|---|---|---|---|
| `CONFIG_DIR` | 启动器 | config.yaml（含 jwt_secret_key）、app.db、temp、logs、cookies | Android 默认排除（Phase 3 backup rules） |
| `TORRENTS_DIR` | 启动器/用户主动种子文件操作 | 本地上传/下载的 `.torrent` 文件 | 排除（可重建） |
| 各扫描根下 `.btdeck_quarantine/` | 桌面/NAS 孤儿清理任务 | 待删孤儿文件；Android 主服务端不创建 | 排除 |
| `frontend_dist` | 打包资源（只读） | SPA 静态文件 | 不适用 |

## 3. HOST（bind）与 ALLOWED_HOSTS（CORS）不是同一开关

| 变量 | 作用层 | 改变的攻击面 | 谁改它 |
|---|---|---|---|
| `HOST` | TCP bind 地址（uvicorn） | 网络可达性（loopback vs LAN/全部接口） | LAN 开关（重启服务生效） |
| `ALLOWED_HOSTS` | CORS `Access-Control-Allow-Origin` | 浏览器跨源凭据携带 | 部署配置；精确来源，禁 `*`（生产校验强制） |

规则：

1. **把 CORS 列表当作网络暴露控制是错误的**——监听地址由 `HOST` 决定。
2. Android 服务端模式默认 `HOST=127.0.0.1`；用户显式打开"局域网开放"后
   由壳工程**重启服务**并绑定 LAN 地址（受控重绑，不允许只改数据库配置而
   继续监听旧地址），同时展示明文凭据暴露风险提示。
3. LAN 打开后应按访问来源生成**精确** CORS origin（如
   `http://192.168.x.x:5001`），沿用现有 JSON 数组格式。
4. 桌面发行版行为不变：`desktop_main.py` 默认回环；Docker compose 由
   `HOST`/`ALLOWED_HOSTS` 环境变量显式配置。
5. 局域网明文 HTTP 不得被当作安全传输；HTTPS/配对码/一次性 token 的评估
   留待计划第 6 节 Phase 3 后续项。

## 4. 变更记录

- 2026-08-23：初版（Phase 1.2）。`CONFIG_DIR`/`DATABASE_PATH`/`TORRENTS_DIR`
  的优先级语义与回归测试同步落地（`tests/core/test_writable_roots.py`）。
- 2026-09-07：明确 Android 主服务端与下载器远端文件系统隔离；本地私有目录不再被误解释为下载器路径，路径映射/孤儿/备份/转移/三级删除由主机能力矩阵硬禁用。
