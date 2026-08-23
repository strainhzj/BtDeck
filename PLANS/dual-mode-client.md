# 双模式客户端计划（服务端模式 / 伴侣客户端模式）

> **状态**：评审修订版（2026-08-23）；实现清单：`feature_list.json` 的 `v1.0.6-dual-mode-client`
>
> **目标**：安卓优先、桌面对齐，为客户端提供两种可切换模式：
> 1. **服务端模式**：完整后端 + 前端在本机运行；安卓仅定位为轻量/临时服务端。
> 2. **伴侣客户端模式**：WebView 直连已有服务器自带前端；首版保持同源，避免运行时前端版本与 API 漂移。

## 1. 已确认的产品边界

- 安卓常驻主力服务端不作为产品承诺。桌面/NAS/服务器部署仍是长期运行的推荐方案。
- 伴侣模式 MVP 是“服务器地址管理 + 健康检查 + 远程 WebView”，可脱离安卓本地 Python 服务端独立交付。
- 安卓服务端模式默认只监听 `127.0.0.1`；用户显式打开“局域网开放”后才重新绑定 LAN，并显示明文凭据暴露风险。
- 首版不做把完整前端打入 APK 后再用运行时 `baseURL` 连接远程服务器；该方案留作后续增强。
- 不依赖 F-Droid 作为分发渠道；自建预编译 Android wheel 与其构建要求存在冲突。目标渠道为 Play + GitHub Release 侧载。
- 移动 UI 按核心流程重做，不以给桌面表格叠加少量响应式 CSS 作为完成标准。

## 2. 当前仓库约束与落地修正

| 领域 | 当前事实 | 计划修正 |
|---|---|---|
| 配置与可写路径 | `CONFIG_DIR` 环境变量已经优先于默认路径；`TORRENTS_PATH` 仍可能回落到包目录 | 原生层显式注入 `CONFIG_DIR` 与 `TORRENTS_DIR`，不要仅依赖脆弱的 `is_android()` 分支；配置、数据库、种子和隔离区均落到应用私有可写目录 |
| 监听与 CORS | `HOST` 是绑定地址；`ALLOWED_HOSTS` 实际承担 CORS 来源配置，二者不是同一安全开关 | LAN 开关独立处理 bind/restart；另行生成精确 CORS 来源，不把 CORS 列表当作网络暴露控制 |
| 迁移与静态资源 | 启动迁移依赖 `alembic.ini`、`alembic/` 和模型导入；前端静态目录由 `factory` 按候选路径寻找 | APK 必须显式打包并测试 Alembic 资源、契约 JSON、frontend dist；为 Android 增加稳定的包内资源解析路径 |
| 连通性探测 | `downloader.py` 与 `initialization.py` 都直接使用 `ping3` ICMP；安卓不能假定有 raw socket 或 shell ping | 统一为按下载器端口的 TCP connect 计时；桌面 ICMP 只能作为可选优化，安卓禁止依赖系统命令 |
| Excel 导出 | `audit_service.py` 已在函数内导入 pandas，但部署依赖仍会带入 pandas/numpy | 优先用 openpyxl 直写；删除 pandas 前同步核对 requirements、部署 requirements、PyInstaller spec 和 Excel 回归 |
| Python 工具链 | 桌面 Docker/打包链仍有 Python 3.11；安卓目标为 Chaquopy Python 3.12 | 建立明确的 3.11 桌面 + 3.12 Android 兼容矩阵；不能只把 pyproject 的目标版本机械改成 3.12 |
| Monaco | 活跃任务编辑器已有动态导入，webpack plugin 仍是全局配置；“高级搜索编辑器”定位不准确 | 先测真实 chunk/首屏收益，再决定是否改 plugin 或组件，不把没有收益的改动列为门禁 |
| 主机能力 | 自定义脚本路径仍涉及 bash、PowerShell、cmd 和宿主文件系统 | 建立 Android capability matrix；脚本执行、任意宿主路径和不适用的定时能力必须显式禁用或降级，并有 API/UI 提示 |
| 远程前端 | 当前 Axios `baseURL` 是构建时环境变量，token/cookie 按 WebView origin 隔离 | 伴侣 MVP 直接加载服务器自己的前端；若未来内置前端连接远程 API，另立 runtime baseURL、CORS、版本兼容和凭据隔离任务 |

## 3. Phase 0 — 风险闸门（服务端模式必须先过）

### 0A. 依赖、Android 与 Play 可行性预审

先固定一次可审计的目标矩阵：Android API、Chaquopy/Gradle 版本、四 ABI、Python 3.12、Play 提交时间点的 target API、FGS 类型和数据处理声明。`target API 34+` 不作为验收口径，实际以提审时 Google Play 官方要求为准，并为 API 36 兼容预留。

同时完成以下决策：

