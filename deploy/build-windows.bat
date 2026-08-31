@echo off
REM ============================================
REM BtDeck Windows build script
REM 1. Build frontend (dev) / consume single build (release)
REM 2. Generate release identity (build-info + manifests)
REM 3. Package backend + frontend + identity with PyInstaller
REM 4. Build installer with Inno Setup (release: mandatory, fail-closed)
REM
REM Modes (release-artifact-equivalence-gate W2):
REM   default (dev) : self-build frontend, --allow-dirty identity,
REM                   ISCC missing -> warn and skip (historical behavior)
REM   --release     : require prebuilt frontend from
REM                   scripts\release\build_frontend.py (manifest hash match),
REM                   clean worktree, ISCC mandatory and failures fatal
REM ============================================

setlocal enabledelayedexpansion

set "RELEASE_MODE=0"
if /I "%~1"=="--release" set "RELEASE_MODE=1"
if not "%~1"=="" if /I not "%~1"=="--release" (
    echo [ERROR] Unknown argument: %~1 ^(supported: --release^)
    exit /b 2
)

for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"
set "BACKEND_DIR=%PROJECT_DIR%\backend"
set "DEPLOY_DIR=%PROJECT_DIR%\deploy"
set "DIST_DIR=%PROJECT_DIR%\dist"
set "NSSM_PATH=%DEPLOY_DIR%\nssm.exe"
set "PACKAGE_REQUIREMENTS=%DEPLOY_DIR%\requirements-windows-package.txt"
set "PACKAGE_VENV=%PROJECT_DIR%\.venv-packaging"
set "PACKAGE_PYTHON=%PACKAGE_VENV%\Scripts\python.exe"
set "PACKAGE_PYINSTALLER=%PACKAGE_VENV%\Scripts\pyinstaller.exe"
set "FRONTEND_MANIFEST=%PROJECT_DIR%\release\build\frontend\frontend-asset-manifest.json"
set "STAGING_DIR=%PROJECT_DIR%\release\build\windows-exe"
set "NPM_CMD="
set "PYTHON_CMD="

echo ============================================
echo   BtDeck Windows Build (mode: %RELEASE_MODE%)
echo ============================================
echo.

REM Check NSSM service manager
if not exist "%NSSM_PATH%" (
    echo [ERROR] NSSM not found
    echo        Expected path: "%NSSM_PATH%"
    echo        Current dir: "%CD%"
    echo        Download from: https://nssm.cc/download - win64 version
    echo        Or visit: https://github.com/dkxCE/NSSM/releases
    exit /b 1
)
echo [OK] NSSM found: "%NSSM_PATH%"

REM Check required tools
where npm.cmd >nul 2>&1
if not errorlevel 1 for /f "delims=" %%I in ('where npm.cmd') do if not defined NPM_CMD set "NPM_CMD=%%I"
if not defined NPM_CMD if exist "%NVM_SYMLINK%\npm.cmd" set "NPM_CMD=%NVM_SYMLINK%\npm.cmd"
if not defined NPM_CMD if exist "%ProgramFiles%\nodejs\npm.cmd" set "NPM_CMD=%ProgramFiles%\nodejs\npm.cmd"
if not defined NPM_CMD if exist "%ProgramFiles(x86)%\nodejs\npm.cmd" set "NPM_CMD=%ProgramFiles(x86)%\nodejs\npm.cmd"
if not defined NPM_CMD if exist "C:\software\nvm\v18.20.8\npm.cmd" set "NPM_CMD=C:\software\nvm\v18.20.8\npm.cmd"
if not defined NPM_CMD (
    echo [ERROR] npm not found. Install Node.js or add npm.cmd to PATH.
    exit /b 1
)
echo [OK] npm found: "%NPM_CMD%"

where python >nul 2>&1
if not errorlevel 1 for /f "delims=" %%I in ('where python') do if not defined PYTHON_CMD set "PYTHON_CMD=%%I"
if not defined PYTHON_CMD (
    echo [ERROR] python not found. Install Python or add python.exe to PATH.
    exit /b 1
)
echo [OK] python found: "%PYTHON_CMD%"

if "%BTDECK_USE_SYSTEM_PYTHON%"=="1" (
    where pyinstaller >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] PyInstaller not found. Install: pip install pyinstaller
        exit /b 1
    )
    set "PACKAGE_PYINSTALLER="
    for /f "delims=" %%I in ('where pyinstaller') do if not defined PACKAGE_PYINSTALLER set "PACKAGE_PYINSTALLER=%%I"
    set "PACKAGE_PYTHON=%PYTHON_CMD%"
    echo [WARN] Using system Python for packaging because BTDECK_USE_SYSTEM_PYTHON=1
) else (
    if not exist "%PACKAGE_REQUIREMENTS%" (
        echo [ERROR] Packaging requirements not found: "%PACKAGE_REQUIREMENTS%"
        exit /b 1
    )
    if not exist "%PACKAGE_PYTHON%" (
        echo [SETUP] Creating packaging venv: "%PACKAGE_VENV%"
        "%PYTHON_CMD%" -m venv "%PACKAGE_VENV%"
        if errorlevel 1 (
            echo [ERROR] Failed to create packaging venv
            exit /b 1
        )
    )
    echo [SETUP] Installing packaging dependencies - two-step: hash-verified lock + windows extras...
    "%PACKAGE_PYTHON%" -m pip install --upgrade pip setuptools wheel
    if errorlevel 1 (
        echo [ERROR] Failed to upgrade pip tooling
        exit /b 1
    )
    "%PACKAGE_PYTHON%" -m pip install --prefer-binary -r "%PROJECT_DIR%\backend\requirements-lock.txt"
    if errorlevel 1 (
        echo [ERROR] Failed to install pinned common lock
        exit /b 1
    )
    "%PACKAGE_PYTHON%" -m pip install --prefer-binary -r "%PACKAGE_REQUIREMENTS%"
    if errorlevel 1 (
        echo [ERROR] Failed to install packaging extras
        exit /b 1
    )
)
echo [OK] packaging python: "%PACKAGE_PYTHON%"
echo [OK] packaging pyinstaller: "%PACKAGE_PYINSTALLER%"

