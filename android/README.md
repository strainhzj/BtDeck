# BtDeck 伴侣模式 App（dual-mode-client Phase 2 MVP）

> 对应计划：`../PLANS/dual-mode-client.md` 第 5 节。本工程**不含 Python**
> （服务端模式是 Phase 3 的独立 Chaquopy 工程）。

## 功能范围（MVP）

- 首启向导：连接已有服务器（伴侣模式）/ 运行本机服务（Phase 3 前给明确"未提供"状态）；可重跑。
- 服务器 profile：显示名、http/https URL、用户名、最近健康状态、最后连接时间、健康检查到的服务端版本；旧 profile 缺少用户名时按空值兼容。
- 健康检查：`GET /health/live` → `GET /health/ready`（读取 `data.version`，Phase 2 后端已加）。
- WebView：远程同源直连服务器自带前端，站内导航继续、外链交系统浏览器；加载超时/失败可重试；副标题展示版本与就绪状态。
- 凭据保存：用户名随 profile 保存；密码进入 `CredentialVault`，由 Android Keystore AES-GCM 加密后写入独立 SharedPreferences，manifest `allowBackup=false`。密码不进入 profile JSON，也不通过 `addJavascriptInterface` 暴露。
- 会话恢复：WebView CookieManager 是进程级单例，**切换 profile 会等待异步 cookie 清理完成后再加载**；若保险库有密码，首屏同源登录脚本自动恢复 access/refresh cookie，TOTP 只在需要时临时询问、不落盘。
- 自签证书：绝不无条件 `handler.proceed()`——指纹未记录时弹风险说明，用户确认后把 SHA-256 指纹记在该 profile（作用域=该服务器地址），证书更换需重新确认。
- 明文 HTTP：双层防线见下。

## 明文 HTTP 策略（双层防线）

Android NSC 是构建期配置，无法运行时按主机开闭、也不支持 CIDR。因此：

1. **构建层（默认安全）**：`network_security_config.xml` cleartext 全局禁止，仅
   loopback 放行（Phase 3 本机服务端需要）。LAN 明文需要显式构建：
   `./gradlew assembleDebug -Pbtdeck.lanCleartext=true`（切换到
   `network_security_config_lan.xml`，cleartext 基线放行）。
2. **应用层（始终生效）**：`net/LanHostPolicy.kt` —— http URL 必须同时满足
   "主机是私有字面量（127/8、RFC1918、169.254/16、fc00::/7、fe80::/10、*.local、
   localhost）" + "该 profile 已记录明文风险确认"；公网主机一律拒绝明文
   （HTTPS 不受限）。添加服务器与每次打开 WebView 前都校验。

DNS 名称指向内网主机但非 *.local 的场景按公网处理（fail-closed）。

## 构建（JDK 17/21 + Android SDK；2026-08-27 脚本化验证通过）

推荐从仓库根目录使用脚本；脚本会独立解析项目路径、检查 Gradle/JDK/SDK，
运行 `:app:testDebugUnitTest`，构建两个变体后复制到 `android/dist/`，并执行
`apksigner verify` 与 `aapt2 dump badging`：

```bat
deploy\build-android.bat
deploy\build-android.bat --strict-only
deploy\build-android.bat --lan-only
build-packages.bat --android
```

工具链不在默认位置时，可设置 `BTDECK_GRADLE`、`BTDECK_JAVA_HOME`、
`ANDROID_SDK_ROOT`（或编辑 `android/local.properties`）。APK 文件名版本可用
`BTDECK_APK_VERSION` 覆盖。

```bash
cd android
gradle wrapper --gradle-version 8.9   # 首次生成 wrapper（wrapper 二进制不入库）
./gradlew :app:testDebugUnitTest      # LanHostPolicy/Hosts 策略单测（纯 JVM，11 用例）
./gradlew :app:assembleDebug
# LAN 明文构建（自用/侧载，manifest 切换到 network_security_config_lan.xml）：
./gradlew :app:assembleDebug -Pbtdeck.lanCleartext=true
```

已验证的工具链组合（2026-08-23 首次编译）：

