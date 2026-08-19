@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem Mirror profiles (format: APT_MIRROR|NPM_REGISTRY|PIP_INDEX_URL|PIP_TRUSTED_HOST)
rem Empty fields = use upstream official source (backward compatible)
rem Profile 1 (official) is the fallback tail of the retry chain.
rem Note: tencent apt mirror is excluded because it enforces HTTPS and the
rem builder stage has no ca-certificates, causing cert verification failure.
rem aliyun/huawei serve apt over HTTP and work in the bare builder stage.
rem ============================================================
set "PROFILE_COUNT=3"
set "PROFILE_1=|||"
set "PROFILE_2=mirrors.aliyun.com|https://registry.npmmirror.com|https://mirrors.aliyun.com/pypi/simple/|mirrors.aliyun.com"
set "PROFILE_3=mirrors.huaweicloud.com|https://mirrors.huaweicloud.com/repository/npm/|https://mirrors.huaweicloud.com/repository/pypi/simple/|mirrors.huaweicloud.com"

set "KEEP_PROXY="
set "QUICK_MODE="
set "START_PROFILE=2"

rem ============================================================
rem Fixed parameters for double-click deployment
rem ============================================================
set "DEFAULT_DEPLOY_ENABLED=1"
set "DEFAULT_DEPLOY_MODE=unraid"
set "DEFAULT_DEPLOY_HOST=root@192.168.5.51"
set "DEFAULT_REMOTE_DIR=/mnt/cache/appdata/docker/btdeck"
set "DEFAULT_REMOTE_COMPOSE_FILE="
rem Credentials are NOT stored in this file anymore: SSH password / host key
rem are loaded from the untracked .btdeck-deploy-credentials.bat (template:
rem .btdeck-deploy-credentials.bat.example). Without that file the deploy
rem step falls back to interactive ssh password prompts.
set "DEFAULT_NO_CACHE=0"
set "PAUSE_ON_EXIT=1"

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%backend"
set "FRONTEND_DIR=%SCRIPT_DIR%frontend"
set "BACKEND_DOCKERFILE=%BACKEND_DIR%\Dockerfile"
set "FRONTEND_DOCKERFILE=%FRONTEND_DIR%\Dockerfile.prod"
set "LOCAL_PLINK=%SCRIPT_DIR%tools\putty\plink.exe"

rem Load deploy credentials from the untracked local file (never commit).
set "DEFAULT_SSH_PASSWORD="
set "DEFAULT_PLINK_HOSTKEY="
if exist "%SCRIPT_DIR%.btdeck-deploy-credentials.bat" call "%SCRIPT_DIR%.btdeck-deploy-credentials.bat"

set "BACKEND_IMAGE=btdeck-backend:latest"
set "FRONTEND_IMAGE=btdeck-frontend:latest"
set "BACKEND_TAR=%SCRIPT_DIR%btdeck-backend.latest.tar"
set "FRONTEND_TAR=%SCRIPT_DIR%btdeck-frontend.latest.tar"

set "BUILD_ARGS="
set "DEPLOY_HOST="
set "REMOTE_DIR="
set "DEPLOY_MODE="
set "REMOTE_COMPOSE_FILE="
set "SSH_PASSWORD=%DEFAULT_SSH_PASSWORD%"
set "SSH_CLIENT=ssh"
set "PLINK_HOSTKEY=%DEFAULT_PLINK_HOSTKEY%"

