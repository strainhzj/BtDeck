# Play 发布材料与包体报告（dual-mode-client Phase 5 / task .7）

> 对应计划：`PLANS/dual-mode-client.md` 第 8 节。本文件汇集 Play Console 申报
> 材料、签名策略、明文流量说明与 bundletool 实测包体数据（不使用估算作验收）。
> 实际 Console 上传/人工审查需要开发者账号操作，属本机之外的边界。

## 1. 发布形态

| 渠道 | 形态 | 签名 | 说明 |
|---|---|---|---|
| Google Play | AAB（`app-release.aab`） | Play App Signing | 按设备 ABI/语言拆分下发；target API 以提审时官方要求为准（当前构建 compileSdk/target 35） |
| GitHub Release | 通用 APK（bundletool universal 或 assembleRelease 产物） | 本地自签 keystore | 见 §6 按 ABI 选择说明；32 位设备不可安装（见 §7） |

## 2. 签名策略

- **本地发布 keystore**：`android/release.keystore`（gitignored，不入库），
  凭据经 `android/local.properties` 的 `RELEASE_*` 四键注入（同样 gitignored）。
  build.gradle.kts 缺凭据时退化为无签名 release——CI 无密钥构建不阻断。
- **Play App Signing**（上传时执行，本机无法代做）：
  1. Play Console → 设置 → 应用完整性 → 加入 Play App Signing；
  2. 上传密钥（upload key）另生成一份专用 keystore（**不要**复用 GitHub Release 的）；
  3. 本地 keystore 丢失不影响 Play 分发（Play 持有分发密钥）；GitHub Release
     渠道丢失 keystore 则无法同身份升级，需备份。
- 证书指纹（当前 GitHub Release keystore，2026-08-30 实测）：
  SHA-256 `92abd2a7c25e4faa49c6dbecc83cc43b4991438fe8beccf6a9409a1c93b3d0e3`。

## 3. FGS specialUse 用途申报

- Manifest：`foregroundServiceType="specialUse"` +
  `PROPERTY_SPECIAL_USE_FGS_SUBTYPE`（值见 AndroidManifest.xml，描述"本机
  自托管 Web 服务，用户发起的临时服务"）。
- Console 申报口径（视频说明/表单文案建议）：*应用提供设备端自托管模式：
  用户主动启动后，前台服务在本机回环地址运行完整 Web 服务端（FastAPI），
  供应用内 WebView 访问；服务通过常驻通知提供状态与停止入口，不采集、
  不上传任何数据，不与后端服务器通信。服务为临时性质（用户随时可停止），
  非常驻 7×24 定位。*
- 依据：target 34+ 对 FGS 类型强制要求；本应用不符合 dataSync/mediaPlayer/
  location 等具名类型，specialUse + 人工审查是既定路线（PLANS 风险表登记）。

## 4. Data Safety 表（按实际行为）

| 数据类别 | 是否收集 | 是否传输 |
|---|---|---|
| 服务器地址/显示名/用户名 | 本地存储（SharedPreferences，allowBackup=false，不进系统备份） | 仅用户显式连接时发往用户自己的服务器 |
| 服务器密码 | Android Keystore AES-GCM 加密后本地存储 | 仅登录请求体发往用户自己的服务器；不落日志 |
| 自签证书指纹 | 本地（按 profile 作用域） | 不传输 |
| 下载器/种子数据 | 服务端数据库（应用私有目录） | 仅用户配置的下载器之间；不经过第三方 |
| 诊断日志 | logcat（本机） | 不上传 |

- **无第三方 SDK、无分析/广告组件、无崩溃上报**——Data Safety 各项可按
  "不收集数据"申报（Web 视图域名豁免说明：WebView 仅加载用户自己的服务器）。

## 5. 隐私政策要点（模板素材）

应用为本地优先的自托管管理工具：所有配置与数据保存在设备应用私有目录或
用户自有的服务器；应用不运营任何后端服务、不收集用户数据；连接远程服务器
时的凭据仅用于该服务器的认证；局域网明文访问为用户显式确认的降级选项。