- `specialUse` 只有在没有更匹配的 FGS 类型时才采用；声明 `FOREGROUND_SERVICE_SPECIAL_USE`、manifest subtype 和 Play Console 用途说明。它不是绕过后台限制或审核的通行证。
- 如果实现或实验采用 `dataSync`，必须覆盖 Android 15 面向 target 35+ 的 6 小时/24 小时预算与 `onTimeout`；不能把该限制误写成所有 FGS 类型都相同。
- 预审清单包含 Android 12+ 后台启动限制、通知权限、应用备份/恢复、Keystore、明文局域网、自签证书和 Data Safety 文案。

### 0B. `btdeck/android-wheels` 独立仓库与完整导入图验证

1. 用 GitHub Actions + `cargo-ndk` 构建固定版本、固定 hash 的 `pydantic-core` cp312 Android wheels：`arm64-v8a`、`armeabi-v7a`、`x86_64`、`x86`。
2. 使用正确的 Android wheel tag、Python ABI、NDK/API level、libc++ 链接和 wheel metadata；`cargo-ndk` 只解决 native 编译，不替代 wheel 打包与索引验证。
3. GitHub Pages 发布 PEP 503 simple index；保留 wheel hash、构建日志、SBOM/license 和源码/工具链版本。
4. 先跑最小 Chaquopy 17 FastAPI + pydantic hello world，再把 BtDeck 的完整 import graph 放入四 ABI 矩阵；至少覆盖 `pydantic/pydantic-core` 配对及 `bcrypt`、`regex`、`Pillow`、`pycryptodomex`、`gmssl` 等 ABI 敏感依赖。
5. 在真实设备或等效环境验证 16 KB page-size 兼容、冷启动、升级安装和 wheel 缺失时的明确失败信息。

**闸门**：所有 ABI 均能安装、导入、启动 `/health/live`，并完成一次数据库迁移和前端静态资源加载，才允许进入安卓服务端工程。否则暂停本地服务端，先交付伴侣模式，并重估 Termux/推迟/减少后端能力等备选方案。

