@echo off
setlocal EnableExtensions

rem BtDeck unified Windows EXE + Android APK build entry.
rem The script is independent of the caller's current directory.

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
set "WINDOWS_SELECTED=0"
set "ANDROID_SELECTED=0"
set "ANDROID_ARGS="
set "HAS_SELECTION=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--windows" (
    set "WINDOWS_SELECTED=1"
    set "HAS_SELECTION=1"
    shift
    goto parse_args
)
if /I "%~1"=="--android" (
    set "ANDROID_SELECTED=1"
    set "ANDROID_ARGS="
    set "HAS_SELECTION=1"
    shift
    goto parse_args
)
if /I "%~1"=="--android-strict-only" (
    set "ANDROID_SELECTED=1"
    set "ANDROID_ARGS=--strict-only"
    set "HAS_SELECTION=1"
    shift
    goto parse_args
)
if /I "%~1"=="--android-lan-only" (
    set "ANDROID_SELECTED=1"
    set "ANDROID_ARGS=--lan-only"
    set "HAS_SELECTION=1"
    shift
    goto parse_args
)
if /I "%~1"=="--help" goto help
echo [ERROR] Unknown option: %~1
echo Use --help for usage.
exit /b 2

:args_done
if "%HAS_SELECTION%"=="0" (
    set "WINDOWS_SELECTED=1"
    set "ANDROID_SELECTED=1"
)

if "%WINDOWS_SELECTED%"=="1" (
    echo.
    echo ========================================
    echo [TARGET] Windows EXE / optional Inno Setup installer
    echo ========================================
    call "%PROJECT_DIR%\deploy\build-windows.bat"
    if errorlevel 1 (
        echo [ERROR] Windows EXE build failed.
        exit /b 1
    )
)

if "%ANDROID_SELECTED%"=="1" (
    echo.
    echo ========================================
    echo [TARGET] Android APK
    echo ========================================
    if defined ANDROID_ARGS (
        call "%PROJECT_DIR%\deploy\build-android.bat" %ANDROID_ARGS%
    ) else (
        call "%PROJECT_DIR%\deploy\build-android.bat"
    )
    if errorlevel 1 (
        echo [ERROR] Android APK build failed.
        exit /b 1
    )
)

echo.
echo [OK] Requested package build targets completed.
exit /b 0

:help
echo Usage: build-packages.bat [options]
echo.
echo Default: build the Windows EXE and both Android debug APK variants.
echo --windows              Build only the existing deploy\build-windows.bat chain.
echo --android              Build both Android strict and LAN APK variants.
echo --android-strict-only  Build only the Android strict APK variant.
echo --android-lan-only     Build only the Android LAN cleartext APK variant.
echo.
echo The Windows build writes dist\btdeck.exe and, when ISCC is installed,
echo also writes the Inno Setup installer. Android artifacts are written to
echo android\dist\.
exit /b 0