where ISCC >nul 2>&1
if errorlevel 1 (
    if "%RELEASE_MODE%"=="1" (
        echo [ERROR] release 模式要求 Inno Setup ISCC 在 PATH 中；缺失即失败（fail-closed）。
        echo        Install from: https://jrsoftware.org/isdl.php
        exit /b 1
    )
    echo [WARN] Inno Setup ISCC not found in PATH.
    echo        Install from: https://jrsoftware.org/isdl.php
    echo        Continuing without installer build...
    set "BUILD_INSTALLER=0"
) else (
    set "BUILD_INSTALLER=1"
)

REM Step 1: Frontend —— dev 自建；release 消费唯一构建（manifest 哈希一致）
if "%RELEASE_MODE%"=="1" (
    echo [1/4] Consuming prebuilt frontend - single build...
    if not exist "%FRONTEND_MANIFEST%" (
        echo [ERROR] release 模式要求先运行 python scripts\release\build_frontend.py 生成唯一前端构建
        exit /b 1
    )
    "%PYTHON_CMD%" "%PROJECT_DIR%\scripts\release\check_prebuilt_frontend.py" "%FRONTEND_MANIFEST%" "%FRONTEND_DIR%\dist"
    if errorlevel 1 (
        echo [ERROR] frontend dist 与唯一构建 manifest 不一致；禁止在制品构建中重建前端
        exit /b 1
    )
) else (
    echo [1/4] Building frontend...
    cd /d "%FRONTEND_DIR%"
    call "%NPM_CMD%" ci --legacy-peer-deps
    if errorlevel 1 (
        echo [ERROR] npm ci failed
        exit /b 1
    )
    call "%NPM_CMD%" run build
    if errorlevel 1 (
        echo [ERROR] npm run build failed
        exit /b 1
    )
    echo [OK] Frontend built
)

REM Step 2: 生成发布身份（build-info + source/frontend manifest；G1/G5）
echo [2/4] Generating release identity...
cd /d "%PROJECT_DIR%"
set GEN_ARGS=--artifact-kind windows-exe --output-dir "%STAGING_DIR%"
if "%RELEASE_MODE%"=="0" set "GEN_ARGS=%GEN_ARGS% --allow-dirty"
"%PYTHON_CMD%" "%PROJECT_DIR%\scripts\release\generate_build_info.py" %GEN_ARGS%
if errorlevel 1 (
    echo [ERROR] 生成发布身份失败（release 模式要求干净工作区与六处版本一致）
    exit /b 1
)

REM Step 3: Package backend with PyInstaller
echo [3/4] Building backend with PyInstaller...
cd /d "%PROJECT_DIR%"
"%PACKAGE_PYINSTALLER%" --clean --noconfirm "%DEPLOY_DIR%\btdeck-windows.spec"
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    exit /b 1
)
echo [OK] Backend packaged

REM Verify package contents before installer build
echo [VERIFY] Checking package contents...
"%PACKAGE_PYTHON%" "%DEPLOY_DIR%\verify-package.py" --project-root "%PROJECT_DIR%"
if errorlevel 1 (
    echo [ERROR] Package verification failed
    exit /b 1
)
echo [OK] Package verification passed

echo [ANALYZE] Package size summary...
"%PACKAGE_PYTHON%" "%DEPLOY_DIR%\analyze-package-size.py" --exe "%DIST_DIR%\btdeck.exe" --top 15
if errorlevel 1 (
    echo [WARN] Package size analysis failed
)

REM Step 4: Build installer with Inno Setup
if "%BUILD_INSTALLER%"=="1" (
    echo [4/4] Building Windows installer...
    if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
    ISCC "%DEPLOY_DIR%\btdeck.iss"
    if errorlevel 1 (
        if "%RELEASE_MODE%"=="1" (
            echo [ERROR] Inno Setup build failed in release mode - failing the build
            exit /b 1
        )
        echo [WARN] Inno Setup build failed, but executable is ready at dist\btdeck.exe
    ) else (
        echo [OK] Installer built at dist\
    )
) else (
    echo [4/4] Skipping installer build - ISCC not found
    echo        Executable ready at dist\btdeck.exe
)

echo.
echo ============================================
echo   Build complete!
echo ============================================
endlocal
