@echo off
REM ============================================
REM BtDeck Windows build script
REM 1. Build frontend
REM 2. Package backend + frontend with PyInstaller
REM 3. Build installer with Inno Setup when available
REM ============================================

setlocal enabledelayedexpansion

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
set "NPM_CMD="
set "PYTHON_CMD="

echo ============================================
echo   BtDeck Windows Build
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
    echo [SETUP] Installing packaging dependencies...
    "%PACKAGE_PYTHON%" -m pip install --upgrade pip setuptools wheel
    if errorlevel 1 (
        echo [ERROR] Failed to upgrade pip tooling
        exit /b 1
    )
    "%PACKAGE_PYTHON%" -m pip install --prefer-binary -r "%PACKAGE_REQUIREMENTS%"
    if errorlevel 1 (
        echo [ERROR] Failed to install packaging dependencies
        exit /b 1
    )
)
echo [OK] packaging python: "%PACKAGE_PYTHON%"
echo [OK] packaging pyinstaller: "%PACKAGE_PYINSTALLER%"

where ISCC >nul 2>&1
if errorlevel 1 (
    echo [WARN] Inno Setup ISCC not found in PATH.
    echo        Install from: https://jrsoftware.org/isdl.php
    echo        Continuing without installer build...
    set "BUILD_INSTALLER=0"
) else (
    set "BUILD_INSTALLER=1"
)

REM Step 1: Build frontend
echo [1/3] Building frontend...
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

REM Step 2: Package backend with PyInstaller
echo [2/3] Building backend with PyInstaller...
cd /d "%PROJECT_DIR%"
"%PACKAGE_PYINSTALLER%" --clean --noconfirm "%DEPLOY_DIR%\btdeck.spec"
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

REM Step 3: Build installer with Inno Setup
if "%BUILD_INSTALLER%"=="1" (
    echo [3/3] Building Windows installer...
    if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
    ISCC "%DEPLOY_DIR%\btdeck.iss"
    if errorlevel 1 (
        echo [WARN] Inno Setup build failed, but executable is ready at dist\btdeck.exe
    ) else (
        echo [OK] Installer built at dist\
    )
) else (
    echo [3/3] Skipping installer build - ISCC not found
    echo        Executable ready at dist\btdeck.exe
)

echo.
echo ============================================
echo   Build complete!
echo ============================================
endlocal
