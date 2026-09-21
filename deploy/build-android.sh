#!/bin/bash

# ============================================
# BtDeck Android APK builder (Linux 移植版)
# 逻辑与 deploy/build-android.bat 一一对应：
#   - 双变体构建：strict（默认明文策略）与 LAN（显式局域网明文测试）
#   - 每个变体：JVM 单测 + assembleDebug + 复制 + apksigner 验签
#     + aapt2 badging + SHA256
# 脚本独立于调用方当前目录。
#
# 用法: deploy/build-android.sh [--strict-only|--lan-only]
# 工具链覆盖:
#   BTDECK_GRADLE              gradle 可执行文件完整路径
#   BTDECK_JAVA_HOME           JDK 17+ 目录
#   BTDECK_APK_VERSION         输出文件名版本，默认 0.2.5
#   BTDECK_BUILD_TOOLS_VERSION Android build-tools 版本，默认 35.0.0
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ANDROID_DIR="$PROJECT_DIR/android"
ANDROID_DIST_DIR="$ANDROID_DIR/dist"
ANDROID_API_LEVEL="35"
BTDECK_BUILD_TOOLS_VERSION="${BTDECK_BUILD_TOOLS_VERSION:-35.0.0}"
BTDECK_APK_VERSION="${BTDECK_APK_VERSION:-0.2.5}"

BUILD_STRICT=1
BUILD_LAN=1

err()  { echo "[ERROR] $*" >&2; }
info() { echo "[INFO] $*"; }

usage() {
    cat <<'EOF'
Usage: deploy/build-android.sh [--strict-only|--lan-only]

Default: run JVM unit tests and assemble both debug APK variants.
--strict-only  Build only the default safe cleartext policy variant.
--lan-only     Build only the explicit LAN cleartext test variant.

Toolchain overrides:
  BTDECK_GRADLE       Full path to gradle executable (or generate android/gradlew)
  BTDECK_JAVA_HOME    JDK 17 or 21 directory
  BTDECK_APK_VERSION  Output filename version, default 0.2.5
  BTDECK_BUILD_TOOLS_VERSION  Android build-tools version, default 35.0.0
EOF
    exit 0
}

# ---------- 参数解析 ----------
while [ $# -gt 0 ]; do
    case "$1" in
        --strict-only) BUILD_STRICT=1; BUILD_LAN=0; shift ;;
        --lan-only)    BUILD_STRICT=0; BUILD_LAN=1; shift ;;
        --help|-h)     usage ;;
        *)
            err "Unknown option: $1"
            err "Use --help for usage."
            exit 2
            ;;
    esac
done

# ---------- 前置检查 ----------
if [ ! -f "$ANDROID_DIR/settings.gradle.kts" ]; then
    err "Android project not found: $ANDROID_DIR"
    exit 1
fi
if [ ! -f "$ANDROID_DIR/app/build.gradle.kts" ]; then
    err "Android app module not found: $ANDROID_DIR/app"
    exit 1
fi

# ---------- 解析 Gradle: 显式覆盖 > 检入的 wrapper > GRADLE_HOME > PATH ----------
GRADLE_CMD=""
if [ -n "${BTDECK_GRADLE:-}" ] && [ -x "$BTDECK_GRADLE" ]; then
    GRADLE_CMD="$BTDECK_GRADLE"
fi
if [ -z "$GRADLE_CMD" ] && [ -x "$ANDROID_DIR/gradlew" ]; then
    GRADLE_CMD="$ANDROID_DIR/gradlew"
fi
if [ -z "$GRADLE_CMD" ] && [ -n "${GRADLE_HOME:-}" ] && [ -x "$GRADLE_HOME/bin/gradle" ]; then
    GRADLE_CMD="$GRADLE_HOME/bin/gradle"
fi
if [ -z "$GRADLE_CMD" ]; then
    GRADLE_BIN="$(command -v gradle 2>/dev/null || true)"
    [ -n "$GRADLE_BIN" ] && GRADLE_CMD="$GRADLE_BIN"
fi
if [ -z "$GRADLE_CMD" ]; then
    err "Gradle was not found."
    err "Set BTDECK_GRADLE to gradle, configure GRADLE_HOME, or generate android/gradlew."
    exit 1
fi

# ---------- 解析 JDK: javac 必需；本项目 Gradle 8.9 需要 JDK 17+ ----------
JAVA_HOME_EFFECTIVE=""
try_java_home() {
    local candidate="$1"
    [ -x "$candidate/bin/javac" ] || return 1
    local version major
    version="$("$candidate/bin/javac" -version 2>&1 | awk '{print $2}')"
    [ -n "$version" ] || return 1
    major="${version%%.*}"
    # 兼容遗留 "1.x" 版本号格式（如 1.8.0）
    if [ "$major" = "1" ]; then
        major="${version#*.}"
        major="${major%%.*}"
    fi
    case "$major" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ "$major" -ge 17 ] || return 1
    JAVA_HOME_EFFECTIVE="$candidate"
}
if [ -n "${BTDECK_JAVA_HOME:-}" ]; then try_java_home "$BTDECK_JAVA_HOME" || true; fi
if [ -z "$JAVA_HOME_EFFECTIVE" ] && [ -n "${JAVA_HOME:-}" ]; then try_java_home "$JAVA_HOME" || true; fi
if [ -z "$JAVA_HOME_EFFECTIVE" ]; then
    JAVAC_BIN="$(command -v javac 2>/dev/null || true)"
    if [ -n "$JAVAC_BIN" ]; then
        try_java_home "$(cd "$(dirname "$JAVAC_BIN")/.." && pwd)" || true
    fi
