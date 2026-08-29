// BtDeck 双模式客户端（dual-mode-client Phase 2 伴侣模式 + Phase 3 本机服务端）
// 版本基线与 android-wheels 仓库 versions.env / Chaquopy 矩阵对齐
// （AGP 8.7.3 + Kotlin 2.0.20 + Chaquopy 17.0.0 组合已在 wheels testapp 实证）。
plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.20" apply false
    id("com.chaquo.python") version "17.0.0" apply false
}
