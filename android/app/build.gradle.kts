plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
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
        versionCode = 1
        // LAN 明文构建用独立 versionName，系统"设置-应用"与安装器里可见，
        // 避免与严格版混淆（曾发生：误装严格版复测报 ERR_CLEARTEXT_NOT_PERMITTED）
        versionName = if (lanCleartext) "0.1.0-mvp+lan" else "0.1.0-mvp"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        manifestPlaceholders["networkSecurityConfig"] =
            if (lanCleartext) "@xml/network_security_config_lan" else "@xml/network_security_config"

        // 构建标识：向导页副标题展示，避免误装/误判当前 APK 的明文能力
        buildConfigField("boolean", "LAN_CLEARTEXT_BUILD", lanCleartext.toString())
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
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

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    // 健康检查（/health/live、/health/ready）与自签证书 TLS 错误的可辨识处理
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}