fi
if [ -z "$JAVA_HOME_EFFECTIVE" ]; then
    err "A JDK was not found."
    err "Set BTDECK_JAVA_HOME or JAVA_HOME to a JDK 17 or newer installation."
    exit 1
fi
export JAVA_HOME="$JAVA_HOME_EFFECTIVE"
export PATH="$JAVA_HOME/bin:$PATH"

# ---------- 解析 Android SDK: local.properties > ANDROID_SDK_ROOT > ANDROID_HOME ----------
SDK_DIR=""
if [ -f "$ANDROID_DIR/local.properties" ]; then
    # 提取 sdk.dir（兼容 CRLF 与大小写）
    SDK_DIR="$(sed -n 's/^[[:space:]]*sdk\.dir[[:space:]]*=[[:space:]]*//Ip' "$ANDROID_DIR/local.properties" | head -1 | tr -d '\r')"
fi
if [ -z "$SDK_DIR" ] && [ -n "${ANDROID_SDK_ROOT:-}" ]; then SDK_DIR="$ANDROID_SDK_ROOT"; fi
if [ -z "$SDK_DIR" ] && [ -n "${ANDROID_HOME:-}" ]; then SDK_DIR="$ANDROID_HOME"; fi
if [ -z "$SDK_DIR" ]; then
    err "Android SDK was not found."
    err "Configure android/local.properties, ANDROID_SDK_ROOT, or ANDROID_HOME."
    exit 1
fi
if [ ! -f "$SDK_DIR/platforms/android-$ANDROID_API_LEVEL/android.jar" ]; then
    err "Android SDK platform android-$ANDROID_API_LEVEL is missing under $SDK_DIR."
    exit 1
fi

BUILD_TOOLS_DIR="$SDK_DIR/build-tools/$BTDECK_BUILD_TOOLS_VERSION"
AAPT2="$BUILD_TOOLS_DIR/aapt2"
APKSIGNER="$BUILD_TOOLS_DIR/apksigner"
if [ ! -x "$AAPT2" ]; then
    err "aapt2 was not found: $AAPT2"
    err "Set BTDECK_BUILD_TOOLS_VERSION to an installed build-tools version."
    exit 1
fi
if [ ! -x "$APKSIGNER" ]; then
    err "apksigner was not found: $APKSIGNER"
    err "Set BTDECK_BUILD_TOOLS_VERSION to an installed build-tools version."
    exit 1
fi

mkdir -p "$ANDROID_DIST_DIR"

echo "[INFO] Project: $PROJECT_DIR"
echo "[INFO] Gradle: $GRADLE_CMD"
echo "[INFO] JAVA_HOME: $JAVA_HOME"
echo "[INFO] Android SDK: $SDK_DIR"
echo "[INFO] Output: $ANDROID_DIST_DIR"

cd "$ANDROID_DIR"

# ---------- 复制并验证单个变体产物 ----------
copy_and_verify() {
    local variant="$1" source_apk="$2" target_apk="$3"
    if [ ! -f "$source_apk" ]; then
        err "$variant APK was not produced: $source_apk"
        return 1
    fi
    if ! cp -f "$source_apk" "$target_apk"; then
        err "Could not copy $variant APK to $target_apk"
        return 1
    fi
    echo "[VERIFY] $variant APK: $target_apk"
    if ! "$APKSIGNER" verify --verbose "$target_apk"; then
        err "apksigner verification failed for $variant APK."
        return 1
    fi
    if ! "$AAPT2" dump badging "$target_apk"; then
        err "aapt2 badging failed for $variant APK."
        return 1
    fi
    sha256sum "$target_apk"
}

if [ "$BUILD_STRICT" = "1" ]; then
    echo
    echo "[BUILD] Strict APK: cleartext disabled except loopback"
    if ! "$GRADLE_CMD" --no-daemon :app:testDebugUnitTest :app:assembleDebug; then
        err "Strict APK build failed."
        exit 1
    fi
    if ! copy_and_verify "strict" \
        "$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk" \
        "$ANDROID_DIST_DIR/btdeck-companion-$BTDECK_APK_VERSION-strict-debug.apk"; then
        exit 1
    fi
fi

if [ "$BUILD_LAN" = "1" ]; then
    echo
    echo "[BUILD] LAN APK: explicit LAN cleartext test build"
    if ! "$GRADLE_CMD" --no-daemon "-Pbtdeck.lanCleartext=true" :app:testDebugUnitTest :app:assembleDebug; then
        err "LAN APK build failed."
        exit 1
    fi
    if ! copy_and_verify "lan-cleartext" \
        "$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk" \
        "$ANDROID_DIST_DIR/btdeck-companion-$BTDECK_APK_VERSION-lan-cleartext-debug.apk"; then
        exit 1
    fi
fi

echo
echo "[OK] Android APK build completed."
exit 0
