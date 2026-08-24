# BtDeck 移动端桌面测试方案

> **适用范围**：dual-mode-client 移动端（前端 `/m/*` 移动 UI + `android/` 伴侣 APK）在 PC 桌面上的开发与测试。
> **建立日期**：2026-08-24（全部链路本机实证通过：浏览器设备模拟、AVD 模拟器、伴侣 APK 安装、健康检查、WebView 加载移动版）。
> **关联**：`PLANS/dual-mode-client.md`、`android/README.md`。

## 一、三层测试体系（按成本递增选用）

| 层 | 手段 | 适用 | 成本 |
|---|------|------|------|
| L1 | Chrome/Edge DevTools 设备模拟 | 前端移动 UI（布局/交互/路由分流）日常开发主力 | 零安装 |
| L2 | Android 官方 AVD 模拟器（已建 `btdeck-test`） | 伴侣 APK 安装、WebView、NSC 明文变体、健康检查 | 已就绪 |
| L3 | 真机 + USB（scrcpy 可选） | 发布前验收（Phase 2 已真机验证通过） | 需手机 |

## 二、本机环境现状（2026-08-24 已就绪）

```text
C:\software\android-build-env\
├── sdk\                          # Android SDK（可整体删除重建，见下文）
│   ├── cmdline-tools\latest\
│   ├── platform-tools\           # adb / fastboot
│   ├── platforms\android-35\
│   ├── build-tools\35.0.0\
│   ├── emulator\
│   └── system-images\android-35\google_apis\x86_64\
├── gradle-8.9\                   # AGP 8.7.3 最低要求
AVD: btdeck-test（Pixel 6 / API 35 / google_apis x86_64）
JDK: C:\Program Files\Java\jdk-17（PATH 中 java 17.0.15）
后端: conda btpManager → C:\Users\thoma\miniconda3\envs\btpManager\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 5001
前端: frontend\npm run serve（host 0.0.0.0:8080，/api 代理到 5001）
```

## 三、L1：浏览器设备模拟（前端移动 UI）

1. 起后端与前端 dev server（见上）。
2. Chrome 打开 `http://localhost:8080/`，F12 → Ctrl+Shift+M 设备模式，选 iPhone/Pixel 或自定义 **390×844**。
3. `ui-mode.ts` auto 模式按视口宽度自动分流到 `/#/m/login` → 登录 → `/#/m/dashboard`（仪表盘）/ `/#/m/torrents`（种子）/ `/#/m/notifications`（通知）。
4. 需要触摸/滚动/网络节流模拟时用 DevTools 对应面板；`npm run serve` 热更新即时生效。

**新库首次登录注意**：admin 初始口令 `admin` 会触发强制改密守卫并跳桌面版设置页（预期行为）。测试环境先完成改密（或用既有账号）再测移动版；改密后**刷新页面**让 store 重建（GetUserInfo 才会拉到新的 mustChangePassword=false）。

## 四、L2：AVD 模拟器（伴侣 APK）

### 4.1 启动模拟器

```bash
export JAVA_HOME="C:/Program Files/Java/jdk-17"
C:/software/android-build-env/sdk/emulator/emulator.exe -avd btdeck-test -no-snapshot-save -no-boot-anim -gpu auto
# 另开终端等启动完成（约 1-2 分钟）：
export PATH="/c/software/android-build-env/sdk/platform-tools:$PATH"
adb shell getprop sys.boot_completed   # 输出 1 即就绪
```

### 4.2 构建并安装 APK

```bash
cd C:/software/full_stack/BtDeck/android
export JAVA_HOME="C:/Program Files/Java/jdk-17"
C:/software/android-build-env/gradle-8.9/bin/gradle.bat --no-daemon :app:assembleDebug -Pbtdeck.lanCleartext=true
# 产物 app/build/outputs/apk/debug/app-debug.apk；命名副本在 android/dist/（不入库）
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.btdeck.companion/.ui.WizardActivity
```

**变体选择**：连本地/局域网 http 后端必须用 `-Pbtdeck.lanCleartext=true`（LAN 明文版，versionName `0.1.0-mvp+lan`）；默认严格版 http 会被 NSC 拦截（ERR_CLEARTEXT_NOT_PERMITTED，属预期防线）。

### 4.3 添加服务器与验证

