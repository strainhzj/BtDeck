# BtDeck 双模式客户端 App（dual-mode-client Phase 2 伴侣模式 + Phase 3 本机服务端）

> 对应计划：`../PLANS/dual-mode-client.md` 第 5/6 节。

## 功能范围

### 伴侣模式（Phase 2）

- 首启向导：连接已有服务器 / 运行本机服务，可重跑。
- 服务器 profile：显示名、http/https URL、用户名、最近健康状态、最后连接时间、健康检查到的服务端版本；旧 profile 缺少用户名时按空值兼容。
- 健康检查：`GET /health/live` → `GET /health/ready`（读取 `data.version`）。
- WebView：远程同源直连服务器自带前端，站内导航继续、外链交系统浏览器；加载超时/失败可重试；副标题展示版本与就绪状态。
- 凭据保存：用户名随 profile 保存；密码进入 `CredentialVault`，由 Android Keystore AES-GCM 加密后写入独立 SharedPreferences，manifest `allowBackup=false`。
- 会话恢复：切换 profile 等待异步 cookie 清理完成后再加载；保险库有密码时首屏同源登录脚本自动恢复。
- 自签证书：显式指纹信任（SHA-256 记录在该 profile 作用域），绝不无条件 proceed。

### 本机服务端模式（Phase 3，Chaquopy 17 + Python 3.12）

- 向导"运行本机服务"：ABI 检测（仅 64 位）→ 通知权限请求（13+，拒绝不阻断）→
  确认对话框（LAN 开关默认关 + 威胁模型）→ `ServerService`（Foreground
  specialUse）→ Python `btdeck_server` 启动链（目录准备 → 迁移 fail-fast →
  深导入 → uvicorn 单 worker → /health/live 自检）→ 就绪后写入本机 profile
  进 WebView；失败按阶段（env/migration/import/bind/health）归因展示。
- 服务常驻通知：状态/版本/地址 + 停止按钮；`START_STICKY` 进程被杀后自动重建。
- 数据锚定：`CONFIG_DIR`/`DATABASE_PATH`/`TORRENTS_DIR` 全部在应用私有目录
  `filesDir/btdeck-server/` 下（空库自动迁移到 head，Alembic 失败拒绝启动）。
- 端口：动态分配优先复用上次端口（LAN 场景其它设备免追端口）。
- 2FA 二维码接口暂不可用（pillow ANDROID-DROP，登记 android-wheels gate.md）；
  后端 cuser 已延迟导入 PIL，完整启动链不受影响。

## 构建与 staging（服务端模式）

```bat
:: 1. 前端先构建（staging 依赖 frontend/dist）
cd frontend && npm run build

:: 2. staging 后端到 android 源集（gitignored）
C:/software/python/python.exe android/tools/stage-server.py

:: 3. 构建（默认含服务端模式；JDK 21 + Gradle 8.9，或用 deploy\build-android.bat）
set JAVA_HOME=C:/software/android-build-env/jdk-21.0.2
C:/software/android-build-env/gradle-8.9/bin/gradle.bat :app:assembleDebug
:: 纯伴侣模式快速构建：-Pbtdeck.server=off
:: LAN 明文变体：-Pbtdeck.lanCleartext=true
```

- Python 依赖经 `--extra-index-url` 指向 android-wheels 索引
  （`https://strainhzj.github.io/android-wheels/simple/`，自建 Android wheel）。
- **改 requirements 后必须 `--rerun-tasks` 并清 `%LOCALAPPDATA%/pip/cache`**
  （gradle 不追踪 `-r` 文件内容变化，wheels 仓实证）。
- **Chaquopy pip 空配置坑（本仓实证）**：pip 块内没有任何 `install()` 时，
  整个 pip 配置（含 `options()`）被判空跳过——requirements-*.imy 只有 22 字节
  空头。tzdata 的 `install()` 同时承担生效锚点，勿删。

## 明文 HTTP 策略（双层防线 + 回环豁免）

