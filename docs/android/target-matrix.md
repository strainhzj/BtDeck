# Android 目标矩阵与 FGS 决策（Phase 0A 风险闸门）

> **状态**: 2026-08-23 固定的第一版可审计目标矩阵（dual-mode-client Phase 0A）。
> 对应计划: `PLANS/dual-mode-client.md` 第 3 节。
> **登记原则**: 本文档是预审基线；`feature_list.json` 仅在对应阶段通过证据后改
> `in-progress/done`，本文档的写入不代表 Phase 0 已通过。

## 1. 目标矩阵（固定基线）

| 维度 | 目标值 | 备注 |
|---|---|---|
| 最低 Android API | 24（Android 7.0） | Chaquopy 支持下限与项目意愿一致，Phase 5 验收项 |
| 目标 Android API | 以提审时 Google Play 官方要求为准（当前预期 35/36） | `target API 34+` **不作为验收口径**；为 API 36 兼容预留 |
| Chaquopy | 17.x（当前主线） | 版本兼容矩阵: https://chaquo.com/chaquopy/doc/current/versions.html |
| Android Gradle Plugin / Gradle | 以 Chaquopy 17 要求为准，锁定在 android-wheels 仓库 | 随 Phase 0B 最小工程一并固定并记录 hash |
| Python（Android） | 3.12（Chaquopy 提供的 cp312） | 与桌面 3.11 的边界见 `toolchain-matrix.md` |
| Python（桌面） | 3.11（Docker 镜像）/ 3.12.4（Windows 打包 venv） | 不因安卓目标机械改动 pyproject |
| ABI | `arm64-v8a`、`armeabi-v7a`、`x86_64`、`x86` | 四 ABI 全量矩阵，缺一即 Phase 0B 闸门失败 |
| native 依赖 | `pydantic-core` 及 ABI 敏感依赖（bcrypt/regex/Pillow/pycryptodomex/gmssl 等） | 完整 import graph 见 android-wheels 仓库清单 |
| 16 KB page-size | 必须兼容 | Android 15+ 要求，真实设备或等效环境验证 |
| 分发渠道 | Play + GitHub Release 侧载 | 不依赖 F-Droid（自编译 wheel 与其构建要求冲突） |

## 2. FGS（Foreground Service）决策

### 2.1 类型选择

- **首选**: `specialUse`（`FOREGROUND_SERVICE_SPECIAL_USE`），仅在没有更匹配的
  FGS 类型时采用。本应用语义是"用户显式启动的临时/轻量 BitTorrent 管理服务端"，
  不是 media/playback/location/dataSync 任何一类。
- `specialUse` **不是**绕过后台限制或 Play 审核的通行证；采用时必须：
  1. manifest 声明 `FOREGROUND_SERVICE_SPECIAL_USE` 权限与
     `android:foregroundServiceType="specialUse"`；
  2. `<property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE">`
     填写 subtype 文案；
  3. Play Console 提交用途说明与人工审查材料（Phase 3 交付物）。
- **若实验采用 `dataSync`**: 必须覆盖 Android 15（target 35+）对 dataSync 的
  6 小时/24 小时超时预算与 `Service.onTimeout()` 回调。
  **注意：该超时预算是 dataSync 特有行为，不得误写成所有 FGS 类型共有。**

### 2.2 生命周期决策

- 服务端模式仅在用户显式操作后启动（无 boot 自启承诺）。
- FGS 常驻通知提供：运行状态、停止、重启入口；通知 channel 独立。
- Android 12+ 后台启动限制：FGS 只能由前台 UI 或用户交互触发；
  进程被杀后的重启策略按"用户下次打开 App 手动恢复"设计，
  **不承诺** auto-restart。
- Doze/OEM 电池策略（小米/华为/三星省电）纳入 Phase 5 设备验收；
  **不以 FGS 消除 Doze 漂移作为承诺**——服务端模式定位是轻量/临时。

### 2.3 权限与数据声明

| 项 | 决策 |
|---|---|
| `POST_NOTIFICATIONS`（Android 13+） | 运行时请求，拒绝时 FGS 仍可运行但无可见通知（降级提示） |
| `INTERNET` / `ACCESS_NETWORK_STATE` | 必需 |
| `FOREGROUND_SERVICE` + subtype 权限 | Phase 3 按最终 FGS 类型声明 |
| 应用备份/恢复（`allowBackup`） | 默认 **关闭** 或 backup rules 排除：config YAML、JWT/refresh token、下载器凭据、加密密钥、app.db —— 详见 Phase 3 存储验收 |
| Keystore | Android Keystore 存放 SM4/加密根密钥（Phase 3），密钥不得进备份/日志 |
| 明文局域网（cleartext HTTP） | 仅按用户逐主机放行（`networkSecurityConfig`），禁止全局 `usesCleartextTraffic="true"` |
| 自签证书 | 用户显式信任并记录作用域，禁止无条件 `handler.proceed()`（Phase 2 WebView 规则） |
| Data Safety 表单 | Play Console 声明：本地处理凭据/日志、局域网传输、无广告/无第三方共享；文案随 Phase 5 提审复核 |

## 3. Phase 0B 闸门判据（引用）

进入安卓服务端工程（Phase 3）前，`btdeck/android-wheels` 独立仓库必须达成：

1. 固定版本/hash 的 `pydantic-core` cp312 四 ABI wheels 经 GitHub Actions +
   `cargo-ndk` 构建成功，PEP 503 索引发布在 GitHub Pages（含 wheel hash、
   构建日志、SBOM/license）。
2. 最小 Chaquopy 17 FastAPI + pydantic hello world 通过。
3. BtDeck 完整 import graph 在四 ABI 矩阵安装、导入、启动 `/health/live`，
   完成一次数据库迁移与前端静态资源加载。
4. 16 KB page-size、冷启动、升级安装、wheel 缺失明确失败信息验证。

任一不满足 → 暂停本地服务端，先交付伴侣模式（Phase 2），并重估
Termux/推迟/裁剪后端能力等备选方案。

## 4. 预审遗留行动项（人工/后续会话）

- [ ] Play Console 账号与 App 创建（用户操作）。
- [ ] 提审时点官方 target API 要求的复核（Phase 5）。
- [ ] FGS subtype 文案与用途说明的最终定稿（Phase 3，需用户确认措辞）。
- [ ] `dataSync` 备选实验仅在 specialUse 审核受阻时启动，且必须覆盖
      6h/24h 预算与 `onTimeout`。
