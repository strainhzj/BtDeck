@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem BtDeck Android APK builder.
rem The script is independent of the caller's current directory.

for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
set "ANDROID_DIR=%PROJECT_DIR%\android"
set "ANDROID_DIST_DIR=%ANDROID_DIR%\dist"
set "ANDROID_API_LEVEL=35"
if not defined BTDECK_BUILD_TOOLS_VERSION set "BTDECK_BUILD_TOOLS_VERSION=35.0.0"
if not defined BTDECK_APK_VERSION set "BTDECK_APK_VERSION=0.1.0-mvp"

set "BUILD_STRICT=1"
set "BUILD_LAN=1"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--strict-only" (
    set "BUILD_STRICT=1"
    set "BUILD_LAN=0"
    shift
    goto parse_args
)
if /I "%~1"=="--lan-only" (
    set "BUILD_STRICT=0"
    set "BUILD_LAN=1"
    shift
    goto parse_args
)
if /I "%~1"=="--help" goto help
echo [ERROR] Unknown option: %~1
echo Use --help for usage.
exit /b 2

:args_done
if not exist "%ANDROID_DIR%\settings.gradle.kts" (
    echo [ERROR] Android project not found: "%ANDROID_DIR%"
    exit /b 1
)
if not exist "%ANDROID_DIR%\app\build.gradle.kts" (
    echo [ERROR] Android app module not found: "%ANDROID_DIR%\app"
    exit /b 1
)

rem Resolve Gradle: explicit override, checked-in wrapper, GRADLE_HOME, PATH,
rem and the standard local build environment used by this workspace.
set "GRADLE_CMD="
if defined BTDECK_GRADLE if exist "%BTDECK_GRADLE%" set "GRADLE_CMD=%BTDECK_GRADLE%"
if not defined GRADLE_CMD if exist "%ANDROID_DIR%\gradlew.bat" set "GRADLE_CMD=%ANDROID_DIR%\gradlew.bat"
if not defined GRADLE_CMD if defined GRADLE_HOME if exist "%GRADLE_HOME%\bin\gradle.bat" set "GRADLE_CMD=%GRADLE_HOME%\bin\gradle.bat"
if not defined GRADLE_CMD (
    for /f "delims=" %%I in ('where gradle.bat 2^>nul') do if not defined GRADLE_CMD set "GRADLE_CMD=%%~fI"
)
if not defined GRADLE_CMD if exist "C:\software\android-build-env\gradle-8.9\bin\gradle.bat" set "GRADLE_CMD=C:\software\android-build-env\gradle-8.9\bin\gradle.bat"
if not defined GRADLE_CMD (
    echo [ERROR] Gradle was not found.
    echo Set BTDECK_GRADLE to gradle.bat, configure GRADLE_HOME, or generate android\gradlew.bat.
    exit /b 1
)

rem Resolve a JDK. javac is required; Gradle 8.9 needs JDK 17+ for this project.
set "JAVA_HOME_EFFECTIVE="
if defined BTDECK_JAVA_HOME call :try_java_home "%BTDECK_JAVA_HOME%"
if not defined JAVA_HOME_EFFECTIVE if defined JAVA_HOME call :try_java_home "%JAVA_HOME%"
if not defined JAVA_HOME_EFFECTIVE if exist "C:\software\android-build-env\jdk-21.0.2\bin\javac.exe" call :try_java_home "C:\software\android-build-env\jdk-21.0.2"
if not defined JAVA_HOME_EFFECTIVE if exist "%ProgramFiles%\Java\jdk-21\bin\javac.exe" call :try_java_home "%ProgramFiles%\Java\jdk-21"
if not defined JAVA_HOME_EFFECTIVE (
    echo [ERROR] A JDK was not found.
    echo Set BTDECK_JAVA_HOME or JAVA_HOME to a JDK 17 or newer installation.
    exit /b 1
)
set "JAVA_HOME=%JAVA_HOME_EFFECTIVE%"
set "PATH=%JAVA_HOME%\bin;%PATH%"

rem Read the same SDK location Gradle will use, then fall back to environment variables.
set "SDK_DIR="
if exist "%ANDROID_DIR%\local.properties" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ANDROID_DIR%\local.properties") do (
        if /I "%%A"=="sdk.dir" set "SDK_DIR=%%B"
    )
)
if defined SDK_DIR set "SDK_DIR=%SDK_DIR:/=\%"
if not defined SDK_DIR if defined ANDROID_SDK_ROOT set "SDK_DIR=%ANDROID_SDK_ROOT%"
if not defined SDK_DIR if defined ANDROID_HOME set "SDK_DIR=%ANDROID_HOME%"
if not defined SDK_DIR if exist "C:\software\android-build-env\sdk\platforms\android-%ANDROID_API_LEVEL%\android.jar" set "SDK_DIR=C:\software\android-build-env\sdk"
if not defined SDK_DIR (
    echo [ERROR] Android SDK was not found.
    echo Configure android\local.properties, ANDROID_SDK_ROOT, or ANDROID_HOME.
    exit /b 1
)
if not exist "%SDK_DIR%\platforms\android-%ANDROID_API_LEVEL%\android.jar" (
    echo [ERROR] Android SDK platform android-%ANDROID_API_LEVEL% is missing under "%SDK_DIR%".
    exit /b 1
)

