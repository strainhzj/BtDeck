# BtDeck Windows 生命周期驱动（release-artifact-equivalence-gate task .5 / G6）
# 仅在 GitHub windows-2022 Runner 执行（本机无 ISCC，本地结果记 NOT_RUN，不得默认通过）。
#
# 前置（同 job 内先完成）：
#   - python scripts\release\build_frontend.py
#   - deploy\build-windows.bat --release     → dist\btdeck.exe + dist\BtDeck-v1.0.7-*-setup.exe
#   - v1.0.6 portable EXE 夹具（tag v1.0.6 worktree 重建），用于“升级数据保留”场景
#     （reconstructed 语义：无 v1.0.6 Inno 安装器历史制品，用 portable 产生旧期数据）
#
# 场景（fail-closed）：
#   A. 免安装 EXE：隔离目录启动→健康/身份→停止→端口释放→二次启动 secret 不重置
#   B. Setup 静默首装→NSSM 服务单实例→同版本静默覆盖→v1.0.6 夹具植入→升级覆盖→
#      secret/数据保留→静默卸载→服务与程序移除、数据默认保留
# 输出：w3-lifecycle-windows.json（job 根目录）

param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path,
    [string]$V106PortableExe = "",
    [string]$ReportPath = "w3-lifecycle-windows.json"
)

$ErrorActionPreference = "Stop"
$script:Phases = New-Object System.Collections.Generic.List[string]
$script:Failed = $false

function Add-Phase([string]$Name, [bool]$Pass, [string]$Details = "") {
    $status = if ($Pass) { "PASS" } else { "FAIL" }
    $entry = @{ name = $Name; status = $status }
    if ($Details) { $entry.details = $Details }
    $script:Phases += ($entry | ConvertTo-Json -Compress)
    if ($Pass) { Write-Output "[PHASE-PASS] $Name" }
    else {
        $script:Failed = $true
        Write-Output "[PHASE-FAIL] $Name $Details"
    }
}

function Wait-Health([string]$Url, [string]$Pattern, [int]$MaxSeconds = 240) {
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $body = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri $Url).Content
            if ($body -match $Pattern) { return $body }
        } catch { Start-Sleep -Seconds 4 }
    }
    return $null
}