if "%DEFAULT_NO_CACHE%"=="1" set "BUILD_ARGS=--no-cache"
if "%DEFAULT_DEPLOY_ENABLED%"=="1" (
    set "DEPLOY_HOST=%DEFAULT_DEPLOY_HOST%"
    set "REMOTE_DIR=%DEFAULT_REMOTE_DIR%"
    set "DEPLOY_MODE=%DEFAULT_DEPLOY_MODE%"
    set "REMOTE_COMPOSE_FILE=%DEFAULT_REMOTE_COMPOSE_FILE%"
)

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--no-cache" (
    set "BUILD_ARGS=--no-cache"
    shift
    goto parse_args
)
if /I "%~1"=="-NoCache" (
    set "BUILD_ARGS=--no-cache"
    shift
    goto parse_args
)
if /I "%~1"=="--quick" (
    set "QUICK_MODE=1"
    shift
    goto parse_args
)
if /I "%~1"=="--keep-proxy" (
    set "KEEP_PROXY=1"
    shift
    goto parse_args
)
if /I "%~1"=="--deploy" (
    if "%~2"=="" goto usage
    if "%~3"=="" goto usage
    set "DEPLOY_HOST=%~2"
    set "REMOTE_DIR=%~3"
    set "DEPLOY_MODE=compose"
    shift
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--compose" (
    if "%~2"=="" goto usage
    set "REMOTE_COMPOSE_FILE=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--unraid" (
    if "%~2"=="" goto usage
    set "DEPLOY_HOST=%~2"
    if "%~3"=="" (
        set "REMOTE_DIR=/mnt/user/appdata/btdeck"
        shift
        shift
    ) else if /I "%~3"=="--no-cache" (
        set "REMOTE_DIR=/mnt/user/appdata/btdeck"
        shift
        shift
    ) else if /I "%~3"=="-NoCache" (
        set "REMOTE_DIR=/mnt/user/appdata/btdeck"
        shift
        shift
    ) else (
        rem Guard: any other --flag (e.g. --compose) means no explicit dir was
        rem given; use the default dir and do not consume the flag as REMOTE_DIR.
        set "UNRAID_ARG3=%~3"
        if "!UNRAID_ARG3:~0,2!"=="--" (
            set "REMOTE_DIR=/mnt/user/appdata/btdeck"
            shift
            shift
        ) else (
            set "REMOTE_DIR=%~3"
            shift
            shift
            shift
        )
    )
    set "DEPLOY_MODE=unraid"
    goto parse_args
)
if /I "%~1"=="--help" goto usage
if /I "%~1"=="-h" goto usage
echo [ERROR] Unknown argument: %~1
goto usage

:args_done

rem ============================================================
rem Proxy clearance (after arg parse so --keep-proxy takes effect)
rem ============================================================
if not "%KEEP_PROXY%"=="1" (
    set "HTTP_PROXY=" & set "HTTPS_PROXY=" & set "ALL_PROXY="
    set "http_proxy=" & set "https_proxy=" & set "all_proxy="
    set "NO_PROXY="   & set "no_proxy="
    echo [INFO] Proxy env cleared for this build session. Use --keep-proxy to keep them.
) else (
    echo [INFO] Keeping proxy env vars ^(--keep-proxy^).
)

where docker >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Docker CLI was not found. Please install/start Docker Desktop and try again.
    exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Docker CLI is installed, but the Docker engine is not reachable.
    echo.
    echo Please check:
    echo   1. Docker Desktop is running.
    echo   2. Docker Desktop has finished starting.
    echo   3. Docker Desktop is using Linux containers.
    echo   4. Run "docker context ls" and switch to a valid context if needed.
    echo.
    echo Common fix:
    echo   docker context use desktop-linux
    echo.
    exit /b 1
)

rem ============================================================
rem Detect Docker registry mirror (informational, not modified)
rem ============================================================
set "DOCKER_MIRRORS="
for /f "delims=" %%i in ('docker info --format "{{json .RegistryConfig.Mirrors}}" 2^>nul') do set "DOCKER_MIRRORS=%%i"
if "!DOCKER_MIRRORS!"=="[]" set "DOCKER_MIRRORS="
if "!DOCKER_MIRRORS!"=="null" set "DOCKER_MIRRORS="
if "!DOCKER_MIRRORS!"=="" (
    echo [TIP] No Docker registry mirror configured. Base image pulls may be slow.
    echo       Add registry-mirrors in Docker Desktop Settings -^> Docker Engine.
)

rem ============================================================
rem Probe mirror profiles to pick the fastest reachable one
rem Skipped by --quick; tests NPM registry root of each CN profile (2..N).
rem A profile is "reachable" if curl gets ANY HTTP response (code != 000),
rem because some registry roots legitimately return 404 while still serving
rem package metadata under /package-name. Only connection failures (000) count
rem as unreachable. First reachable profile wins; otherwise fall back to 2.
rem ============================================================
if "%QUICK_MODE%"=="1" goto probe_skip
where curl >nul 2>nul
if errorlevel 1 (
    echo [WARN] curl not found, skip mirror probe, use default profile !START_PROFILE!.
    goto probe_done
)
set /a "PROBE_IDX=2"
set "PROBE_FOUND=0"
:probe_loop
if !PROBE_IDX! GTR !PROFILE_COUNT! goto probe_done
for /f "tokens=1,2,3,4 delims=|" %%a in ("!PROFILE_%PROBE_IDX%!") do set "PROBE_NPM=%%b"
if "!PROBE_NPM!"=="" (
    set /a "PROBE_IDX+=1"
    goto probe_loop
)
set "PROBE_CODE=000"
for /f "delims=" %%c in ('curl -s -o NUL -m 6 -w "%%{http_code}" "!PROBE_NPM!" 2^>nul') do set "PROBE_CODE=%%c"
if not "!PROBE_CODE!"=="000" (
    set /a "START_PROFILE=!PROBE_IDX!"
    set "PROBE_FOUND=1"
    echo [INFO] Mirror probe selected profile !START_PROFILE! ^(HTTP !PROBE_CODE! reachable^).
    goto probe_done
)
echo [INFO] Profile !PROBE_IDX! unreachable ^(HTTP 000^), trying next...
set /a "PROBE_IDX+=1"
goto probe_loop
:probe_done
if "!PROBE_FOUND!"=="0" echo [WARN] All CN mirrors unreachable in probe, fall back to profile !START_PROFILE!.
goto probe_end
:probe_skip
echo [INFO] Mirror probe skipped ^(--quick^), use profile !START_PROFILE!.
:probe_end