| 组件 | 版本 | 说明 |
|---|---|---|
| AGP / Kotlin | 8.7.3 / 2.0.20 | AGP 8.5 不支持 compileSdk 35，首次验证时升级 |
| Gradle | 8.9 | AGP 8.7 的最低要求 |
| JDK | 21（IntelliJ JBR） | 17+ 均可 |
| SDK | platforms;android-35 + build-tools;35.0.0 | |

首次验证结论：`:app:testDebugUnitTest` 11 用例全绿；`:app:assembleDebug`
产出 app-debug.apk（约 6.0 MB，debug 签名）；两个 NSC 构建变体经
`aapt2 dump xmltree` 实证——默认变体 manifest 指向
`network_security_config`（严格），`-Pbtdeck.lanCleartext=true` 变体指向
`network_security_config_lan`。向导页副标题会标明当前构建能力
（BuildConfig.LAN_CLEARTEXT_BUILD）。

测试用 APK 已按变体命名输出到 `android/dist/`（不入库）：

- `btdeck-companion-0.1.0-mvp-strict-debug.apk`——默认严格版：局域网 http
  会被系统拦截（`ERR_CLEARTEXT_NOT_PERMITTED`，属预期防线）
- `btdeck-companion-0.1.0-mvp-lan-cleartext-debug.apk`——LAN 明文版：
  供局域网 http 服务器测试；应用层 LanHostPolicy 仍强制"私有主机 + 显式
  风险确认"，公网明文依旧拒绝

## 结构

```text
app/src/main/java/com/btdeck/companion/
├── CompanionApp.kt            # WebView CookieManager 初始化
├── data/
│   ├── ServerProfile.kt       # profile 模型（含信任指纹/明文同意/健康状态，JSON 序列化）
│   ├── ServerProfileStore.kt  # SharedPreferences 持久化（allowBackup=false，不进系统备份）
│   └── HealthClient.kt        # /health/live + /health/ready + 版本（OkHttp）
├── net/
│   ├── LanHostPolicy.kt       # 明文准入策略（纯 JVM 可测）
│   └── TrustScope.kt          # 自签证书 SHA-256 指纹
├── ui/
│   ├── WizardActivity.kt      # 首启向导（模式二选一）
│   ├── ServerListActivity.kt  # 服务器管理（添加/测试/长按忘记/重跑向导）
│   └── WebViewActivity.kt     # 远程同源 WebView（隔离/超时/重试/自签流程/版本提示）
└── util/Hosts.kt              # URL 解析与私有主机判定（纯 JVM 可测）
app/src/test/java/com/btdeck/companion/LanHostPolicyTest.kt   # 策略行为锁定
```

## 已知边界（MVP）

- 自签 HTTPS 的**健康检查**（OkHttp）不信任 WebView 侧记录的指纹，显示"证书错误"
  —— WebView 内浏览不受影响；后续可把指纹注入 OkHttp 的 custom TrustManager。
- 明文 LAN 需 `-Pbtdeck.lanCleartext=true` 构建（默认构建里 WebView 会报
  `ERR_CLEARTEXT_NOT_PERMITTED`，属预期防线）。
- 已编译验证 + JVM 单测通过；**仪表化测试与真机验收**（Android 13 通知、Doze、
  四 ABI、真机 WebView 行为）在 Phase 5 统一执行。

## data 包重建记录（2026-08-24）

`a2f4e72` 首次提交时 `data/` 包三个文件（ServerProfile/ServerProfileStore/HealthClient）
漏入库，工作区副本后丢失，导致干净检出无法编译。本日依据调用方
（ServerListActivity/WebViewActivity）与 README 契约重建：

- 接口形状与提交信息描述一致（构造参数、字段可变性、`Report(state, version, detail)`）；
- 重建后 `:app:assembleDebug` + `:app:testDebugUnitTest` 全部通过，并在 AVD
  （Pixel 6 / API 35）实测：添加服务器（明文确认复选框按策略出现）→ 测试连接
  显示 `就绪 / v1.0.5 · 服务就绪` → WebView 加载出 BtDeck 移动版登录页；
- 桌面测试环境与 SOP 见 `../docs/android/desktop-testing.md`。