## 6. GitHub Release 说明（按 ABI 选择）

- **arm64-v8a 设备**（绝大多数真机）：直接安装通用 APK。
- **x86_64**（模拟器/少数平板）：同一通用 APK 可用（内置双 ABI）。
- **32 位设备（armeabi-v7a/x86）**：**不支持**——Chaquopy 15.0.1 起 Python 3.12
  仅提供 64 位 ABI（android-wheels 仓 versions.env 冻结决策），安装将失败
  （INSTALL_FAILED_NO_MATCHING_ABIS）；此类设备请使用"连接已有服务器"的
  桌面/服务器部署形态。

## 7. 明文流量说明（双层防线）

1. 默认构建：NSC 全局禁止 cleartext，仅放行 loopback（本机服务端场景）；
2. LAN 明文需专用构建变体（`-Pbtdeck.lanCleartext=true`，versionName 带
   `+lan` 后缀区分）+ 应用层 LanHostPolicy 强制"私有主机 + 显式风险确认"；
3. Play 分发仅上传默认严格变体；LAN 变体仅供 GitHub Release 自用侧载
   （Console 对 cleartextTrafficPermitted 基线放行的审查风险高，不申报）。

## 8. 包体精算（bundletool 实测，2026-08-30，0.2.0-server/versionCode 2）

| 产物 | 大小 |
|---|---|
| AAB（app-release.aab） | 67.7 MB |
| 签名 release APK（assembleRelease，双 ABI） | 87.7 MB |
| bundletool universal APK | 85.6 MB |
| Play 单设备下发（base-master + arm64-v8a + zh 语言包） | ≈ 73 MB |
| base-arm64_v8a.apk / base-x86_64.apk（native 拆分） | 12.2 / 12.2 MB |

native 库清单（每 ABI 8 个，全来自 Chaquopy 运行时）：
`libpython3.12.so`（~6.6MB）、`libcrypto_python.so`（~3.7MB）、
`libsqlite3_python.so`、`libssl_python.so`、`libchaquopy_java.so` 及
crypto/ssl/sqlite 的 chaquopy 桩。Python 依赖与前端 dist 以
assets/chaquopy/*.imy 压缩映像承载（requirements-common 13.8MB 压缩前）。

- debug→release 体积差 ≈2.7MB（无 minify，见 §9）。
- 16KB 页对齐：自建 wheel 已对齐（android-wheels 判据 6）；Chaquopy 官方
  运行时 so 已在 ps16k AVD 实证可加载。

## 9. minify 决策

release 保持 `isMinifyEnabled=false`：Chaquopy 的 Python 互操作依赖运行时
反射与字节码加载，R8 混淆/裁剪的收益（≈2-3MB）显著小于回归风险；ProGuard
规则维护成本高且难以对 Python 侧做静态验证。后续如开启，必须全量重跑设备
矩阵与导入验证。

## 10. 设备矩阵状态

| 项 | 状态 |
|---|---|
| API 35（Android 15，4096 页） | ✅ 全流程（Phase 3/4 批次实证） |
| API 35 ps16k（16KB 页） | ✅ 仪表化 + 启动链 |
| API 24（最低支持） | 本批批次 B 实测（release APK 冷启动/服务/旋转/Doze） |
| API 34（Android 14） | 本批批次 B 实测 |
| arm64 真机 | ❌ 无设备，登记遗留（import/16KB 已由 wheels 矩阵覆盖 x86_64 实测 + arm64 wheel 自建全绿） |
| 跨版本升级迁移演练 | ❌ 需两个带服务端的发布版本对（建议 v1.0.7 时补） |
| 进程杀死恢复 / FGS 停止 / 通知权限 | ✅（Phase 3 批次） |
| 旋转 / Doze / LAN 开关绑定变化 | 本批批次 B |
| HTTP/HTTPS/坏证书 | 逻辑层单测 + E2E；自签弹窗人工项登记 task .3 |