if not exist "%BACKEND_DIR%\" (
    echo [ERROR] Missing backend directory: "%BACKEND_DIR%"
    exit /b 1
)

if not exist "%FRONTEND_DIR%\" (
    echo [ERROR] Missing frontend directory: "%FRONTEND_DIR%"
    exit /b 1
)

if not "%DEPLOY_HOST%"=="" (
    if not "%SSH_PASSWORD%"=="" (
        if exist "%LOCAL_PLINK%" (
            set "SSH_CLIENT=%LOCAL_PLINK%"
        ) else (
            where plink >nul 2>nul
            if errorlevel 1 (
                echo [ERROR] DEFAULT_SSH_PASSWORD is set, but plink.exe was not found.
                echo         Expected local plink: "%LOCAL_PLINK%"
                echo         Or install PuTTY and make sure plink.exe is in PATH.
                exit /b 1
            )
            set "SSH_CLIENT=plink"
        )
    ) else (
        where ssh >nul 2>nul
        if errorlevel 1 (
            echo [ERROR] ssh was not found. Install OpenSSH Client or Git for Windows.
            exit /b 1
        )
    )

    where tar >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] tar was not found. Windows 10/11 usually includes tar.exe.
        exit /b 1
    )
)

call :build_image "%BACKEND_IMAGE%" "%BACKEND_DOCKERFILE%" "%BACKEND_DIR%" backend
if errorlevel 1 exit /b 1

echo.
call :build_image "%FRONTEND_IMAGE%" "%FRONTEND_DOCKERFILE%" "%FRONTEND_DIR%" frontend
if errorlevel 1 exit /b 1

echo.
echo [INFO] Exporting backend image to: "%BACKEND_TAR%"
call :export_image "%BACKEND_IMAGE%" "%BACKEND_TAR%" "Backend"
if errorlevel 1 exit /b 1
echo [OK] Backend image exported

echo.
echo [INFO] Exporting frontend image to: "%FRONTEND_TAR%"
call :export_image "%FRONTEND_IMAGE%" "%FRONTEND_TAR%" "Frontend"
if errorlevel 1 exit /b 1
echo [OK] Frontend image exported

rem ============================================================
rem Prune dangling (<none>) images left over from rebuilding
rem fixed tags. Only dangling images are removed; tagged images
rem and named volumes/containers are left untouched.
rem ============================================================
echo.
echo [INFO] Pruning dangling images left by rebuild...
docker image prune -f --filter "dangling=true"
echo [OK] Dangling images pruned

if not "%DEPLOY_HOST%"=="" (
    echo.
    if /I "%DEPLOY_MODE%"=="unraid" (
        echo [INFO] Unraid deploy mode enabled
    )
    echo.
    echo [INFO] Uploading image archives and deploying through one SSH session
    if not "%SSH_PASSWORD%"=="" (
        echo [INFO] Using plink with credentials from .btdeck-deploy-credentials.bat.
    ) else (
        echo [INFO] You should only be prompted for the SSH password once.
    )
    echo [INFO] Upload list:
    echo        %BACKEND_TAR%
    echo        %FRONTEND_TAR%
    pushd "%SCRIPT_DIR%" >nul
    if not "%SSH_PASSWORD%"=="" (
        tar -cf - "btdeck-backend.latest.tar" "btdeck-frontend.latest.tar" ".btdeck-remote-deploy.sh" | "%SSH_CLIENT%" -batch -hostkey "%PLINK_HOSTKEY%" -pw "%SSH_PASSWORD%" "%DEPLOY_HOST%" "set -e; mkdir -p %REMOTE_DIR%; tar -xf - -C %REMOTE_DIR%; cd %REMOTE_DIR%; BTDECK_REMOTE_COMPOSE=%REMOTE_COMPOSE_FILE% sh .btdeck-remote-deploy.sh"
    ) else (
        tar -cf - "btdeck-backend.latest.tar" "btdeck-frontend.latest.tar" ".btdeck-remote-deploy.sh" | ssh "%DEPLOY_HOST%" "set -e; mkdir -p %REMOTE_DIR%; tar -xf - -C %REMOTE_DIR%; cd %REMOTE_DIR%; BTDECK_REMOTE_COMPOSE=%REMOTE_COMPOSE_FILE% sh .btdeck-remote-deploy.sh"
    )
    set "DEPLOY_RESULT=!ERRORLEVEL!"
    popd >nul
    if not "!DEPLOY_RESULT!"=="0" (
        echo [ERROR] Remote deployment failed.
        exit /b 1
    )
    echo [OK] Remote deployment finished
)

