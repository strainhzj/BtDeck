@echo off
REM ============================================
REM BtDeck Windows 构建脚本
REM 1. 构建前端
REM 2. PyInstaller 打包后端+前端
REM 3. Inno Setup 制作安装包
REM ============================================

setlocal enabledelayedexpansion

set PROJECT_DIR=%~dp0..
set FRONTEND_DIR=%PROJECT_DIR%\frontend
set BACKEND_DIR=%PROJECT_DIR%\backend
set DEPLOY_DIR=%PROJECT_DIR%\deploy
set DIST_DIR=%PROJECT_DIR%\dist

echo ============================================
echo   BtDeck Windows Build
echo ============================================
echo.

REM 检查工具
where pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] PyInstaller not found. Install: pip install pyinstaller
    exit /b 1
)

where ISCC >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] Inno Setup (ISCC) not found in PATH.
    echo        Install from: https://jrsoftware.org/isdl.php
    echo        Continuing without installer build...
    set BUILD_INSTALLER=0
) else (
    set BUILD_INSTALLER=1
)

REM Step 1: 构建前端
echo [1/3] Building frontend...
cd /d %FRONTEND_DIR%
call npm ci --legacy-peer-deps
if %ERRORLEVEL% neq 0 (
    echo [ERROR] npm ci failed
    exit /b 1
)
call npm run build
if %ERRORLEVEL% neq 0 (
    echo [ERROR] npm run build failed
    exit /b 1
)
echo [OK] Frontend built

REM Step 2: PyInstaller 打包
echo [2/3] Building backend with PyInstaller...
cd /d %PROJECT_DIR%
pyinstaller --clean --noconfirm %DEPLOY_DIR%\btdeck.spec
if %ERRORLEVEL% neq 0 (
    echo [ERROR] PyInstaller build failed
    exit /b 1
)
echo [OK] Backend packaged

REM Step 3: Inno Setup 安装包
if "%BUILD_INSTALLER%"=="1" (
    echo [3/3] Building Windows installer...
    if not exist %DIST_DIR% mkdir %DIST_DIR%
    ISCC %DEPLOY_DIR%\btdeck.iss
    if %ERRORLEVEL% neq 0 (
        echo [WARN] Inno Setup build failed, but executable is ready at build\btdeck.exe
    ) else (
        echo [OK] Installer built at dist\
    )
) else (
    echo [3/3] Skipping installer build (ISCC not found)
    echo        Executable ready at build\btdeck.exe
)

echo.
echo ============================================
echo   Build complete!
echo ============================================
endlocal