function Stop-BtDeckProcesses {
    # 通配匹配：v1.0.6 夹具进程名为 btdeck-v106-fixture.exe——精确名 "btdeck"
    # 杀不掉它，残留进程占住 5001 使后续 B4 的 v1.0.7 服务 bind 失败
    # （Errno 10048）并进入 NSSM
    # 重启循环（W3 CI 第二十轮归档日志实证）
    Get-Process -Name "btdeck*" -ErrorAction SilentlyContinue | Stop-Process -Force
    & "$ProjectRoot\deploy\nssm.exe" stop BtDeck 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

$NewExe = Join-Path $ProjectRoot "dist\btdeck.exe"
$SetupExe = Get-ChildItem (Join-Path $ProjectRoot "dist") -Filter "BtDeck-v*-windows-x64-setup.exe" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$IsccNssm = Join-Path $ProjectRoot "deploy\nssm.exe"
$InstallDir = "$env:ProgramFiles\BtDeck"

# ---------------- 场景 A：免安装 EXE ----------------
# 强制服务端模式：CI runner 的用户态会话会让 desktop_main 的桌面分支判定为真，
# EXE 弹 GUI 启动器等待交互 → 无头环境卡死、端口永不监听（W3 CI 实测拦截）。
# Start-Process 继承当前进程环境变量。
$env:BTDECK_DESKTOP_WINDOW = "0"
# v1.0.6 起入口已 reconfigure UTF-8（v1.0.5 夹具时代的编码垫片随之退役），
# 保留 PYTHONIOENCODING 对 stderr 落盘无害
$env:PYTHONIOENCODING = "utf-8"
$IsoDir = Join-Path $env:RUNNER_TEMP "w3-iso"
New-Item -ItemType Directory -Force -Path $IsoDir | Out-Null
Copy-Item $NewExe (Join-Path $IsoDir "btdeck.exe")
# 输出重定向：EXE 启动失败时保留错误证据（Hidden 窗口会吞掉全部输出）
$ExeOutLog = Join-Path $IsoDir "exe-stdout.log"
$ExeErrLog = Join-Path $IsoDir "exe-stderr.log"
$p = Start-Process -FilePath (Join-Path $IsoDir "btdeck.exe") -WorkingDirectory $IsoDir -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $ExeOutLog -RedirectStandardError $ExeErrLog
# 健康响应为紧凑 JSON（无空格分隔符），-match 匹配串一律不带空格（CI 实测拦截）。
# v1.0.6 起制品的健康契约含 version/build 字段，按 version 精确断言。
$body = Wait-Health "http://127.0.0.1:5001/health/live" '"status":"alive"'
$okA = $null -ne $body -and $body -match '"version":"1.0.7"' -and $body -match '"build":\{"status":"ok"'
Add-Phase "portable_exe_start_identity" $okA ("last=" + ($body -replace '\s+', '')[0..120] -join '')
if (-not $okA) {
    foreach ($log in @($ExeErrLog, $ExeOutLog)) {
        if (Test-Path $log) {
            $tail = (Get-Content $log -Tail 15 -ErrorAction SilentlyContinue) -join ' | '
            Write-Output "[DIAG] ${log}: $tail"
        }
    }
}
# Windows EXE 形态的密钥落在 config.yaml（security 段：init_config_file 生成，
# settings 读取；btdeck.env 是 deb/rpm postinst 概念，Windows 下不存在——
# 第十三轮实测 null==null 假 stable 使 $null 断言挂）
$secretFile = Join-Path $IsoDir "config\config.yaml"
if (Test-Path $secretFile) {
    $secret1 = (Get-FileHash $secretFile -Algorithm SHA256).Hash
} else { $secret1 = $null; Get-ChildItem $IsoDir -Recurse | Select-Object -First 5 | ForEach-Object { Write-Output $_.FullName } }
# 按进程名杀全部实例（onefile bootloader 与 Python 子进程是两个 PID，只杀
# 启动句柄的 PID 会留下占着 5001 的子进程——W3 CI 实测 stop_port_freed FAIL
# 连锁二次启动失败），并轮询等待端口真正释放
Stop-BtDeckProcesses
$portFreeDeadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $portFreeDeadline) {
    if (-not (Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Seconds 2
}
$portFreed = -not (Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)
Add-Phase "portable_exe_stop_port_freed" $portFreed
# 二次启动同样重定向输出（入口 reconfigure UTF-8，utf-8 落盘安全）——
# 第十四轮二次启动失败无任何输出可诊断
$Exe2OutLog = Join-Path $IsoDir "exe2-stdout.log"
$Exe2ErrLog = Join-Path $IsoDir "exe2-stderr.log"
$p2 = Start-Process -FilePath (Join-Path $IsoDir "btdeck.exe") -WorkingDirectory $IsoDir -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $Exe2OutLog -RedirectStandardError $Exe2ErrLog
$body2 = Wait-Health "http://127.0.0.1:5001/health/live" '"status":"alive"'
if ($null -eq $body2) {
    foreach ($log in @($Exe2ErrLog, $Exe2OutLog)) {
        if (Test-Path $log) {
            Write-Output "[DIAG] ${log}: $((Get-Content $log -Tail 12 -ErrorAction SilentlyContinue) -join ' | ')"
        }
    }
}
$secret2 = if (Test-Path $secretFile) {
    (Get-FileHash $secretFile -Algorithm SHA256).Hash } else { $null }
Add-Phase "portable_exe_restart_secret_stable" ($null -ne $body2 -and $secret1 -eq $secret2 -and $null -ne $secret1)
Stop-BtDeckProcesses

# ---------------- 场景 B：Setup 生命周期 ----------------
if ($null -eq $SetupExe) {
    Add-Phase "setup_silent_install" $false "dist 下未找到 setup exe（build-windows.bat --release 应产出）"
} else {
    # B1 静默首装
    Start-Process -FilePath $SetupExe.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
    $svc = Get-Service -Name BtDeck -ErrorAction SilentlyContinue
    $bodyB = Wait-Health "http://127.0.0.1:5001/health/live" '"version":"1.0.7"'
    $single = ($svc | Measure-Object).Count -eq 1 -and $svc.Status -eq "Running"
    $listeners = @(Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue).Count
    $b1ok = $single -and $null -ne $bodyB -and $listeners -eq 1
    Add-Phase "setup_silent_install" $b1ok "listeners=$listeners"
    if (-not $b1ok) {
        # 服务侧诊断：Setup 的 NSSM 已把 stdout/stderr 落盘到 logs\service-*.log
        foreach ($svcl in @("service-stderr.log", "service-stdout.log")) {
            $lp = Join-Path $InstallDir "logs\$svcl"
            if (Test-Path $lp) {
                Write-Output "[DIAG] $lp : $((Get-Content $lp -Tail 12 -ErrorAction SilentlyContinue) -join ' | ')"
            }
        }
        & "$ProjectRoot\deploy\nssm.exe" status BtDeck 2>$null | ForEach-Object { Write-Output "[DIAG] nssm status: $_" }
    }

    # Windows EXE 形态的密钥在 config.yaml（security 段），非 btdeck.env
    $envFile = Join-Path $InstallDir "config\config.yaml"
    $secretB1 = if (Test-Path $envFile) { (Get-FileHash $envFile -Algorithm SHA256).Hash } else { $null }

    # B2 同版本静默覆盖
    Start-Process -FilePath $SetupExe.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
    Start-Sleep -Seconds 5
    # 重装后服务可能短暂重启中：先等健康（服务端就绪），再判服务态（时序鲁棒）
    $bodyB2 = Wait-Health "http://127.0.0.1:5001/health/live" '"version":"1.0.7"' 60
    if ($null -eq $bodyB2) {
        & $IsccNssm start BtDeck 2>$null | Out-Null
        $bodyB2 = Wait-Health "http://127.0.0.1:5001/health/live" '"version":"1.0.7"' 60
    }
    $svc2 = Get-Service -Name BtDeck -ErrorAction SilentlyContinue
    $secretB2 = if (Test-Path $envFile) { (Get-FileHash $envFile -Algorithm SHA256).Hash } else { $null }
    $svcCount = @(Get-Service -Name BtDeck -ErrorAction SilentlyContinue).Count
    $b2ok = $svcCount -eq 1 -and $svc2.Status -eq "Running" -and $secretB1 -eq $secretB2 -and $null -ne $secretB1 -and $null -ne $bodyB2
    Add-Phase "setup_same_version_reinstall" $b2ok `
        "services=$svcCount status=$($svc2.Status) secretStable=$($secretB1 -eq $secretB2) health=$($null -ne $bodyB2)"

    # B3 v1.0.6 夹具植入（portable 落位安装目录运行一次，产生 v1.0.6 期配置/数据库）
    $markerPath = Join-Path $InstallDir "config\w3-marker.txt"
    if ($V106PortableExe -and (Test-Path $V106PortableExe)) {
        Stop-BtDeckProcesses
        # 端口释放等待：v1.0.6 夹具与 v1.0.7 服务共用 5001，残留监听会让夹具起不来
        $b3Deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $b3Deadline) {
            if (-not (Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Seconds 2
        }
        Copy-Item $V106PortableExe (Join-Path $InstallDir "btdeck-v106-fixture.exe") -Force
        # v1.0.6 起入口已 reconfigure UTF-8，v1.0.5 夹具时代的 wrapper.bat 编码
        # 垫片（PYTHONUTF8 cmd 内 set + cmd 层 2> 重定向）随之退役——直接
        # Start-Process 启动，stderr 重定向保留诊断证据，健康按 version 精确断言
        $fixturePath = Join-Path $InstallDir "btdeck-v106-fixture.exe"
        $v106Out = Join-Path $env:RUNNER_TEMP "v106-exe-stderr.log"
        $v106OutLog = Join-Path $env:RUNNER_TEMP "v106-exe-stdout.log"
        $pf = Start-Process -FilePath $fixturePath -WorkingDirectory $InstallDir -PassThru -WindowStyle Hidden `
            -RedirectStandardError $v106Out -RedirectStandardOutput $v106OutLog
        $bodyV106 = Wait-Health "http://127.0.0.1:5001/health/live" '"version":"1.0.6"' 180
        Add-Phase "v106_fixture_seeded" ($null -ne $bodyV106)
        if ($null -eq $bodyV106) {
            $cfg = Join-Path $InstallDir "config\config.yaml"
            Write-Output "[DIAG] v106 fixture config exists: $(Test-Path $cfg); processes: $((Get-Process btdeck* -ErrorAction SilentlyContinue | Measure-Object).Count)"
            Write-Output "[DIAG] v106 stderr: $((Get-Content $v106Out -Tail 12 -ErrorAction SilentlyContinue) -join ' | ')"
        }
        Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue
        Stop-BtDeckProcesses
        # 夹具释放 5001 后再走升级（v1.0.7 服务与夹具同端口）
        $b3StopDeadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $b3StopDeadline) {
            if (-not (Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Seconds 2
        }
        Set-Content -Path $markerPath -Value "w3-windows-upgrade"
        $secretBefore = (Get-FileHash $envFile -Algorithm SHA256).Hash

        # B4 升级覆盖（同 v1.0.7 setup 再装一遍 = 覆盖升级路径）
        Start-Process -FilePath $SetupExe.FullName -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
        Start-Sleep -Seconds 5
        & $IsccNssm start BtDeck 2>$null | Out-Null
        $bodyUp = Wait-Health "http://127.0.0.1:5001/health/live" '"version":"1.0.7"' 240
        $secretAfter = if (Test-Path $envFile) { (Get-FileHash $envFile -Algorithm SHA256).Hash } else { $null }
        $b4ok = $null -ne $bodyUp -and (Test-Path $markerPath) -and $secretBefore -eq $secretAfter
        Add-Phase "upgrade_keeps_secret_and_data" $b4ok `
            "health=$($null -ne $bodyUp) marker=$(Test-Path $markerPath) secretStable=$($secretBefore -eq $secretAfter)"
        if (-not $b4ok) {
            # v1.0.7 服务读 v1.0.6 期 config.yaml/app.db 的升级路径诊断：
            # NSSM 服务日志（Setup 已配 AppStdout/AppStderr 落盘）。
            # AppRotateFiles=1 下崩溃重启循环会反复轮转主日志文件——必须
            # 列出目录并读取归档（第十八轮实测主文件空、真凶在轮转件里）
            $logsDir = Join-Path $InstallDir "logs"
            $dirList = (Get-ChildItem $logsDir -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending |
                Select-Object -First 8 | ForEach-Object { '{0}({1}b)' -f $_.Name, $_.Length }) -join ' '
            Write-Output "[DIAG] B4 logs dir: $dirList"
            $newestErr = Get-ChildItem $logsDir -Filter "*stderr*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 2
            foreach ($f in $newestErr) {
                Write-Output "[DIAG] B4 $($f.Name): $((Get-Content $f.FullName -Tail 15 -ErrorAction SilentlyContinue) -join ' | ')"
            }
            & $IsccNssm status BtDeck 2>$null | ForEach-Object { Write-Output "[DIAG] B4 nssm status: $_" }
        }
    } else {
        Add-Phase "v106_fixture_seeded" $false "未提供 v1.0.6 portable 夹具（--V106PortableExe）"
        Add-Phase "upgrade_keeps_secret_and_data" $false "前置夹具缺失"
    }

    # B5 静默卸载：服务+程序移除、数据默认保留
    $uninst = Join-Path $InstallDir "unins000.exe"
    if (Test-Path $uninst) {
        Start-Process -FilePath $uninst -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES" -Wait
        Start-Sleep -Seconds 3
        $svcGone = $null -eq (Get-Service -Name BtDeck -ErrorAction SilentlyContinue)
        $exeGone = -not (Test-Path (Join-Path $InstallDir "btdeck.exe"))
        $dataKept = (Test-Path $markerPath) -and (Test-Path $envFile)
        Add-Phase "uninstall_removes_program_keeps_data" ($svcGone -and $exeGone -and $dataKept) `
            "svcGone=$svcGone exeGone=$exeGone dataKept=$dataKept"
    } else {
        Add-Phase "uninstall_removes_program_keeps_data" $false "未找到 unins000.exe"
    }
}

Stop-BtDeckProcesses

$verdict = if ($script:Failed) { "FAIL" } else { "PASS" }
$report = @{
    schema_version = 1
    scenario = "windows-lifecycle"
    executed_at = (Get-Date -AsUTC -Format "yyyy-MM-ddTHH:mm:ssZ")
    verdict = $verdict
    phases = $script:Phases
}
$report | ConvertTo-Json -Depth 4 | Set-Content -Path $ReportPath
Write-Output "report: $ReportPath verdict=$verdict"
if ($script:Failed) { exit 1 }
