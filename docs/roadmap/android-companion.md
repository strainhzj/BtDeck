# android/app — 伴侣模式凭据与会话

> 2026-08-26 源码实测。Android 端只保存 profile 元数据和加密凭据，不包含本地 Python 服务端。

| 文件 | 关键入口（当前行号） | 职责 |
|------|----------------------|------|
| `app/src/main/java/com/btdeck/companion/data/ServerProfile.kt` | `ServerProfile:14` | profile JSON 增加 username；旧 JSON 缺字段按空字符串兼容 |
| `app/src/main/java/com/btdeck/companion/data/CredentialVault.kt` | `CredentialVault:21`、`buildAutoLoginScript:94` | Android Keystore AES-GCM 密文 + 独立凭据 SharedPreferences；同源登录脚本与 TOTP 临时 prompt |
| `app/src/main/java/com/btdeck/companion/ui/ServerListActivity.kt` | `ServerListActivity:38`、`showProfileActions:116`、`showAddDialog:134` | 用户名/密码录入、清除凭据/忘记服务器操作 |
| `app/src/main/java/com/btdeck/companion/ui/WebViewActivity.kt` | `WebViewActivity:43`、`prepareSession:132`、`maybeAutoLogin:196` | 等待异步 CookieManager 清理后加载 profile；有凭据时恢复前端会话 |
| `app/src/test/java/com/btdeck/companion/ServerProfileTest.kt` | `ServerProfileTest:8` | username 元数据与旧构造器默认值回归 |

## 约束

- `android:allowBackup="false"` 与 Keystore 绑定保证凭据不会通过系统备份迁移。
- CookieManager 是进程级单例，profile 切换必须等待 `removeAllCookies` 回调；WebStorage 与旧 token 不能跨 profile 复用。
- 不使用 `addJavascriptInterface` 暴露密码；脚本只在同源页面短暂执行登录并写入前端现有 cookie。