echo.
echo [OK] Done
echo   %BACKEND_TAR%
echo   %FRONTEND_TAR%
if not "%DEPLOY_HOST%"=="" (
    echo   deployed to %DEPLOY_HOST%:%REMOTE_DIR%
)

if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
exit /b 0

rem ============================================================
rem Subroutine: parse a mirror profile into MIRROR_ARGS
rem   %1 = profile index (1..PROFILE_COUNT)
rem   Sets global MIRROR_ARGS = series of quoted --build-arg tokens (or empty)
rem   Each --build-arg is independently quoted to avoid cmd arg-splitting issues.
rem ============================================================
:apply_profile
set "PROFILE_LINE=!PROFILE_%~1!"
set "AP=" & set "NP=" & set "PP=" & set "PH="
for /f "tokens=1,2,3,4 delims=|" %%a in ("!PROFILE_LINE!") do (
    set "AP=%%a"
    set "NP=%%b"
    set "PP=%%c"
    set "PH=%%d"
)
set "MIRROR_ARGS="
if not "!AP!"=="" set "MIRROR_ARGS=!MIRROR_ARGS! --build-arg "APT_MIRROR=!AP!""
if not "!NP!"=="" set "MIRROR_ARGS=!MIRROR_ARGS! --build-arg "NPM_REGISTRY=!NP!""
if not "!PP!"=="" set "MIRROR_ARGS=!MIRROR_ARGS! --build-arg "PIP_INDEX_URL=!PP!""
if not "!PH!"=="" set "MIRROR_ARGS=!MIRROR_ARGS! --build-arg "PIP_TRUSTED_HOST=!PH!""
exit /b 0

rem ============================================================
rem Subroutine: build a docker image with mirror-failover retry
rem   %1 = image tag
rem   %2 = Dockerfile path
rem   %3 = context dir
rem   %4 = friendly name (backend / frontend) -- used for log filename
rem   Starts at START_PROFILE, walks to PROFILE_COUNT on network errors,
rem   then falls back to profile 1 (official source) once before giving up.
rem   Retries force --no-cache to avoid corrupted intermediate layers.
rem   Non-network errors abort immediately (no pointless retries).
rem ============================================================
:build_image
set "B_TAG=%~1"
set "B_DF=%~2"
set "B_CTX=%~3"
set "B_NAME=%~4"
set "B_LOG=%TEMP%\btdeck-!B_NAME!.log"
set /a "B_IDX=START_PROFILE"
set /a "B_TRIES=0"
rem Track whether profile 1 (official) already participated, so the fallback
rem tail runs exactly once even when START_PROFILE is edited to 1. B_OFFICIAL_TAIL
rem marks that profile 1 is being attempted as the LAST resort (abort after it).
if "!START_PROFILE!"=="1" (set "B_TRIED_OFFICIAL=1") else (set "B_TRIED_OFFICIAL=0")
set "B_OFFICIAL_TAIL=0"
:build_retry
set /a "B_TRIES+=1"
call :apply_profile !B_IDX!
set "B_ARGS=%BUILD_ARGS%"
if !B_TRIES! GTR 1 set "B_ARGS=%BUILD_ARGS% --no-cache"
echo [INFO] Building !B_NAME! image !B_TAG! ^(profile !B_IDX!, try !B_TRIES!^)
docker build !B_ARGS! !MIRROR_ARGS! -f "!B_DF!" -t "!B_TAG!" "!B_CTX!" > "!B_LOG!" 2>&1
if not errorlevel 1 goto build_image_ok
findstr /C:"Could not resolve" /C:"dial tcp" /C:"Connection reset" /C:"Temporary failure" /C:"Connection timed out" /C:"timed out" /C:"Failed to connect" /C:"Unable to fetch" /C:"i/o timeout" /C:"context deadline exceeded" /C:"connection refused" /C:"no route to host" "!B_LOG!" >nul
if errorlevel 1 (
    echo [ERROR] !B_NAME! image build failed ^(non-network error^).
    echo         See log: !B_LOG!
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
)
echo [WARN] Network error detected in !B_NAME! build, switching to next mirror profile...
if "!B_OFFICIAL_TAIL!"=="1" goto build_chain_done
set /a "B_IDX+=1"
if !B_IDX! LEQ !PROFILE_COUNT! goto build_retry
if "!B_TRIED_OFFICIAL!"=="0" (
    set "B_IDX=1"
    set "B_TRIED_OFFICIAL=1"
    set "B_OFFICIAL_TAIL=1"
    echo [WARN] All CN mirror profiles failed, retrying once with official source ^(profile 1^).
    goto build_retry
)
:build_chain_done
echo [ERROR] !B_NAME! image build failed after all mirror profiles ^(incl. official^).
echo         See log: !B_LOG!
if "%PAUSE_ON_EXIT%"=="1" pause
exit /b 1
:build_image_ok
echo [OK] !B_NAME! image built
exit /b 0