set "BUILD_TOOLS_DIR=%SDK_DIR%\build-tools\%BTDECK_BUILD_TOOLS_VERSION%"
set "AAPT2=%BUILD_TOOLS_DIR%\aapt2.exe"
set "APKSIGNER=%BUILD_TOOLS_DIR%\apksigner.bat"
if not exist "%AAPT2%" (
    echo [ERROR] aapt2 was not found: "%AAPT2%"
    echo Set BTDECK_BUILD_TOOLS_VERSION to an installed build-tools version.
    exit /b 1
)
if not exist "%APKSIGNER%" (
    echo [ERROR] apksigner was not found: "%APKSIGNER%"
    echo Set BTDECK_BUILD_TOOLS_VERSION to an installed build-tools version.
    exit /b 1
)

if not exist "%ANDROID_DIST_DIR%" mkdir "%ANDROID_DIST_DIR%"
if errorlevel 1 (
    echo [ERROR] Could not create Android distribution directory.
    exit /b 1
)

echo [INFO] Project: %PROJECT_DIR%
echo [INFO] Gradle: %GRADLE_CMD%
echo [INFO] JAVA_HOME: %JAVA_HOME%
echo [INFO] Android SDK: %SDK_DIR%
echo [INFO] Output: %ANDROID_DIST_DIR%

pushd "%ANDROID_DIR%"
if errorlevel 1 (
    echo [ERROR] Could not enter Android project directory.
    exit /b 1
)

if "%BUILD_STRICT%"=="1" (
    echo.
    echo [BUILD] Strict APK: cleartext disabled except loopback
    call "%GRADLE_CMD%" --no-daemon :app:testDebugUnitTest :app:assembleDebug
    if errorlevel 1 (
        echo [ERROR] Strict APK build failed.
        popd
        exit /b 1
    )
    call :copy_and_verify "strict" "%ANDROID_DIR%\app\build\outputs\apk\debug\app-debug.apk" "%ANDROID_DIST_DIR%\btdeck-companion-%BTDECK_APK_VERSION%-strict-debug.apk"
    if errorlevel 1 (
        popd
        exit /b 1
    )
)

if "%BUILD_LAN%"=="1" (
    echo.
    echo [BUILD] LAN APK: explicit LAN cleartext test build
    call "%GRADLE_CMD%" --no-daemon "-Pbtdeck.lanCleartext=true" :app:testDebugUnitTest :app:assembleDebug
    if errorlevel 1 (
        echo [ERROR] LAN APK build failed.
        popd
        exit /b 1
    )
    call :copy_and_verify "lan-cleartext" "%ANDROID_DIR%\app\build\outputs\apk\debug\app-debug.apk" "%ANDROID_DIST_DIR%\btdeck-companion-%BTDECK_APK_VERSION%-lan-cleartext-debug.apk"
    if errorlevel 1 (
        popd
        exit /b 1
    )
)

popd
echo.
echo [OK] Android APK build completed.
exit /b 0

:copy_and_verify
set "VARIANT=%~1"
set "SOURCE_APK=%~2"
set "TARGET_APK=%~3"
if not exist "%SOURCE_APK%" (
    echo [ERROR] %VARIANT% APK was not produced: "%SOURCE_APK%"
    exit /b 1
)
copy /Y "%SOURCE_APK%" "%TARGET_APK%" >nul
if errorlevel 1 (
    echo [ERROR] Could not copy %VARIANT% APK to "%TARGET_APK%"
    exit /b 1
)
echo [VERIFY] %VARIANT% APK: "%TARGET_APK%"
call "%APKSIGNER%" verify --verbose "%TARGET_APK%"
if errorlevel 1 (
    echo [ERROR] apksigner verification failed for %VARIANT% APK.
    exit /b 1
)
"%AAPT2%" dump badging "%TARGET_APK%"
if errorlevel 1 (
    echo [ERROR] aapt2 badging failed for %VARIANT% APK.
    exit /b 1
)
certutil -hashfile "%TARGET_APK%" SHA256
exit /b 0

:try_java_home
set "JAVA_CANDIDATE=%~1"
if not exist "%JAVA_CANDIDATE%\bin\javac.exe" exit /b 1
set "JAVAC_VERSION="
for /f "tokens=2" %%V in ('"%JAVA_CANDIDATE%\bin\javac.exe" -version 2^>^&1') do set "JAVAC_VERSION=%%V"
set "JAVA_MAJOR="
for /f "tokens=1,2 delims=." %%A in ("!JAVAC_VERSION!") do (
    set "JAVA_MAJOR=%%A"
    if "%%A"=="1" set "JAVA_MAJOR=%%B"
)
if not defined JAVA_MAJOR exit /b 1
if !JAVA_MAJOR! LSS 17 exit /b 1
set "JAVA_HOME_EFFECTIVE=%JAVA_CANDIDATE%"
exit /b 0

:help
echo Usage: deploy\build-android.bat [--strict-only^|--lan-only]
echo.
echo Default: run JVM unit tests and assemble both debug APK variants.
echo --strict-only  Build only the default safe cleartext policy variant.
echo --lan-only     Build only the explicit LAN cleartext test variant.
echo.
echo Toolchain overrides:
echo   BTDECK_GRADLE       Full path to gradle.bat
echo   BTDECK_JAVA_HOME    JDK 17 or 21 directory
echo   BTDECK_APK_VERSION  Output filename version, default 0.1.0-mvp
echo   BTDECK_BUILD_TOOLS_VERSION  Android build-tools version, default 35.0.0
exit /b 0
