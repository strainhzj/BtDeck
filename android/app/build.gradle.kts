import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// LAN 明文构建开关（默认 false）：
// false → network_security_config.xml（cleartext 全局禁止，仅 loopback 放行）
// true  → network_security_config_lan.xml（cleartext 基线放行，配合应用内
//         LanHostPolicy 仍仅允许用户选择的私有 LAN 主机——平台 NSC 无法在
//         运行时按主机开闭，这是 Android 的构建期约束，双层防线见 README）
val lanCleartext = (findProperty("btdeck.lanCleartext") as? String)?.toBooleanStrictOrNull() ?: false

android {
    namespace = "com.btdeck.companion"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.btdeck.companion"
        minSdk = 24
        targetSdk = 35
        versionCode = 2
        // LAN 明文构建用独立 versionName，系统"设置-应用"与安装器里可见，
        // 避免与严格版混淆（曾发生：误装严格版复测报 ERR_CLEARTEXT_NOT_PERMITTED）
        versionName = if (lanCleartext) "0.2.0-server+lan" else "0.2.0-server"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // Chaquopy 15.0.1 起 Python 3.12 仅支持 64 位 ABI（官方矩阵，wheels 仓
        // versions.env 同源决策）。代价：32 位设备无法安装本 app（Play AAB 按
        // ABI 分发不受影响；侧载边界登记 README）。本机服务端模式另在运行时
        // 以 SUPPORTED_ABIS 检测给出可读提示。
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }

        manifestPlaceholders["networkSecurityConfig"] =
            if (lanCleartext) "@xml/network_security_config_lan" else "@xml/network_security_config"

        // 构建标识：向导页副标题展示，避免误装/误判当前 APK 的明文能力
        buildConfigField("boolean", "LAN_CLEARTEXT_BUILD", lanCleartext.toString())
    }

    buildFeatures {
        buildConfig = true
    }

    // Phase 5 发布签名：凭据经 local.properties（gitignored）注入，keystore 不入库；
    // 缺失时不创建 signingConfig（退化为无签名 release，本地 CI 构建不阻断）。
    signingConfigs {
        val props = Properties()
        val f = rootProject.file("local.properties")
        if (f.exists()) f.inputStream().use { props.load(it) }
        val storePath = props.getProperty("RELEASE_STORE_FILE")
        if (storePath != null && rootProject.file(storePath).exists()) {
            create("release") {
                storeFile = rootProject.file(storePath)
                storePassword = props.getProperty("RELEASE_STORE_PASSWORD")
                keyAlias = props.getProperty("RELEASE_KEY_ALIAS")
                keyPassword = props.getProperty("RELEASE_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

// ============ Phase 3 本机服务端：Chaquopy 17 + Python 3.12 ============
// 源集与 requirements 由 android/tools/stage-server.py 生成（gitignored）。
// 默认启用（生产功能）；未 staging 时构建直接失败并给出指引；
// 纯伴侣模式快速构建可用 -Pbtdeck.server=off 跳过。
// 改 requirements 后必须 --rerun-tasks 并清 %LOCALAPPDATA%/pip/cache
// （gradle 不追踪 -r 文件内容变化，wheels 仓实证）。
val serverMode = providers.gradleProperty("btdeck.server").getOrElse("on") != "off"

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            // Chaquopy 无 extraIndexUrls DSL 属性，pip 旗标统一经 options(...) 传。
            // android-wheels 索引（自建 Android wheel：pydantic-core/bcrypt/greenlet/
            // regex/pycryptodomex；PEP 503 索引常驻）
            options("--extra-index-url", "https://strainhzj.github.io/android-wheels/simple/")
            // tzdata：Android 无系统 tz 数据库（zoneinfo 报 No time zone found，
            // 调度器启动失败实证）。放 DSL 而非 stage 生成文件——它是 Android
            // 平台特有补充而非后端 pin；同时是 pip 配置的生效锚点（Chaquopy 17
            // 实证：pip 块无任何 install() 时整个 pip 配置含 options() 被判空跳过）
            install("tzdata>=2024.1")
            if (serverMode) {
                val req = file("src/server/server-requirements.txt")
                if (req.exists()) {
                    options("-r", req.absolutePath)
                } else {
                    throw GradleException(
                        "btdeck.server 未关闭但缺 ${req.absolutePath}——" +
                            "先运行 android/tools/stage-server.py" +
                            "（或以 -Pbtdeck.server=off 构建纯伴侣模式）"
                    )
                }
            }
        }
    }
    productFlavors { }
    sourceSets {
        getByName("main") {
            if (serverMode && file("src/server/python").isDirectory) {
                srcDir("src/server/python")
            }
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    // 健康检查（/health/live、/health/ready）与自签证书 TLS 错误的可辨识处理
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
    // JVM 单测用真 org.json 替代 android.jar 的 not-mocked stub
    // （ServerStates/LocalServerProfile 契约测试需要真实 JSON 行为）
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}