:export_image
set "EXPORT_IMAGE=%~1"
set "EXPORT_TARGET=%~2"
set "EXPORT_LABEL=%~3"
set "EXPORT_TEMP=%TEMP%\%~n2.%RANDOM%%RANDOM%.tmp.tar"

if exist "%EXPORT_TEMP%" del /F /Q "%EXPORT_TEMP%" >nul 2>nul

docker save -o "%EXPORT_TEMP%" "%EXPORT_IMAGE%"
if errorlevel 1 (
    echo [ERROR] %EXPORT_LABEL% image export failed while writing temp file.
    if exist "%EXPORT_TEMP%" del /F /Q "%EXPORT_TEMP%" >nul 2>nul
    exit /b 1
)

for /L %%I in (1,1,5) do (
    if exist "%EXPORT_TARGET%" (
        attrib -R "%EXPORT_TARGET%" >nul 2>nul
        del /F /Q "%EXPORT_TARGET%" >nul 2>nul
    )

    if not exist "%EXPORT_TARGET%" (
        move /Y "%EXPORT_TEMP%" "%EXPORT_TARGET%" >nul 2>nul
        if not errorlevel 1 exit /b 0
    )

    echo [WARN] Target file is temporarily locked, retrying %%I/5...
    timeout /T 2 /NOBREAK >nul
)

echo [ERROR] Cannot replace "%EXPORT_TARGET%".
echo         Windows reports the file is locked. Try excluding this folder from antivirus scanning,
echo         closing Explorer/archiver windows, or exporting to a different directory.
if exist "%EXPORT_TEMP%" del /F /Q "%EXPORT_TEMP%" >nul 2>nul
exit /b 1

:usage
echo Usage:
echo   %~nx0 [--no-cache] [--quick] [--keep-proxy]
echo   %~nx0 [--no-cache] --deploy user@host /path/to/btdeck
echo   %~nx0 [--no-cache] --unraid root@tower [/mnt/user/appdata/btdeck]
echo   %~nx0 [--no-cache] --unraid root@tower /path/to/tars --compose /path/to/compose.yml
echo.
echo Mirror options:
echo   --quick        Skip mirror probe, use default profile (aliyun) directly.
echo   --keep-proxy   Keep proxy env vars (default: clear them for this session).
echo.
echo   Deploy credentials are read from the untracked local file
echo   .btdeck-deploy-credentials.bat (copy it from .btdeck-deploy-credentials.bat.example).
echo   Without it the deploy step falls back to interactive ssh password prompts.
echo.
echo On network-related build failures, the script auto-switches among mirror
echo profiles: aliyun -^> huawei -^> official, each retry forces --no-cache.
echo.
echo Examples:
echo   %~nx0
echo   %~nx0 --no-cache
echo   %~nx0 --deploy root@192.168.1.10 /opt/btdeck
echo   %~nx0 --unraid root@tower
echo   %~nx0 --unraid root@192.168.1.20 /mnt/user/appdata/btdeck
echo   %~nx0 --unraid root@192.168.1.20 /mnt/cache/appdata/docker/btdeck --compose /mnt/user/appdata/docker/btdeck/docker-compose.yml
exit /b 1