参考：[Chaquopy 版本兼容矩阵](https://chaquo.com/chaquopy/doc/current/versions.html)、[自定义 wheels](https://chaquo.com/chaquopy/doc/current/faq.html)、[Chaquopy wheel 索引说明](https://github.com/chaquo/chaquopy/blob/master/server/pypi/README.md)。

## 4. Phase 1 — 后端平台无关改造与能力分级

这些工作可在没有 Android 工程的情况下开始，全部执行现有后端/前端 DoD。

1. **统一下载器探测**：新增可复用的 TCP probe，尊重下载器 host/port；桌面可在权限允许时先 ICMP，失败回退 TCP；安卓不调用 `ping` 子进程。覆盖连接成功、拒绝、超时、`PermissionError` 和两个现有调用链的回归测试。
2. **配置与路径**：保留 `CONFIG_DIR` 环境变量优先语义；补齐 `TORRENTS_DIR`/隔离区等所有可写根目录；本地服务默认 loopback。LAN 开关变化必须触发受控重绑或服务重启，不能只改数据库配置而继续监听旧地址。
3. **依赖瘦身**：确认全仓零 import、部署 spec 和 transitive dependency 后再删除 `sympy`、`common`；将 Excel 导出改为 openpyxl 直写并移除 pandas/numpy 的打包入口；保留一套 Excel 内容回归。
4. **工具链矩阵**：明确桌面 Python 3.11 与 Android Python 3.12 的支持边界，更新 CI/打包说明及真正需要的类型检查配置；不破坏现有桌面发行版。
5. **Android 打包契约**：补充包内 `alembic.ini`、迁移目录、contracts JSON、frontend dist 的启动测试；校验 `factory`、migration、`CONFIG_DIR`、`TORRENTS_DIR` 在 frozen/package 环境中的解析。
6. **前端资源审计**：以构建产物大小和首屏加载数据为依据处理 Monaco；当前活跃任务编辑器已懒加载，不预设“高级搜索编辑器”存在。
7. **能力矩阵**：标注自定义脚本、宿主任意路径、SAF 文件选择、下载/上传、通知、定时任务和本地服务的 Android 支持级别；不支持项在 API、设置页和任务列表一致降级。

## 5. Phase 2 — 伴侣模式 MVP（可独立先行）

- 首启向导：运行本机服务 / 连接已有服务器；支持重新选择和清晰的离线、认证失败、版本不兼容状态。
- 服务器地址管理：只允许 `http/https` URL，保存显示名、最近健康状态和最后连接时间；调用 `/health/live`、`/health/ready` 做连接测试。
- WebView 直接加载远程服务器自带前端，保持同源，首版不复制前端 API/store 到 APK 内。
- 每个服务器 profile 使用独立 WebView cookie/storage；切换地址时清除或隔离 access/refresh token，不能跨服务器复用凭据。
- 明文 HTTP 仅按用户选择的私有 LAN 主机放行，不做全局 cleartext；自签证书必须由用户显式信任并记录范围，禁止无条件 `handler.proceed()`。
- 增加加载超时、重试、返回/退出、重新测试、忘记服务器和服务端版本提示；不以 UA 自动识别作为唯一模式依据。

## 6. Phase 3 — 安卓本地服务端壳工程

- Chaquopy 17 + Python 3.12；程序化启动单 worker Uvicorn，启动顺序为目录准备 → 配置 → Alembic fail-fast → `/health/live` 握手。
- `CONFIG_DIR`、`DATABASE_PATH`、`TORRENTS_DIR` 明确指向 app-private writable storage；首次启动、升级、迁移失败和回滚均有可读错误。
- 服务端模式仅在用户操作后启动；Foreground Service 提供常驻通知、状态、停止/重启操作和 notification channel。Android 13+ 通知权限、Android 12+ 后台启动限制、进程被杀重启策略和 OEM 电池策略均加入测试，不承诺用 FGS 消除 Doze 漂移。
- 实际采用 `specialUse` 时完成 manifest subtype、Play 声明和人工审查材料；不把 `specialUse` 当作永久后台保证。
- LAN 开关默认关闭，打开前展示威胁模型；绑定改变要重启服务并更新 WebView 目标。局域网 HTTP 不得被误认为安全传输，后续应评估 HTTPS/配对码/一次性 token。
- Android 私有存储、SAF、下载目录、备份规则和 Keystore 单独验收；配置 YAML、JWT/refresh token、下载器凭据和加密密钥不得随意进入系统备份或日志。

## 7. Phase 4 — 移动 UI 与桌面对齐

### 移动 M1/M2

- M1：底部 Tab、登录、仪表盘、卡片式种子列表、种子详情与常用操作、通知中心。
- M2：高级搜索、查询模板、回收站、日志、下载器高级设置等；不支持能力显示明确降级，必要时回退桌面视图并保留可用的横向滚动。
- Vue 2 Options/class 风格、现有 API 响应信封、`app.state.store` 连接缓存和现有 api/store 约束不变；新增移动组件要有组件/契约测试。

### 桌面

- 现有 PyInstaller exe 继续作为服务端模式，默认行为不变。
- 启动器增加同一套模式选择；桌面伴侣模式优先打开浏览器/内嵌窗口连接远程服务器，复用 Phase 2 的 profile、健康检查和版本提示。

## 8. Phase 5 — 发布与验收

- Play：按提审时官方 target API 要求构建，配置 Play App Signing、隐私政策、Data Safety、FGS 类型/用途申报和明文流量说明；GitHub Release 提供通用 APK 与按 ABI 选择说明。
- 包体：用 `bundletool` 记录 AAB/APK 的真实大小、ABI 分布和 native `.so` 清单，不使用 60–80 MB 估算作为验收。
- Android 自动化/设备验收：API 24 最低启动、Android 14/15/16 代表设备、四 ABI、冷启动、迁移升级、进程杀死、屏幕旋转、Doze、通知权限、FGS 停止、存储权限、HTTP/HTTPS/坏证书、LAN 开关和服务端版本不匹配。
- 既有 DoD：后端 mypy/black/flake8/pytest，前端 typecheck/lint/Jest/build，根 `./init.sh`；新增 Gradle lint/test、wheel import matrix、bundletool 和 release artifact 校验。
- 只有伴侣模式和本地服务端模式均能从首启向导进入、退出、恢复，且失败路径可解释，才将任务标记 done。

## 9. 风险登记

| 风险 | 等级 | 缓解/退出条件 |
|---|---|---|
| pydantic-core 或其他 native wheel 缺失 | 高 | Phase 0 完整导入图门禁；失败则伴侣模式先行，服务端模式重估 |
| `specialUse` 被 Play 拒绝或系统行为不稳定 | 高 | Phase 0 预审；无可接受声明时不承诺常驻服务端 |
| Doze、FGS 生命周期和 target API 变化 | 高 | 以临时服务端定位；用户可见停止/恢复；设备矩阵实测 |
| 局域网明文泄露凭据 | 高 | LAN 默认关闭、按主机放行、风险提示；优先评估 HTTPS/配对 |
| Android 存储/备份泄露配置密钥 | 高 | app-private + Keystore + backup 规则 + 日志审计 |
| 前端远程版本、cookie 和 CORS 漂移 | 中 | MVP 使用远程同源 WebView；内置前端另立 runtime baseURL 契约 |
| APK 体积与 ABI 兼容性 | 中 | 四 ABI 真实构建、bundletool 报告、16 KB page-size 验证 |

**登记原则**：`feature_list.json` 只在对应阶段真正实现并通过证据后改为 `in-progress/done`；本计划和清单条目的写入不代表 Phase 0 已通过。