1. **构建层（默认安全）**：`network_security_config.xml` cleartext 全局禁止，
   仅 loopback 放行（本机服务端需要）。LAN 明文需 `-Pbtdeck.lanCleartext=true`。
2. **应用层（始终生效）**：`net/LanHostPolicy.kt` —— http URL 必须私有主机；
   **回环（127/8、::1、localhost）豁免明文确认**（无窃听面，本机服务端固定
   形态）；其余私有主机仍需 profile 记录明文风险确认；公网一律拒绝。

LAN 访问开关（服务端绑 0.0.0.0）默认关闭，打开前展示威胁模型；绑定变化
自动完整重启服务端。注意：其它设备访问本机服务端不受本机 NSC 约束——
这正是威胁模型弹窗存在的原因（明文、无认证配对，登记计划风险表）。

## ABI 边界

Chaquopy 15.0.1 起 Python 3.12 仅支持 arm64-v8a / x86_64（无 32 位 ABI，
android-wheels versions.env 同源决策）。**32 位设备无法安装本 app**；
Play AAB 按 ABI 分发不受影响。运行时 `ServerService.isAbiSupported()` 兜底提示。

## 测试

- JVM 单测（`:app:testDebugUnitTest`，28 用例）：LanHostPolicy（含回环豁免）、
  Hosts、ServerProfile、ServerStates 契约、LocalServerProfile、HealthClient 钉扎。
- AVD 仪表化（`:app:connectedDebugAndroidTest`）：`LocalServerAndroidTest`
  start→迁移→健康握手→SPA 首页→停机→重启（端口复用）。
- 向导/FGS/通知/进程杀死恢复：手动流程实录（Phase 5 设备矩阵扩展）。

## 结构

```text
app/src/main/java/com/btdeck/companion/
├── CompanionApp.kt            # WebView CookieManager 初始化
├── data/                      # profile 模型/存储/健康检查/凭据保险库
├── net/                       # 明文准入策略（回环豁免）/证书指纹
├── server/                    # Phase 3 本机服务端
│   ├── ServerService.kt       # FGS specialUse：Python 生命周期+轮询+通知
│   ├── ServerStates.kt        # 状态 JSON 契约与文案映射（纯 JVM 可测）
│   ├── LocalServerProfile.kt  # 本机 profile 构建（固定 id + 动态端口）
│   └── LocalServerState.kt    # 进程级状态镜像 + 偏好持久化
├── ui/
│   ├── WizardActivity.kt      # 首启向导（模式二选一 + 本机服务端全流程）
│   ├── ServerListActivity.kt  # 服务器管理（本机 profile 未运行引导）
│   └── WebViewActivity.kt     # 远程/本机同源 WebView
└── util/Hosts.kt              # URL 解析/主机分类/回环判定（纯 JVM 可测）
android/server-python/btdeck_server.py  # Python 运行体源码（staging 拷入源集）
android/tools/stage-server.py           # staging 脚本（backend → src/server）
app/src/server/                         # staged 产物（gitignored）
```

## 已知边界

- 自签 HTTPS 的健康检查（OkHttp）在指纹未注入 custom TrustManager 前显示"证书错误"
  （WebView 内浏览不受影响）。
- 升级安装（旧库增量迁移）未验证（wheels 仓登记遗留项，Phase 5 演练）。
- APK 体积：debug 90.4MB（Python 运行时+32 依赖+前端 dist）；release 与
  bundletool 精算留 Phase 5。

## data 包重建记录（2026-08-24）

`a2f4e72` 首次提交时 `data/` 包三个文件（ServerProfile/ServerProfileStore/HealthClient）
漏入库，工作区副本后丢失，导致干净检出无法编译。本日依据调用方
（ServerListActivity/WebViewActivity）与 README 契约重建并实证（AVD 实测添加服务器
→ 测试连接就绪 → WebView 加载登录页）。桌面测试环境与 SOP 见
`../docs/android/desktop-testing.md`。