- 模拟器访问宿主机服务用 **`http://10.0.2.2:5001`**（AVD 专用回环别名；10.x 是私有地址，满足应用层 LanHostPolicy）。
- 添加对话框里 http+私有地址会自动出现"明文风险确认"复选框，勾选后才能保存（双层防线设计）。
- 菜单"测试连接"应显示 `就绪`、`v1.0.5 · 服务就绪`（HealthClient 链式探测 live→ready）。
- 点击列表项进入 WebView → 应加载出 BtDeck 移动版登录页，副标题 `v1.0.5 · 服务就绪`。

### 4.4 常用调试命令

```bash
adb exec-out screencap -p > shot.png            # 截图
adb logcat -d | grep -iE "btdeck|chromium"      # 日志（WebView console 输出含 chromium tag）
adb shell input tap X Y && adb shell input text "..."   # 注：input text 不支持中文
adb shell am start -n com.btdeck.companion/.ui.WebViewActivity --es profile_id <id>   # 直达页面（需 adb root；profile_id 见
# /data/data/com.btdeck.companion/shared_prefs/btdeck_companion.xml 的 server_profiles JSON）
```

## 五、L3：真机（发布前验收）

USB 调试 + `adb install -r <lan-cleartext apk>`；服务器地址填宿主机局域网 IP（当前 `192.168.2.218`，DHCP 可能变化）。可选 [scrcpy](https://github.com/Genymobile/scrcpy) 投屏桌面操作 + 录屏。

## 六、已知坑（本机实证记录）

1. **Git Bash 路径转换**：`adb shell uiautomator dump /sdcard/...` 的 `/sdcard` 会被转成 Git 安装目录——写成 `//sdcard/...`。
2. **uiautomator dump 坐标与视觉位置偏差**：本 AVD 上 ListView 行的 dump bounds 从 y=0 起（与 action bar 重叠），按 dump 坐标点击列表项无效；底部按钮等其余元素坐标正常。列表项点击请用真机或 `adb root` + `am start --es profile_id` 直达 WebView（本文 4.4）。
3. **adb input text 不支持中文**：表单测试用 ASCII 文本。
4. **`local.properties` 路径**：`sdk.dir` 用正斜杠 `C\:/software/android-build-env/sdk`；反斜杠需双写，单反斜杠会被 properties 转义吞掉导致构建报"文件名、目录名或卷标语法不正确"。
5. **JDK**：PATH 中 `java` 指向 javapath shim，`JAVA_HOME` 需显式指 `C:\Program Files\Java\jdk-17`。
6. **后端登录端点行为差异**：`POST /api/v1/auth/login` 的 password **明文**直传（无 base64 解码），`/user/changePassword` 的旧/新密码 **base64** 编码——写脚本时注意。
7. **devServer 局域网访问**：`vue.config.js` 已 `host:'0.0.0.0'`、`allowedHosts:["main.btpmanager.top"]`；真机/其它设备用 IP 访问 dev server 时需把 IP 加进 allowedHosts（L2 走 10.0.2.2 时 Host 是 IP，如被拒同理）。后端 CORS 在 dev 下走前端同源代理不受影响。
8. **模拟器资源**：AVD 全量冷启约 70 秒（本机实测），日常建议不关模拟器只重装 APK。

## 七、一次性重建（若 `C:\software\android-build-env` 被删除）

```bash
mkdir C:/software/android-build-env && cd C:/software/android-build-env
curl -sL -o cmt.zip https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip && unzip -q cmt.zip
mkdir -p sdk/cmdline-tools/latest && mv cmdline-tools/* sdk/cmdline-tools/latest/ && rm cmt.zip
curl -sL -o g.zip https://mirrors.cloud.tencent.com/gradle/gradle-8.9-bin.zip && unzip -q g.zip && rm g.zip
export JAVA_HOME="C:/Program Files/Java/jdk-17"
yes | sdk/cmdline-tools/latest/bin/sdkmanager.bat --sdk_root=C:/software/android-build-env/sdk "platform-tools" "platforms;android-35" "build-tools;35.0.0" "emulator" "system-images;android-35;google_apis;x86_64"
sdk/cmdline-tools/latest/bin/avdmanager.bat create avd -n btdeck-test -k "system-images;android-35;google_apis;x86_64" -d pixel_6
cd <repo>/android && printf 'sdk.dir=C\\:/software/android-build-env/sdk\n' > local.properties
```
