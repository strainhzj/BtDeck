# android/app — 伴侣模式凭据与会话

> 2026-08-27 源码与构建链实测。Android 端只保存 profile 元数据和加密凭据，不包含本地 Python 服务端。

## 构建入口

- `deploy/build-android.bat`：从仓库根目录可直接调用；默认构建严格版与 LAN 明文版，
  每个变体先跑 `:app:testDebugUnitTest`，再 assemble、复制到 `android/dist/`，并执行
  `apksigner`/`aapt2` 产物校验。`--strict-only` 与 `--lan-only` 可单独构建变体。
- `build-packages.bat`：根目录 EXE + APK 统一入口；`--android`、
  `--android-strict-only`、`--android-lan-only` 可选择 Android 目标。
- 工具链路径支持 `BTDECK_GRADLE`、`BTDECK_JAVA_HOME`、`ANDROID_SDK_ROOT`，
  SDK 版本与 `android/local.properties` 保持一致。

| 文件 | 关键入口（当前行号） | 职责 |
|------|----------------------|------|
| `app/src/main/java/com/btdeck/companion/data/ServerProfile.kt` | `ServerProfile:14` | profile JSON 增加 username；旧 JSON 缺字段按空字符串兼容 |
| `app/src/main/java/com/btdeck/companion/data/CredentialVault.kt` | `CredentialVault:21`、`buildAutoLoginScript:94` | Android Keystore AES-GCM 密文 + 独立凭据 SharedPreferences；同源登录脚本与 TOTP 临时 prompt |
| `app/src/main/java/com/btdeck/companion/ui/ServerListActivity.kt` | `ServerListActivity:38`、`showProfileActions:116`、`showAddDialog:134` | 用户名/密码录入、清除凭据/忘记服务器操作 |
| `app/src/main/java/com/btdeck/companion/ui/WebViewActivity.kt` | `WebViewActivity:43`、`prepareSession:132`、`maybeAutoLogin:196` | 等待异步 CookieManager 清理后加载 profile；有凭据时恢复前端会话 |
| `app/src/main/java/com/btdeck/companion/net/TrustScope.kt` | `sha256Fingerprint:22` | 自签证书指纹＝公钥 SPKI 的 SHA-256（RFC 7469 pin 语义；此前按整证书 DER 与 OkHttp 校验永不匹配，2026-09-04 设备级实证修复） |
| `app/src/main/java/com/btdeck/companion/data/HealthClient.kt` | `probe`、`pinnedClient`、`CapturingTrustManager` | 自签钉扎：全信 TrustManager 捕获证书链 + 握手后手动 SPKI pin 比对（OkHttp CertificatePinner 与自定义 SSLSocketFactory 不兼容，链清洗为空；2026-09-04） |
| `app/src/main/res/values-v35/themes.xml` | `windowOptOutEdgeToEdgeEnforcement` | targetSdk 35 强制 e2e 致 AppCompat ActionBar 不下推内容（列表首行画进工具栏，生产路径实证）；退出恢复传统布局，API 36 起出口移除需迁移 insets 自处理（2026-09-04） |
| `app/src/androidTest/java/com/btdeck/companion/`（CompanionOfflineUiTest/SelfSignedCert/ProfileIsolation + TinyLoopbackServer/CompanionTestState） | 设备级 UI 验收 | 离线覆盖层/自签证书信任与换签/多 profile cookie+storage+凭据隔离/自动登录；自持回环 HTTP(S) 假后端（双 PKCS12 证书），Espresso+ActivityScenario（2026-09-04） |
| `app/src/test/java/com/btdeck/companion/ServerProfileTest.kt` | `ServerProfileTest:8` | username 元数据与旧构造器默认值回归 |

## 约束

- `android:allowBackup="false"` 与 Keystore 绑定保证凭据不会通过系统备份迁移。
- CookieManager 是进程级单例，profile 切换必须等待 `removeAllCookies` 回调；WebStorage 与旧 token 不能跨 profile 复用。
- 不使用 `addJavascriptInterface` 暴露密码；脚本只在同源页面短暂执行登录并写入前端现有 cookie。
